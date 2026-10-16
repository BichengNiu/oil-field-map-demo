"""Date selection uses one UTC day, preserving gaps and cross-source deduplication."""
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ais_history
import dashboard_data
import data_store
import report_data
from historical_dates import nearest_day, nearest_sea_day
from monitoring_cards import SEA_MONITORING_AREAS


class HistoricalMapTest(unittest.TestCase):
    def test_day_snapshot_filters_both_boundaries_and_deduplicates_sources_readonly(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'history.duckdb'
            with patch.dict(os.environ, {'MONITORING_DB_PATH': str(path), 'MONITORING_READ_ONLY': 'false'}):
                with data_store.connect() as conn:
                    for mmsi, timestamp, source, received, lon in (
                        ('123456789', '2026-10-14T23:59:59Z', 'A', '2026-10-15T00:01:00Z', 51),
                        ('123456789', '2026-10-15T00:00:00Z', 'A', '2026-10-15T00:01:00Z', 52),
                        ('123456789', '2026-10-15T10:00:00Z', 'A', '2026-10-15T10:01:00Z', 53),
                        ('123456789', '2026-10-15T10:00:00Z', 'B', '2026-10-15T10:02:00Z', 54),
                        ('123456789', '2026-10-16T00:00:00Z', 'A', '2026-10-16T00:01:00Z', 55),
                        ('223456789', '2026-10-15T23:59:59Z', 'A', '2026-10-16T00:01:00Z', 56),
                        ('323456789', '2026-10-16T00:00:00Z', 'A', '2026-10-16T00:01:00Z', 57),
                    ):
                        conn.execute('INSERT INTO ais_reports VALUES (?,?,?,?)', [mmsi,timestamp,source,json.dumps({
                            'mmsi':mmsi,'observed_at':timestamp,'received_at':received,'lon':lon,'lat':25,'source':source})])
                data_store.save_portwatch('ports', [{'portid':'port105','date':'2019-01-01'}], 'test')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.dict(os.environ, {'MONITORING_DB_PATH': str(path), 'MONITORING_READ_ONLY': 'true'}), \
                 patch('ais_history.urlopen', side_effect=AssertionError('network')):
                rows = ais_history.day_snapshot(date(2026,10,15))
                self.assertEqual({r['mmsi'] for r in rows}, {'123456789','223456789'})
                self.assertEqual(next(r['lon'] for r in rows if r['mmsi']=='123456789'),54)
                self.assertEqual(ais_history.day_snapshot(date(2020,1,1)), [])
                self.assertEqual(dashboard_data.openwaters_snapshot(0,date(2020,1,1))['vessels'],[])
                bounds = dashboard_data.snapshot_date_bounds((str(path),))
                self.assertEqual(bounds,(date(2019,1,1),date(2026,10,16)))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)


class NearestHistoryTest(unittest.TestCase):
    def test_nearest_uses_both_sides_and_breaks_ties_earlier(self):
        self.assertEqual(nearest_day(['2026-10-09','2026-10-13'],date(2026,10,11)),date(2026,10,9))
        self.assertEqual(nearest_day(['2026-10-09','2026-10-13'],date(2026,10,12)),date(2026,10,13))
        self.assertIsNone(nearest_day([],date(2026,10,12)))
        rows = [{'sea':sea,'date':day,'passages':0} for sea in SEA_MONITORING_AREAS
                for day in ('2026-10-09','2026-10-13')]
        rows.append({'sea':SEA_MONITORING_AREAS[0],'date':'2026-10-11','passages':0})
        self.assertEqual(nearest_sea_day(rows,date(2026,10,11)),date(2026,10,9))

    def test_each_portwatch_source_chooses_valid_records_readonly(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'nearest.duckdb'
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'false'}):
                data_store.save_portwatch('ports',[
                    {'portid':'port105','date':'2026-10-09','portcalls':0},
                    {'portid':'port105','date':'2026-10-11','portcalls':None},
                    {'portid':'port105','date':'2026-10-13','portcalls':2}], 'test')
                data_store.save_portwatch('chokepoints',[
                    {'portid':'chokepoint1','date':'2026-10-12','n_total':0}], 'test')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'true'}):
                self.assertEqual(dashboard_data.nearest_portwatch_day('ports',date(2026,10,11),(str(path),)),date(2026,10,9))
                self.assertEqual(dashboard_data.nearest_portwatch_day('ports',date(2026,10,12),(str(path),)),date(2026,10,13))
                self.assertEqual(dashboard_data.nearest_portwatch_day('chokepoints',date(2026,10,11),(str(path),)),date(2026,10,12))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_local_sea_history_anchors_to_collection_days_not_synthesized_calendar_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'sea.duckdb'
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'false'}):
                with data_store.connect() as conn:
                    for day in (6,10):
                        conn.execute("INSERT INTO collection_runs VALUES (?,'Open Waters',?,?,'ok',2,'{}')",[
                            str(day),f'2026-10-{day:02d} 00:00:00+00:00',f'2026-10-{day:02d} 00:01:00+00:00'])
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'true'}), \
                 patch('sea_history.read_history',return_value={'source':None,'rows':[]}), \
                 patch('sea_tracking.observation_summary',return_value={'source':'local','rows':[],'card':('observed',)}) as summary:
                result=report_data.card_sea_history.__wrapped__(0,'2026-10-08')
                self.assertEqual(result['selected_day'],date(2026,10,6))
                self.assertEqual(summary.call_args.args[0].date(),date(2026,10,6))

    def test_later_collection_run_cannot_make_earlier_month_observed(self):
        import sea_tracking
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'cutoff.duckdb'
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'false'}):
                data_store.set_meta('local_collection_started_at','2026-10-06T00:00:00+00:00')
                with data_store.connect() as conn:
                    conn.execute("INSERT INTO collection_runs VALUES ('future','Open Waters','2026-10-10 00:00:00+00:00','2026-10-10 00:01:00+00:00','ok',1,'{}')")
            with patch.dict(os.environ,{'MONITORING_DB_PATH':str(path),'MONITORING_READ_ONLY':'true'}):
                result=sea_tracking.observation_summary(datetime(2026,10,6,12,tzinfo=timezone.utc))
                self.assertIn('本月已记录通过—艘次',result['card'][3])
                self.assertTrue(all(row['passages'] is None for row in result['rows']))
