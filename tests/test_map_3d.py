"""The optional 3D view shares snapshot data and safely transports labels."""
import unittest
from unittest.mock import patch
import map_renderer


class ThreeDimensionalMapTest(unittest.TestCase):
    def build(self, **kwargs):
        return map_renderer.build_map_html(
            [], [{'portid':'p1','name':'</script><script>alert(1)</script>',
                  'lat':25,'lon':55}], [], [], '2026-10-09','2026-10-11',
            asset_popup=lambda *_:'',port_popup=lambda *_:'港口详情',
            chokepoint_popup=lambda *_:'',**kwargs)

    def test_3d_shares_selected_data_and_escapes_script_boundaries(self):
        with patch('map_3d.compressed_document',side_effect=lambda s:s):
            html = self.build(three_dimensional=True,
                              snapshot_day='2026-10-09',
                              focus_request={'key':'port:p1','revision':2})
        self.assertIn('cesium@1.124.0',html)
        self.assertIn('"popupKey":"port:p1"',html)
        self.assertIn('"focus":{"key":"port:p1","revision":2}',html)
        self.assertIn('历史观测日：2026-10-09',html)
        self.assertNotIn('</script><script>alert(1)',html)
        self.assertIn('\\u003c/script>',html)
        self.assertNotIn('leaflet.js',html)

    def test_default_2d_does_not_load_cesium_or_transport_credentials(self):
        with patch('map_renderer.compressed_document',side_effect=lambda s:s):
            html = self.build(google_maps_key='must-not-be-sent-in-2d')
        self.assertNotIn('cesium@',html)
        self.assertNotIn('must-not-be-sent-in-2d',html)


if __name__ == '__main__':
    unittest.main()
