"""Pipeline evidence remains traceable, offline and geometrically valid."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import data_store
import map_renderer
import pipeline_catalog
from pipeline_capacity import million_bpd

ROOT = Path(__file__).resolve().parents[1]


class PipelineMapTest(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / pipeline_catalog.DOCUMENT).read_text())

    def render(self, document):
        with patch('map_renderer.compressed_document', side_effect=lambda html: html):
            return map_renderer.build_map_html(
                [], [], [], [], '2026-10-16', '2026-10-16', pipelines=document,
                visible_categories=set(), asset_popup=lambda *a: '',
                port_popup=lambda *a: '', chokepoint_popup=lambda *a: '')

    def test_source_routes_have_unique_keys_valid_geometry_and_per_segment_provenance(self):
        pipeline_catalog.validate(self.document)
        self.assertEqual(len(self.document['features']), 250)
        names = {f['properties']['name_en'] for f in self.document['features']}
        for name in ('East-West Crude Oil Pipeline', 'Bab-Habshan–Fujairah Oil Pipeline',
                     'Sumed Oil Pipeline', 'Kirkuk-Ceyhan Oil Pipeline'):
            self.assertIn(name, names)
        invalid = copy.deepcopy(self.document)
        invalid['features'].append(invalid['features'][0])
        with self.assertRaisesRegex(ValueError, '重复'):
            pipeline_catalog.validate(invalid)
        invalid = copy.deepcopy(self.document)
        invalid['features'][0]['geometry'] = {'type': 'LineString', 'coordinates': [[53,26],[190,26]]}
        with self.assertRaisesRegex(ValueError, '坐标'):
            pipeline_catalog.validate(invalid)

    def test_readonly_load_uses_published_document_without_network_or_file_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = str(Path(temporary) / 'pipeline.duckdb')
            with patch.dict(os.environ, {'MONITORING_DB_PATH': path, 'MONITORING_READ_ONLY': 'false'}):
                data_store.ingest_document(pipeline_catalog.DOCUMENT)
                data_store.ingest_document('data/pipeline_capacity_review.json')
            before = Path(path).read_bytes()
            with patch.dict(os.environ, {'MONITORING_DB_PATH': path, 'MONITORING_READ_ONLY': 'true'}), \
                 patch('urllib.request.urlopen', side_effect=AssertionError('network')), \
                 patch('pathlib.Path.read_bytes', side_effect=AssertionError('source-file fallback')):
                self.assertEqual(pipeline_catalog.load(), self.document)
            self.assertEqual(Path(path).read_bytes(), before)

    def test_popup_preserves_units_dates_status_and_escapes_source_text(self):
        p = dict(self.document['features'][0]['properties'], name='<script>bad</script>',
                 status='mothballed', capacity='15,000', capacity_unit='bpd',
                 capacity_million_bpd='0.015', capacity_extra=[],
                 capacity_review_status='table_reference_number_matches')
        html = pipeline_catalog.popup(p)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        for text in ('封存（非实时）', '0.015 百万桶/日', p['updated_at'], 'CC BY 4.0', '路线'):
            self.assertIn(text, html)

    def test_capacity_units_and_unsupported_mass_conversion(self):
        self.assertEqual(million_bpd('1,250,000.00', 'bpd'), '1.25')
        self.assertEqual(million_bpd('15,000', 'bpd'), '0.015')
        self.assertEqual(million_bpd('0', 'bpd'), '0')
        self.assertIsNone(million_bpd('7', 'mtpa'))
        for value in ('NaN', 'Infinity', '-1', 'bad'):
            with self.assertRaises(ValueError):
                million_bpd(value, 'bpd')

    def test_review_preserves_system_scope_ranges_conflicts_and_missing_values(self):
        index = {f['properties']['project_id']: f['properties'] for f in self.document['features']}
        for pid in ('P0530', 'P5121'):
            self.assertIsNone(index[pid]['capacity_million_bpd'])
            self.assertEqual(index[pid]['capacity_extra'][0]['value_million_bpd'], '2.5')
            self.assertEqual(index[pid]['capacity_system_id'], 'SUMED')
            self.assertIn('单线运力', pipeline_catalog.popup(index[pid]))
        self.assertEqual(index['P5349']['capacity_range_million_bpd'], ['0.45', '0.6'])
        self.assertIn('0.45—0.6 百万桶/日', pipeline_catalog.popup(index['P5349']))
        self.assertIsNone(index['P6093']['capacity_million_bpd'])
        self.assertIn('待核实', pipeline_catalog.popup(index['P6093']))
        for p in index.values():
            if not p['capacity'] or p['capacity_unit'] == 'mtpa':
                self.assertIsNone(p['capacity_million_bpd'])
        bad = copy.deepcopy(self.document)
        withheld = next(f['properties'] for f in bad['features'] if f['properties']['project_id'] == 'P6093')
        withheld['capacity_million_bpd'] = '0.03'
        with self.assertRaisesRegex(ValueError, '未核实'):
            pipeline_catalog.validate(bad)

    def test_map_preserves_multiline_geometry_and_status_styles(self):
        html = self.render(self.document)
        rendered = json.loads(re.search(r'const pipelines = (.*);', html).group(1))
        self.assertEqual([f['geometry'] for f in rendered['features']],
                         [f['geometry'] for f in self.document['features'] if f['properties'].get('map_drawable', True)])
        self.assertIn('输油管线', html)
        self.assertNotIn('未选择显示类别', html)
        script = re.findall(r'<script>(.*?)</script>', html, re.S)[-1]
        node = shutil.which('node')
        if node is None:
            return
        checked = subprocess.run([node, '--check'], input=script, text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        style_function = re.search(r'const pipelineStyle = .*?\n      };', script, re.S).group(0)
        assertions = """
        const style = (status, route_accuracy='high') => pipelineStyle({properties:{status,route_accuracy}});
        if (style('operating').dashArray !== null) throw new Error('operating');
        if (style('construction').dashArray !== '9 5') throw new Error('construction');
        if (style('retired').dashArray !== '3 7') throw new Error('retired');
        if (style('operating','very low (straight line/schematic)').dashArray !== '5 5') throw new Error('schematic');
        """
        checked = subprocess.run([node], input=style_function + assertions, text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == '__main__':
    unittest.main()
