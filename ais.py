"""Server-side AISStream collector and normalized vessel snapshots.

The collector intentionally keeps the API key and raw WebSocket connection on the
server.  The Streamlit/Leaflet client only receives a bounded latest-position
snapshot with no credentials.
"""

from __future__ import annotations

import json
import random
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from websockets.sync.client import connect as websocket_connect
except ImportError:  # The rest of the application must still work without AIS.
    websocket_connect = None


SOURCE = "https://aisstream.io/documentation"
STREAM_URL = "wss://stream.aisstream.io/v0/stream"
MODULE_VERSION = 2

# south, north, west, east.  Keep aligned with portwatch.REGIONS.
REGIONS = {
    "霍尔木兹海峡": (25.7, 27.4, 55.9, 57.5),
    "阿曼湾": (22.0, 26.6, 56.0, 61.8),
    "波斯湾": (23.5, 30.9, 47.0, 56.8),
    "苏伊士运河": (29.4, 31.6, 31.7, 33.5),
    "曼德海峡": (11.0, 15.4, 42.0, 45.7),
}

POSITION_MESSAGE_TYPES = (
    "PositionReport",
    "StandardClassBPositionReport",
    "ExtendedClassBPositionReport",
    "LongRangeAisBroadcastMessage",
)
STATIC_MESSAGE_TYPES = ("ShipStaticData", "StaticDataReport")
FILTER_MESSAGE_TYPES = (*POSITION_MESSAGE_TYPES, *STATIC_MESSAGE_TYPES)

VESSEL_TYPE_LABELS = {
    "tanker": "油轮/液货船",
    "cargo": "货船",
    "passenger": "客船",
    "fishing": "渔船",
    "tug": "拖轮/作业船",
    "pleasure": "帆船/游艇",
    "other": "其他船舶",
    "unknown": "船型待识别",
}

NAVIGATION_STATUS_LABELS = {
    0: "机动航行",
    1: "锚泊",
    2: "失控",
    3: "操纵能力受限",
    4: "受吃水限制",
    5: "系泊",
    6: "搁浅",
    7: "从事捕鱼",
    8: "帆船航行",
    14: "AIS-SART活动",
    15: "未定义",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def region_for(lat: float, lon: float) -> str | None:
    for name, (south, north, west, east) in REGIONS.items():
        if south <= lat <= north and west <= lon <= east:
            return name
    return None


def subscription(api_key: str) -> dict[str, Any]:
    """Build the complete AISStream subscription sent immediately after connect."""

    return {
        "APIKey": api_key,
        "BoundingBoxes": [
            [[north, west], [south, east]]
            for south, north, west, east in REGIONS.values()
        ],
        "FilterMessageTypes": list(FILTER_MESSAGE_TYPES),
    }


def classify_ship_type(ship_type: int | None) -> tuple[str, str]:
    """Map the base AIS ship-type code to a deliberately broad category."""

    if ship_type is None:
        category = "unknown"
    elif 80 <= ship_type <= 89:
        category = "tanker"
    elif 70 <= ship_type <= 79:
        category = "cargo"
    elif 60 <= ship_type <= 69:
        category = "passenger"
    elif ship_type == 30:
        category = "fishing"
    elif ship_type in {31, 32, 50, 51, 52, 53, 54, 55, 58}:
        category = "tug"
    elif ship_type in {36, 37}:
        category = "pleasure"
    elif 1 <= ship_type <= 99:
        category = "other"
    else:
        category = "unknown"
    return category, VESSEL_TYPE_LABELS[category]


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).replace("@", "").strip()
    return text or None


