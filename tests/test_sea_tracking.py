"""Traffic events are transitions, not a count of positions or unique ships."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shapely.geometry import box
from shapely.prepared import prep

import ais
import ais_history
import data_store
import sea_tracking


class SeaTrackingTest(unittest.TestCase):
    def setUp(self):
        self.base = datetime(2020, 10, 6, 0, 0, tzinfo=timezone.utc)
        # Small artificial polygon near the Persian Gulf, used only in tests.
        self.polygons = {"波斯湾": (prep(box(53.01, 26.01, 53.09, 26.09)),
                                    prep(box(52.99, 25.99, 53.11, 26.11)))}

    def points(self, values, step=5):
        return [(self.base + timedelta(minutes=i * step), lat, lon, "test") for i, (lat, lon) in enumerate(values)]

    def test_initial_presence_is_baseline_and_repeated_entries_count(self):
        inside, outside = (26.05, 53.05), (26.05, 52.98)
        self.assertEqual(sea_tracking.infer_entries(self.points([inside, inside]), self.polygons), [])
        points = self.points([outside, inside, inside, outside, outside, inside, inside])
        events = sea_tracking.infer_entries(points, self.polygons)
        self.assertEqual([e[1] for e in events], [points[1][0], points[5][0]])

    def test_long_gap_jamming_jump_and_boundary_jitter_do_not_create_entries(self):
        outside, inside, border = (26.05, 52.98), (26.05, 53.05), (26.05, 53.005)
        self.assertEqual(sea_tracking.infer_entries(self.points([outside, inside, inside], step=40), self.polygons), [])
        self.assertEqual(sea_tracking.infer_entries(self.points([(27, 54), inside, inside], step=1), self.polygons), [])
        self.assertEqual(sea_tracking.infer_entries(self.points([outside, border, outside, border, border]), self.polygons), [])

    def test_archive_replay_handles_late_data_duplicates_and_restart(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MONITORING_DB_PATH": str(Path(temp) / "monitoring.duckdb")}), \
                patch.object(sea_tracking, "boundaries", return_value=("test-v1", self.polygons)):
            sea_tracking.start_collection(self.base)
            points = self.points([(26.05, 52.98), (26.05, 53.05), (26.05, 53.05),
                                  (26.05, 52.98), (26.05, 52.98), (26.05, 53.05), (26.05, 53.05)])
            rows = [{"mmsi": "123456789", "observed_at": stamp.isoformat(), "lat": lat, "lon": lon,
                     "source": "test", "data_source": "test"} for stamp, lat, lon, _ in points]
            ais_history.archive_reports(rows[3:] + rows[:3])
            # Each archive call opens and closes DuckDB, as a restarted reader does.
            self.assertEqual(ais_history.archive_reports(rows), 0)
            # A new later observation replays existing events without multiplying them.
            ais_history.archive_reports([{**rows[-1], "observed_at": (self.base + timedelta(minutes=35)).isoformat()}])
            with data_store.connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sea_entries").fetchone()[0], 2)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM ais_reports").fetchone()[0], 8)

    def test_comparison_requires_continuous_period_and_known_zero_is_observed(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MONITORING_DB_PATH": str(Path(temp) / "monitoring.duckdb")}), \
                patch.object(sea_tracking, "boundaries", return_value=("test-v1", self.polygons)):
            sea_tracking.start_collection(self.base)
            with data_store.connect() as conn:
                conn.execute("INSERT INTO collection_runs VALUES ('run','Open Waters',?,?,'ok',1,'{}')", (self.base, self.base))
            summary = sea_tracking.observation_summary(self.base + timedelta(minutes=1))
            self.assertIn("本月已记录通过0艘次", summary["card"][3])
            self.assertIn("同比 —", summary["card"][3])
            self.assertIn("上周累计通过—", summary["card"][2])
            with data_store.connect() as conn:
                self.assertTrue(sea_tracking._continuous(conn, self.base, self.base + timedelta(minutes=1)))
                self.assertFalse(sea_tracking._continuous(conn, self.base, self.base + timedelta(minutes=5)))

    def test_all_four_areas_include_outside_context_and_each_free_request_is_bounded(self):
        self.assertIn("亚丁湾", ais.REGIONS)
        self.assertTrue(ais.in_collection_area(26, 57.6))
        for group in ais.openwaters_bbox_groups():
            self.assertLessEqual(sum((north - south) * (east - west) for south, north, west, east in group), 100)

    def test_incremental_checkpoint_retains_pending_crossing_and_late_correction(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"MONITORING_DB_PATH": str(Path(temp) / "monitoring.duckdb")}), \
                patch.object(sea_tracking, "boundaries", return_value=("test-v1", self.polygons)):
            sea_tracking.start_collection(self.base)
            points = self.points([(26.05, 52.98), (26.05, 53.05), (26.05, 53.05),
                                  (26.05, 52.98), (26.05, 52.98), (26.05, 53.05), (26.05, 53.05)])
            for stamp, lat, lon, _ in points:
                ais_history.archive_reports([{"mmsi": "123456789", "observed_at": stamp.isoformat(), "lat": lat,
                                              "lon": lon, "source": "test", "data_source": "test"}])
            with data_store.connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sea_entries").fetchone()[0], 2)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sea_vessel_checkpoints").fetchone()[0], 1)
            # This late, implausible outside jump invalidates the first crossing.
            ais_history.archive_reports([{"mmsi": "123456789", "observed_at": (self.base + timedelta(minutes=8)).isoformat(),
                                          "lat": 26.05, "lon": 52.98, "source": "test", "data_source": "test"}])
            with data_store.connect() as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM sea_entries").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
