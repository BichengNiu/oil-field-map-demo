"""Session freshness and historical-date integration, without upstream traffic."""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os
import json
import importlib
import re
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import ais
import ais_history
import public_ais_archive
import portwatch
import portwatch_downloads
import port_inventory


class PageUpdates(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.latest_port = date(2026, 9, 25)
        self.latest_choke = date(2026, 9, 27)
        self.queries = []
        self.fail_dates = False
        self.patches = [
            patch.dict(os.environ, {"AIS_ARCHIVE_PATH": str(Path(temp.name) / "ais.sqlite3")}),
            patch.object(ais_history, "_fetch_track", return_value=([], False)),
            patch.object(importlib, "reload", side_effect=lambda module: module),
            patch.object(port_inventory, "enrich", side_effect=lambda rows: rows),
            patch.object(portwatch, "_query", side_effect=self.query),
            patch.object(ais, "openwaters_snapshot", return_value={
                "vessels": [], "error": None, "status": "fixture"}),
        ]
        for mocked in self.patches:
            mocked.start()
        self.addCleanup(lambda: [mocked.stop() for mocked in reversed(self.patches)])

    def query(self, url, **params):
        self.queries.append((url, params))
        if url in (portwatch.DAILY, portwatch.CHOKEPOINT_DAILY) and params.get("where") == "1=1":
            if self.fail_dates:
                raise TimeoutError("fixture source unavailable")
            latest = self.latest_port if url == portwatch.DAILY else self.latest_choke
            return {"features": [{"attributes": {"latest_date": latest.isoformat()}}]}
        if url == portwatch.PORTS:
            rows = [{"portid": "port1", "portname": "Fixture port", "country": "Oman",
                     "lat": 26.5, "lon": 56.4}]
        elif url == portwatch.CHOKEPOINTS:
            rows = [{"portid": "chokepoint6", "portname": "Hormuz", "fullname": "Strait of Hormuz",
                     "lat": 26.5, "lon": 56.4}]
        elif url == portwatch.SPILLOVERS:
            rows = [{"from_portid": "port1", "risk_capacity": 1000}]
        else:
            requested = re.findall(r"DATE '([\d-]+)'", params["where"])
            first, last = date.fromisoformat(requested[0]), date.fromisoformat(requested[-1])
            rows = []
            day = first
            while day <= last:
                if url == portwatch.DAILY and day <= self.latest_port:
                    row = {"date": day.isoformat(), "portid": "port1", "portcalls": day.day,
                           "portname": "Fixture port", "country": "Oman", "import": 1000, "export": 1000}
                    for kind in (*portwatch.SHIP_TYPES, "cargo"):
                        row.update({f"portcalls_{kind}": 1, f"import_{kind}": 1000, f"export_{kind}": 1000})
                    rows.append(row)
                elif url == portwatch.CHOKEPOINT_DAILY and day <= self.latest_choke:
                    rows.append({"date": day.isoformat(), "portid": "chokepoint6",
                                 "portname": "Hormuz", "n_total": day.day * 10, "capacity": 10000})
                day += timedelta(days=1)
        offset = params.get("resultOffset", 0)
        return {"features": [{"attributes": row} for row in rows[offset:offset + 1000]]}

    def page(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=15).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_new_session_rechecks_warm_source_cache_and_filters_reuse_it(self):
        app = self.page()
        count = len(self.queries)
        app.text_input(key="asset_search").set_value("Rumaila").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.queries), count)
        self.latest_port = date(2026, 9, 28)
        second_page = self.page()
        self.assertEqual(second_page.slider(key="map_history_day").value, self.latest_port)
        self.assertGreater(len(self.queries), count)

    def test_drag_queries_same_historical_day_and_latest_returns_independent_dates(self):
        app = self.page()
        app.multiselect(key="map_layers").set_value(["ports", "chokepoints", "vessels"]).run()
        app.slider(key="map_history_day").set_value(date(2026, 9, 24)).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.radio(key="map_time_mode").value, "历史回看")
        self.assertTrue(any(m.label == "霍尔木兹海峡" and m.value == "240 艘" for m in app.metric))
        self.assertEqual(app.dataframe[0].value.iloc[0]["日期 UTC"], "2026-09-24")
        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertIn("const vessels = [];", iframe)
        self.assertIn("港口 2026-09-24 UTC · 咽喉点 2026-09-24 UTC", iframe)
        app.radio(key="map_time_mode").set_value("最新").run()
        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertIn("港口 2026-09-25 UTC · 咽喉点 2026-09-27 UTC", iframe)

    def test_missing_port_day_remains_unknown_and_source_failure_is_visible(self):
        app = self.page()
        app.slider(key="map_history_day").set_value(date(2026, 9, 26)).run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.dataframe[0].value.iloc[0]["当日有效进港 艘次"])
        self.assertIn("无日度记录", app.get("iframe")[0].proto.srcdoc)
        self.fail_dates = True
        failed = self.page()
        self.assertFalse(failed.exception)
        self.assertTrue(failed.slider)
        self.assertEqual(failed.status[0].state, "error")
        self.assertTrue(any("fixture source unavailable" in w.value for w in failed.warning))

    def test_historical_map_table_and_export_use_same_day_not_current_positions(self):
        def report(day, lat):
            return {"mmsi": "123456789", "received_at": f"2026-09-{day:02d}T12:00:00Z",
                    "lat": lat, "lon": 56.4, "source": "dated-test-fixture", "sog": 2}
        ais_history.archive_reports([report(23, 26.1), report(24, 26.2), report(25, 26.3)])
        app = self.page()
        app.multiselect(key="map_layers").set_value(["ports", "chokepoints", "vessels"]).run()
        app.slider(key="map_history_day").set_value(date(2026, 9, 24)).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        iframe = app.get("iframe")[0].proto.srcdoc
        vessels = json.loads(re.search(r"const vessels = (.*?);", iframe).group(1))
        self.assertEqual([v["lat"] for v in vessels], [26.2])
        self.assertIn("船位 2026-09-24 UTC", iframe)
        table = next(df.value for df in app.dataframe if "MMSI" in df.value.columns)
        self.assertEqual(table.iloc[0]["历史日期 UTC"], "2026-09-24")
        self.assertTrue(table["AIS报告时间 UTC"].str.startswith("2026-09-24").all())
        app.slider(key="map_history_day").set_value(date(2026, 9, 22)).run()
        self.assertIn("const vessels = [];", app.get("iframe")[0].proto.srcdoc)
        self.assertTrue(any("历史船位不可用" in item.value for item in app.info))

    def test_public_sample_button_selects_date_enables_layer_and_discloses_coverage(self):
        ais_history.archive_reports([{
            "mmsi": "123456789", "received_at": "2026-03-16T23:59:59Z",
            "provider_received_at": "2026-03-17T00:00:05Z",
            "lat": 26.2, "lon": 56.4, "source": "synthetic-test-fixture"}])
        with patch.object(public_ais_archive, "ensure_public_archive",
                          return_value={"coverage": "fixture coverage, not actual AIS"}):
            app = self.page()
            app.button(key="public_ais_history").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.slider(key="map_history_day").value, date(2026, 3, 16))
        self.assertEqual(app.radio(key="map_time_mode").value, "历史回看")
        self.assertIn("vessels", app.multiselect(key="map_layers").value)
        self.assertEqual(set(app.multiselect(key="monitor_regions").value), {"波斯湾", "霍尔木兹海峡", "阿曼湾"})
        table = next(df.value for df in app.dataframe if "MMSI" in df.value.columns)
        self.assertEqual(table.iloc[0]["历史日期 UTC"], "2026-03-16")
        self.assertEqual(table.iloc[0]["采集器接收时间 UTC"], "2026-03-17T00:00:05Z")
        self.assertTrue(any("fixture coverage" in item.value for item in app.caption))

    def test_port_shortcut_opens_full_history_download_and_map_hides_removed_elements(self):
        app = self.page()
        self.assertNotIn("download_chokepoint_history", app.session_state)
        self.assertNotIn("source_check_utc", app.session_state)
        self.assertFalse(any("最新模式：" in item.value or "最近向源站检查：" in item.value
                             for item in app.caption))
        app.button(key="download_port_history").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(app.session_state["main_tabs"], "数据下载")
        self.assertEqual(app.radio(key="pw_download_mode").value, "全部可用历史")
        self.assertEqual(app.multiselect(key="pw_download_kinds").value, ["ports"])
        self.assertEqual(app.multiselect(key="pw_download_nodes").value, [("ports", "port1")])

    def test_download_page_passes_normalized_mode_to_source_collector(self):
        manifest = {"schema_version": 1, "source": "IMF PortWatch / UN Global Platform",
            "source_url": portwatch.SOURCE, "generated_at_utc": "2026-10-01T00:00:00+00:00",
            "timezone": "UTC", "mode": "latest", "requested_start_utc": None,
            "requested_end_utc": None, "derived": False, "node_count": 2,
            "row_counts": {"ports": 0, "chokepoints": 0}, "fetch_complete": True,
            "coverage": [], "queries": [], "notes": []}
        result = {"datasets": {"ports": [], "chokepoints": []}, "catalog": [],
                  "coverage": [], "dictionary": [], "manifest": manifest}
        with patch.object(portwatch_downloads, "collect", return_value=result) as collect:
            app = self.page()
            app.button(key="pw_download_generate").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(app.success)
        self.assertEqual(collect.call_args.args[1], "latest")
        self.assertEqual(collect.call_args.kwargs["first"], None)


if __name__ == "__main__":
    unittest.main()
