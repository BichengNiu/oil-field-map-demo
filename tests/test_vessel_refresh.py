"""Exercise automatic vessel acquisition through real storage and display reads."""
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ais
import ais_history
import dashboard_data
import data_store


def vessel_response(observed, longitude=53.0):
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [longitude, 26.0]},
            "properties": {
                "kind": "vessel", "mmsi": 123456789,
                "seen": observed.isoformat(), "name": "TEST VESSEL",
                "source": "test-station", "type": 70,
            },
        }],
    }


class VesselRefreshTest(unittest.TestCase):
    def test_run_archives_source_responses_and_exposes_latest_vessel(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=2)
        response = vessel_response(observed)
        encoded = json.dumps(response).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "monitoring.duckdb"
            with patch.dict(os.environ, {"MONITORING_DB_PATH": str(path)}), \
                 patch("ais.urlopen", side_effect=lambda *a, **kw: io.BytesIO(encoded)) as upstream:
                snapshot = dashboard_data.openwaters_snapshot(ais.MODULE_VERSION)

                self.assertIsNone(snapshot["archive_error"])
                self.assertEqual(len(snapshot["vessels"]), 1)
                self.assertEqual(snapshot["vessels"][0]["mmsi"], "123456789")
                self.assertEqual(snapshot["refresh_summary"]["inserted"], 1)
                self.assertEqual(upstream.call_count, len(ais.openwaters_bbox_groups()))
                with data_store.connect() as conn:
                    queries = conn.execute(
                        "SELECT endpoint, params, response FROM source_queries"
                    ).fetchall()
                self.assertEqual(len(queries), upstream.call_count)
                for endpoint, params, saved_response in queries:
                    self.assertEqual(endpoint, ais.OPENWATERS_API)
                    self.assertIn(["max_age", "120m"], json.loads(params)["query_parameters"])
                    self.assertEqual(json.loads(saved_response), response)

    def test_new_run_fetches_new_positions_and_failed_run_keeps_saved_snapshot(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=2)
        response = vessel_response(observed)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "monitoring.duckdb"
            with patch.dict(os.environ, {"MONITORING_DB_PATH": str(path)}):
                with patch("ais.urlopen", side_effect=lambda *a, **kw: io.BytesIO(json.dumps(response).encode())) as upstream:
                    first = dashboard_data.openwaters_snapshot(ais.MODULE_VERSION)
                    newer = observed + timedelta(minutes=1)
                    response = vessel_response(newer, longitude=53.1)
                    second = dashboard_data.openwaters_snapshot(ais.MODULE_VERSION)
                    self.assertEqual(upstream.call_count, 2 * len(ais.openwaters_bbox_groups()))
                self.assertEqual(first["vessels"][0]["lon"], 53.0)
                self.assertEqual(second["vessels"][0]["lon"], 53.1)
                self.assertIsNone(second["archive_error"])

                with patch("ais.urlopen", side_effect=TimeoutError("source timed out")) as failed, \
                     patch("ais.utc_now", return_value=newer + timedelta(days=1)):
                    cached = dashboard_data.openwaters_snapshot(ais.MODULE_VERSION)
                    self.assertEqual(ais_history.latest_snapshot(), [])
                self.assertEqual(failed.call_count, len(ais.openwaters_bbox_groups()))
                self.assertIn("TimeoutError", cached["archive_error"])
                self.assertEqual(len(cached["vessels"]), 1)
                self.assertEqual(cached["vessels"][0]["lon"], 53.1)
                self.assertEqual(cached["vessels"][0]["observed_at"], newer.isoformat())
                self.assertEqual(cached["vessels"][0]["age_minutes"], 1440)
                with data_store.connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM ais_reports").fetchone()[0], 2)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM collection_runs").fetchone()[0], 3)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM source_queries").fetchone()[0],
                                     2 * len(ais.openwaters_bbox_groups()))


if __name__ == "__main__":
    unittest.main()
