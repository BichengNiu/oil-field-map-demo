"""Tests for Chinese PortWatch selector labels."""
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
            fallback = (f"{port_inventory.country_label(row['country'])}"
                        f"港口（编号{port_id}）")
            with self.subTest(port=row["name"]):
                self.assertTrue(_has_chinese(label))
                self.assertNotEqual(label, fallback)

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
        for port in enriched:
            with self.subTest(port=port["portid"]):
                self.assertTrue(_has_chinese(port["name_cn"]))

    def test_common_portwatch_aliases_are_translated(self):
        self.assertEqual(port_inventory.port_label({
            "name": "Khor Fakkan", "country": "United Arab Emirates",
        }), "豪尔费坎港")
        self.assertEqual(port_inventory.port_label({
            "name": "Ras Tanura", "country": "Saudi Arabia",
        }), "拉斯坦努拉港")


if __name__ == "__main__":
    unittest.main()