"""Temporal integrity, explicit provenance, and archive persistence."""
from datetime import date, datetime, timezone
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

import ais
import ais_history as history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        env = patch.dict(os.environ, {"AIS_ARCHIVE_PATH": str(Path(temp.name) / "archive.sqlite3")})
        env.start()
        self.addCleanup(env.stop)

    def row(self, observed, lat=26.2):
        return {"mmsi": "123456789", "received_at": observed, "lat": lat,
                "lon": 56.4, "source": "test-fixture", "sog": 2}

    def test_day_boundaries_offsets_latest_and_deduplication(self):
        rows = [self.row("2026-09-23T23:59:59Z"),
                self.row("2026-09-24T01:00:00+08:00"),
                self.row("2026-09-24T00:00:00Z", 26.3),
                self.row("2026-09-24T23:59:59Z", 26.4),
                self.row("2026-09-25T00:00:00Z", 26.5)]
        self.assertEqual(history.archive_reports(rows), 5)
        self.assertEqual(history.archive_reports(rows), 0)
        self.assertEqual(len(history.day_reports(date(2026, 9, 24))), 2)
        state = history.historical_snapshot(date(2026, 9, 24))
        self.assertEqual(state["vessels"][0]["lat"], 26.4)
        self.assertIsNone(state["vessels"][0]["age_minutes"])
        self.assertEqual(history.historical_snapshot(date(2026, 9, 22))["vessels"], [])

    def test_invalid_import_does_not_partially_write(self):
        data = b"mmsi,received_at,lat,lon,source\n123456789,2026-09-24T12:00:00Z,26.2,56.4,fixture\n123456789,,26.2,56.4,fixture\n"
        with self.assertRaises(ValueError):
            history.import_csv(data)
        self.assertEqual(history.known_mmsis(), [])
        with self.assertRaises(ValueError):
            history.archive_reports([{**self.row("2026-09-24T12:00:00Z"), "source": ""}])

    def test_csv_export_format_round_trip_preserves_observation_and_source(self):
        data = "MMSI,AIS报告时间 UTC,纬度,经度,数据源,船型,航速 节\n123456789,2026-09-24T12:00:00Z,26.2,56.4,fixture,货船,2\n".encode("utf-8-sig")
        self.assertEqual(history.import_csv(data), 1)
        row = history.day_reports(date(2026, 9, 24))[0]
        self.assertEqual(row["category"], "cargo")
        self.assertEqual(row["received_at"], "2026-09-24T12:00:00+00:00")

    def test_track_uses_aligned_historical_fields_and_excludes_other_dates(self):
        track = {"type": "Feature", "geometry": {"type": "LineString",
                 "coordinates": [[56.4, 26.1], [56.4, 26.2], [56.4, 26.3]]},
                 "properties": {"mmsi": 123456789,
                 "times": ["2026-09-23T23:59:59Z", "2026-09-24T12:00:00Z", "2026-09-25T00:00:00Z"],
                 "sog": [1, 2, 3], "heading": [511, 511, 511], "cog": [10, 20, 30]},
                 "attribution": {"fixture": "Test fixture, not actual AIS"}}
        rows = history.track_reports(track, "123456789", date(2026, 9, 24))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sog"], 2)
        self.assertEqual(rows[0]["course"], 20)
        self.assertIsNone(rows[0]["destination"])
        self.assertEqual(rows[0]["category"], "unknown")
        track["properties"]["times"] = []
        with self.assertRaises(ValueError):
            history.track_reports(track, "123456789", date(2026, 9, 24))

    def test_recent_backfill_archives_and_error_preserves_existing_day(self):
        now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        row = self.row("2026-09-30T12:00:00Z")
        with patch.object(ais, "utc_now", return_value=now), patch.object(
            history, "_fetch_track", return_value=([row], True)) as fetch:
            state = history.historical_snapshot(date(2026, 9, 30), ("123456789",))
            self.assertEqual(state["vessels"][0]["historical_day"], "2026-09-30")
            self.assertTrue(state["truncated"])
            self.assertEqual(fetch.call_count, 1)
        with patch.object(ais, "utc_now", return_value=now), patch.object(
            history, "_fetch_track", side_effect=TimeoutError("fixture outage")):
            state = history.historical_snapshot(date(2026, 9, 30), ("123456789",))
            self.assertEqual(len(state["vessels"]), 1)
            self.assertIn("fixture outage", state["error"])

    def test_old_day_never_calls_recent_only_interface(self):
        with patch.object(history, "_fetch_track") as fetch:
            history.historical_snapshot(date(2020, 1, 1), ("123456789",))
            fetch.assert_not_called()

    def test_background_collector_archives_without_open_page(self):
        from test_ais import position_event, NOW
        collector = ais.AISCollector("unused", connector=lambda *args, **kwargs: None)
        self.assertTrue(collector.ingest(position_event(), NOW))
        rows = history.day_reports(NOW.date())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "AISStream")


if __name__ == "__main__":
    unittest.main()
