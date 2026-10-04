"""Protect evidence dates, metric scope and uncertainty in the October follow-up."""
import json
import csv
from pathlib import Path
import unittest
from unittest.mock import patch
import field_catalog
import final_review
import port_inventory
import portwatch


class FollowupReviewTests(unittest.TestCase):
    def setUp(self):
        self.assets = {(a['country'], a['name']): a for a in field_catalog.ASSETS}

    def test_historical_output_does_not_become_current_or_target_output(self):
        a = self.assets['伊朗', 'Reshadat']
        self.assertEqual(a['value'], '8')
        self.assertEqual(a['metric_type'], 'actual_output')
        self.assertIn('2014', a['data_date'])
        self.assertIn('底层观察期未明', a['data_date'])
        self.assertEqual(a['data_audit_date'], '2026-10-04')
        for name in ('Abuzar', 'Doroud', 'Foroozan'):
            a = self.assets['伊朗', name]
            self.assertIn('140+140+80=360', a['note'])
            self.assertIn('320', a['note'])
            self.assertNotEqual(a['source_url'], self.assets['伊朗', 'Reshadat']['source_url'])

    def test_recovery_discovery_and_gas_facility_evidence_keep_scope(self):
        self.assertEqual(self.assets['沙特阿拉伯', 'Manifa']['operating_status'], 'producing')
        khurais = self.assets['沙特阿拉伯', 'Khurais']
        self.assertEqual(khurais['operating_status'], 'restoration_unconfirmed')
        self.assertTrue(khurais['strategic_default'])
        self.assertIn('2026-04-12', khurais['operating_status_as_of'])
        for name in ('Kahlolah', 'Kabd', 'Al-Qashaniya', 'Homah'):
            a = self.assets['科威特', name]
            self.assertIsNone(a['value'])
            self.assertEqual(a['operating_status'], 'discovered')
        self.assertIn('Houma', self.assets['科威特', 'Homah']['aliases'])
        self.assertNotEqual(self.assets['科威特', 'Humma']['name'], 'Homah')
        self.assertEqual(set(self.assets['科威特', 'Arq']['countries']), {'科威特', '沙特阿拉伯'})
        for name in ('Shah Gas Project', 'Habshan Gas Processing Complex'):
            a = self.assets['阿联酋', name]
            self.assertEqual(a['asset_level'], 'project')
            self.assertIsNone(a['value'])
            self.assertFalse(a['map_drawable'])
        self.assertEqual(self.assets['阿联酋', 'Shah Gas Project']['operating_status'], 'unknown')
        self.assertEqual(self.assets['阿联酋', 'Habshan Gas Processing Complex']['operating_status'], 'partially_operating')

    def test_facilities_do_not_borrow_portwatch_statistics_or_expand_status_scope(self):
        with Path('PORT_ACTIVITY_AUDIT_2026-10-03_OBS_2026-09-25.csv').open(encoding='utf-8-sig') as stream:
            rows = [dict(portid=r['PortWatch ID'], name=r['港口'], country=r['国家'],
                         lat=float(r['纬度']), lon=float(r['经度']), region=r['水域'])
                    for r in csv.DictReader(stream) if portwatch._valid_port_ids((r['PortWatch ID'],))]
        ports = {p['portid']: p for p in port_inventory.enrich(rows)}
        new = port_inventory.PORT_FOLLOWUP['additions']
        for row in new:
            p = ports[row['portid']]
            self.assertFalse(p['statistics_available'])
            self.assertIsNone(p['lat'])
            self.assertIsNone(p['lon'])
        self.assertEqual(ports['port570']['port_operating_status'], 'activity_confirmed')
        self.assertEqual(ports['port1408']['port_operating_status'], 'unknown')
        self.assertEqual(ports['facility_yanbu_north_crude']['port_operating_status'], 'unknown')
        with patch.object(portwatch, '_query') as query:
            self.assertEqual(portwatch.daily_activity.__wrapped__(__import__('datetime').date(2026, 9, 25), tuple(p['portid'] for p in new)), {})
            query.assert_not_called()
