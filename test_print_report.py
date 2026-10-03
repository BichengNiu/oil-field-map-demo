"""Unit tests for the self-contained print report renderer."""

from datetime import datetime, timedelta
import unittest
from zoneinfo import ZoneInfo

import print_report


class PrintReportTests(unittest.TestCase):
    def make_report(self, **overrides):
        arguments = {
            "scope_label": "全项目",
            "generated_at": datetime(2026, 10, 2, 10, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            "port_catalog": [
                {"portid": "port-1", "name": "测试港", "country": "测试国",
                 "lat": 24.0, "lon": 55.0, "statistics_available": True},
            ],
            "choke_catalog": [
                {"portid": "choke-1", "name_cn": "测试咽喉点",
                 "lat": 26.0, "lon": 56.0},
            ],
            "latest_ports": [
                {"portid": "port-1", "name": "测试港", "country": "测试国",
                 "date": "2026-09-25", "portcalls": None, "import": None, "export": None},
            ],
            "latest_chokes": [
                {"portid": "choke-1", "date": "2026-10-01", "n_total": 12},
            ],
            "port_history": [],
            "choke_history": [],
            "assets": [],
            "asset_table": [],
            "vessels": [],
            "regions": {"霍尔木兹": (22.0, 28.0, 54.0, 60.0)},
            "port_day": "2026-09-25",
            "choke_day": "2026-10-01",
            "ais_status": "等待数据",
            "ais_source_note": "暂无船位",
        }
        arguments.update(overrides)
        return print_report.build_report_html(**arguments)

    def test_report_keeps_source_dates_distinct_and_missing_values_blank(self):
        html = self.make_report()

        self.assertIn("中东能源与战略通道运输监测", html)
        self.assertIn("2026-09-25", html)
        self.assertIn("2026-10-01", html)
        self.assertIn("—", html)
        self.assertNotIn("2026-09-25", html.split("PortWatch 咽喉点", 1)[1].split("</tr>", 1)[0])
        self.assertIn("@media print", print_report.PRINT_CSS)
        self.assertIn("@page { size:A4 portrait", print_report.PRINT_CSS)

    def test_standalone_report_is_visible_and_has_a_direct_print_action(self):
        document = print_report.build_standalone_document(self.make_report())

        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertIn(".print-report { display: block;", document)
        self.assertIn("window.print()", document)
        self.assertIn("中东能源与战略通道运输监测", document)

    def test_cover_has_the_requested_attribution_month_and_map(self):
        html = self.make_report(vessels=[{
            "name": "测试船", "lat": 25.0, "lon": 55.0,
        }])

        self.assertIn("生成时间：2026年10月", html)
        self.assertNotIn("2026-10-02 10:30", html)
        self.assertIn('<p class="report-sponsor">中国驻阿联酋大使馆、国家发改委国家信息中心</p>', html)
        self.assertNotIn("<strong>中国驻阿联酋大使馆", html)
        self.assertNotIn("<h2>监测概览</h2>", html)
        self.assertIn('<section class="report-cover report-overview">', html)
        self.assertLess(html.index('<div class="map-frame">'), html.index('<div class="metric-grid">'))
        self.assertIn('aria-label="监测水域与节点空间分布示意"', html)
        self.assertIn('fill="#14866d" fill-opacity=".65"', html)
        self.assertIn('[data-testid="stTabs"] { display:none!important; }', print_report.PRINT_CSS)

    def test_asset_text_is_html_escaped(self):
        html = self.make_report(asset_table=[{
            "中文名称": "<script>alert(1)</script>",
            "国家": "测试国",
            "生产状态": "生产中",
            "本层级日产量": "—",
            "其他日量指标": "—",
            "指标口径": "未披露",
            "数据日期": "—",
            "地图坐标精度": "公开坐标",
        }])

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_supplemental_map_ports_are_not_counted_as_independent_statistics(self):
        html = self.make_report(port_catalog=[
            {"portid": "port-1", "name": "统计港", "statistics_available": True},
            {"portid": "wpi-1", "name": "补充港"},
            {"portid": "wpi-2", "name": "另一补充港", "statistics_available": False},
        ])

        self.assertIn("其中独立统计点 1 个", html)

    def test_chokepoint_comparison_uses_complete_seven_day_windows(self):
        first_day = datetime(2026, 9, 24).date()
        history = []
        for offset in range(14):
            day = first_day + timedelta(days=offset)
            history.append({
                "portid": "choke-1",
                "date": day.isoformat(),
                "n_total": 10 if offset < 7 else 20,
                "capacity": 100,
            })

        html = self.make_report(
            choke_history=history,
            choke_day=history[-1]["date"],
        )

        self.assertIn("+100.0%", html)
        self.assertIn("前7日均值", html)


if __name__ == "__main__":
    unittest.main()
