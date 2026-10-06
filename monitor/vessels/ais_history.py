"""Persist AIS reports whose source provides an explicit observation time."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import monitor.vessels.ais as ais


def archive_path() -> Path:
    configured = os.environ.get("AIS_ARCHIVE_PATH")
    if configured:
        return Path(configured)
    state_home = Path(os.environ.get("XDG_STATE_HOME") or
                      Path.home() / ".local" / "state")
    return state_home / "oil-field-map-demo" / "ais-history.sqlite3"


@contextmanager
def connect_archive():
    """Open the shared report archive and ensure its schema exists."""
    path = archive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS reports (mmsi TEXT, observed TEXT, source TEXT, "
                         "payload TEXT NOT NULL, PRIMARY KEY (mmsi, observed, source))")
            conn.execute("CREATE INDEX IF NOT EXISTS reports_time ON reports(observed)")
            yield conn
    finally:
        conn.close()


def normalize_report(row: dict) -> dict:
    """Normalize one report without substituting receipt time for observation time."""
    mmsi = ais.parse_integer(row.get("mmsi", row.get("MMSI")))
    observed = ais.parse_utc(row.get("observed_at") or row.get("AIS报告时间 UTC"))
    received = ais.parse_utc(
        row.get("received_at") or row.get("采集器接收时间 UTC")) or ais.utc_now()
    lat = ais.parse_number(row.get("lat", row.get("纬度")))
    lon = ais.parse_number(row.get("lon", row.get("经度")))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        raise ValueError("MMSI无效")
    if observed is None or observed > ais.utc_now() + timedelta(minutes=5):
        raise ValueError("AIS报告时间缺失、无效或在未来")
    if not ais.valid_coordinate(lat, lon) or ais.region_for(lat, lon) is None:
        raise ValueError("坐标无效或不在监测水域")
    category = row.get("category") or next((key for key, label in ais.VESSEL_TYPE_LABELS.items()
                                           if label == row.get("船型")), "unknown")
    if category not in ais.VESSEL_TYPE_LABELS:
        category = "unknown"
    sog = ais.parse_number(row.get("sog", row.get("航速 节")))
    course = ais.parse_number(row.get("course", row.get("航向 °")))
    if sog is not None and not 0 <= sog < 102.3:
        sog = None
    if course is not None and not 0 <= course < 360:
        course = None
    source = row.get("source") or row.get("data_source") or row.get("数据源")
    if not source:
        raise ValueError("需要提供原始数据源")
    return {**row, "mmsi": str(mmsi), "observed_at": observed.isoformat(),
            "received_at": received.isoformat(),
            "provider_received_at": row.get("provider_received_at", row.get("采集器接收时间 UTC")),
            "lat": lat, "lon": lon, "region": ais.region_for(lat, lon),
            "name": row.get("name", row.get("船名")),
            "imo": row.get("imo", row.get("IMO")),
            "sog": sog, "course": course, "moving": (sog or 0) >= 0.5,
            "category": category, "category_label": ais.VESSEL_TYPE_LABELS[category],
            "navigation_status": row.get("navigation_status", row.get("航行状态")),
            "destination": row.get("destination", row.get("目的地")),
            "draught": row.get("draught", row.get("吃水 米")),
            "source": str(source), "data_source": row.get("data_source", str(source)),
            "source_url": row.get("source_url", row.get("来源")),
            "age_minutes": None}


def archive_reports(rows: list[dict]) -> int:
    """Insert unique, time-valid AIS reports into the local archive."""
    observed_rows = [
        row for row in rows
        if row.get("observed_at") or row.get("AIS报告时间 UTC")
    ]
    normalized = [normalize_report(row) for row in observed_rows]
    if not normalized:
        return 0
    with connect_archive() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO reports VALUES (?, ?, ?, ?)",
                         [(row["mmsi"], row["observed_at"], row["source"],
                           json.dumps(row, ensure_ascii=False)) for row in normalized])
        return conn.total_changes - before
