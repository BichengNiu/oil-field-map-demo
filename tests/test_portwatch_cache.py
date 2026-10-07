"""Ensure complete persisted PortWatch facts serve history without network I/O."""
from datetime import date, datetime, timedelta, timezone
import csv
import io
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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

    def test_compressed_history_cache_merges_newer_daily_facts(self):
        first = date(2026, 10, 1)
        cached_at = "2026-10-03T00:00:00+00:00"
        cached = {"rows": [
            {"portid": "port105", "date": first.isoformat(), "portcalls": 1},
            {"portid": "port105", "date": (first + timedelta(days=1)).isoformat(), "portcalls": 2},
        ], "query": {"retrieved_at_utc": cached_at, "source_count": 2}}
        updated = {"portid": "port105", "date": (first + timedelta(days=1)).isoformat(),
                   "portcalls": 8}
        with patch("portwatch_downloads._cache", return_value=cached), \
             patch("portwatch_downloads.data_store.portwatch_window_latest_fetch",
                   return_value=datetime(2026, 10, 4, tzinfo=timezone.utc)), \
             patch("portwatch_downloads.data_store.cached_portwatch_rows_since",
                   return_value=[updated]), \
             patch("portwatch_downloads.pw.query",
                   side_effect=AssertionError("new local facts should avoid a full history fetch")):
            rows, metadata = portwatch_downloads.fetch_window(
                "ports", ("port105",), first, first + timedelta(days=1)
            )
        self.assertEqual([row["portcalls"] for row in rows], [1, 8])
        self.assertEqual(metadata["updated_local_rows"], 1)

    def test_large_export_streams_chunk_csv_to_zip_without_session_rows(self):
        first = datetime.now(timezone.utc).date() - timedelta(days=6)
        last = first + timedelta(days=1)
        node = {"node_kind": "ports", "portid": "port105", "node_name": "Test port",
                "region": "Gulf", "country": "Test", "lat": 25.0, "lon": 56.0,
                "statistics_available": True}
        def fetch(kind, ids, begin, end, **kwargs):
            return ([{"portid": "port105", "date": day.isoformat(),
                      "portname": "Test port", "portcalls": index}
                     for index, day in enumerate((first, last), 1) if begin <= day <= end],
                    {"endpoint": "test-source", "retrieved_at_utc": "2026-10-07T00:00:00+00:00",
                     "source_count": (end - begin).days + 1, "count_verified": True})

        with patch("portwatch_downloads.INLINE_EXPORT_ROW_LIMIT", 1), \
             patch("portwatch_downloads.bounds", return_value=(
                 {"port105": {"first": first.isoformat(), "last": last.isoformat(), "records": 2}}, []
             )), \
             patch("portwatch_downloads.fetch_window", side_effect=fetch):
            result = portwatch_downloads.collect([node], "history", first, last)

        self.assertNotIn("port105", result["datasets"])
        self.assertEqual(result["manifest"]["row_counts"]["ports"], 2)
        self.assertEqual(result["coverage"][0]["records"], 2)
        artifact = result["artifact_path"]
        self.addCleanup(lambda: os.path.exists(artifact) and os.unlink(artifact))
        with zipfile.ZipFile(artifact) as bundle:
            data_names = [name for name in bundle.namelist() if name.endswith(".csv") and "daily" in name]
            self.assertEqual(len(data_names), 1)
            rows = [row for name in data_names for row in csv.DictReader(
                io.StringIO(bundle.read(name).decode("utf-8-sig")))]
        self.assertEqual([row["date"] for row in rows], [first.isoformat(), last.isoformat()])

    def test_streamed_derived_windows_match_inline_export_across_refresh_cutoff(self):
        today = datetime.now(timezone.utc).date()
        first, last = today - timedelta(days=32), today - timedelta(days=1)
        node = {"node_kind": "ports", "portid": "port105", "node_name": "Test port",
                "region": "Gulf", "country": "Test", "lat": 25.0, "lon": 56.0,
                "statistics_available": True}
        all_rows = []
        for offset in range((last - first).days + 1):
            day = first + timedelta(days=offset)
            row = {metric: 1.0 for metric in portwatch_downloads.PORT_METRICS}
            row.update({"portid": "port105", "date": day.isoformat(), "portname": "Test port",
                        "portcalls": float(offset), "import": float(offset), "export": float(offset * 2)})
            all_rows.append(row)

        def fetch(kind, ids, begin, end, **kwargs):
            rows = [row.copy() for row in all_rows if begin <= date.fromisoformat(row["date"]) <= end]
            return rows, {"endpoint": "test-source", "retrieved_at_utc": "2026-10-07T00:00:00+00:00",
                          "source_count": len(rows), "count_verified": True}

        limits = {"port105": {"first": first.isoformat(), "last": last.isoformat(),
                               "records": len(all_rows)}}
        with patch("portwatch_downloads.bounds", return_value=(limits, [])), \
             patch("portwatch_downloads.fetch_window", side_effect=fetch), \
             patch("portwatch_downloads.INLINE_EXPORT_ROW_LIMIT", 1):
            streamed = portwatch_downloads.collect([node], "history", first, last, derived=True)
        self.addCleanup(lambda: os.path.exists(streamed["artifact_path"])
                        and os.unlink(streamed["artifact_path"]))
        with patch("portwatch_downloads.bounds", return_value=(limits, [])), \
             patch("portwatch_downloads.fetch_window", side_effect=fetch), \
             patch("portwatch_downloads.INLINE_EXPORT_ROW_LIMIT", 100_000):
            inline = portwatch_downloads.collect([node], "history", first, last, derived=True)

        streamed_rows = []
        with zipfile.ZipFile(streamed["artifact_path"]) as bundle:
            for name in bundle.namelist():
                if "_daily_" in name and name.endswith(".csv"):
                    streamed_rows.extend(csv.DictReader(io.StringIO(
                        bundle.read(name).decode("utf-8-sig"))))
        inline_by_date = {row["date"]: row for row in inline["datasets"]["ports"]}
        streamed_by_date = {row["date"]: row for row in streamed_rows}
        self.assertEqual(set(streamed_by_date), set(inline_by_date))
        for field in ("observed_days_7d", "avg_portcalls_7d", "avg_import_7d",
                      "avg_export_30d", "observed_days_30d"):
            expected = inline_by_date[last.isoformat()][field]
            actual = streamed_by_date[last.isoformat()][field]
            self.assertEqual(float(actual), float(expected))

    def test_history_export_force_refreshes_exactly_the_latest_seven_days(self):
        today = datetime.now(timezone.utc).date()
        first, last = today - timedelta(days=10), today
        node = {"node_kind": "ports", "portid": "port105", "node_name": "Test port",
                "region": "Gulf", "country": "Test", "lat": 25.0, "lon": 56.0,
                "statistics_available": True}
        all_rows = [{"portid": "port105", "date": (first + timedelta(days=i)).isoformat(),
                     "portname": "Test port", "portcalls": i}
                    for i in range((last - first).days + 1)]
        calls = []

        def fetch(kind, ids, begin, end, force=False, **kwargs):
            calls.append((begin, end, force))
            rows = [row.copy() for row in all_rows
                    if begin <= date.fromisoformat(row["date"]) <= end]
            return rows, {"endpoint": "test-source", "retrieved_at_utc": "2026-10-07T00:00:00+00:00",
                          "source_count": len(rows), "count_verified": True}

        with patch("portwatch_downloads.bounds", return_value=({
            "port105": {"first": first.isoformat(), "last": last.isoformat(), "records": len(all_rows)}
        }, [])), patch("portwatch_downloads.fetch_window", side_effect=fetch):
            result = portwatch_downloads.collect([node], "history", first, last)

        self.assertEqual(len(result["datasets"]["ports"]), len(all_rows))
        forced = [(begin, end) for begin, end, force in calls if force]
        cached = [(begin, end) for begin, end, force in calls if not force]
        self.assertEqual(forced, [(today - timedelta(days=6), today)])
        self.assertEqual(cached, [(first, today - timedelta(days=7))])

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

    def test_bulk_history_write_accepts_7110_rows_under_duckdb_memory_limit(self):
        first = date(2020, 1, 1)
        rows = [
            {"portid": f"port{index % 30}",
             "date": (first + timedelta(days=index // 30)).isoformat(),
             "portcalls": index, "import": index * 2, "export": index * 3}
            for index in range(7_110)
        ]

        data_store.save_portwatch("ports", rows, "test-source")

        with data_store.connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM portwatch_daily").fetchone()[0]
        self.assertEqual(count, 7_110)
        self.assertEqual(data_store.revision("ports"), 1)

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
