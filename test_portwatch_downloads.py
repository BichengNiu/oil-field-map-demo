"""PortWatch history extraction, completeness checks, and export integrity."""
from datetime import date, timedelta
import csv
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import xml.etree.ElementTree as ET

import portwatch
import portwatch_downloads as downloads


class PortWatchDownloads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"PORTWATCH_DOWNLOAD_CACHE": str(Path(self.temp.name) / "cache.sqlite3")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.port_rows = [self.port("2026-01-01", 8, 100),
                          self.port("2026-01-02", 0, 0),
                          self.port("2026-01-04", 12, 300)]
        self.choke_rows = [self.choke("2026-01-02", 15), self.choke("2026-01-03", 18)]
        self.count_calls = {}
        self.change_count = False
        self.mock = patch.object(portwatch, "_query", side_effect=self.query)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    @staticmethod
    def port(day, calls, imports):
        row = {"ObjectId": int(day[-2:]), "date": day, "portid": "port1",
               "portname": "Fixture port", "country": "Oman", "ISO3": "OMN",
               "portcalls": calls, "import": imports, "export": imports + 50}
        for ship in (*portwatch.SHIP_TYPES, "cargo"):
            row.update({f"portcalls_{ship}": calls, f"import_{ship}": imports,
                        f"export_{ship}": imports + 50})
        return row

    @staticmethod
    def choke(day, count):
        row = {"ObjectId": int(day[-2:]), "date": day, "portid": "chokepoint6",
               "portname": "Hormuz", "n_total": count, "capacity": count * 1000}
        for ship in (*portwatch.SHIP_TYPES, "cargo"):
            row.update({f"n_{ship}": count, f"capacity_{ship}": count * 1000})
        return row

    @staticmethod
    def requested_ids(where):
        return set(re.findall(r"'((?:port|fso|chokepoint)\d+)'", where))

    def query(self, url, **params):
        source = self.port_rows if url == portwatch.DAILY else self.choke_rows
        where = params.get("where", "")
        ids = self.requested_ids(where)
        rows = [row for row in source if row["portid"] in ids]
        if params.get("outStatistics"):
            grouped = {}
            for row in rows:
                grouped.setdefault(row["portid"], []).append(row)
            return {"features": [{"attributes": {"portid": pid,
                    "first_date": min(r["date"] for r in group),
                    "last_date": max(r["date"] for r in group), "records": len(group)}}
                    for pid, group in grouped.items()]}
        if params.get("returnCountOnly") == "true":
            key = (url, where)
            self.count_calls[key] = self.count_calls.get(key, 0) + 1
            count = sum(1 for row in rows if self.matches_dates(row, where))
            if self.change_count and self.count_calls[key] > 1:
                count += 1
            return {"count": count}
        rows = [row for row in rows if self.matches_dates(row, where)]
        rows.sort(key=lambda row: (row["portid"], row["date"], row["ObjectId"]))
        offset, limit = params.get("resultOffset", 0), params.get("resultRecordCount", 1000)
        return {"features": [{"attributes": row} for row in rows[offset:offset + limit]]}

    @staticmethod
    def matches_dates(row, where):
        requested = re.findall(r"DATE '([\d-]+)'", where)
        return not requested or date.fromisoformat(requested[0]) <= date.fromisoformat(row["date"]) <= date.fromisoformat(requested[-1])

    def port_node(self):
        return downloads.node("ports", {"portid": "port1", "name": "Fixture port",
            "country": "Oman", "region": "霍尔木兹海峡", "lat": 26.5, "lon": 56.4})

    def test_history_preserves_zero_and_reports_missing_day(self):
        result = downloads.collect([self.port_node()], "history", date(2026, 1, 1), date(2026, 1, 4))
        self.assertEqual([row["date"] for row in result["datasets"]["ports"]],
                         ["2026-01-01", "2026-01-02", "2026-01-04"])
        self.assertEqual(result["datasets"]["ports"][1]["import"], 0)
        coverage = result["coverage"][0]
        self.assertEqual(coverage["status"], "gaps")
        self.assertEqual(coverage["missing_days"], 1)
        self.assertEqual(coverage["missing_intervals_utc"], "2026-01-03/2026-01-03")
        self.assertTrue(result["manifest"]["fetch_complete"])

    def test_latest_is_per_node_and_full_history_is_source_count_checked(self):
        latest = downloads.collect([self.port_node()], "latest")
        self.assertEqual([r["date"] for r in latest["datasets"]["ports"]], ["2026-01-04"])
        self.assertEqual(latest["coverage"][0]["latest_available_utc"], "2026-01-04")
        full = downloads.collect([self.port_node()], "all")
        self.assertEqual(len(full["datasets"]["ports"]), 3)
        self.assertTrue(all(q.get("count_verified") for q in full["manifest"]["queries"]
                            if q.get("operation") != "node_date_bounds"))

    def test_derived_means_require_every_calendar_day(self):
        result = downloads.collect([self.port_node()], "history", date(2026, 1, 1),
                                   date(2026, 1, 4), derived=True)
        jan2, jan4 = result["datasets"]["ports"][1:]
        self.assertEqual(jan2["avg_import_7d"], None)
        self.assertEqual(jan4["observed_days_7d"], 3)
        self.assertIsNone(jan4["avg_import_7d"])

    def test_nodes_without_statistics_are_documented_without_querying_fake_ids(self):
        node = downloads.node("ports", {"portid": "wpi48295", "name": "Supplement",
            "country": "Oman", "region": "霍尔木兹海峡"})
        before = len(self.count_calls)
        result = downloads.collect([node], "latest")
        self.assertEqual(result["datasets"]["ports"], [])
        self.assertEqual(result["coverage"][0]["status"], "no_independent_statistics")
        self.assertEqual(len(self.count_calls), before)

    def test_changed_source_count_fails_closed(self):
        self.change_count = True
        with self.assertRaisesRegex(downloads.DownloadError, "记录数发生变化"):
            downloads.collect([self.port_node()], "history", date(2026, 1, 1), date(2026, 1, 4))

    def test_pagination_reads_past_one_source_page(self):
        first = date(2019, 1, 1)
        self.port_rows = [self.port((first + timedelta(days=offset)).isoformat(), offset % 11, offset)
                          for offset in range(downloads.PAGE_SIZE + 17)]
        rows, query = downloads.fetch_window("ports", ("port1",), first,
            first + timedelta(days=len(self.port_rows) - 1))
        self.assertEqual(len(rows), downloads.PAGE_SIZE + 17)
        self.assertTrue(query["count_verified"])

    def test_refresh_revision_bypasses_old_disk_snapshot_and_then_reuses_new_one(self):
        first, last = date(2026, 1, 1), date(2026, 1, 4)
        original, _ = downloads.fetch_window("ports", ("port1",), first, last)
        self.port_rows[0]["import"] = 777
        cached, _ = downloads.fetch_window("ports", ("port1",), first, last)
        refreshed, _ = downloads.fetch_window(
            "ports", ("port1",), first, last, cache_revision=1)
        refreshed_cached, _ = downloads.fetch_window(
            "ports", ("port1",), first, last, cache_revision=1)

        self.assertNotEqual(original[0]["import"], refreshed[0]["import"])
        self.assertEqual(cached[0]["import"], original[0]["import"])
        self.assertEqual(refreshed_cached, refreshed)

    def test_excel_limit_keeps_large_exports_in_csv_and_zip(self):
        result = {"datasets": {"ports": [{}] * (downloads.XLSX_ROW_LIMIT + 1)},
                  "manifest": {"derived": False}}
        with self.assertRaisesRegex(downloads.DownloadError, "ZIP下载全量数据"):
            downloads.xlsx_bytes(result)

    def test_csv_zip_and_xlsx_exports_are_readable_and_provenanced(self):
        result = downloads.collect([self.port_node()], "history", date(2026, 1, 1), date(2026, 1, 4))
        rows = result["datasets"]["ports"]
        rows[0]["portname"] = "=HYPERLINK(\"https://invalid\")"
        payload = downloads.csv_bytes(rows, downloads.columns("ports"))
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"))
        decoded = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        self.assertEqual(decoded[0]["portname"], "'=HYPERLINK(\"https://invalid\")")
        with zipfile.ZipFile(io.BytesIO(downloads.zip_bytes(result))) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("manifest.json", archive.namelist())
            self.assertIn("coverage.csv", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["source"], "IMF PortWatch / UN Global Platform")
        with zipfile.ZipFile(io.BytesIO(downloads.xlsx_bytes(result))) as workbook:
            self.assertIsNone(workbook.testzip())
            self.assertIn("xl/workbook.xml", workbook.namelist())
            workbook_xml = ET.fromstring(workbook.read("xl/workbook.xml"))
            ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            self.assertEqual([sheet.attrib["name"] for sheet in workbook_xml.findall(".//x:sheet", ns)],
                             ["港口日表", "下载说明", "节点目录", "覆盖情况", "数据字典", "来源查询"])
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            self.assertTrue(sheet.findall(".//x:autoFilter", ns))


if __name__ == "__main__":
    unittest.main()
