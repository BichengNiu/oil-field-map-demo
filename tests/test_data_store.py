"""Real DuckDB tests for unified storage, atomic legacy migration and concurrency."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zlib

import data_store
import sea_history


class DataStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "monitoring.duckdb"
        env = patch.dict(os.environ, {"MONITORING_DB_PATH": str(self.path)})
        env.start()
        self.addCleanup(env.stop)

    def test_source_bytes_and_structured_rows_round_trip(self):
        relative = "PORT_REVIEW_2026-10-04.json"
        raw = (data_store.ROOT / relative).read_bytes()
        loaded = data_store.read_json(relative)
        self.assertEqual(loaded, json.loads(raw))
        with data_store.connect() as conn:
            digest, content, count = conn.execute("SELECT sha256,content,row_count FROM documents WHERE path=?", (relative,)).fetchone()
        self.assertEqual(content, raw)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        self.assertGreater(count, 0)

    def test_atomic_copy_from_all_three_legacy_stores_and_repeat_is_safe(self):
        ais = Path(self.temp.name) / "ais.sqlite3"
        ports = Path(self.temp.name) / "ports.sqlite3"
        sea = Path(self.temp.name) / "sea.sqlite3"
        with sqlite3.connect(ais) as old:
            old.execute("CREATE TABLE reports(mmsi TEXT,observed TEXT,source TEXT,payload TEXT)")
            old.execute("INSERT INTO reports VALUES (?,?,?,?)", ("123456789", "2020-10-05T01:00:00Z", "test", '{"lat":26,"lon":53}'))
            old.execute("CREATE TABLE archive_imports(sha256 TEXT,metadata TEXT)")
        with sqlite3.connect(ports) as old:
            old.execute("CREATE TABLE queries(key TEXT,saved REAL,payload BLOB)")
            payload = {"rows": [{"portid": "port1", "date": "2020-10-05", "portcalls": 7}],
                       "query": {"endpoint": "https://example.test/Daily_Ports_Data"}}
            old.execute("INSERT INTO queries VALUES (?,?,?)", ("k", 1, zlib.compress(json.dumps(payload).encode())))
        manifest = {"source": "test-provider", "definition_id": "test-v1", "timezone": "Asia/Shanghai", "event_basis": "sea_entry"}
        with sqlite3.connect(sea) as old:
            old.execute("CREATE TABLE metadata(id INTEGER,manifest TEXT)")
            old.execute("INSERT INTO metadata VALUES (1,?)", (json.dumps(manifest),))
            old.execute("CREATE TABLE entries(sea TEXT,mmsi TEXT,entered_at TEXT,day TEXT)")
            old.execute("INSERT INTO entries VALUES ('红海','123456789','2020-10-05T01:00:00Z','2020-10-05')")
            old.execute("CREATE TABLE coverage(sea TEXT,day TEXT,event_count INTEGER)")
            old.execute("INSERT INTO coverage VALUES ('红海','2020-10-05',1)")
        originals = {p: p.read_bytes() for p in (ais, ports, sea)}
        sources = {"ais": ais, "portwatch": ports, "sea": sea}
        self.assertEqual(data_store.migrate_legacy(sources=sources), {"ais": 1, "portwatch": 1, "sea": 1})
        self.assertEqual(data_store.migrate_legacy(sources=sources), {})
        with data_store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ais_reports").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT portcalls FROM portwatch_metrics").fetchone()[0], 7)
        self.assertEqual(sea_history.read_history()["rows"], [{"sea": "红海", "date": "2020-10-05", "passages": 1}])
        for p, content in originals.items():
            self.assertEqual(p.read_bytes(), content)

    def test_shared_thread_writes_and_failed_transaction_roll_back(self):
        def write(i):
            with data_store.connect() as conn:
                conn.execute("INSERT INTO app_meta VALUES (?,?)", (str(i), str(i)))
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(write, range(12)))
        with self.assertRaises(RuntimeError):
            with data_store.connect() as conn:
                conn.execute("DELETE FROM app_meta")
                raise RuntimeError("abort")
        with data_store.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM app_meta").fetchone()[0], 12)

    def test_catalog_keeps_numeric_types_dates_and_units(self):
        original = [{"country": "X", "name": "field", "value_numeric": Decimal("1.23456789"),
                     "unit": "千桶/日", "data_date": "2018-12-31", "metric_type": "capacity"}]
        data_store.save_catalog("assets", original)
        self.assertEqual(data_store.load_catalog("assets"), original)

    def test_portwatch_fact_revisions_advance_only_when_source_values_change(self):
        row = {"portid": "port105", "date": "2026-10-06", "portcalls": 7}
        self.assertEqual(data_store.revision("ports"), 0)
        data_store.save_portwatch("ports", [row], "test-source")
        self.assertEqual(data_store.revision("ports"), 1)
        data_store.save_portwatch("ports", [row], "test-source")
        self.assertEqual(data_store.revision("ports"), 1)
        data_store.save_portwatch("ports", [{**row, "portcalls": 8}], "test-source")
        self.assertEqual(data_store.revision("ports"), 2)

    def test_lazy_nested_reads_reuse_the_same_transaction(self):
        with data_store.connect() as outer:
            data_store.set_meta("test", 1, outer)
            with data_store.connect() as inner:
                self.assertIs(inner, outer)
                self.assertEqual(data_store.meta("test", conn=inner), 1)
            self.assertEqual(data_store.read_json("PORT_REVIEW_2026-10-04.json")["review_date"], "2026-10-04")


if __name__ == "__main__":
    unittest.main()
