from datetime import datetime, timedelta, timezone
import json
import unittest

import ais


NOW = datetime(2026, 9, 29, 8, 0, tzinfo=timezone.utc)


def position_event(mmsi=636000111, lat=26.55, lon=56.35, sog=12.4, cog=88.0,
                   ship_name=" TEST TANKER @"):
    return {
        "MessageType": "PositionReport",
        "MetaData": {"MMSI": mmsi, "ShipName": ship_name, "Latitude": lat,
                     "Longitude": lon},
        "Message": {"PositionReport": {
            "UserID": mmsi, "Valid": True, "Sog": sog, "Cog": cog,
            "TrueHeading": 511, "NavigationalStatus": 0,
        }},
    }


def static_event(mmsi=636000111, ship_type=80):
    return {
        "MessageType": "ShipStaticData",
        "MetaData": {"MMSI": mmsi},
        "Message": {"ShipStaticData": {
            "UserID": mmsi, "Name": "TEST TANKER", "Type": ship_type,
            "ImoNumber": 9876543, "CallSign": "D5AA1", "Destination": "FUJAIRAH",
            "MaximumStaticDraught": 12.3,
        }},
    }


def class_b_static_event(part, mmsi=636000222):
    return {
        "MessageType": "StaticDataReport",
        "MetaData": {"MMSI": mmsi},
        "Message": {"StaticDataReport": {
            "UserID": mmsi, "PartNumber": part == "B",
            "ReportA": {"Valid": part == "A", "Name": "CLASS B CARGO"},
            "ReportB": {"Valid": part == "B", "ShipType": 70,
                        "CallSign": "9V1234"},
        }},
    }


class AISParsingTests(unittest.TestCase):
    def test_subscription_is_scoped_and_complete(self):
        request = ais.subscription("secret")
        self.assertEqual(len(request["BoundingBoxes"]), 5)
        self.assertEqual(request["APIKey"], "secret")
        self.assertIn("PositionReport", request["FilterMessageTypes"])
        self.assertIn("ShipStaticData", request["FilterMessageTypes"])

    def test_collector_sends_subscription_and_decodes_binary_frame(self):
        sent = []
        collector = None
        frames = [
            json.dumps({
                "MessageType": "SubscriptionConfirmation",
                "Message": {"CompressionEnabled": True},
            }),
            json.dumps(position_event()).encode("utf-8"),
        ]

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def send(self, message):
                sent.append(json.loads(message))

            def recv(self, timeout):
                frame = frames.pop(0)
                if not frames:
                    collector._stop.set()
                return frame

        def connector(*args, **kwargs):
            self.assertEqual(args[0], ais.STREAM_URL)
            self.assertEqual(kwargs["compression"], "deflate")
            return FakeSocket()

        collector = ais.AISCollector("server-only-key", connector=connector)
        collector._run()
        self.assertEqual(sent[0]["APIKey"], "server-only-key")
        self.assertEqual(collector.status()["tracked_vessels"], 1)
        self.assertTrue(collector.status()["compression_enabled"])
        self.assertEqual(collector.status()["raw_event_count"], 1)
        self.assertEqual(collector.status()["position_message_count"], 1)

    def test_collector_distinguishes_rejected_events_from_missing_events(self):
        collector = ais.AISCollector("unused", connector=lambda *a, **k: None)
        self.assertFalse(collector.ingest(position_event(lat=91), NOW))
        self.assertTrue(collector.ingest(position_event(), NOW))

        state = collector.status()
        self.assertEqual(state["raw_event_count"], 2)
        self.assertEqual(state["rejected_event_count"], 1)
        self.assertEqual(state["message_count"], 1)
        self.assertEqual(state["position_message_count"], 1)
        self.assertEqual(state["last_raw_message_type"], "PositionReport")
        self.assertEqual(state["last_rejection_reason"], "经纬度缺失或无效")

    def test_position_normalization(self):
        row = ais.normalize_event(position_event(), NOW)
        self.assertIsNotNone(row)
        self.assertEqual(row["mmsi"], "636000111")
        self.assertEqual(row["name"], "TEST TANKER")
        self.assertEqual(row["region"], "霍尔木兹海峡")
        self.assertEqual(row["course"], 88.0)
        self.assertEqual(row["navigation_status"], "机动航行")

    def test_invalid_coordinates_are_not_plotted(self):
        self.assertIsNone(ais.normalize_event(position_event(lat=91), NOW))

    def test_static_and_position_join(self):
        collector = ais.AISCollector("unused", connector=lambda *a, **k: None)
        self.assertTrue(collector.ingest(static_event(), NOW - timedelta(seconds=5)))
        self.assertTrue(collector.ingest(position_event(), NOW))
        original_clock = ais.utc_now
        ais.utc_now = lambda: NOW
        try:
            rows = collector.snapshot(max_age_minutes=30)
        finally:
            ais.utc_now = original_clock
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "tanker")
        self.assertEqual(rows[0]["category_label"], "油轮/液货船")
        self.assertEqual(rows[0]["imo"], 9876543)
        self.assertTrue(rows[0]["moving"])

    def test_class_b_static_parts_join_without_overwriting_type(self):
        collector = ais.AISCollector("unused", connector=lambda *a, **k: None)
        # Receive type first and name second: the name-only part must not reset
        # the already-known cargo classification to unknown.
        collector.ingest(class_b_static_event("B"), NOW - timedelta(seconds=10))
        collector.ingest(class_b_static_event("A"), NOW - timedelta(seconds=5))
        collector.ingest(position_event(mmsi=636000222, ship_name=None), NOW)
        original_clock = ais.utc_now
        ais.utc_now = lambda: NOW
        try:
            rows = collector.snapshot(max_age_minutes=30)
        finally:
            ais.utc_now = original_clock
        self.assertEqual(rows[0]["name"], "CLASS B CARGO")
        self.assertEqual(rows[0]["call_sign"], "9V1234")
        self.assertEqual(rows[0]["category"], "cargo")

    def test_stale_positions_expire_without_becoming_zero(self):
        collector = ais.AISCollector("unused", connector=lambda *a, **k: None)
        collector.ingest(position_event(), NOW - timedelta(minutes=31))
        original_clock = ais.utc_now
        ais.utc_now = lambda: NOW
        try:
            rows = collector.snapshot(max_age_minutes=30)
        finally:
            ais.utc_now = original_clock
        self.assertEqual(rows, [])
        self.assertEqual(collector.status()["tracked_vessels"], 0)

    def test_ais_type_groups(self):
        self.assertEqual(ais.classify_ship_type(80)[0], "tanker")
        self.assertEqual(ais.classify_ship_type(70)[0], "cargo")
        self.assertEqual(ais.classify_ship_type(60)[0], "passenger")
        self.assertEqual(ais.classify_ship_type(None)[0], "unknown")


if __name__ == "__main__":
    unittest.main()
