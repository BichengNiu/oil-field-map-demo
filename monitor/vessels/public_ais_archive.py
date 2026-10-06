"""Reproducible import of a small, public AIS observation sample, not a census."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading

import monitor.vessels.ais as ais
import monitor.vessels.ais_history as ais_history

SOURCE_URL = "https://huggingface.co/datasets/yasumorishima/hormuz-ais"
REVISION = "eef53f9bb006e3cf026824fa1f54ab6d3404468f"
DOWNLOAD_URL = f"{SOURCE_URL}/resolve/{REVISION}/positions.parquet"
SHA256 = "9eb4bc1bc9250721f30554cf8a24d5487ea2dbedad5759982ef7c962c866473c"
SOURCE = "yasumorishima/hormuz-ais · AISStream"
START, END = date(2026, 3, 14), date(2026, 4, 11)
MAX_BYTES = 15 * 1024 * 1024
_LOCK = threading.Lock()


def _verify(path: Path) -> None:
    if path.stat().st_size > MAX_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("公开AIS档案校验失败；不导入与已核查版本不同的内容")


def download_archive() -> Path:
    import requests
    path = ais_history.archive_path().parent / f"hormuz-{SHA256[:12]}.parquet"
    if path.exists():
        _verify(path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".part")
    try:
        with requests.get(DOWNLOAD_URL, stream=True, timeout=(15, 20)) as response:
            response.raise_for_status()
            size = 0
            with temporary.open("wb") as output:
                for chunk in response.iter_content(256 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("公开AIS档案超出预期大小")
                    output.write(chunk)
        _verify(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _value(value):
    return None if isinstance(value, float) and not math.isfinite(value) else value


def convert_report(row: dict) -> tuple[dict | None, str | None]:
    """Preserve AIS time and collector time separately; reject suspect rows."""
    mmsi = ais.parse_integer(row.get("mmsi"))
    if mmsi is None or not 100000000 <= mmsi <= 999999999:
        return None, "invalid_mmsi"
    observed = ais.parse_utc(row.get("timestamp"))
    if observed is None or not START <= observed.date() <= END:
        return None, "invalid_or_out_of_range_time"
    lat, lon = ais.parse_number(row.get("latitude")), ais.parse_number(row.get("longitude"))
    if not ais.valid_coordinate(lat, lon) or ais.region_for(lat, lon) is None:
        return None, "invalid_or_out_of_region_coordinate"
    speed = ais.parse_number(row.get("speed"))
    # Source's conservative speed screen, including the AIS 102.3 sentinel.
    # This is a quality heuristic, not proof that every rejected report is false.
    if speed is not None and not 0 <= speed < 40:
        return None, "speed_screen_ge40_or_negative"
    category, label = ais.classify_ship_type(ais.parse_integer(row.get("ship_type")))
    heading = ais.parse_number(row.get("heading"))
    course = heading if heading is not None and 0 <= heading < 360 else row.get("course")
    received = ais.parse_utc(row.get("received_at")) or ais.utc_now()
    report = ais_history.normalize_report({
        "mmsi": str(mmsi), "observed_at": observed.isoformat(),
        "received_at": received.isoformat(),
        "provider_received_at": row.get("received_at"),
        "lat": lat, "lon": lon, "name": row.get("ship_name"),
        "sog": speed, "course": course, "category": category, "category_label": label,
        "destination": row.get("destination"), "draught": row.get("draught"),
        "length": row.get("length"), "width": row.get("width"), "flag": row.get("flag"),
        "source": SOURCE, "data_source": "公开岸基AIS历史采样（迪拜附近为主）",
        "source_url": SOURCE_URL,
        "source_attribution": "AISStream broadcasts · collected by yasumorishima; source terms apply",
        "source_sha256": SHA256,
    })
    return report, None


def import_archive(path: Path) -> dict:
    """Import reports and completion marker atomically into the same database."""
    import pyarrow.parquet as parquet
    _verify(path)
    table = parquet.read_table(path)
    required = {"mmsi", "timestamp", "latitude", "longitude", "speed"}
    if not required <= set(table.column_names):
        raise ValueError("公开AIS档案缺少必要列")
    rejected, region_counts, day_counts = Counter(), Counter(), Counter()
    ships, region_ships = set(), defaultdict(set)
    earliest = latest = None
    accepted = inserted = 0
    with ais_history.connect_archive() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS archive_imports (sha256 TEXT PRIMARY KEY, metadata TEXT)")
        previous = conn.execute("SELECT metadata FROM archive_imports WHERE sha256=?", (SHA256,)).fetchone()
        if previous:
            return json.loads(previous[0])
        for batch in table.to_batches(max_chunksize=1000):
            payloads = []
            for raw in batch.to_pylist():
                row = {key: _value(value) for key, value in raw.items()}
                observed = ais.parse_utc(row.get("timestamp"))
                if observed:
                    stamp = observed.isoformat()
                    earliest = min(earliest, stamp) if earliest else stamp
                    latest = max(latest, stamp) if latest else stamp
                report, reason = convert_report(row)
                if reason:
                    rejected[reason] += 1
                    continue
                accepted += 1
                ships.add(report["mmsi"])
                region_counts[report["region"]] += 1
                region_ships[report["region"]].add(report["mmsi"])
                day_counts[report["observed_at"][:10]] += 1
                payloads.append((report["mmsi"], report["observed_at"], SOURCE,
                                 json.dumps(report, ensure_ascii=False, allow_nan=False)))
            before = conn.total_changes
            conn.executemany("INSERT OR IGNORE INTO reports VALUES (?, ?, ?, ?)", payloads)
            inserted += conn.total_changes - before
        metadata = {
            "source_url": SOURCE_URL, "revision": REVISION, "sha256": SHA256,
            "raw_rows": table.num_rows, "accepted_rows": accepted, "inserted_rows": inserted,
            "duplicate_or_existing_rows": accepted - inserted, "accepted_mmsis": len(ships),
            "first_report_utc": earliest, "last_report_utc": latest,
            "rejected": dict(rejected), "reports_per_utc_day": dict(sorted(day_counts.items())),
            "regions": {region: {"reports": region_counts[region], "mmsis": len(region_ships[region])}
                        for region in ais.REGIONS},
            "imported_at_utc": datetime.now(timezone.utc).isoformat(),
            "coverage": f"岸基两分钟采样，主要在迪拜附近；霍尔木兹仅{region_counts['霍尔木兹海峡']}条合格报告；苏伊士和曼德无覆盖。不是全量船舶普查，不可推算通行总量。",
            "terms": "Dataset license is other/see-source-terms, not a redistribution grant. Check AISStream terms before redistributing.",
            "filters": "Valid nine-digit MMSI, source UTC timestamp within published dates, valid coordinates in project regions, speed <40 knots when present; >=40 is a conservative heuristic. Original file retained.",
        }
        conn.execute("INSERT INTO archive_imports VALUES (?, ?)", (SHA256, json.dumps(metadata, ensure_ascii=False)))
    return metadata


def ensure_public_archive(day: date) -> dict | None:
    if not START <= day <= END:
        return None
    with _LOCK:
        with ais_history.connect_archive() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS archive_imports (sha256 TEXT PRIMARY KEY, metadata TEXT)")
            previous = conn.execute("SELECT metadata FROM archive_imports WHERE sha256=?", (SHA256,)).fetchone()
        if previous:
            return json.loads(previous[0])
        return import_archive(download_archive())


if __name__ == "__main__":
    print(json.dumps(ensure_public_archive(START), ensure_ascii=False, indent=2))
