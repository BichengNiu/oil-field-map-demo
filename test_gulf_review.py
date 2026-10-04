"""Evidence grain and complete country scope, using dated source snapshots."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import field_catalog
import map_renderer
import port_inventory
import portwatch


class GulfReviewTests(unittest.TestCase):
    def test_equity_allocation_and_test_output_are_not_gross_field_output(self):
        index = {(a['country'], a['name']): a for a in field_catalog.ASSETS}
        block = index['阿曼', 'Blocks 3&4']
        self.assertEqual(block['value'], '7.6')
        self.assertIn('权益', block['ownership_basis'])
        for name in ('Farha South', 'Ulfa', 'Saiwan East', 'Shahd', 'Samha', 'Erfan'):
            asset = index['阿曼', name]
            self.assertIsNone(asset['value'])
            self.assertEqual(asset['parent_asset'], 'Blocks 3&4')
        awali = index['巴林', 'Bahrain Field (Awali)']
        self.assertEqual(awali['value'], '38.378')
        self.assertEqual(awali['commodity'], 'crude_oil')
        self.assertIn('2024', awali['data_date'])
        self.assertIn('unfccc.int', awali['additional_measurements'][0]['source_url'])
        abu = index['巴林', 'Abu Safah']
        self.assertEqual(abu['metric_type'], 'capacity')
        self.assertIn('巴林', abu['additional_measurements'][-1]['data_date'])
        shadegan = index['伊朗', 'Shadegan']
        self.assertIsNone(shadegan['value'])
        test = shadegan['additional_measurements'][-1]
        self.assertEqual(test['value'], '>115')
        self.assertNotIn(test['metric_type'], field_catalog.OUTPUT_METRIC_TYPES)

    def test_shared_fields_are_single_records_and_status_dates_are_separate(self):
        assets = field_catalog.ASSETS
        khafji = [a for a in assets if a['name'] == 'Khafji']
        self.assertEqual(len(khafji), 1)
        self.assertEqual(set(khafji[0]['countries']), {'科威特', '沙特阿拉伯'})
        for countries in ({'沙特阿拉伯'}, {'科威特'}, {'沙特阿拉伯', '科威特'}):
            self.assertEqual(len([a for a in khafji if set(a['countries']) & countries]), 1)
        aljumd = next(a for a in assets if a['name'] == 'Al Jumd')
        self.assertEqual(aljumd['operating_status'], 'producing')
        self.assertIn('2026-04', aljumd['operating_status_as_of'])
        self.assertIsNone(aljumd['value'])
        hiran = next(a for a in assets if a['name'] == 'Al-Hiran')
        self.assertEqual(hiran['operating_status'], 'discovered')
        self.assertIsNone(hiran['value'])  # Announced well tests stay out of field output.

    def test_full_country_query_keeps_ports_outside_old_boxes_and_short_pages(self):
        source = json.loads(Path('PORTWATCH_GULF_DIRECTORY_2026-10-03.json').read_text())['rows']
        def query(url, **params):
            self.assertEqual(url, portwatch.PORTS)
            for country in portwatch.GULF_COUNTRIES:
                self.assertIn("'" + country + "'", params['where'])
            offset = params['resultOffset']
            rows = source[:10] if offset == 0 else source[10:]
            return {'features': [{'attributes': r} for r in rows], 'exceededTransferLimit': offset == 0}
        with patch.object(portwatch, '_query', side_effect=query), patch.object(port_inventory, 'enrich', side_effect=lambda rows: rows):
            ports = portwatch.port_catalog.__wrapped__()
        self.assertEqual({p['portid'] for p in ports}, {p['portid'] for p in source})
        for name, region in (('Salalah', '阿拉伯海'), ('Jeddah', '红海沿岸'), ('Nowshahr Port', '里海')):
            self.assertEqual(next(p for p in ports if p['name'] == name)['region'], region)

    def test_unlocated_facilities_keep_unknown_statistics_and_do_not_draw(self):
        additions = port_inventory.PORT_REVIEW['additions']
        self.assertEqual(len({p['portid'] for p in additions}), len(additions))
        self.assertTrue(all(not p['statistics_available'] for p in additions))
        unlocated = [p for p in additions if p['lat'] is None]
        self.assertTrue(unlocated)
        with patch.object(portwatch, '_query') as query:
            self.assertEqual(portwatch.daily_activity.__wrapped__(__import__('datetime').date(2026, 9, 25), tuple(p['portid'] for p in unlocated)), {})
            query.assert_not_called()
        def unexpected_popup(*args):
            self.fail('Unlocated port must not become a map marker')
        rendered = map_renderer.build_map_html([], unlocated, [], [], '2026-09-25', '2026-09-27', asset_popup=unexpected_popup, port_popup=unexpected_popup, chokepoint_popup=unexpected_popup, vessel_popup=unexpected_popup)
        self.assertEqual(json.loads(re.search(r'const ports = (.*);', rendered).group(1)), [])

    def test_new_raw_snapshot_hash_does_not_replace_previous_audit(self):
        for day in ('2026-09-30', '2026-10-03', '2026-10-04'):
            summary = json.loads(Path(f'PORT_AUDIT_SUMMARY_{day}.json').read_text())
            raw = gzip.decompress(Path(summary['raw_file']).read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), summary['raw_sha256'])
            self.assertEqual(len(json.loads(raw)), summary['raw_daily_rows'])


if __name__ == '__main__':
    unittest.main()
