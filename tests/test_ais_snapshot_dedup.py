"""Keep one stable current report per vessel across multiple AIS sources."""
from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import ais_history
import data_store


class AISSnapshotDedupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {
            "MONITORING_DB_PATH": os.path.join(self.temp.name, "monitoring.duckdb"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_same_observation_from_two_sources_returns_one_latest_received_row(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=3)
        earlier = observed + timedelta(seconds=1)
        later = observed + timedelta(seconds=2)
        with data_store.connect() as conn:
            for source, received, lon in (
                ("AISStream", earlier, 56.0),
                ("Open Waters", later, 56.1),
            ):
                payload = {
                    "mmsi": "123456789", "observed_at": observed.isoformat(),
                    "received_at": received.isoformat(), "source": source,
                    "data_source": source, "lat": 25.0, "lon": lon,
                }
                conn.execute(
                    "INSERT INTO ais_reports VALUES (?,?,?,?)",
                    ("123456789", observed.isoformat(), source,
                     json.dumps(payload, ensure_ascii=False)),
                )

        rows = ais_history.latest_snapshot()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "Open Waters")
        self.assertEqual(rows[0]["lon"], 56.1)


if __name__ == "__main__":
    unittest.main()
