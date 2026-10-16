"""Unlocated facilities remain searchable without invented points or traffic."""
import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import data_store
import map_renderer
import pipeline_catalog
from port_additions import extend_inventory

ROOT = Path(__file__).resolve().parents[1]


class CoverageGapTest(unittest.TestCase):
    def test_unlocated_facilities_remain_in_catalog_and_have_no_activity_identity(self):
        doc = json.loads((ROOT/'PORT_ADDITIONS_2026-10-16.json').read_text())
        new = [row for row in doc['ports'] if row.get('reviewed_at') == '2026-10-17']
        self.assertEqual(len(new), 9)
        self.assertTrue(all(not row['statistics_available'] for row in new))
        self.assertEqual(sum(row['lat'] is None for row in new), 1)
        with patch('data_store.read_json', return_value=doc):
            self.assertEqual(len(extend_inventory([])), 48)
        bad = copy.deepcopy(doc)
        row = next(row for row in bad['ports'] if row['lat'] is None)
        row['lat'] = 0  # A half-filled coordinate must not become a marker.
        with patch('data_store.read_json', return_value=bad):
            with self.assertRaisesRegex(ValueError, '坐标'):
                extend_inventory([])

    def test_unlocated_search_record_reaches_fixed_popup_without_leaflet_marker(self):
        ports = [{'portid':'facility_no_point', 'name':'Known Facility', 'lat':None, 'lon':None}]
        options = map_renderer.search_objects([], ports, [])
        self.assertEqual(options[0]['key'], 'port:facility_no_point')
        with patch('map_renderer.compressed_document', side_effect=lambda text:text):
            html = map_renderer.build_map_html([],ports,[],[],'2026-10-09','2026-10-11',
                asset_popup=lambda *_:'',port_popup=lambda *_:'KNOWN UNLOCATED FACILITY',
                chokepoint_popup=lambda *_:'')
        rows = json.loads(re.search(r'const ports = (.*);',html).group(1))
        self.assertIsNone(rows[0]['lat'])
        self.assertIn('KNOWN UNLOCATED FACILITY',rows[0]['popup'])
        self.assertIn('if (port.lat == null || port.lon == null) return;',html)
        self.assertIn('ports.find(row => row.popupKey === key',html)

    def test_current_capacity_evidence_preserves_previous_reference_without_second_line(self):
        doc = json.loads((ROOT/'data/oil_pipelines.geojson').read_text())
        review = json.loads((ROOT/'data/pipeline_capacity_review.json').read_text())
        with patch.object(data_store,'read_json',side_effect=lambda path:doc if path.endswith('.geojson') else review):
            pipeline_catalog.load()
        rows = [row for row in review['records'] if row['project_id']=='P0551']
        self.assertEqual(len(rows),1)
        row = rows[0]
        self.assertEqual(row['capacity_million_bpd'],'7')
        self.assertEqual(row['previous_capacity_review']['capacity_million_bpd'],'5')
        self.assertIn('aramco.com',row['capacity_reference_url'])
        self.assertEqual(row['capacity_reference_date'],'2026-05-10')
