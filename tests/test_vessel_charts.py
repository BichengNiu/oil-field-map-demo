"""Vessel charts count distinct ships in observed periods, with unknown gaps."""
from datetime import date
import unittest
import vessel_charts


class VesselChartsTest(unittest.TestCase):
    def test_distinct_vessels_across_reports_days_and_sources(self):
        rows = [{"mmsi": ship, "observed_at": f"2026-10-{day:02}T12:00:00Z",
                 "region": "波斯湾", "flag_country": "中国", "destination": "DUBAI"}
                for day, ship in [(5, "1"), (5, "1"), (6, "1"), (6, "2"), (8, "3")]]
        args = (date(2026, 10, 5), date(2026, 10, 8))
        daily = vessel_charts.aggregate(rows, *args, "日度", ["中国"], ["DUBAI"])
        self.assertEqual([r["波斯湾"] for r in daily], [1, 2, None, 1])
        weekly = vessel_charts.aggregate(rows, *args, "周度", ["中国"], ["DUBAI"])
        self.assertEqual(weekly[0]["波斯湾"], 3)
        self.assertIsNone(weekly[0]["阿曼湾"])
        empty = vessel_charts.aggregate(rows, *args, "日度", [], [])
        self.assertEqual([r["波斯湾"] for r in empty], [0, 0, None, 0])

    def test_unknown_speed_is_not_counted_as_berthed_and_chinese_flag_is_explicit(self):
        rows = [{"sog": None, "category": "unknown", "mmsi": "413000000"},
                {"sog": 0, "category": "tanker", "flag": "CN"},
                {"sog": 4, "category": "cargo", "flag": "HK"},
                {"sog": 2, "category": "passenger", "flag": "PA"}]
        self.assertEqual([value for _, value in vessel_charts.metrics(rows, True)], [2, 1, 1, 1, 2, 1])
        self.assertTrue(all(value == "—" for _, value in vessel_charts.metrics([], False)))

    def test_filters_use_unknown_options_and_clip_dates(self):
        row = {"observed_at": "2026-10-01T23:59:00Z", "mmsi": "1", "region": "波斯湾"}
        self.assertTrue(vessel_charts.matches(row, ["未知船籍"], ["未知目的地"]))
        records = vessel_charts.aggregate([row], date(2026, 10, 2), date(2026, 10, 2),
                                          "月度", ["未知船籍"], ["未知目的地"])
        self.assertIsNone(records[0]["波斯湾"])
        self.assertEqual(records[0]["period_start"], date(2026, 10, 2))


if __name__ == "__main__":
    unittest.main()
