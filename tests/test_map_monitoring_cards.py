"""Exercise the map rendering path without remote data or Streamlit installed."""
import ast
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid
from zoneinfo import ZoneInfo

import monitoring_cards

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
    def test_normal_map_renders_four_cards_before_map(self):
        calls = []
        st = SimpleNamespace(html=lambda html: calls.append(('cards', html)),
                             iframe=lambda html, **kwargs: calls.append(('map', html)),
                             container=lambda **kwargs: nullcontext(),
                             checkbox=lambda *args, **kwargs: calls.append(('checkbox', args[0])) or True,
                             button=lambda *args, **kwargs: None)
        state = SimpleNamespace(live_positions=[], filtered_vessels=[], visible_map_layers=set(),
                                ais_status={}, port_error=None, chokepoint_error=None,
                                archive_error=None, ais_enabled=True, open_state={},
                                unlocated_asset_count=0, unlocated_port_count=0,
                                map_assets=[], map_ports=[], map_chokepoints=[],
                                selected_day=None, selected_chokepoint_day=None, focus_assets=False)
        ns = {'st': st, 'monitoring_cards': monitoring_cards,
              'map_renderer': SimpleNamespace(build_map_html=lambda *args, **kwargs: 'map')}
        ns.update({name: None for name in ('asset_popup', 'port_popup', 'chokepoint_popup', 'vessel_popup', 'refresh_portwatch_data', 'refresh_vessel_data')})
        render = view_function('render_map_panel', ns)
        cards = monitoring_cards.build_cards([], [], [], [], [], None, None)
        render(state, cards)
        self.assertEqual([call[0] for call in calls], ['cards', 'checkbox', 'checkbox', 'checkbox', 'map'])
        self.assertEqual(calls[0][1].count('class="monitoring-card"'), 4)
        for label in ('港口监测', '通道监测', '船只监测', '油田监测'):
            self.assertIn(label, calls[0][1])

    def test_source_failure_still_returns_four_cards(self):
        def fail(*args, **kwargs):
            raise RuntimeError('source unavailable')
        ns = {'st': SimpleNamespace(session_state={}), 'uuid': uuid,
              'PORTWATCH': SimpleNamespace(has_independent_statistics=lambda p: True),
              'report_data': SimpleNamespace(history_window=fail, comparison_history=fail,
                                            card_vessel_history=fail),
              'monitoring_cards': monitoring_cards, 'datetime': datetime,
              'ZoneInfo': ZoneInfo, 'ASSETS': []}
        state = SimpleNamespace(selected_day=datetime(2026, 10, 6).date(),
                                selected_chokepoint_day=datetime(2026, 10, 6).date(), live_positions=[])
        prepare = view_function('prepare_monitoring_cards', ns)
        cards, errors = prepare([{'portid': 'p'}], [{'portid': 'c'}], state)
        self.assertEqual(len(cards), 4)
        self.assertEqual(len(errors), 5)

    def test_map_call_is_outside_print_mode(self):
        tree = ast.parse((ROOT / 'app.py').read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        map_branch = next(node for node in main.body if isinstance(node, ast.If)
                          and ast.unparse(node.test) == 'tab_map.open')
        calls = [node.func.id for node in ast.walk(map_branch) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)]
        self.assertIn('prepare_monitoring_cards', calls)
        self.assertIn('render_map_panel', calls)


if __name__ == '__main__':
    unittest.main()
