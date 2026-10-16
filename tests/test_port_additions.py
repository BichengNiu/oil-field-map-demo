"""Country-wide collection, explicit crosswalks and catalogue-only additions."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import data_store
import portwatch
from port_additions import extend_inventory
from port_metadata import monitored_ports
from port_types import port_type_label, port_business_label

ROOT = Path(__file__).resolve().parents[1]


class PortAdditionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads((ROOT/'PORT_ADDITIONS_2026-10-16.json').read_text())
        cls.reference = json.loads((ROOT/'audits/port_scope_portwatch_reference_2026-10-16.json').read_text())

    def test_additions_keep_independent_ids_and_do_not_duplicate_wpi_crosswalks(self):
        with patch('data_store.read_json', return_value=self.document):
            rows = extend_inventory([])
            again = extend_inventory(rows)
        self.assertEqual(rows, again)
        self.assertEqual(len(rows), 48)
        self.assertEqual(sum(p['statistics_available'] for p in rows), 12)
        self.assertEqual(sum(not p['statistics_available'] for p in rows), 36)
        self.assertEqual(len({p['portid'] for p in rows}), len(rows))
        wpi = [wid for p in rows for wid in p['wpi_ids']]
        self.assertEqual(len(wpi), 26)
        self.assertEqual(len(set(wpi)), 26)
        for row in rows:
            self.assertNotEqual(port_type_label(row), '待核实')
            self.assertNotEqual(port_business_label(row), '待核实')
            if row['lat'] is None:
                self.assertIsNone(row['lon'])
                self.assertEqual(row['coordinate_status'], 'unresolved_no_map_point')
            else:
                self.assertTrue(row['coordinate_source_url'])
            self.assertNotIn('portcalls', row)
            self.assertEqual(portwatch.has_independent_statistics(row), row['statistics_available'])
        data_store_port_ids = [row['portid'] for row in rows if not row['statistics_available']]
        self.assertEqual(portwatch._activity_ids(tuple(data_store_port_ids)), ())

    def test_country_query_includes_all_source_ports_outside_the_watch_boxes(self):
        saved = {}
        def save(kind, rows):
            saved[kind] = rows
        with patch('portwatch.query', return_value=self.reference) as query, \
             patch('data_store.read_json', return_value=self.document), \
             patch('data_store.save_catalog', side_effect=save), \
             patch('data_store.load_catalog', side_effect=lambda kind: saved[kind]):
            rows = portwatch.port_catalog.__wrapped__('country-coverage-check')
        where = query.call_args.kwargs['where']
        self.assertIn("'Egypt'", where)
        self.assertIn("'Yemen'", where)
        self.assertNotIn('Eritrea', where)
        self.assertNotIn('lat >=', where)
        ids = {p['portid'] for p in rows}
        self.assertTrue({f['attributes']['portid'] for f in self.reference['features']} <= ids)
        self.assertEqual(len(rows), 180)
        self.assertEqual(len(monitored_ports(rows)), 179)
        self.assertEqual(next(p for p in rows if p['portid']=='port23')['region'], '地中海')
        for row in rows:
            self.assertFalse(any(k.startswith(('port_operating_status', 'port_status_')) for k in row))

    def test_identity_or_country_conflicts_are_rejected_without_mutating_input(self):
        original = copy.deepcopy(self.document['ports'][0])
        wrong = {**original, 'country':'Oman'}
        with patch('data_store.read_json', return_value=self.document):
            with self.assertRaisesRegex(ValueError, '来源身份'):
                extend_inventory([wrong])
        self.assertEqual(wrong['country'], 'Oman')
        self.assertEqual(self.document['ports'][0], original)
