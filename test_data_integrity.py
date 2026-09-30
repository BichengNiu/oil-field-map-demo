"""Regression tests for observed failures: unsupported values, BOE and nulls."""
import unittest
import ast
import html
import json
import gzip
import hashlib
import csv
from pathlib import Path
from datetime import date, timedelta
from unittest.mock import patch

import field_catalog
import portwatch
import port_inventory
import reconciled_assets
from audited_measurements import daily_thousand_barrels


class CatalogIntegrity(unittest.TestCase):
    def test_checkpoint_clues_are_not_lost_or_promoted_without_evidence(self):
        index = {(a["country"], a["name"]): a for a in field_catalog.ASSETS}
        for row in reconciled_assets.GEM_ROWS:
            key = (row["country"], row["name"])
            if key in reconciled_assets.MERGES:
                for target in reconciled_assets.MERGES[key]:
                    self.assertIn((key[0], target), index)
            elif row["catalog_name_confirmed"]:
                asset = index[key]
                self.assertIsNone(asset["value"])
                self.assertEqual(asset["operating_status"], "historical_unverified")
                if row["coordinates"]:
                    self.assertEqual(asset["map_lat"], row["coordinates"]["lat"])
                    self.assertEqual(asset["coordinate_source_url"], row["url"])
            else:
                self.assertNotIn(key, index)
        for name in ("Qatargas 2", "Dolphin", "RasGas 3"):
            self.assertEqual(index[("卡塔尔", name)]["asset_level"], "project")
            self.assertEqual(index[("卡塔尔", name)]["parent_asset"], "North Field")
        with Path("ASSET_CHECKPOINT_RECONCILIATION_2026-09-30.csv").open(encoding="utf-8-sig") as stream:
            unresolved = {(r["国家"], r["快照名称"]) for r in csv.DictReader(stream) if not r["当前对应"]}
        self.assertEqual(unresolved, {(r["国家"], r["名称线索"]) for r in reconciled_assets.pending()})

    def test_estimates_retain_period_commodity_and_original_inputs(self):
        index = {(a["country"], a["name"]): a for a in field_catalog.ASSETS}
        sakarya = index[("土耳其", "Sakarya")]
        self.assertEqual(sakarya["value"], "约8.34")
        self.assertAlmostEqual(sakarya["estimate_total_million_m3"] * sakarya["estimate_share"] / sakarya["calendar_days"], 8.341, places=3)
        self.assertEqual(sakarya["metric_type"], "estimated_daily_average")
        self.assertEqual(sakarya["commodity"], "natural_gas")
        gabar = index[("土耳其", "Gabar")]
        self.assertEqual(gabar["value"], "约76.6")
        self.assertEqual(index[("阿联酋", "Umm Shaif Gas Cap")]["metric_type"], "target_capacity")
        self.assertEqual(index[("伊拉克", "Khor Mor")]["value"], ">700")

    def test_units_aliases_and_withdrawals(self):
        rows = field_catalog.ASSETS
        index = {(a["country"], a["name"]): a for a in rows}
        self.assertEqual(len(rows), len(index))
        self.assertNotIn(("伊朗", "Darquain"), index)
        self.assertIn("Darquain", index[("伊朗", "Darkhovin")]["aliases"])
        self.assertEqual(index[("伊拉克", "Badra")]["value"], "35.2")
        self.assertEqual(index[("伊拉克", "East Baghdad")]["value"], "18.2")
        for name in ("Nahr Umar", "Nassiriya", "Najma", "Subba"):
            self.assertIsNone(index[("伊拉克", name)]["value"])
        for name in ("Tawke", "Peshkabir"):
            self.assertEqual(index[("伊拉克", name)]["metric_type"], "actual_output_boe")
            self.assertIn("油当量", index[("伊拉克", name)]["unit"])
        for name in ("Fakkah", "Bazerkan", "Abu Gharb"):
            self.assertEqual(index[("伊拉克", name)]["parent_asset"], "Missan Fields")
            self.assertIsNone(index[("伊拉克", name)]["value"])
        self.assertEqual(daily_thousand_barrels(366000, 2016), "1.0")
        self.assertEqual(daily_thousand_barrels(365000, 2021), "1.0")

    def test_all_rows_have_honest_dates_and_valid_graph(self):
        index = {(a["country"], a["name"]): a for a in field_catalog.ASSETS}
        for row in index.values():
            self.assertTrue(row["source_url"].startswith("https://"))
            self.assertTrue(row["freshness_note"])
            self.assertEqual(row["value"] is None, row["metric_type"] == "undisclosed")
            seen = set()
            current = row
            while current.get("parent_asset"):
                key = (current["country"], current["name"])
                self.assertNotIn(key, seen)
                seen.add(key)
                current = index[(current["country"], current["parent_asset"])]
            if row["map_drawable"]:
                self.assertTrue(-90 <= row["map_lat"] <= 90)
                self.assertTrue(-180 <= row["map_lon"] <= 180)


