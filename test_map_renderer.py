"""Map presentation tests without a Streamlit runtime or browser."""
import unittest

import map_renderer


class MapRendererTests(unittest.TestCase):
    def test_visible_layers_and_popup_callbacks_are_applied(self):
        html = map_renderer.build_map_html(
            [],
            [{"lat": 25, "lon": 55, "name": "测试港", "portcalls": 3}],
            [], [], "2026-09-25", "2026-09-27",
            visible_layers={"ports"},
            asset_popup=lambda _: "asset popup",
            port_popup=lambda row, day: f"{row['name']} {day}",
            chokepoint_popup=lambda *_: "choke popup",
            vessel_popup=lambda _: "vessel popup",
        )

        self.assertIn("测试港 2026-09-25", html)
        self.assertIn("保存地图 PNG", html)
        self.assertNotIn("船舶：三角形", html)
        self.assertNotIn("油气：菱形", html)


if __name__ == "__main__":
    unittest.main()
