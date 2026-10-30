"""Exercise the map rendering path without remote data or Streamlit installed."""
import ast
import os
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tempfile
import uuid
from zoneinfo import ZoneInfo

import monitoring_cards
import portwatch_downloads
import data_store
import report_data

ROOT = Path(__file__).resolve().parents[1]


def view_function(name, namespace):
    tree = ast.parse((ROOT / 'dashboard_views.py').read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    for argument in fn.args.args:
        argument.annotation = None
    fn.returns = None
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(ROOT / 'dashboard_views.py'), 'exec'), namespace)
    return namespace[name]


class MonitoringCardsTest(unittest.TestCase):
    def test_card_html_keeps_requested_values_without_explanation_text(self):
        html = monitoring_cards.cards_html([
            ('港口监测', '580艘次', '已披露进港艘次｜2026-10-19—2026-10-23', '独立统计91个', '日记录覆盖94.5%'),
            ('咽喉点监测', '514艘次', '已披露通过艘次｜2026-10-19—2026-10-25', '独立统计3个'),
            ('油田监测', '92个', '各资产最新披露日产量合计（非同日）', '原油 771.2591 万桶/日',
             '天然气 91.6475 百万立方米/日', '产量数据：1978—2026年',
             '在产比例 33.7%（31/92）', '待确认比例 63.0%（58/92）')])
        for text in ['港口监测', '咽喉点监测', '油田监测', '580艘次', '514艘次', '92个']:
            self.assertIn(text, html)
        for text in ['monitoring-card-detail', '原油', '天然气', '在产比例', '待确认比例',
                     '已披露', '独立统计', '日记录覆盖', '非同日', '产量数据：', '2026-10-19']:
            self.assertNotIn(text, html)

    def test_card_history_uses_selected_nodes_latest_week_without_future_rows(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                'MONITORING_DB_PATH': str(Path(temporary) / 'monitoring.duckdb'),
                'MONITORING_READ_ONLY': 'false'}):
            data_store.save_portwatch('ports', [
                {'portid': 'port105', 'date': '2026-10-09', 'portcalls': 2},
                {'portid': 'port105', 'date': '2026-10-12', 'portcalls': 3},
                {'portid': 'port105', 'date': '2026-10-13', 'portcalls': 4},
                {'portid': 'port106', 'date': '2026-10-23', 'portcalls': 999},
            ], 'test-source')
            # port106's newer week must not move port105's statistics forward;
            # the later port105 observation must not leak into a past cutoff.
            rows = report_data.card_activity_history('ports', ('port105',), '2026-10-12', 987654)
            self.assertEqual([(row['portid'], row['date']) for row in rows],
                             [('port105', '2026-10-12')])

    def test_latest_partial_data_week_is_used_instead_of_previous_week(self):
        anchor = datetime(2026, 10, 7).date()
        week_start = anchor - timedelta(days=anchor.weekday() + 7)
        rows = [
            {"portid": "port105", "date": (week_start + timedelta(days=i)).isoformat(),
             "portcalls": 1}
            for i in range(7)
        ]
        rows.extend(
            {"portid": "port105", "date": (anchor.replace(day=1) + timedelta(days=i)).isoformat(),
             "portcalls": 1}
            for i in range((anchor - anchor.replace(day=1)).days + 1)
        )
        rows.extend(
            {"portid": "port105", "date": f"2025-10-{day:02d}", "portcalls": 1}
            for day in range(1, 7)
        )

        cards = monitoring_cards.build_cards(
            [{"portid": "port105", "statistics_available": True}], [], rows, [], anchor, None,
            vessel_day=anchor,
        )

        self.assertEqual(cards[0][1], "3艘次")
        self.assertIn("2026-10-05—2026-10-07（未满周）", cards[0][2])
        self.assertIn("100.0%（3/3）", cards[0][4])

    def test_missing_daily_records_are_disclosed_instead_of_counted_as_zero(self):
        rows = [{"portid": "p1", "date": "2026-10-19", "n_total": 0},
                {"portid": "p1", "date": "2026-10-20", "n_total": 5},
                {"portid": "p2", "date": "2026-10-20", "n_total": None},
                {"portid": "p1", "date": "2026-10-21", "n_total": 999}]
        card = monitoring_cards.activity_card('咽喉点监测', [{'portid': 'p1'}, {'portid': 'p2'}],
                                               rows, 'n_total', '通过', datetime(2026, 10, 20).date())
        self.assertEqual(card[1], '5艘次')
        self.assertIn('50.0%（2/4）', card[4])

    def test_sunday_closes_the_data_week_and_conflicting_duplicates_are_rejected(self):
        rows = [{"portid": "p", "date": f"2026-10-{day}", "n_total": 1} for day in range(19, 26)]
        card = monitoring_cards.activity_card('咽喉点监测', [{'portid': 'p'}], rows,
                                               'n_total', '通过', datetime(2026, 10, 25).date())
        self.assertEqual(card[1], '7艘次')
        self.assertNotIn('未满周', card[2])
        with self.assertRaisesRegex(ValueError, '数据冲突'):
            monitoring_cards.activity_card('咽喉点监测', [{'portid': 'p'}],
                rows + [{"portid": "p", "date": "2026-10-19", "n_total": 9}],
                'n_total', '通过', datetime(2026, 10, 25).date())

    def test_asset_totals_keep_products_separate_and_status_denominator_deduplicated(self):
        def row(product, value, year):
            return {'商品': product, '日产量（混合单位）': value, '数据时间': year}
        first = {'scope_id': 'a', 'operating_states': ['producing', 'producing'],
                 'production_rows': [row('原油', 1, '2023'), row('天然气', 2, '2025')]}
        assets = [first, first,
                  {'scope_id': 'b', 'operating_states': ['historical_unverified'],
                   'production_rows': [row('原油', None, '2024')]},
                  {'scope_id': 'c', 'operating_states': ['temporarily_suspended'],
                   'production_rows': [row('原油', 0, '2025')]}]
        card = monitoring_cards.asset_card(assets)
        self.assertEqual(card[1], '3个')
        self.assertIn('原油 1 万桶/日', card)
        self.assertIn('天然气 2 百万立方米/日', card)
        self.assertIn('非同日', card[2])
        self.assertIn('2023—2025年；可汇总3/4条', card[5])
        self.assertEqual(card[6], '在产比例 33.3%（1/3）')
        self.assertEqual(card[7], '待确认比例 33.3%（1/3）')

    def test_normal_map_renders_three_cards_before_map(self):
        calls = []
        buttons = []
        st = SimpleNamespace(session_state={}, html=lambda html: calls.append(('cards', html)),
                             iframe=lambda html, **kwargs: calls.append(('map', html)),
                             caption=lambda message: calls.append(('caption', message)),
                             container=lambda **kwargs: nullcontext(),
                             selectbox=lambda *args, **kwargs: None,
                             checkbox=lambda *args, **kwargs: calls.append(('checkbox', args[0])) or True,
                             button=lambda label, *args, **kwargs: buttons.append(label))
        state = SimpleNamespace(live_positions=[], filtered_vessels=[], visible_map_layers=set(),
                                ais_status={}, port_error=None, chokepoint_error=None,
                                archive_error=None, ais_enabled=True, open_state={},
                                unlocated_asset_count=0, unlocated_port_count=0,
                                map_assets=[], map_ports=[], map_chokepoints=[],
                                selected_day=None, selected_chokepoint_day=None, focus_assets=False)
        ns = {'st': st, 'monitoring_cards': monitoring_cards,
              'pipeline_catalog': SimpleNamespace(load=lambda: {"type": "FeatureCollection", "features": []}, load_gas_connections=lambda: {"features": []}, load_unmapped_projects=lambda: []),
              'map_renderer': SimpleNamespace(build_map_html=lambda *args, **kwargs: 'map', search_objects=lambda *args: [])}
        ns.update({name: None for name in ('asset_popup', 'port_popup', 'chokepoint_popup', 'vessel_popup', 'queue_map_screenshot', 'queue_map_focus')})
        render = view_function('render_map_panel', ns)
        cards = monitoring_cards.build_cards([], [], [], [], None, None)
        render(state, cards)
        self.assertEqual([call[0] for call in calls], [
            'cards', 'checkbox', 'checkbox', 'checkbox', 'checkbox', 'checkbox', 'map'])
        self.assertEqual(calls[0][1].count('class="monitoring-card"'), 3)
        self.assertNotIn('海域监测', calls[0][1])
        self.assertNotIn('刷新船舶数据', buttons)
        self.assertNotIn('刷新港口数据', buttons)
        for label in ('港口监测', '咽喉点监测', '油田监测'):
            self.assertIn(label, calls[0][1])

    def test_source_failure_still_returns_three_cards(self):
        def fail(*args, **kwargs):
            raise RuntimeError('source unavailable')
        ns = {'st': SimpleNamespace(session_state={}), 'uuid': uuid,
              'PORTWATCH': SimpleNamespace(has_independent_statistics=lambda p: True),
              'report_data': SimpleNamespace(card_activity_history=fail, card_sea_history=fail),
              'monitoring_cards': monitoring_cards, 'portwatch_downloads': portwatch_downloads,
              'datetime': datetime,
              'ZoneInfo': ZoneInfo, 'ASSETS': []}
        state = SimpleNamespace(selected_day=datetime(2026, 10, 6).date(),
                                selected_chokepoint_day=datetime(2026, 10, 6).date(), live_positions=[], map_assets=[])
        prepare = view_function('prepare_monitoring_cards', ns)
        cards, errors = prepare([{'portid': 'p'}], [{'portid': 'c'}], state)
        self.assertEqual(len(cards), 3)
        self.assertEqual(len(errors), 2)

    def test_expected_history_cache_miss_does_not_render_as_warning(self):
        revisions = []
        def local_rows(*args, **kwargs):
            revisions.append(args[3])
            return []

        ns = {'st': SimpleNamespace(session_state={}), 'uuid': uuid,
              'PORTWATCH': SimpleNamespace(has_independent_statistics=lambda p: True),
              'report_data': SimpleNamespace(card_activity_history=local_rows,
                                            card_sea_history=lambda revision=0: {'rows': [], 'card': None}),
              'monitoring_cards': monitoring_cards, 'portwatch_downloads': portwatch_downloads,
              'datetime': datetime, 'ZoneInfo': ZoneInfo, 'ASSETS': []}
        state = SimpleNamespace(selected_day=datetime(2026, 10, 6).date(),
                                selected_chokepoint_day=datetime(2026, 10, 6).date(),
                                live_positions=[], map_assets=[])

        cards, errors = view_function('prepare_monitoring_cards', ns)(
            [{'portid': 'p'}], [{'portid': 'c'}], state)

        self.assertEqual(len(cards), 3)
        self.assertEqual(errors, [])
        self.assertEqual(revisions, [0, 0])

    def test_map_call_is_outside_print_mode(self):
        tree = ast.parse((ROOT / 'app.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_render_dashboard')
        map_branch = next(node for node in main.body if isinstance(node, ast.If)
                          and ast.unparse(node.test) == 'tab_map.open'
                          and any(isinstance(child, ast.Call)
                                  and isinstance(child.func, ast.Name)
                                  and child.func.id == 'prepare_monitoring_cards'
                                  for child in ast.walk(node)))
        calls = [node.func.id for node in ast.walk(map_branch) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)]
        self.assertIn('prepare_monitoring_cards', calls)
        self.assertIn('render_map_panel', calls)

    def test_print_report_is_always_available_for_streamlit_print(self):
        tree = ast.parse((ROOT / 'app.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_render_dashboard')
        calls = [node.func.id for node in ast.walk(main) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)]
        self.assertIn('render_print_report', calls)
        self.assertNotIn('prepare_report', ast.unparse(main))


if __name__ == '__main__':
    unittest.main()
