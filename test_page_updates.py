"""Session freshness and historical-date integration, without upstream traffic."""
from datetime import date, timedelta
from pathlib import Path
import importlib
import re
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
import ais
import portwatch
import port_inventory


class PageUpdates(unittest.TestCase):
    def setUp(self):
        self.latest_port = date(2026, 9, 25)
        self.latest_choke = date(2026, 9, 27)
        self.queries = []
        self.fail_dates = False
        self.patches = [
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
        self.assertFalse(failed.slider)
        self.assertEqual(failed.status[0].state, "error")
        self.assertTrue(any("fixture source unavailable" in w.value for w in failed.warning))


if __name__ == "__main__":
    unittest.main()
