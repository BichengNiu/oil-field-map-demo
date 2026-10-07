"""Ensure complete persisted PortWatch facts serve history without network I/O."""
from datetime import date, timedelta
import os
import tempfile
import unittest
from unittest.mock import patch

import data_store
import portwatch_downloads


class PortWatchCacheTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "MONITORING_DB_PATH": os.path.join(self.temp.name, "monitoring.duckdb"),
            "XDG_CACHE_HOME": self.temp.name,
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_complete_persistent_window_avoids_portwatch_requests(self):
        first = date(2026, 10, 1)
        ids = ("port105", "port106")
        rows = [
            {"portid": node_id, "date": (first + timedelta(days=offset)).isoformat(),
             "portcalls": offset}
            for offset in range(3)
            for node_id in ids
        ]
        data_store.save_portwatch("ports", rows, "test-source")

        with patch("portwatch_downloads._cache", return_value=None), \
             patch("portwatch_downloads.pw.query", side_effect=AssertionError("unexpected network request")):
            result, metadata = portwatch_downloads.fetch_window(
                "ports", ids, first, first + timedelta(days=2), cache_revision="initial")
            again, again_metadata = portwatch_downloads.fetch_window(
                "ports", ids, first, first + timedelta(days=2), cache_revision="initial")

        self.assertEqual(len(result), len(rows))
        self.assertEqual(again, result)
        self.assertTrue(metadata["cache_hit"])
        self.assertTrue(again_metadata["cache_hit"])
        self.assertEqual(metadata["cache_source"], "DuckDB verified daily facts")

    def test_complete_stale_history_window_serves_initial_page(self):
        first = date(2026, 10, 1)
        ids = ("port105", "port106")
        rows = [
            {"portid": node_id, "date": (first + timedelta(days=offset)).isoformat(),
             "portcalls": offset}
            for offset in range(3)
            for node_id in ids
        ]
        data_store.save_portwatch("ports", rows, "test-source")
        with data_store.connect() as conn:
            conn.execute(
                "UPDATE portwatch_daily SET fetched_at=current_timestamp - INTERVAL '2 days'"
            )

        with patch("portwatch_downloads._cache", return_value=None), \
             patch("portwatch_downloads.pw.query", side_effect=AssertionError("unexpected network request")):
            result, metadata = portwatch_downloads.fetch_window(
                "ports", ids, first, first + timedelta(days=2),
                cache_revision="initial", allow_stale=True)

        self.assertEqual(len(result), len(rows))
        self.assertTrue(metadata["cache_hit"])
        self.assertEqual(metadata["cache_source"], "DuckDB verified daily facts")

    def test_explicit_force_refresh_bypasses_persistent_facts(self):
        first = date(2026, 10, 1)
        ids = ("port105", "port106")
        data_store.save_portwatch("ports", [
            {"portid": node_id, "date": (first + timedelta(days=offset)).isoformat(),
             "portcalls": 0}
            for offset in range(2)
            for node_id in ids
        ], "test-source")
        calls = []

        def source_query(_endpoint, **params):
            calls.append(params)
            if params.get("returnCountOnly"):
                return {"count": 4}
            return {"features": [
                {"attributes": {"portid": node_id,
                                "date": (first + timedelta(days=offset)).isoformat(),
                                "portcalls": offset + 1}}
                for offset in range(2)
                for node_id in ids
            ]}

        with patch("portwatch_downloads._cache", return_value=None), \
             patch("portwatch_downloads.pw.query", side_effect=source_query):
            result, metadata = portwatch_downloads.fetch_window(
                "ports", ids, first, first + timedelta(days=1),
                force=True, cache_revision="manual-refresh")

        self.assertEqual(len(result), 4)
        self.assertFalse(metadata["cache_hit"])
        self.assertGreaterEqual(len(calls), 3)

    def test_cache_only_history_miss_never_contacts_portwatch(self):
        first = date(2026, 10, 1)
        ids = ("port105",)
        with patch("portwatch_downloads._cache", return_value=None), \
             patch("portwatch_downloads.pw.query", side_effect=AssertionError("unexpected network request")):
            with self.assertRaisesRegex(portwatch_downloads.DownloadError, "本地PortWatch历史缓存"):
                portwatch_downloads.fetch_window(
                    "ports", ids, first, first + timedelta(days=2),
                    allow_stale=True, cache_only=True)

    def test_partial_local_window_is_available_without_filling_missing_days(self):
        first = date(2026, 10, 1)
        rows = [
            {"portid": "port105", "date": first.isoformat(), "portcalls": 0},
            {"portid": "port105", "date": (first + timedelta(days=2)).isoformat(), "portcalls": 3},
        ]
        data_store.save_portwatch("ports", rows, "test-source")

        observed = data_store.cached_portwatch_observations(
            "ports", ("port105",), first, first + timedelta(days=2))

        self.assertEqual([row["date"] for row in observed], [
            first.isoformat(), (first + timedelta(days=2)).isoformat()])
        self.assertNotIn(first + timedelta(days=1), [date.fromisoformat(row["date"]) for row in observed])

    def test_incomplete_persistent_window_falls_back_to_source(self):
        first = date(2026, 10, 1)
        ids = ("port105", "port106")
        data_store.save_portwatch("ports", [
            {"portid": node_id, "date": first.isoformat(), "portcalls": 0}
            for node_id in ids
        ], "test-source")

        with data_store.connect() as conn:
            conn.execute("DELETE FROM portwatch_daily WHERE kind='ports' AND node_id='port106'")

        calls = []

        def source_query(_endpoint, **params):
            calls.append(params)
            if params.get("returnCountOnly"):
                return {"count": 4}
            if params.get("resultOffset"):
                return {"features": []}
            return {"features": [
                {"attributes": {"portid": node_id,
                                "date": (first + timedelta(days=offset)).isoformat(),
                                "portcalls": 0}}
                for offset in range(2)
                for node_id in ids
            ]}

        with patch("portwatch_downloads._cache", return_value=None), \
             patch("portwatch_downloads.pw.query", side_effect=source_query):
            result, metadata = portwatch_downloads.fetch_window(
                "ports", ids, first, first + timedelta(days=1), cache_revision="initial")

        self.assertEqual(len(result), 4)
        self.assertFalse(metadata["cache_hit"])
        self.assertGreaterEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
