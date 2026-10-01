"""Synthetic fixtures verify source integrity and time handling; no network."""
from datetime import date
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pyarrow as arrow
import pyarrow.parquet as parquet
import ais_history
import public_ais_archive as archive


class PublicArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        mocked = patch.dict(os.environ, {"AIS_ARCHIVE_PATH": str(self.root / "archive.sqlite3")})
        mocked.start()
        self.addCleanup(mocked.stop)

    def row(self, **values):
        return {"mmsi": 123456789, "timestamp": "2026-03-16T23:59:59.100000",
                "received_at": "2026-03-17T00:00:05+00:00", "latitude": 26.2,
                "longitude": 56.4, "speed": 2.0, "heading": 511.0, "course": 123.0,
                "ship_type": 80.0, "ship_name": "Synthetic test fixture", **values}

    def fixture(self, rows):
        path = self.root / "fixture.parquet"
        parquet.write_table(arrow.Table.from_pylist(rows), path)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_observation_day_not_collector_day_and_heading_sentinel(self):
        report, reason = archive.convert_report(self.row())
        self.assertIsNone(reason)
        self.assertEqual(report["received_at"], "2026-03-16T23:59:59.100000+00:00")
        self.assertEqual(report["provider_received_at"], "2026-03-17T00:00:05+00:00")
        self.assertEqual(report["course"], 123)
        self.assertEqual(report["category"], "tanker")

    def test_quality_screen_does_not_pad_ids_or_manufacture_times(self):
        cases = [(self.row(mmsi=732710), "invalid_mmsi"),
                 (self.row(speed=40), "speed_screen_ge40_or_negative"),
                 (self.row(speed=102.3), "speed_screen_ge40_or_negative"),
                 (self.row(timestamp=None), "invalid_or_out_of_range_time"),
                 (self.row(latitude=0), "invalid_or_out_of_region_coordinate")]
        for row, reason in cases:
            self.assertEqual(archive.convert_report(row), (None, reason))

    def test_atomic_import_deduplication_and_marker_persist_together(self):
        path, sha = self.fixture([self.row(), self.row(), self.row(speed=102.3)])
        with patch.object(archive, "SHA256", sha):
            metadata = archive.import_archive(path)
            self.assertEqual(metadata["accepted_rows"], 2)
            self.assertEqual(metadata["inserted_rows"], 1)
            self.assertEqual(metadata["rejected"], {"speed_screen_ge40_or_negative": 1})
            self.assertEqual(len(ais_history.day_reports(date(2026, 3, 16))), 1)
            self.assertEqual(ais_history.day_reports(date(2026, 3, 17)), [])
            with patch.object(archive, "download_archive") as download:
                self.assertEqual(archive.ensure_public_archive(date(2026, 3, 16)), metadata)
                download.assert_not_called()
        self.assertEqual(metadata["regions"]["苏伊士运河"]["reports"], 0)

    def test_hash_failure_and_conversion_failure_leave_no_partial_import(self):
        path, sha = self.fixture([self.row(), self.row(timestamp="2026-03-16T13:00:00")])
        with self.assertRaisesRegex(ValueError, "校验失败"):
            archive.import_archive(path)
        self.assertEqual(ais_history.known_mmsis(), [])
        original = archive.convert_report
        with patch.object(archive, "SHA256", sha), patch.object(
            archive, "convert_report", side_effect=[original(self.row()), RuntimeError("fixture failure")]):
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                archive.import_archive(path)
        self.assertEqual(ais_history.known_mmsis(), [])
        with ais_history._connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM archive_imports").fetchone()[0], 0)

    def test_uncovered_date_never_downloads_and_loader_failure_is_visible(self):
        with patch.object(archive, "download_archive") as download:
            self.assertIsNone(archive.ensure_public_archive(date(2026, 5, 1)))
            download.assert_not_called()
        with patch.object(archive, "ensure_public_archive", side_effect=TimeoutError("fixture outage")):
            state = ais_history.historical_snapshot(date(2026, 3, 16))
            self.assertIn("fixture outage", state["error"])
            self.assertEqual(state["vessels"], [])


if __name__ == "__main__":
    unittest.main()
