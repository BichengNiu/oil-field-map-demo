"""Source flag metadata survives normalization, repeat collection and display."""
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ais
import ais_history
import dashboard_rows
import data_store
import map_renderer


class VesselFlagsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.environment = patch.dict(os.environ, {
            "MONITORING_DB_PATH": str(Path(self.temporary.name) / "monitoring.duckdb"),
            "MONITORING_READ_ONLY": "false",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.now = datetime.now(timezone.utc)

    def feature(self, flag):
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [53, 26]},
                "properties": {"mmsi": 352001544, "seen": self.now.isoformat(),
                               "source": "test", "flag": flag, "name": "TEST SHIP"}}

    def test_source_country_is_preserved_in_archive_and_export(self):
        vessel = ais.openwaters_feature_to_vessel(self.feature("pa"), received_at=self.now)
        self.assertEqual(vessel["flag"], "PA")
        self.assertEqual(vessel["flag_country"], "巴拿马")
        self.assertEqual(vessel["flag_source"], ais.OPENWATERS_API)
        self.assertEqual(ais_history.archive_reports([vessel]), 1)
        saved = ais_history.latest_snapshot()[0]
        self.assertEqual(saved["flag_country"], "巴拿马")
        self.assertEqual(dashboard_rows.vessel_rows([saved])[0]["船籍"], "巴拿马")

    def test_repeated_observation_enriches_flag_without_adding_a_position(self):
        vessel = ais.openwaters_feature_to_vessel(self.feature(None), received_at=self.now)
        self.assertEqual(ais_history.archive_reports([vessel]), 1)
        previous_revision = data_store.revision("ais")
        updated = ais.openwaters_feature_to_vessel(self.feature("AE"), received_at=self.now)
        self.assertEqual(ais_history.archive_reports([updated]), 0)
        saved = ais_history.latest_snapshot()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["flag"], "AE")
        self.assertGreater(data_store.revision("ais"), previous_revision)
        # A subsequent source report without flag must not erase known metadata.
        self.assertEqual(ais_history.archive_reports([vessel]), 0)
        self.assertEqual(ais_history.latest_snapshot()[0]["flag"], "AE")

    def test_missing_or_invalid_flag_stays_unknown_despite_known_mmsi(self):
        for value in (None, "", "ZZ", "Panama", "<script>"):
            vessel = ais.openwaters_feature_to_vessel(self.feature(value), received_at=self.now)
            self.assertIsNone(vessel["flag"])
            self.assertEqual(dashboard_rows.vessel_rows([vessel])[0]["船籍"], "—")

    def test_map_popup_receives_country_without_changing_ship_category(self):
        vessel = ais.openwaters_feature_to_vessel(self.feature("PA"), received_at=self.now)
        with patch("map_renderer.compressed_document", side_effect=lambda html: html):
            html = map_renderer.build_map_html(
                [], [], [], [vessel], "2026-10-15", "2026-10-15",
                asset_popup=lambda *args: "", port_popup=lambda *args: "",
                chokepoint_popup=lambda *args: "",
            )
        self.assertIn('"unknown", "巴拿马"', html)
        self.assertIn('<span>船籍</span>', html)
        self.assertIn("chineseFlag ? '#dc2626'", html)
        self.assertIn("hasChineseFlag ? '#dc2626'", html)
        self.assertNotIn('#f59e0b',html)

    def test_northern_red_sea_gulfs_are_queried_within_anonymous_limits(self):
        for latitude, longitude in ((29, 33), (29.5, 34.9)):
            self.assertTrue(ais.in_collection_area(latitude, longitude))
            self.assertTrue(any(south <= latitude <= north and west <= longitude <= east
                                for group in ais.openwaters_bbox_groups()
                                for south, north, west, east in group))
        self.assertEqual(len(ais.openwaters_bbox_groups()), 4)
        for group in ais.openwaters_bbox_groups():
            self.assertLessEqual(sum((north - south) * (east - west)
                                     for south, north, west, east in group), 100)


if __name__ == "__main__":
    unittest.main()
