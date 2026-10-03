"""Session freshness and latest-only dashboard behavior, without upstream traffic."""
from datetime import date, timedelta
from pathlib import Path
import tempfile
import os
import re
import unittest
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest
import ais
import portwatch
import portwatch_downloads
import port_inventory


class PageUpdates(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.latest_port = date(2026, 9, 25)
        self.latest_choke = date(2026, 9, 27)
        self.include_no_data_port = False
        self.queries = []
        self.fail_dates = False
        self.openwaters_calls = 0
        st.cache_data.clear()
        portwatch.clear_live_cache()
        portwatch.port_risk_capacity.clear()
        self.patches = [
            patch.dict(os.environ, {
                "AIS_ARCHIVE_PATH": str(Path(temp.name) / "ais.sqlite3"),
                "PORTWATCH_DOWNLOAD_CACHE": str(Path(temp.name) / "portwatch.sqlite3"),
                "AISSTREAM_API_KEY": "",
            }),
            patch.object(port_inventory, "enrich", side_effect=self.enrich_fixture),
            patch.object(portwatch, "_query", side_effect=self.query),
            patch.object(ais, "openwaters_snapshot", side_effect=self.openwaters_snapshot),
        ]
        for mocked in self.patches:
            mocked.start()
        self.addCleanup(lambda: [mocked.stop() for mocked in reversed(self.patches)])

    @staticmethod
    def enrich_fixture(rows):
        return [dict(row, port_operating_status_label="当前停复运待核",
                     port_operating_status_as_of="测试观察期",
                     port_status_basis="测试用未核状态", port_status_evidence_url=None)
                for row in rows]

    def query(self, url, **params):
        self.queries.append((url, params))
        if url in (portwatch.DAILY, portwatch.CHOKEPOINT_DAILY) and params.get("where") == "1=1":
            if self.fail_dates:
                raise TimeoutError("fixture source unavailable")
            latest = self.latest_port if url == portwatch.DAILY else self.latest_choke
            return {"features": [{"attributes": {"latest_date": latest.isoformat()}}]}
        if url == portwatch.PORTS:
            rows = [{"portid": "port1", "portname": "Fixture port", "country": "Oman",
                     "lat": 26.5, "lon": 56.4, "statistics_available": True}]
            if self.include_no_data_port:
                rows.append({"portid": "port2", "portname": "No data fixture", "country": "Oman",
                             "lat": 26.7, "lon": 56.5, "statistics_available": True})
                rows.append({"portid": "wpi12345", "portname": "Supplemental fixture",
                             "country": "Oman", "lat": 26.8, "lon": 56.6,
                             "statistics_available": False,
                             "activity_source": "无独立PortWatch统计"})
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
        if params.get("returnCountOnly"):
            return {"count": len(rows)}
        return {"features": [{"attributes": row} for row in rows[offset:offset + 1000]]}

    def openwaters_snapshot(self, **kwargs):
        self.openwaters_calls += 1
        return {"vessels": [], "error": None, "status": "fixture"}

    def page(self):
        app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=15).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return app

    def test_new_session_reuses_shared_cache_and_explicit_refresh_updates_dates(self):
        app = self.page()
        count = len(self.queries)
        app.text_input(key="asset_search").set_value("Rumaila").run()
        self.assertFalse(app.exception)
        self.assertEqual(len(self.queries), count)
        self.latest_port = date(2026, 9, 28)
        second_page = self.page()
        self.assertEqual(len(self.queries), count)
        self.assertTrue(any("刷新 PortWatch 数据" in button.label for button in second_page.button))
        next(button for button in second_page.button
             if button.label == "刷新 PortWatch 数据").click().run()
        self.assertFalse(second_page.exception, [e.message for e in second_page.exception])
        self.assertTrue(any("2026-09-28" in params.get("where", "")
                            for url, params in self.queries if url == portwatch.DAILY))
        self.assertGreater(len(self.queries), count)

    def test_default_map_skips_risk_model_and_ais_until_requested(self):
        app = self.page()
        self.assertEqual(self.openwaters_calls, 0)
        self.assertFalse(any(url == portwatch.SPILLOVERS for url, _ in self.queries))

        app.session_state["main_tabs"] = "港口"
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(any(url == portwatch.SPILLOVERS for url, _ in self.queries))
        app.session_state["main_tabs"] = "船舶"
        app.run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertEqual(self.openwaters_calls, 1)

    def test_reviewed_assets_render_and_shared_country_search_does_not_duplicate(self):
        app = self.page()
        app.multiselect(key="map_layers").set_value(["assets"]).run()
        for name in ("Al Jumd", "Blocks 3&4", "Shadegan", "Bahrain Field (Awali)"):
            app.text_input(key="asset_search").set_value(name).run()
            self.assertFalse(app.exception, [e.message for e in app.exception])
        app.text_input(key="asset_search").set_value("Khafji").run()
        app.multiselect(key="asset_countries").set_value(["沙特阿拉伯"]).run()
        self.assertIn('Khafji', app.get("iframe")[0].proto.srcdoc)
        app.multiselect(key="asset_countries").set_value(["沙特阿拉伯", "科威特"]).run()
        import json
        markers = json.loads(re.search(r'const assets = (.*);', app.get("iframe")[0].proto.srcdoc).group(1))
        self.assertEqual(len(markers), 1)

    def test_map_uses_latest_dates_without_replay_controls(self):
        app = self.page()
        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertNotIn("map_time_mode", app.session_state)
        self.assertNotIn("map_history_day", app.session_state)
        self.assertFalse(any(widget.label == "地图时间" for widget in app.radio))
        self.assertFalse(any(widget.label == "通行时间轴（UTC，按日）" for widget in app.slider))
        self.assertNotIn("港口 2026-09-25 UTC · 咽喉点 2026-09-27 UTC", iframe)
        self.assertNotIn("map-date", iframe)

    def test_selected_chokepoint_is_sent_to_map_and_gets_a_fresh_viewport(self):
        app = self.page()
        app.multiselect(key="map_layers").set_value(["chokepoints"]).run()
        app.multiselect(key="chokepoint_ids").set_value(["chokepoint6"]).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])

        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertIn('const visibleLayers = ["chokepoints"]', iframe)
        self.assertIn('"lat": 26.5, "lon": 56.4', iframe)
        self.assertIn("saved.signature === viewSignature", iframe)

    def test_port_summary_uses_fixed_seven_day_window_without_source_date_controls(self):
        portwatch.rolling_activity.clear()
        app = self.page()
        self.assertFalse(any(widget.label == "日均窗口" for widget in app.radio))
        self.assertFalse(any("源站最新：" in item.value for item in app.caption))
        self.assertFalse(any("咽喉点最新：" in item.value for item in app.caption))
        rolling_queries = [
            params.get("where", "") for url, params in self.queries
            if url == portwatch.DAILY
        ]
        self.assertTrue(any(
            "date >= DATE '2026-09-12' AND date <= DATE '2026-09-25'" in where
            for where in rolling_queries
        ), rolling_queries)

    def test_explicit_select_all_and_independent_location_filters(self):
        app = self.page()
        app.session_state["main_tabs"] = "数据下载"
        app.run()
        self.assertNotIn("monitor_regions", app.session_state)
        self.assertFalse(any(widget.label == "航运水域" for widget in app.multiselect))
        self.assertIn("港口筛选", [item.label for item in app.expander])
        self.assertIn("咽喉点筛选", [item.label for item in app.expander])

        for key in ("port_countries", "port_ids", "chokepoint_ids",
                    "ais_categories", "asset_countries", "asset_levels",
                    "asset_statuses", "asset_types", "asset_metrics",
                    "pw_download_kinds"):
            self.assertEqual(app.multiselect(key=key).value, ["全选"])

        countries = app.multiselect(key="asset_countries")
        one_country = countries.options[1]
        countries.set_value([one_country]).run()
        self.assertEqual(app.multiselect(key="asset_countries").value, [one_country])
        app.multiselect(key="asset_countries").set_value(
            [one_country, "全选"]).run()
        self.assertEqual(app.multiselect(key="asset_countries").value, ["全选"])
        app.multiselect(key="asset_countries").set_value(
            ["全选", one_country]).run()
        self.assertEqual(app.multiselect(key="asset_countries").value, [one_country])
        app.multiselect(key="asset_countries").set_value([]).run()
        self.assertEqual(app.multiselect(key="asset_countries").value, [])

        app.multiselect(key="chokepoint_ids").set_value([]).run()
        self.assertEqual(app.multiselect(key="port_countries").value, ["全选"])
        self.assertEqual(app.multiselect(key="port_ids").value, ["全选"])
        self.assertTrue(any(widget.label == "显示 AIS 实时船位" for widget in app.toggle))

    def test_latest_data_checkbox_filters_map_markers_only(self):
        self.include_no_data_port = True
        app = self.page()
        self.assertFalse(app.checkbox(key="ports_latest_data_only").value)
        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertIn("No data fixture", iframe)

        app.checkbox(key="ports_latest_data_only").set_value(True).run()
        iframe = app.get("iframe")[0].proto.srcdoc
        self.assertIn("Fixture port", iframe)
        self.assertNotIn("No data fixture", iframe)

    def test_source_failure_is_visible_without_replay_controls(self):
        self.fail_dates = True
        failed = self.page()
        self.assertFalse(failed.exception)
        self.assertFalse(failed.status)
        self.assertTrue(any("fixture source unavailable" in w.value for w in failed.warning))
        self.assertNotIn("map_time_mode", failed.session_state)
        self.assertNotIn("map_history_day", failed.session_state)

    def test_history_replay_and_import_controls_are_removed(self):
        app = self.page()
        self.assertNotIn("map_time_mode", app.session_state)
        self.assertNotIn("map_history_day", app.session_state)
        self.assertNotIn("ais_history_upload", app.session_state)
        self.assertNotIn("public_ais_history", app.session_state)
        self.assertFalse(any(button.key == "public_ais_history" for button in app.button))

    def test_port_shortcut_opens_full_history_download_and_map_hides_removed_elements(self):
        app = self.page()
        self.assertNotIn("download_chokepoint_history", app.session_state)
        self.assertNotIn("source_check_utc", app.session_state)
        self.assertFalse(any("最新模式：" in item.value or "最近向源站检查：" in item.value
                             for item in app.caption))
        app.session_state["main_tabs"] = "港口"
        app.run()
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
        class OpenTab:
            open = True

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch.object(st, "tabs", return_value=[OpenTab() for _ in range(6)]), \
             patch.object(portwatch_downloads, "collect", return_value=result) as collect:
            app = self.page()
            app.button(key="pw_download_generate").click().run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        self.assertTrue(app.success)
        self.assertEqual(collect.call_args.args[1], "latest")
        self.assertEqual(collect.call_args.kwargs["first"], None)

    def test_print_history_is_opt_in_and_uses_only_independent_statistics_points(self):
        self.include_no_data_port = True
        app = self.page()
        self.assertFalse(app.toggle(key="print_mode").value)
        self.assertFalse(any(params.get("returnCountOnly") for _, params in self.queries))

        app.toggle(key="print_mode").set_value(True).run()
        self.assertFalse(app.exception, [e.message for e in app.exception])
        report_counts = [params for url, params in self.queries
                         if url in (portwatch.DAILY, portwatch.CHOKEPOINT_DAILY)
                         and params.get("returnCountOnly")]
        self.assertEqual(len(report_counts), 4)
        self.assertIn("'port1'", report_counts[0]["where"])
        self.assertNotIn("wpi12345", report_counts[0]["where"])
        self.assertTrue(any(item.label == "打印模式" for item in app.toggle))
        self.assertTrue(any(item.label == "下载可打印报告（HTML）" for item in app.get("download_button")))


if __name__ == "__main__":
    unittest.main()
