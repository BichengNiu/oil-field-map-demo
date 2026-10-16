"""Published names retain source identities, exports and quarantined geometry."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from entity_names import display_name, enrich_catalog, validate_catalogs
import map_renderer
import pipeline_catalog

ROOT = Path(__file__).resolve().parents[1]


class EntityNamesTest(unittest.TestCase):
    def test_bilingual_catalog_enrichment_preserves_keys_and_source_names(self):
        translations = json.loads((ROOT / 'data/bilingual_names.json').read_text())
        raw = {'country': '阿联酋', 'name': 'Habshan', 'name_cn': 'Habshan', 'parent_asset': 'Bab'}
        result = enrich_catalog('assets', [raw], translations)[0]
        self.assertEqual(result['name'], 'Habshan')
        self.assertEqual(result['parent_asset'], 'Bab')
        self.assertEqual(result['display_name'], '哈布善（Habshan）')
        self.assertEqual(raw['name_cn'], 'Habshan')
        validate_catalogs({'assets': [result]})
        with self.assertRaisesRegex(ValueError, 'Chinese'):
            validate_catalogs({'assets': [raw]})

    def test_every_published_pipeline_has_chinese_english_name_and_translation(self):
        for path in ('data/oil_pipelines.geojson', 'data/uae_gas_connections.geojson'):
            for feature in json.loads((ROOT / path).read_text())['features']:
                p = feature['properties']
                self.assertRegex(p['name_cn'], r'[\u3400-\u9fff]')
                self.assertEqual(p['name'], f"{p['name_cn']}（{p['name_en']}）")

    def test_gas_cannot_be_oil_and_bad_routes_are_retained_but_not_drawn(self):
        oil = json.loads((ROOT / pipeline_catalog.DOCUMENT).read_text())
        gas = json.loads((ROOT / 'data/uae_gas_connections.geojson').read_text())
        index = {f['properties']['project_id']: f for f in [*oil['features'], *gas['features']]}
        self.assertFalse(index['P0640']['properties']['map_drawable'])
        self.assertFalse(index['P5684']['properties']['map_drawable'])
        self.assertEqual(index['P5683']['properties']['fuel'], 'Gas')
        self.assertNotEqual(index['P5683']['geometry']['coordinates'][-1], index['P5711']['geometry']['coordinates'][0])
        with patch('pipeline_catalog.data_store.read_json', return_value=gas):
            self.assertEqual(pipeline_catalog.load_gas_connections(), gas)
        combined = {'features': [*oil['features'], *gas['features']]}
        with patch('map_renderer.compressed_document', side_effect=lambda x: x):
            html = map_renderer.build_map_html([], [], [], [], '2026-10-16', '2026-10-16',
                pipelines=combined, asset_popup=lambda *a: '', port_popup=lambda *a: '', chokepoint_popup=lambda *a: '')
        self.assertNotIn('"project_id": "P0640"', html)
        self.assertNotIn('"project_id": "P5684"', html)
        self.assertIn('"project_id": "P5683"', html)
        self.assertIn('输气管线（非运行）', html)
        popup = pipeline_catalog.popup(index['P5683']['properties'])
        self.assertIn('天然气（不属于原油运力）', popup)
        self.assertNotIn('百万桶/日', popup)
        self.assertIn('adnocgas.ae', popup)

    def test_export_name_fallback_does_not_change_original(self):
        row = {'name': 'Das Island', 'name_cn': '达斯岛港'}
        self.assertEqual(display_name(row), '达斯岛港（Das Island）')
        self.assertEqual(row['name'], 'Das Island')
