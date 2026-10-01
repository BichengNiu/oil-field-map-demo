"""Observed AIS reports only: persistent archive and bounded recent backfill."""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import ais


def archive_path() -> Path:
    return Path(os.environ.get("AIS_ARCHIVE_PATH") or
                Path(__file__).with_name("runtime") / "ais-history.sqlite3")


@contextmanager
def _connect():
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
    """Require explicit UTC observation time; never manufacture it from now."""
    mmsi = ais._integer(row.get("mmsi", row.get("MMSI")))
    observed = ais._parse_utc(row.get("received_at", row.get("AIS报告时间 UTC")))
    lat = ais._number(row.get("lat", row.get("纬度")))
    lon = ais._number(row.get("lon", row.get("经度")))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        raise ValueError("MMSI无效")
    if observed is None or observed > ais.utc_now() + timedelta(minutes=5):
        raise ValueError("AIS报告时间缺失、无效或在未来")
    if not ais._valid_coordinate(lat, lon) or ais.region_for(lat, lon) is None:
        raise ValueError("坐标无效或不在监测水域")
    category = row.get("category") or next((key for key, label in ais.VESSEL_TYPE_LABELS.items()
                                           if label == row.get("船型")), "unknown")
    if category not in ais.VESSEL_TYPE_LABELS:
        category = "unknown"
    sog = ais._number(row.get("sog", row.get("航速 节")))
    course = ais._number(row.get("course", row.get("航向 °")))
    if sog is not None and not 0 <= sog < 102.3:
        sog = None
    if course is not None and not 0 <= course < 360:
        course = None
    source = row.get("source") or row.get("data_source") or row.get("数据源")
    if not source:
        raise ValueError("需要提供原始数据源")
    return {**row, "mmsi": str(mmsi), "received_at": observed.isoformat(),
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
    normalized = [normalize_report(row) for row in rows]
    if not normalized:
        return 0
    with _connect() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO reports VALUES (?, ?, ?, ?)",
                         [(row["mmsi"], row["received_at"], row["source"],
                           json.dumps(row, ensure_ascii=False)) for row in normalized])
        return conn.total_changes - before


def import_csv(data: bytes) -> int:
    """Validate the entire upload before writing; reject malformed rows atomically."""
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("CSV没有船位报告")
    return archive_reports(rows)


def day_reports(day: date) -> list[dict]:
    start = datetime.combine(day, time.min, timezone.utc)
    end = start + timedelta(days=1)
    with _connect() as conn:
        rows = conn.execute("SELECT payload FROM reports WHERE observed >= ? AND observed < ? "
                            "ORDER BY observed", (start.isoformat(), end.isoformat())).fetchall()
    return [json.loads(row[0]) for row in rows]


def known_mmsis() -> list[str]:
    with _connect() as conn:
        return [row[0] for row in conn.execute("SELECT mmsi FROM reports GROUP BY mmsi "
                                              "ORDER BY MAX(observed) DESC LIMIT 1000")]


def track_reports(feature: dict, expected_mmsi: str, day: date) -> list[dict]:
    """Normalize aligned track arrays; use only fields contained in the track."""
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    if feature.get("type") != "Feature" or feature.get("error"):
        raise ValueError("无法识别的历史轨迹响应")
    if geometry.get("type") == "LineString":
        coordinates = geometry.get("coordinates") or []
    elif geometry.get("type") == "Point":
        coordinates = [geometry["coordinates"]]
    elif not geometry:
        return []
    else:
        raise ValueError("不支持的轨迹几何")
    times = properties.get("times") or []
    if len(coordinates) != len(times):
        raise ValueError("轨迹坐标与时间未对齐")
    mmsi = str(properties.get("mmsi", feature.get("id", expected_mmsi)))
    if mmsi != expected_mmsi:
        raise ValueError("轨迹MMSI与请求不一致")
    credit = feature.get("attribution") or properties.get("attribution") or {}
    attribution = " · ".join(map(str, credit.values())) if isinstance(credit, dict) else str(credit)
    rows = []
    for index, coordinate in enumerate(coordinates):
        observed = ais._parse_utc(times[index])
        if observed is None or observed.date() != day:
            continue
        def value(key):
            values = properties.get(key) or []
            return values[index] if isinstance(values, list) and index < len(values) else None
        category, label = ais.classify_ship_type(ais._integer(properties.get("type")))
        heading = ais._number(value("heading"))
        course = heading if heading is not None and 0 <= heading < 360 else value("cog")
        try:
            rows.append(normalize_report({
                "mmsi": mmsi, "received_at": times[index], "lon": coordinate[0],
                "lat": coordinate[1], "name": properties.get("name"),
                "sog": value("sog"), "course": course, "category": category,
                "category_label": label,
                "navigation_status": ais.NAVIGATION_STATUS_LABELS.get(value("nav_status"), "未报告"),
                "source": "Open Waters track", "data_source": "Open Waters 历史轨迹",
                "source_url": ais.OPENWATERS_SOURCE, "source_attribution": attribution,
            }))
        except ValueError:
            # Vessel may have been outside these monitored waters that day.
            continue
    return rows


def _fetch_track(mmsi: str, day: date) -> tuple[list[dict], bool]:
    start = datetime.combine(day, time.min, timezone.utc)
    end = min(start + timedelta(days=1), ais.utc_now())
    params = urlencode({"from": start.isoformat(), "to": end.isoformat(), "limit": 1000})
    req = Request(f"{ais.OPENWATERS_API}/{mmsi}/track?{params}",
                  headers={"Accept": "application/geo+json", "User-Agent": "oil-field-map-demo/1.0"})
    with urlopen(req, timeout=8) as response:
        feature = json.load(response)
    return track_reports(feature, mmsi, day), bool(
        feature.get("truncated") or (feature.get("properties") or {}).get("truncated"))


def historical_snapshot(day: date, candidates: tuple[str, ...] = ()) -> dict:
    errors = []
    reports = []
    try:
        reports = day_reports(day)
    except Exception as exc:
        errors.append(f"历史档案读取失败：{exc}")
    attempted = 0
    truncated = False
    start = datetime.combine(day, time.min, timezone.utc)
    recent = start + timedelta(days=1) > ais.utc_now() - timedelta(hours=48) and start < ais.utc_now()
    # Bound anonymous requests and latency. This is a known-vessel sample, never
    # an enumeration of every vessel formerly present in the area.
    queried = list(dict.fromkeys(candidates))[:20] if recent else []
    if queried:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch_track, mmsi, day): mmsi for mmsi in queried}
            for future in as_completed(futures):
                attempted += 1
                try:
                    rows, limited = future.result()
                    reports.extend(rows)
                    truncated |= limited
                    archive_reports(rows)
                except Exception as exc:
                    errors.append(f"{futures[future]}：{type(exc).__name__}: {exc}")
    vessels = ais.merge_vessel_snapshots(reports)
    for vessel in vessels:
        vessel.update({"historical_day": day.isoformat(), "age_minutes": None})
    return {"vessels": vessels, "day": day.isoformat(), "reports": len(reports),
            "queried_vessels": attempted, "truncated": truncated,
            "candidate_limit": len(candidates) > 20, "error": "; ".join(errors) or None,
            "coverage": "当日有报告船舶的最后观测位置；档案与已知MMSI轨迹样本，非完整水域普查、非同时快照"}
