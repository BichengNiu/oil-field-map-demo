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
