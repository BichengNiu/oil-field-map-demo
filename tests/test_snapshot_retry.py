"""A backup must recover a missed run without duplicating a successful one."""
from datetime import datetime, timezone
import unittest

from deploy.snapshot_retry import decision


def full_snapshot(when):
    return {"completed_at": when,
            "after": {"latest_vessel": when, "counts": {"ais_reports": 42}}}


class SnapshotRetryTest(unittest.TestCase):
    now = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)  # 13:00 Dubai

    def test_no_run_or_yesterday_failure_requires_retry(self):
        for marker in [None, {}, full_snapshot("2026-10-26T04:01:00+00:00")]:
            self.assertEqual(decision(marker, self.now)["status"], "retry_due")

    def test_successful_primary_or_manual_recovery_skips_duplicate(self):
        for when in ["2026-10-27T04:01:00+00:00", "2026-10-27T05:41:01+00:00"]:
            result = decision(full_snapshot(when), self.now)
            self.assertEqual(result["status"], "skipped_already_published")
            self.assertEqual(result["primary_window_start"], "2026-10-27T08:00:00+04:00")

    def test_catalog_change_or_notification_is_not_full_collection(self):
        for marker in [{"completed_at": "2026-10-27T05:00:00+00:00", "mode": "catalog_review"},
                       {"completed_at": "2026-10-27T05:00:00+00:00", "after": {"counts": {}}}]:
            self.assertEqual(decision(marker, self.now)["status"], "retry_due")

    def test_midnight_is_not_a_new_primary_window(self):
        # 01:00 Oct28 Dubai still belongs to Oct27's 08:00 primary window.
        now = datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc)
        self.assertEqual(decision(full_snapshot("2026-10-27T04:01:00+00:00"), now)["status"],
                         "skipped_already_published")

    def test_pre_primary_success_does_not_replace_today_primary(self):
        self.assertEqual(decision(full_snapshot("2026-10-27T03:00:00+00:00"), self.now)["status"],
                         "retry_due")

    def test_future_or_timezone_free_success_cannot_silently_skip(self):
        for when in ["2026-10-28T04:01:00+00:00", "2026-10-27T04:01:00"]:
            with self.assertRaises(ValueError):
                decision(full_snapshot(when), self.now)
