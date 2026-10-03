"""Tests for Chinese PortWatch selector labels."""
import csv
import json
from pathlib import Path
import unittest

import port_inventory


REGIONS = (
    (25.7, 27.4, 55.9, 57.5),
    (22.0, 26.6, 56.0, 61.8),
    (23.5, 30.9, 47.0, 56.8),
    (29.4, 31.6, 31.7, 33.5),
    (11.0, 15.4, 42.0, 45.7),
)


def _inside_scope(row):
    return any(south <= row["lat"] <= north and west <= row["lon"] <= east
               for south, north, west, east in REGIONS)


def _has_chinese(value):
    return any("\u4e00" <= character <= "\u9fff" for character in value)


class PortInventoryLabelTests(unittest.TestCase):
    def test_all_countries_in_the_monitoring_scope_have_chinese_labels(self):
        countries = {row["country"] for row in port_inventory.WPI_ROWS
                     if _inside_scope(row)}
        self.assertEqual(len(countries), 12)
        for country in countries:
            with self.subTest(country=country):
                self.assertTrue(_has_chinese(port_inventory.country_label(country)))

    def test_all_wpi_ports_in_the_monitoring_scope_have_chinese_names(self):
        rows = [row for row in port_inventory.WPI_ROWS if _inside_scope(row)]
        self.assertEqual(len(rows), 91)
        for row in rows:
            port_id = row["portwatch_id"] or f"wpi{row['wpi']}"
            label = port_inventory.port_label({
                "portid": port_id, "name": row["name"], "country": row["country"],
            })
            with self.subTest(port=row["name"]):
                self.assertTrue(_has_chinese(label))
                self.assertFalse(label.startswith("港口（编号"), msg=label)

    def test_latest_regional_catalog_snapshot_has_no_generic_labels(self):
        snapshot = Path(__file__).with_name("PORT_ACTIVITY_AUDIT_2026-09-25.csv")
        with snapshot.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 96)
        for row in rows:
            label = port_inventory.port_label({
                "portid": row["PortWatch ID"],
                "name": row["点位库港名"],
                "country": row["国家"],
            })
            with self.subTest(port_id=row["PortWatch ID"], name=row["点位库港名"]):
                self.assertTrue(_has_chinese(label))
                self.assertFalse(label.startswith("港口（编号"), msg=label)

    def test_enriched_port_records_carry_chinese_names(self):
        raw_by_id = {}
        for row in port_inventory.WPI_ROWS:
            port_id = row["portwatch_id"]
            if port_id:
                raw_by_id.setdefault(port_id, {
                    "portid": port_id, "name": row["name"],
                    "country": row["country"], "lat": row["lat"],
                    "lon": row["lon"], "region": row["region"],
                })
        enriched = port_inventory.enrich(list(raw_by_id.values()))
        self.assertTrue(enriched)
        by_id = {port["portid"]: port for port in enriched}
        self.assertTrue(all(by_id[port_id]["statistics_available"] for port_id in raw_by_id))
        for port in enriched:
            with self.subTest(port=port["portid"]):
                self.assertTrue(_has_chinese(port["name_cn"]))
        supplemental = [port for port in enriched
                        if port["portid"].startswith(("wpi", "facility_"))]
        self.assertTrue(supplemental)
        self.assertTrue(all(not port["statistics_available"] for port in supplemental))

    def test_common_portwatch_aliases_are_translated(self):
        self.assertEqual(port_inventory.port_label({
            "name": "Khor Fakkan", "country": "United Arab Emirates",
        }), "豪尔费坎港")
        self.assertEqual(port_inventory.port_label({
            "name": "Ras Tanura", "country": "Saudi Arabia",
        }), "拉斯坦努拉港")


if __name__ == "__main__":
    unittest.main()
