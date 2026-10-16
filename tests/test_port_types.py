"""Coverage, provenance and ambiguous-identity guards for reviewed port types."""
import json
from pathlib import Path
import unittest

import duckdb
from port_types import REVIEWED_PORT_TYPES, port_type_label

ROOT = Path(__file__).resolve().parents[1]


class PortTypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads((ROOT / 'audits/port_type_review_2026-10-16.json').read_text())

    def test_published_catalog_id_name_country_and_location_are_reconciled(self):
        with duckdb.connect(str(ROOT / 'runtime/monitoring.duckdb'), read_only=True) as conn:
            published = {p['portid']:p for (payload,) in conn.execute("SELECT payload FROM catalogs WHERE kind='ports'").fetchall()
                         for p in [json.loads(payload)]}
        reviewed = {p['portid']:p for p in self.audit['ports']}
        self.assertEqual(len(reviewed),len(self.audit['ports']))
        self.assertEqual(set(reviewed),set(published))
        self.assertEqual(set(reviewed),set(REVIEWED_PORT_TYPES))
        for pid, row in published.items():
            for field in ('name','country','lat','lon'):
                self.assertEqual(reviewed[pid][field],row[field],(pid,field))
            self.assertNotIn(port_type_label(row),('待核实','未知',''))

    def test_every_label_has_matching_audit_receipt_with_source_date_separate(self):
        sources = self.audit['sources']
        for row in self.audit['ports']:
            pid = row['portid']
            self.assertEqual(REVIEWED_PORT_TYPES[pid]['label'],row['label'])
            self.assertEqual(REVIEWED_PORT_TYPES[pid]['verification'],row['verification'])
            self.assertTrue(row['evidence'])
            for evidence in row['evidence']:
                receipt = sources[evidence['source_id']]
                self.assertRegex(receipt['sha256'],r'^[0-9a-f]{64}$')
                self.assertTrue(receipt['retrieved_at'])
                self.assertIn('source_date',receipt)
                self.assertTrue(evidence['source_url'].startswith('https://'))
                self.assertTrue(all(quote.strip() for quote in evidence['excerpts']))
            if row['verification']=='documented_broad_type':
                self.assertTrue(row['scope_note'])
                self.assertEqual(row['confidence'],'medium')

    def test_lpg_identity_conflict_and_jask_scope_are_not_hidden(self):
        self.assertIn('液化石油气',port_type_label({'portid':'wpi48406','name':'Khawr Al Zubair Lng Terminal'}))
        self.assertEqual(REVIEWED_PORT_TYPES['wpi48406']['identity_status'],'source_name_conflict')
        self.assertNotIn('原油',port_type_label({'portid':'port2486'}))
        self.assertIn('较远处',REVIEWED_PORT_TYPES['port2486']['scope_note'])
        self.assertIn('牲畜',port_type_label({'portid':'facility_aljeer'}))
        self.assertIn('渔港',port_type_label({'portid':'facility_mirfa'}))
        self.assertIn('项目',port_type_label({'portid':'facility_grand_faw'}))
        self.assertIn('复合港区',port_type_label({'portid':'port1342'}))

    def test_unknown_future_ids_are_not_classified_from_names_or_traffic(self):
        self.assertEqual(port_type_label({'portid':'new_port','name':'Some Oil Terminal','week_calls_tanker':999}), '待核实')
        for pid in ('fso151','fso158'):
            self.assertIn('未具名',port_type_label({'portid':pid}))
            self.assertEqual(REVIEWED_PORT_TYPES[pid]['identity_status'],'unnamed_in_source')
