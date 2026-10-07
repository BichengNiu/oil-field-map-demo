"""Verify history contracts with synthetic fixtures, never imported into the app."""
import csv
from datetime import date, timedelta
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

import monitoring_cards
import sea_history


def bundle(events, coverage, definition="test-boundaries-v1", source="test-provider"):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps({
            "schema_version": 1, "event_basis": "sea_entry", "timezone": "Asia/Shanghai",
            "source": source, "source_url": "https://example.test/history",
            "definition_id": definition, "seas": list(monitoring_cards.SEA_MONITORING_AREAS)}))
        for name, columns, rows in (("events.csv", sea_history.EVENT_COLUMNS, events),
                                    ("coverage.csv", sea_history.COVERAGE_COLUMNS, coverage)):
            stream = StringIO()
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(rows)
            archive.writestr(name, stream.getvalue())
    return output.getvalue()


class SeaHistoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "monitoring.duckdb"

    def test_reentries_distinct_seas_and_duplicate_imports(self):
        events = [("波斯湾", "123456789", "2020-10-05T01:00:00Z"),
                  ("波斯湾", "123456789", "2020-10-05T01:00:00+00:00"),
                  ("波斯湾", "123456789", "2020-10-05T03:00:00Z"),
                  ("阿曼湾", "123456789", "2020-10-05T03:00:00Z")]
        coverage = [("波斯湾", "2020-10-05", "complete", 2),
                    ("阿曼湾", "2020-10-05", "complete", 1),
                    ("红海", "2020-10-05", "complete", 0)]
        data = bundle(events, coverage)
        for _ in range(2):
            self.assertEqual(sea_history.import_bundle(data, self.path)["events"], 3)
        rows = sea_history.read_history(self.path)["rows"]
        self.assertEqual({r["sea"]: r["passages"] for r in rows}, {"波斯湾": 2, "阿曼湾": 1, "红海": 0})
        self.assertNotIn("亚丁湾", {r["sea"] for r in rows})

    def test_timestamp_uses_statistical_day(self):
        data = bundle([("红海", "123456789", "2020-10-04T18:00:00Z")],
                      [("红海", "2020-10-05", "complete", 1)])
        sea_history.import_bundle(data, self.path)
        self.assertEqual(sea_history.read_history(self.path)["rows"][0]["date"], "2020-10-05")

    def test_corrected_delivery_replaces_day(self):
        sea_history.import_bundle(bundle([("红海", "123456789", "2020-10-05T01:00:00Z")],
                                  [("红海", "2020-10-05", "complete", 1)]), self.path)
        sea_history.import_bundle(bundle([], [("红海", "2020-10-05", "complete", 0)]), self.path)
        self.assertEqual(sea_history.read_history(self.path)["rows"][0]["passages"], 0)

    def test_mixed_boundaries_and_truncated_delivery_do_not_change_archive(self):
        good = bundle([], [("红海", "2020-10-05", "complete", 0)])
        sea_history.import_bundle(good, self.path)
        before = sea_history.read_history(self.path)
        with self.assertRaises(ValueError):
            sea_history.import_bundle(bundle([], [("红海", "2020-10-05", "complete", 0)],
                                             definition="other-boundaries"), self.path)
        with self.assertRaises(ValueError):
            sea_history.import_bundle(bundle([], [("红海", "2020-10-05", "complete", 1)]), self.path)
        self.assertEqual(sea_history.read_history(self.path), before)

    def test_reject_samples_unknown_coverage_and_naive_time(self):
        for events, coverage in (
            ([("红海", "123456789", "2020-10-05T01:00:00")], [("红海", "2020-10-05", "complete", 1)]),
            ([("红海", "123456789", "2020-10-05T01:00:00Z")], []),
            ([], [("红海", "2020-10-05", "partial", 0)]),
            ([], [("红海", sea_history.datetime.now(sea_history.TZ).date().isoformat(), "complete", 0)]),
        ):
            with self.assertRaises(ValueError):
                sea_history.import_bundle(bundle(events, coverage), self.path)
        self.assertFalse(self.path.exists())

    def test_history_reaches_card_with_comparisons_and_missing_sea_is_not_zero(self):
        anchor = date(2020, 10, 6)
        days = set()
        for first, last in monitoring_cards.windows(anchor - timedelta(days=1)):
            days.update(first + timedelta(days=i) for i in range((last - first).days + 1))
        events, coverage = [], []
        for day in sorted(days):
            for sea in monitoring_cards.SEA_MONITORING_AREAS:
                coverage.append((sea, day.isoformat(), "complete", 1))
                events.append((sea, "123456789", day.isoformat() + "T01:00:00Z"))
        sea_history.import_bundle(bundle(events, coverage), self.path)
        rows = sea_history.read_history(self.path)["rows"]
        cards = monitoring_cards.build_cards([], [], [], [], [], None, None,
                                            vessel_day=anchor, sea_passage_history=rows)
        self.assertIn("通过28艘次（环比 +0.0%）", cards[2][2])
        self.assertIn("通过20艘次（环比 +0.0%，同比 +0.0%）", cards[2][3])
        rows = [r for r in rows if not (r["sea"] == "红海" and r["date"] == "2020-10-03")]
        broken = monitoring_cards.sea_activity_card(rows, anchor)
        self.assertIn("通过—艘次", broken[2])
        self.assertIn("通过—艘次", broken[3])

    def test_monday_keeps_last_complete_week_and_no_previous_month_as_current(self):
        anchor = date(2020, 10, 5)  # Monday, source only through Sunday.
        rows = [{"sea": sea, "date": (anchor - timedelta(days=i)).isoformat(), "passages": 1}
                for i in range(1, 15) for sea in monitoring_cards.SEA_MONITORING_AREAS]
        card = monitoring_cards.sea_activity_card(rows, anchor)
        self.assertIn("通过28艘次（环比 +0.0%）", card[2])
        prior_month_only = [r for r in rows if r["date"] < "2020-10-01"]
        self.assertIn("本月累计通过—艘次", monitoring_cards.sea_activity_card(prior_month_only, anchor)[3])


if __name__ == "__main__":
    unittest.main()
