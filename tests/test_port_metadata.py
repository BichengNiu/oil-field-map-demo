"""Reviewed display/published metadata stays consistent without losing source identities."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
import data_store
from port_metadata import apply_port_metadata, monitored_ports, PORT_COUNTRIES

ROOT = Path(__file__).resolve().parents[1]


class PortMetadataTest(unittest.TestCase):
    def test_dashboard_scope_keeps_eleven_countries_without_erasing_archive(self):
        import dashboard_data
        audit = json.loads((ROOT/'audits/port_catalog_review_2026-10-16.json').read_text())
        rows = [dict(row) for row in audit['ports']]
        self.assertEqual(len(PORT_COUNTRIES), 11)
        self.assertEqual(len(monitored_ports(rows)), 131)
        self.assertNotIn('Eritrea', {row['country'] for row in monitored_ports(rows)})
        self.assertEqual(len(rows), 132)
        self.assertEqual({row['country'] for row in monitored_ports(rows)}, PORT_COUNTRIES)
        dashboard_data.portwatch_state.clear()
        with patch('data_store.cached_catalog', return_value=rows):
            saved, error = dashboard_data.portwatch_state('ports', 'catalog', -101)
            self.assertEqual(len(saved), 131)
            self.assertIsNone(error)
        with patch('data_store.read_only', return_value=False), \
             patch('portwatch.port_catalog', return_value=rows):
            fetched, error = dashboard_data.portwatch_state('ports', 'catalog', -102, refresh_revision='scope-test')
            self.assertEqual(len(fetched), 131)
            self.assertIsNone(error)
        with patch('data_store.cached_catalog', return_value=rows):
            saved, error = dashboard_data.portwatch_state('chokepoints', 'catalog', -103)
            self.assertEqual(len(saved), 132)
        dashboard_data.portwatch_state.clear()

    def test_each_published_id_matches_the_review_and_country_source(self):
        audit = json.loads((ROOT/'audits/port_catalog_review_2026-10-16.json').read_text())
        with duckdb.connect(str(ROOT/'runtime/monitoring.duckdb'), read_only=True) as conn:
            original = [json.loads(row[0]) for row in conn.execute("SELECT payload FROM catalogs WHERE kind='ports'").fetchall()]
        checked = {row['portid']: row for row in apply_port_metadata(original)}
        self.assertEqual(set(checked), {row['portid'] for row in audit['ports']})
        for record in audit['ports']:
            row = checked[record['portid']]
            for key in ('name_cn','country','region'):
                self.assertEqual(row[key], record[key], (row['portid'], key))
            self.assertEqual(row['name'], record['name_source'])
        self.assertEqual(audit['unmatched_baseline_entries'], len(audit['unmatched_reference_entries']))

    def test_source_values_are_preserved_and_corrections_are_idempotent(self):
        row = {'portid':'wpi48406', 'name':'Khawr Al Zubair Lng Terminal', 'name_en':'Khawr Al Zubair Lng Terminal',
               'name_cn':'祖拜尔液化天然气码头', 'country':'Iraq', 'region':'波斯湾'}
        before = copy.deepcopy(row)
        checked = apply_port_metadata([row])[0]
        self.assertEqual(row, before)
        self.assertEqual(checked['name_cn'], '祖拜尔液化石油气码头')
        self.assertEqual(checked['name_cn_source'], before['name_cn'])
        self.assertEqual(checked['name'], before['name'])
        self.assertEqual(apply_port_metadata([checked])[0], checked)
        with self.assertRaisesRegex(ValueError, '来源身份不匹配'):
            apply_port_metadata([{**row, 'country':'Egypt'}])

    def test_read_only_cache_and_publisher_write_use_the_same_correction(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                'MONITORING_DB_PATH':str(Path(temporary)/'test.duckdb'), 'MONITORING_READ_ONLY':'false'}):
            row = {'portid':'port9','name':'Aden','name_cn':'亚丁港','country':'Yemen','region':'曼德海峡'}
            data_store.save_catalog('ports', [row])
            self.assertEqual(data_store.load_catalog('ports')[0]['region'], '亚丁湾')
            self.assertEqual(data_store.cached_catalog('ports', allow_stale=True)[0]['region'], '亚丁湾')
            with data_store.connect() as conn:
                saved = json.loads(conn.execute("SELECT payload FROM catalogs WHERE kind='ports'").fetchone()[0])
            self.assertEqual(saved['region'], '亚丁湾')
            self.assertEqual(saved['region_source'], '曼德海峡')
            with patch.dict(os.environ, {'MONITORING_READ_ONLY':'true'}):
                self.assertEqual(data_store.load_catalog('ports')[0]['region'], '亚丁湾')
