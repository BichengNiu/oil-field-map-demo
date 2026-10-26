"""Source-backed regression checks plus shared map/table population invariants."""
import copy
import re
import unittest
from unittest.mock import patch
import data_store
import asset_table_recheck
import production_units as p

class AssetTableRecheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = copy.deepcopy(data_store.load_catalog('assets'))
        asset_table_recheck.apply(cls.assets)

    def test_source_corrections_select_latest_and_preserve_original(self):
        chosen, rows, column, _ = p.statistical_view(self.assets)
        by_key = {(o['name'], o['product']): row for o, row in zip(chosen, rows)}
        self.assertEqual(by_key[('Bahrain Field (Awali)', 'crude_oil')][column], 3.7007)
        self.assertEqual(by_key[('Bahrain Field (Awali)', 'crude_oil')]['数据时间'], '2025')
        self.assertEqual(by_key[('Artawi', 'crude_oil')][column], 6)
        self.assertEqual(by_key[('Artawi', 'crude_oil')]['数据时间'], '未明确')
        self.assertEqual(by_key[('Nahr Umar', 'crude_oil')][column], 4.5)
        self.assertEqual(by_key[('Sirri E', 'crude_oil')]['数据时间'], '未明确')
        self.assertAlmostEqual(by_key[('Ramadan', 'natural_gas')][column], 1.4158423296)
        self.assertEqual(by_key[('Belayim', 'crude_oil')]['备注'], '估算产量')
        self.assertEqual(by_key[('Block 5 (Jannah)', 'crude_oil')]['数据时间'], '未明确')
        self.assertNotIn(('Block 9 (Malik)', 'crude_oil'), by_key)
        self.assertIn(('Hiswah (Haswa)', 'crude_oil'), by_key)
        self.assertNotIn(('Faihaa', 'natural_gas'), by_key)
        self.assertNotIn(('Balal', 'crude_oil'), by_key)

    def test_map_identity_popup_and_rows_match_under_all_single_country_filters(self):
        with patch.dict('os.environ', {'MONITORING_READ_ONLY': 'true'}):
            from map_popups import asset_popup
        countries = sorted({c for a in self.assets for c in a.get('countries', [a['country']]) if c != '土耳其'})
        for country in [None, *countries]:
            for products in [[], ['crude_oil'], ['natural_gas'], ['crude_oil', 'natural_gas']]:
                chosen, rows, _, _ = p.statistical_view(self.assets, [country] if country else [], products)
                units = p.map_units(self.assets, chosen, rows)
                self.assertEqual({o['scope_id'] for o in chosen}, {u['scope_id'] for u in units})
                self.assertEqual(sum(len(u['production_rows']) for u in units), len(rows))
                for unit in units:
                    html = asset_popup(unit)
                    labels = re.findall(r'<span>(.*?)</span>', html)
                    self.assertEqual(labels, [key for row in unit['production_rows'] for key in row])
                    self.assertNotIn('坐标精度', html)
                    self.assertNotIn('状态置信度', html)
                    self.assertNotIn('上级资产', html)
                    if unit['map_drawable']:
                        self.assertIsNotNone(unit['map_lat'])
                    else:
                        self.assertIsNone(unit['map_lat'])
                for product in products:
                    subset = [o for o in chosen if o['product'] == product]
                    for i, a in enumerate(subset):
                        for b in subset[i+1:]:
                            self.assertFalse(a['coverage'] & b['coverage'])

    def test_review_is_idempotent_and_hierarchy_is_not_geographic_guess(self):
        assets = copy.deepcopy(self.assets)
        asset_table_recheck.apply(assets)
        self.assertEqual(assets, self.assets)
        index = {(a['country'], a['name']): a for a in assets}
        self.assertIsNone(index[('沙特阿拉伯', 'South Ghawar')]['parent_asset'])
        self.assertNotIn('South Ghawar', index[('沙特阿拉伯', 'Ghawar')]['constituent_assets'])