def _valid_coordinate(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180


def normalize_event(event: dict[str, Any], received_at: datetime | None = None) -> dict[str, Any] | None:
    """Normalize one AISStream event into a position or static-data update."""

    message_type = event.get("MessageType")
    if message_type not in FILTER_MESSAGE_TYPES:
        return None
    metadata = event.get("MetaData") or {}
    message = event.get("Message") or {}
    payload = message.get(message_type) or {}
    mmsi_value = metadata.get("MMSI", payload.get("UserID"))
    mmsi_int = _integer(mmsi_value)
    if mmsi_int is None or not 100000000 <= mmsi_int <= 999999999:
        return None
    received = received_at or utc_now()
    base: dict[str, Any] = {
        "mmsi": str(mmsi_int),
        "received_at": received.isoformat(),
        "message_type": message_type,
    }

    if message_type in POSITION_MESSAGE_TYPES:
        lat = _number(metadata.get("Latitude", payload.get("Latitude")))
        lon = _number(metadata.get("Longitude", payload.get("Longitude")))
        if not _valid_coordinate(lat, lon):
            return None
        assert lat is not None and lon is not None
        sog = _number(payload.get("Sog"))
        cog = _number(payload.get("Cog"))
        heading = _number(payload.get("TrueHeading"))
        # AIS sentinels: SOG 102.3, COG 3600/360, heading 511.
        if sog is not None and not 0 <= sog < 102.3:
            sog = None
        if cog is not None and not 0 <= cog < 360:
            cog = None
        if heading is not None and not 0 <= heading < 360:
            heading = None
        nav_code = _integer(payload.get("NavigationalStatus"))
        base.update({
            "kind": "position",
            "name": _clean_text(metadata.get("ShipName")),
            "lat": lat,
            "lon": lon,
            "region": region_for(lat, lon),
            "sog": sog,
            "cog": cog,
            "heading": heading,
            "course": heading if heading is not None else cog,
            "navigation_status_code": nav_code,
            "navigation_status": NAVIGATION_STATUS_LABELS.get(nav_code, "未报告"),
        })
        # Extended Class B reports can carry the base ship-type code directly.
        ship_type = _integer(payload.get("Type", payload.get("ShipType")))
        if ship_type is not None:
            category, label = classify_ship_type(ship_type)
            base.update({"ship_type_code": ship_type, "category": category,
                         "category_label": label})
        return base

    # Message 24 (Class B static data) arrives as independent ReportA/name and
    # ReportB/type + call-sign parts.  Keep absent fields as None so one part
    # cannot overwrite useful data already received from the other part.
    report_a = payload.get("ReportA") or {}
    report_b = payload.get("ReportB") or {}
    if not report_a.get("Valid", True):
        report_a = {}
    if not report_b.get("Valid", True):
        report_b = {}
    ship_type = _integer(payload.get(
        "Type", payload.get("ShipType", report_b.get("ShipType"))))
    category, label = classify_ship_type(ship_type)
    base.update({
        "kind": "static",
        "name": _clean_text(
            payload.get("Name", payload.get(
                "ShipName", report_a.get("Name", metadata.get("ShipName"))))),
        "call_sign": _clean_text(payload.get("CallSign", report_b.get("CallSign"))),
        "imo": _integer(payload.get("ImoNumber", payload.get("IMO"))),
        "destination": _clean_text(
            payload.get("DestinationName", payload.get("Destination"))),
        "draught": _number(payload.get("MaximumStaticDraught", payload.get("Draught"))),
        "ship_type_code": ship_type,
        "category": category if ship_type is not None else None,
        "category_label": label if ship_type is not None else None,
    })
    return base


def _normalization_rejection_reason(event: dict[str, Any]) -> str:
    """Return a safe, compact reason for a decoded event that was not accepted."""

    message_type = event.get("MessageType")
    if message_type not in FILTER_MESSAGE_TYPES:
        return f"不支持的消息类型：{message_type or '缺失'}"
    metadata = event.get("MetaData")
    metadata = metadata if isinstance(metadata, dict) else {}
    message = event.get("Message")
    message = message if isinstance(message, dict) else {}
    payload = message.get(message_type)
    payload = payload if isinstance(payload, dict) else {}
    mmsi_value = metadata.get("MMSI", payload.get("UserID"))
    mmsi = _integer(mmsi_value)
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        return "MMSI缺失或无效"
    if message_type in POSITION_MESSAGE_TYPES:
        lat = _number(metadata.get("Latitude", payload.get("Latitude")))
        lon = _number(metadata.get("Longitude", payload.get("Longitude")))
        if not _valid_coordinate(lat, lon):
            return "经纬度缺失或无效"
    return "消息结构不符合预期"


class AISCollector:
    """A reconnecting, thread-safe latest-position collector."""

    def __init__(self, api_key: str, connector: Callable[..., Any] | None = None) -> None:
        self._api_key = api_key
        self._connector = connector or websocket_connect
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._positions: dict[str, dict[str, Any]] = {}
        self._static: dict[str, dict[str, Any]] = {}
        self._status = "未启动"
        self._last_error: str | None = None
        self._last_message_at: str | None = None
        self._last_position_message_at: str | None = None
        self._last_raw_event_at: str | None = None
        self._last_raw_message_type: str | None = None
        self._last_rejection_reason: str | None = None
        self._message_count = 0
        self._raw_event_count = 0
        self._rejected_event_count = 0
        self._position_message_count = 0
        self._static_message_count = 0
        self._connected_at: str | None = None
        self._subscription_confirmed_at: str | None = None
        self._compression_enabled: bool | None = None

    def start(self) -> "AISCollector":
        if self._thread and self._thread.is_alive():
            return self
        if not self._api_key:
            with self._lock:
                self._status = "未配置密钥"
            return self
        if self._connector is None:
            with self._lock:
                self._status = "缺少 websockets 依赖"
                self._last_error = "请安装 requirements.txt 后重启应用"
            return self
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="aisstream-collector", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._status = "连接中" if attempt == 0 else "重连中"
                assert self._connector is not None
                with self._connector(
                    STREAM_URL, open_timeout=10, close_timeout=5,
                    ping_interval=20, ping_timeout=20, compression="deflate",
                    max_size=2 * 1024 * 1024,
                ) as socket:
                    socket.send(json.dumps(subscription(self._api_key)))
                    with self._lock:
                        self._status = "已连接，等待订阅确认"
                        self._connected_at = utc_now().isoformat()
                        self._last_error = None
                    attempt = 0
                    while not self._stop.is_set():
                        try:
                            frame = socket.recv(timeout=5)
                        except TimeoutError:
                            continue
                        if isinstance(frame, bytes):
                            frame = frame.decode("utf-8")
                        event = json.loads(frame)
                        if event.get("MessageType") == "SubscriptionConfirmation":
                            confirmation = event.get("Message") or {}
                            compression_enabled = confirmation.get("CompressionEnabled")
                            if not isinstance(compression_enabled, bool):
                                compression_enabled = None
                            with self._lock:
                                self._status = "订阅已确认"
                                self._subscription_confirmed_at = utc_now().isoformat()
                                self._compression_enabled = compression_enabled
                            continue
                        if event.get("error"):
                            raise RuntimeError(str(event["error"]))
                        self.ingest(event)
            except Exception as exc:  # Network failures are expected; reconnect safely.
                attempt += 1
                with self._lock:
                    self._status = "重连等待"
                    self._last_error = f"{type(exc).__name__}: {exc}"
                delay = min(60.0, 2 ** min(attempt, 5)) + random.random()
                self._stop.wait(delay)
        with self._lock:
            self._status = "已停止"

    def ingest(self, event: dict[str, Any], received_at: datetime | None = None) -> bool:
        received = received_at or utc_now()
        message_type = str(event.get("MessageType") or "缺失")
        with self._lock:
            self._raw_event_count += 1
            self._last_raw_event_at = received.isoformat()
            self._last_raw_message_type = message_type
        try:
            normalized = normalize_event(event, received)
        except Exception as exc:
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = f"解析异常：{type(exc).__name__}"
            return False
        if normalized is None:
            reason = _normalization_rejection_reason(event)
            with self._lock:
                self._rejected_event_count += 1
                self._last_rejection_reason = reason
            return False
        mmsi = normalized["mmsi"]
        with self._lock:
            self._message_count += 1
            self._last_message_at = normalized["received_at"]
            if normalized["kind"] == "static":
                self._static_message_count += 1
                previous = self._static.get(mmsi, {})
                self._static[mmsi] = {
                    **previous,
                    **{key: value for key, value in normalized.items()
                       if value is not None},
                }
            else:
                self._position_message_count += 1
                self._last_position_message_at = normalized["received_at"]
                previous = self._positions.get(mmsi, {})
                self._positions[mmsi] = {
                    **previous,
                    **{key: value for key, value in normalized.items()
                       if value is not None},
                }
        return True

    def snapshot(self, max_age_minutes: int = 30,
                 limit: int | None = None) -> list[dict[str, Any]]:
        cutoff = utc_now().timestamp() - max_age_minutes * 60
        with self._lock:
            rows = []
            stale_mmsi = []
            for mmsi, position in self._positions.items():
                received = datetime.fromisoformat(position["received_at"]).timestamp()
                if received < cutoff:
                    stale_mmsi.append(mmsi)
                    continue
                static = self._static.get(mmsi, {})
                merged = {**static, **position}
                # Position messages often carry the fresher ship name; static data owns type.
                if static.get("category"):
                    merged["category"] = static["category"]
                    merged["category_label"] = static["category_label"]
                    merged["ship_type_code"] = static.get("ship_type_code")
                category = merged.get("category") or "unknown"
                merged["category"] = category
                merged["category_label"] = VESSEL_TYPE_LABELS[category]
                merged["moving"] = (merged.get("sog") or 0) >= 0.5
                merged["age_minutes"] = max(0.0, (utc_now().timestamp() - received) / 60)
                rows.append(merged)
            for mmsi in stale_mmsi:
                self._positions.pop(mmsi, None)
            rows.sort(key=lambda row: row["received_at"], reverse=True)
            if limit is not None:
                rows = rows[:limit]
            return deepcopy(rows)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "last_error": self._last_error,
                "last_message_at": self._last_message_at,
                "last_position_message_at": self._last_position_message_at,
                "last_raw_event_at": self._last_raw_event_at,
                "last_raw_message_type": self._last_raw_message_type,
                "last_rejection_reason": self._last_rejection_reason,
                "message_count": self._message_count,
                "raw_event_count": self._raw_event_count,
                "rejected_event_count": self._rejected_event_count,
                "position_message_count": self._position_message_count,
                "static_message_count": self._static_message_count,
                "connected_at": self._connected_at,
                "subscription_confirmed_at": self._subscription_confirmed_at,
                "compression_enabled": self._compression_enabled,
                "tracked_vessels": len(self._positions),
            }