class PortWindowIntegrity(unittest.TestCase):
    end = date(2026, 9, 25)

    def test_preserved_source_rows_hash_coverage_and_ship_totals(self):
        snapshot = json.loads(Path("PORT_AUDIT_SUMMARY_2026-09-30.json").read_text())
        data = gzip.decompress(Path(snapshot["raw_file"]).read_bytes())
        self.assertEqual(hashlib.sha256(data).hexdigest(), snapshot["raw_sha256"])
        rows = json.loads(data)
        self.assertEqual(len(rows), snapshot["raw_daily_rows"])
        keys = {(r["portid"], r["date"]) for r in rows}
        self.assertEqual(len(rows), len(keys))
        self.assertEqual(len({r["date"] for r in rows}), 60)
        for row in rows:
            self.assertEqual(row["portcalls"], sum(row[f"portcalls_{kind}"] for kind in portwatch.SHIP_TYPES))

    def records(self):
        output = []
        for offset in range(14):
            r = {"date": (self.end - timedelta(days=offset)).isoformat(), "portid": "port1",
                 "portcalls": 5, "import": 100, "export": 150}
            for kind in (*portwatch.SHIP_TYPES, "cargo"):
                r.update({f"portcalls_{kind}": 1, f"import_{kind}": 20, f"export_{kind}": 30})
            output.append({"attributes": r})
        return output

    def calculate(self, rows, ids=("port1",)):
        with patch.object(portwatch, "_query", return_value={"features": rows}):
            return portwatch.rolling_activity.__wrapped__(self.end, ids, 7)

    def test_null_volume_does_not_erase_observed_calls(self):
        rows = self.records()
        rows[0]["attributes"].update(import_tanker=None, **{"import": None})
        r = self.calculate(rows)["port1"]
        self.assertEqual(r["avg_calls_tanker"], 1)
        self.assertEqual(r["avg_calls"], 5)
        self.assertIsNone(r["avg_handled_tanker"])
        self.assertIsNone(r["tanker_calls_zero_volume_days"])
        self.assertIsNone(r["avg_handled"])

    def test_observed_zero_missing_date_and_supplement(self):
        rows = self.records()
        for r in rows:
            r["attributes"]["portcalls_tanker"] = 0
        complete = self.calculate(rows)["port1"]
        self.assertEqual(complete["avg_calls_tanker"], 0)
        missing = self.calculate(rows[1:])["port1"]
        self.assertIsNone(missing["avg_calls_tanker"])
        self.assertIsNone(missing["active_day_rate"])
        result = self.calculate(rows, ("port1", "wpi48295"))
        self.assertIsNone(result["wpi48295"]["avg_calls"])
        self.assertIsNone(result["wpi48295"]["active_days"])
        with patch.object(portwatch, "_query") as query:
            self.assertEqual(portwatch.daily_activity.__wrapped__(self.end, ("wpi48295",)), {})
            query.assert_not_called()

    def test_duplicate_and_unregistered_identifiers_fail(self):
        rows = self.records()
        with self.assertRaisesRegex(ValueError, "重复"):
            self.calculate(rows + [rows[0]])
        with self.assertRaises(ValueError):
            self.calculate(rows, ("facility_made_up",))
        with self.assertRaises(ValueError):
            port_inventory.enrich([])  # Crosswalk changes cannot silently lose coverage.

    def test_chokepoint_popup_is_independent_of_selected_ports(self):
        # Load just the renderer, without executing the network-backed Streamlit UI.
        tree = ast.parse(Path("app.py").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_chokepoint_popup")
        namespace = {"html": html, "PORTWATCH": portwatch}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), namespace)
        snapshot = json.loads(Path("PORT_AUDIT_SUMMARY_2026-09-30.json").read_text())
        for row in snapshot["chokepoints"]:
            row["name_cn"] = portwatch.CHOKEPOINT_LABELS[row["portid"]]
            rendered = namespace["_chokepoint_popup"](row, snapshot["chokepoint_date"])
            self.assertIn(portwatch.SOURCE, rendered)
            self.assertIn(row["name_cn"], rendered)


if __name__ == "__main__":
    unittest.main()
