"""Archive gaps must be repaired per node, not just by global min/max dates."""
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import data_store
import portwatch_history as history


class HistoryRepairTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        environment = patch.dict(os.environ, {
            "MONITORING_DB_PATH": str(Path(self.temporary.name) / "monitoring.duckdb"),
            "MONITORING_READ_ONLY": "false",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        self.ids = {"ports": ("port105", "port106"), "chokepoints": ("chokepoint1",)}
        self.ends = {"ports": date(2026, 10, 9), "chokepoints": date(2026, 10, 11)}
        self.holes = {"ports": (date(2025, 10, 10), date(2026, 7, 4)),
                      "chokepoints": (date(2025, 10, 12), date(2026, 7, 6))}
        for kind, ids in self.ids.items():
            data_store.save_catalog(kind, [{"portid": node, "statistics_available": True} for node in ids])
            first, last = self.holes[kind]
            data_store.save_portwatch(kind, [
                {"portid": node, "date": day.isoformat(), "portcalls": 1, "n_total": 1}
                for node in ids for day in history._dates(date(2025, 10, 1), self.ends[kind])
                if not first <= day <= last
            ], "test-source")

    def fetch(self, kind, ids, first, last, *, force):
        self.assertTrue(force)
        self.assertLessEqual((last - first).days + 1, 90)
        rows = [{"portid": node, "date": day.isoformat(), "portcalls": 1, "n_total": 1}
                for node in ids for day in history._dates(first, last)]
        data_store.save_portwatch(kind, rows, "test-source")
        return rows, {"count_verified": True, "source_count": len(rows), "endpoint": "test-source"}

    def repair_all(self):
        for kind, ids in self.ids.items():
            history.repair(kind, ids, self.ends[kind], self.now)

    def test_both_disjoint_windows_become_continuous_without_repeat_downloads(self):
        self.assertTrue(history.needs_repair(self.now))
        with patch("portwatch_downloads.fetch_window", side_effect=self.fetch) as upstream:
            self.repair_all()
            first_count = upstream.call_count
            self.assertEqual(first_count, 6)
            self.repair_all()
            self.assertEqual(upstream.call_count, first_count)
        reports = history.validate_all(self.now)
        self.assertEqual(reports["ports"]["stored_records"], 374 * 2)
        self.assertEqual(reports["chokepoints"]["stored_records"], 376)
        self.assertTrue(all(report["status"] == "complete" for report in reports.values()))
        self.assertFalse(history.needs_repair(self.now))

    def test_node_specific_hole_is_detected_even_when_total_count_does_not_fall(self):
        with patch("portwatch_downloads.fetch_window", side_effect=self.fetch):
            self.repair_all()
        with data_store.connect() as conn:
            conn.execute("DELETE FROM portwatch_daily WHERE kind='ports' AND node_id='port105' AND day=DATE '2026-01-01'")
        data_store.save_portwatch("ports", [{"portid": "port106", "date": "2026-10-10"}], "test-source")
        self.assertTrue(history.needs_repair(self.now))
        with self.assertRaisesRegex(ValueError, "历史完整性"):
            history.validate_all(self.now)
        with patch("portwatch_downloads.fetch_window", side_effect=self.fetch):
            history.repair("ports", self.ids["ports"], date(2026, 10, 10), self.now)
        self.assertEqual(history.validate_all(self.now)["ports"]["status"], "complete")

    def test_verified_source_omissions_remain_missing_and_expire_for_recheck(self):
        with patch("portwatch_downloads.fetch_window", return_value=([], {"count_verified": True, "source_count": 0})):
            self.repair_all()
        reports = history.validate_all(self.now)
        self.assertEqual(reports["ports"]["source_missing_records"], 268 * 2)
        self.assertEqual(reports["ports"]["status"], "source_gaps")
        self.assertFalse(history.needs_repair(self.now))
        self.assertTrue(history.needs_repair(self.now + timedelta(days=8)))
        with self.assertRaisesRegex(ValueError, "历史完整性"):
            history.validate_all(self.now + timedelta(days=8))

    def test_unverified_result_cannot_certify_a_gap(self):
        with patch("portwatch_downloads.fetch_window", return_value=([], {})):
            with self.assertRaisesRegex(ValueError, "上游记录数校验"):
                history.repair("ports", self.ids["ports"], self.ends["ports"], self.now)
        self.assertIsNone(data_store.meta(history.AUDIT_PREFIX + "ports"))

    def test_rows_returned_but_not_persisted_cannot_be_marked_as_source_omissions(self):
        rows = [{"portid": "port105", "date": "2025-10-10"}]
        with patch("portwatch_downloads.fetch_window", return_value=(rows, {"count_verified": True})):
            # Restrict the chunk so this response is valid yet fails persistence.
            with patch.object(history, "MAX_CHUNK_DAYS", 365):
                with self.assertRaisesRegex(ValueError, "未成功入库"):
                    history.repair("ports", self.ids["ports"], self.ends["ports"], self.now)


if __name__ == "__main__":
    unittest.main()
