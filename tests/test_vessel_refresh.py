"""Exercise manual vessel refresh through real storage and display reads."""
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ais
import dashboard_data
import data_store


class VesselRefreshTest(unittest.TestCase):
    def test_refresh_archives_source_responses_and_exposes_latest_vessel(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=2)
        response = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [53.0, 26.0]},
                "properties": {
                    "kind": "vessel", "mmsi": 123456789,
                    "seen": observed.isoformat(), "name": "TEST VESSEL",
                    "source": "test-station", "type": 70,
                },
            }],
        }
        encoded = json.dumps(response).encode()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "monitoring.duckdb"
            with patch.dict(os.environ, {"MONITORING_DB_PATH": str(path)}), \
                 patch("ais.urlopen", side_effect=lambda *a, **kw: io.BytesIO(encoded)) as upstream, \
                 patch("dashboard_data.st.session_state", {}):
                dashboard_data.refresh_vessel_data()
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


if __name__ == "__main__":
    unittest.main()
