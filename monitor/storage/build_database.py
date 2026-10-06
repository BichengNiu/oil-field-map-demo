"""Collect configured project sources and build the local DuckDB data store."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import uuid

import duckdb

from monitor.common.paths import PROJECT_ROOT, runtime_path
from monitor.oilgas.field_catalog import ASSETS


ASSET_AUDITS = (
    "2026-09-30/oilgas/ASSET_DATA_AUDIT_2026-09-30.csv",
    "2026-10-01/oilgas/ASSET_DATA_AUDIT_2026-10-01.csv",
    "2026-10-03/oilgas/ASSET_DATA_AUDIT_2026-10-03.csv",
    "2026-10-04/oilgas/ASSET_DATA_AUDIT_2026-10-04.csv",
)
PORT_AUDITS = (
    "2026-09-18/ports/PORT_ACTIVITY_AUDIT_2026-09-18.csv",
    "2026-09-25/ports/PORT_ACTIVITY_AUDIT_2026-09-25.csv",
    "2026-10-03/ports/PORT_ACTIVITY_AUDIT_2026-10-03_OBS_2026-09-25.csv",
    "2026-10-04/ports/PORT_ACTIVITY_AUDIT_2026-10-04_OBS_2026-09-25.csv",
)
AUDIT_ROOT = PROJECT_ROOT / "docs" / "audits"
LIVE_TABLES = (
    "portwatch_catalog", "portwatch_daily", "portwatch_risk_capacity",
    "vessel_positions", "ais_reports", "sea_history_events", "source_payloads",
    "source_fetch_runs", "source_documents",
)
LOCAL_DOCUMENT_ROOTS = ("data", "snapshots", "docs/audits")


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _date_from_path(path: Path) -> str:
    match = re.search(r"2026-(\d\d-\d\d)", path.name)
    if not match:
        raise ValueError(f"Source filename has no review date: {path}")
    return f"2026-{match.group(1)}"


def _asset_rows():
    for relative in ASSET_AUDITS:
        path = AUDIT_ROOT / relative
        review_date = _date_from_path(path)
        for row_number, row in enumerate(_read_csv(path), 1):
            country = row.get("国家") or row.get("country")
            name = row.get("名称") or row.get("name")
            if not country or not name:
                continue
            yield (
                review_date, row_number, country, name,
                row.get("层级") or row.get("asset_level"),
                row.get("上级") or row.get("parent_asset"),
                row.get("商品") or row.get("commodity"),
                row.get("数值") or row.get("值") or row.get("value"),
                row.get("单位") or row.get("unit"),
                row.get("指标类型") or row.get("口径") or row.get("metric_type"),
                row.get("状态") or row.get("operating_status"),
                _number(row.get("地图纬度") or row.get("纬度") or row.get("latitude")),
                _number(row.get("地图经度") or row.get("经度") or row.get("longitude")),
                _json(row), relative,
            )


def _port_rows():
    for relative in PORT_AUDITS:
        path = AUDIT_ROOT / relative
        review_date = _date_from_path(path)
        for row_number, row in enumerate(_read_csv(path), 1):
            observed = (row.get("日期UTC") or row.get("date") or "")[:10] or None
            yield (
                review_date, observed, row_number,
                row.get("水域") or row.get("sea"),
                row.get("国家") or row.get("country"),
                row.get("港口") or row.get("port"),
                row.get("PortWatch ID") or row.get("portwatch_id"),
                _number(row.get("当日油轮艘次")),
                _number(row.get("当日其他货轮艘次")),
                _number(row.get("纬度")), _number(row.get("经度")),
                _json(row), relative,
            )


def _catalog_rows():
    sources = (
        ("portwatch_gulf", PROJECT_ROOT / "data/ports/PORTWATCH_GULF_DIRECTORY_2026-10-03.json", "rows"),
        ("wpi_reference", PROJECT_ROOT / "data/ports/port_inventory_wpi_2026-09-30.json", None),
    )
    for source_name, path, key in sources:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload[key] if key else payload
        for row_number, record in enumerate(records, 1):
            yield (
                source_name, row_number,
                record.get("name") or record.get("NAME") or record.get("port_name") or record.get("portname"),
                record.get("country") or record.get("COUNTRY"),
                record.get("region"),
                str(record.get("portid") or record.get("portwatch_id") or record.get("wpi") or ""),
                _number(record.get("lat") or record.get("latitude")),
                _number(record.get("lon") or record.get("longitude")),
                _json(record), path.relative_to(PROJECT_ROOT).as_posix(),
            )


def _document_row_count(payload) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        counts = [len(value) for value in payload.values() if isinstance(value, list)]
        return sum(counts) if counts else 1
    return 1


def _local_documents() -> list[dict]:
    """Load versioned structured data files while retaining source hashes."""
    documents = []
    for root in LOCAL_DOCUMENT_ROOTS:
        for path in sorted((PROJECT_ROOT / root).rglob("*")):
            if not path.is_file():
                continue
            if path.name.endswith(".json.gz"):
                source_bytes = path.read_bytes()
                content = gzip.decompress(source_bytes).decode("utf-8-sig")
                payload = json.loads(content)
                source_format = "json.gz"
            elif path.suffix == ".json":
                source_bytes = path.read_bytes()
                payload = json.loads(source_bytes.decode("utf-8-sig"))
                source_format = "json"
            elif path.suffix == ".csv":
                source_bytes = path.read_bytes()
                content = source_bytes.decode("utf-8-sig")
                payload = list(csv.DictReader(io.StringIO(content, newline="")))
                source_format = "csv"
            else:
                continue
            documents.append({
                "source_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "source_kind": root,
                "source_format": source_format,
                "file_bytes": len(source_bytes),
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
                "source_rows": _document_row_count(payload),
                "payload": payload,
            })
    return documents


def _source_rows(documents: list[dict] | None = None) -> list[tuple]:
    sources = [
        ("oilgas_assets", PROJECT_ROOT / "monitor/oilgas/field_catalog.py", len(ASSETS)),
    ]
    sources += [("oilgas_audit", AUDIT_ROOT / path, sum(1 for _ in _read_csv(AUDIT_ROOT / path)))
                for path in ASSET_AUDITS]
    sources += [("port_activity_audit", AUDIT_ROOT / path, sum(1 for _ in _read_csv(AUDIT_ROOT / path)))
                for path in PORT_AUDITS]
    sources += [
        ("portwatch_gulf", PROJECT_ROOT / "data/ports/PORTWATCH_GULF_DIRECTORY_2026-10-03.json",
         len(json.loads((PROJECT_ROOT / "data/ports/PORTWATCH_GULF_DIRECTORY_2026-10-03.json").read_text())["rows"])),
        ("wpi_reference", PROJECT_ROOT / "data/ports/port_inventory_wpi_2026-09-30.json",
         len(json.loads((PROJECT_ROOT / "data/ports/port_inventory_wpi_2026-09-30.json").read_text()))),
    ]
    evidence_files = sorted((PROJECT_ROOT / "data/oilgas").glob("*.json")) + [
        PROJECT_ROOT / "data/oilgas/CONTINUATION_EVIDENCE_2026-10-01.json",
        PROJECT_ROOT / "data/oilgas/FINAL_REVIEW_2026-10-04.json",
        PROJECT_ROOT / "data/oilgas/GEM_RECONCILIATION_2026-09-30.json",
        PROJECT_ROOT / "data/oilgas/GULF_REVIEW_2026-10-03.json",
    ]
    for path in dict.fromkeys(evidence_files):
        payload = json.loads(path.read_text(encoding="utf-8"))
        sources.append(("oilgas_evidence", path, _document_row_count(payload)))
    output_paths = {path.relative_to(PROJECT_ROOT).as_posix() for _, path, _ in sources}
    for document in documents or []:
        if document["source_path"] not in output_paths:
            sources.append(("local_source_document", PROJECT_ROOT / document["source_path"],
                            document["source_rows"]))
            output_paths.add(document["source_path"])
    output = []
    for dataset, path, row_count in sources:
        output.append((
            dataset, path.relative_to(PROJECT_ROOT).as_posix(),
            path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(), row_count,
        ))
    return output


def _insert_local_documents(connection, documents: list[dict]) -> int:
    loaded_at = datetime.now(timezone.utc)
    values = [(
        document["source_path"], document["sha256"], document["source_kind"],
        document["source_format"], document["file_bytes"], document["source_rows"],
        loaded_at, _json(document["payload"]),
    ) for document in documents]
    if values:
        connection.executemany("""
            INSERT INTO source_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source_path, sha256) DO UPDATE SET
                source_kind=excluded.source_kind, source_format=excluded.source_format,
                file_bytes=excluded.file_bytes, source_rows=excluded.source_rows,
                loaded_at=excluded.loaded_at, payload=excluded.payload
        """, values)
    return len(values)


def _insert_portwatch_snapshots(connection, documents: list[dict]) -> int:
    rows_before = connection.execute("SELECT count(*) FROM portwatch_daily").fetchone()[0]
    for document in sorted(
            (row for row in documents if row["source_path"].startswith("snapshots/portwatch/")),
            key=lambda row: row["source_path"], reverse=True):
        match = re.search(r"PORTWATCH_RAW_(\d{4}-\d{2}-\d{2})", document["source_path"])
        if not match:
            raise ValueError(f"PortWatch快照路径缺少来源日期：{document['source_path']}")
        fetched_at = datetime.combine(date.fromisoformat(match.group(1)), datetime.min.time(), timezone.utc)
        values = []
        for record in document["payload"]:
            if not isinstance(record, dict) or not record.get("portid") or not record.get("date"):
                raise ValueError(f"PortWatch快照行缺少节点或观测日期：{document['source_path']}")
            values.append((
                "port", str(record["portid"]), date.fromisoformat(str(record["date"])[:10]),
                record.get("portname"), record.get("country"), fetched_at,
                _number(record.get("portcalls")), _number(record.get("import")),
                _number(record.get("export")), None, None,
                _json({"source_path": document["source_path"],
                       "source_sha256": document["sha256"], "record": record}),
            ))
        if values:
            connection.executemany("""
                INSERT INTO portwatch_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (node_kind, portid, observed_date) DO NOTHING
            """, values)
    rows_after = connection.execute("SELECT count(*) FROM portwatch_daily").fetchone()[0]
    return rows_after - rows_before


def _utc(value) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _store_fetch_run(connection, run_id, source, started, status, rows, details, error=None):
    connection.execute(
        "INSERT INTO source_fetch_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, source, started, datetime.now(timezone.utc), status,
         rows, error, _json(details)),
    )


def _load_live_modules():
    # The same checked source readers used by the dashboard keep API rules,
    # validation and geographic coverage consistent with the product.
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import monitor.ports.portwatch as portwatch
    import monitor.vessels.ais as ais
    return portwatch, ais


def _insert_portwatch_catalog(connection, run_id, portwatch):
    started = datetime.now(timezone.utc)
    try:
        ports = portwatch.port_catalog()
        chokes = portwatch.chokepoint_catalog()
        fetched_at = datetime.now(timezone.utc)
        records = [("port", row) for row in ports] + [("chokepoint", row) for row in chokes]
        values = []
        for kind, row in records:
            values.append((
                kind, str(row["portid"]), row.get("name") or row.get("portname"),
                row.get("country"), row.get("region"), _number(row.get("lat")),
                _number(row.get("lon")), bool(portwatch.has_independent_statistics(row))
                if kind == "port" else True,
                fetched_at, _json(row),
            ))
        connection.execute("DELETE FROM portwatch_catalog")
        connection.executemany(
            "INSERT INTO portwatch_catalog VALUES (" + ",".join(["?"] * 10) + ")",
            values,
        )
        _store_fetch_run(
            connection, run_id, "portwatch.catalog", started, "success", len(values),
            {"ports": len(ports), "chokepoints": len(chokes),
             "port_endpoint": portwatch.PORTS, "chokepoint_endpoint": portwatch.CHOKEPOINTS},
        )
        connection.execute("INSERT INTO source_payloads VALUES (?, ?, ?, ?, ?)",
                           (run_id, "portwatch.catalog_snapshot", fetched_at, "current",
                            _json({"ports": ports, "chokepoints": chokes})))
        return ports, chokes
    except Exception as exc:
        _store_fetch_run(connection, run_id, "portwatch.catalog", started, "error", 0,
                          {}, f"{type(exc).__name__}: {exc}")
        return None, None


def _insert_portwatch_activity(connection, run_id, portwatch, ports, chokes):
    if ports is None or chokes is None:
        started = datetime.now(timezone.utc)
        _store_fetch_run(connection, run_id, "portwatch.daily.ports", started, "skipped", 0,
                          {}, "PortWatch目录读取失败")
        _store_fetch_run(connection, run_id, "portwatch.daily.chokepoints", started,
                          "skipped", 0, {}, "PortWatch目录读取失败")
        return
    import monitor.ports.portwatch_downloads as downloads

    os.environ.setdefault(
        "PORTWATCH_DOWNLOAD_CACHE",
        str(runtime_path("portwatch-download-cache.sqlite3")),
    )
    fetched_at = datetime.now(timezone.utc)
    try:
        port_latest = portwatch.latest_date()
        port_first = port_latest - timedelta(days=89)
        stats_ports = [row for row in ports if portwatch.has_independent_statistics(row)]
        port_ids = tuple(sorted(str(row["portid"]) for row in stats_ports))
        names = {str(row["portid"]): row for row in stats_ports}
        grouped: dict[str, dict[date, dict]] = {}
        group_errors = []
        group_size = 20
        groups = [port_ids[offset:offset + group_size]
                  for offset in range(0, len(port_ids), group_size)]
        for index, ids in enumerate(groups, 1):
            print(f"PortWatch港口近90天：节点组 {index}/{len(groups)}…", flush=True)
            try:
                grouped.update(portwatch._activity_rows(port_latest, ids, 90))
            except Exception as exc:
                group_errors.append(f"group {index}: {type(exc).__name__}: {exc}")

        port_output = []
        port_coverage = []
        for port_id, by_day in grouped.items():
            catalog = names[port_id]
            days = sorted(by_day)
            port_coverage.append({
                "portid": port_id, "records": len(days),
                "first_observed_date": days[0].isoformat() if days else None,
                "latest_observed_date": days[-1].isoformat() if days else None,
                "window_start": port_first.isoformat(), "window_end": port_latest.isoformat(),
                "missing_days": 90 - len(days),
            })
            for observed, record in by_day.items():
                port_output.append((
                    "port", port_id, observed, record.get("portname") or catalog.get("name"),
                    record.get("country") or catalog.get("country"), fetched_at,
                    _number(record.get("portcalls")), _number(record.get("import")),
                    _number(record.get("export")), None, None, _json(record),
                ))
        if port_output:
            connection.executemany("""
                INSERT INTO portwatch_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (node_kind, portid, observed_date) DO UPDATE SET
                    name=excluded.name, country=excluded.country, fetched_at=excluded.fetched_at,
                    calls=excluded.calls, import_tonnes=excluded.import_tonnes,
                    export_tonnes=excluded.export_tonnes, payload=excluded.payload
            """, port_output)
        covered_ids = {port_id for port_id, by_day in grouped.items() if by_day}
        missing_ids = sorted(set(port_ids) - covered_ids)
        problems = list(group_errors)
        if missing_ids:
            problems.append(f"no daily rows returned for {len(missing_ids)} of {len(port_ids)} catalog nodes")
        port_status = "partial" if problems and port_output else ("error" if problems else "success")
        port_error = "; ".join(problems) if problems else None
        port_details = {
            "endpoint": portwatch.DAILY, "mode": "verified_recent_window",
            "window_days": 90, "window_start": port_first.isoformat(),
            "window_end": port_latest.isoformat(), "catalog_nodes": len(stats_ports),
            "nodes_with_rows": len(covered_ids), "nodes_without_rows": missing_ids,
            "groups_requested": len(groups), "groups_failed": group_errors,
            "coverage": port_coverage,
        }
        connection.execute("INSERT INTO source_payloads VALUES (?, ?, ?, ?, ?)",
                           (run_id, "portwatch.window_manifest", fetched_at,
                            "ports_recent_90_days", _json(port_details)))
        _store_fetch_run(connection, run_id, "portwatch.daily.ports", fetched_at,
                         port_status, len(port_output), port_details, port_error)
    except Exception as exc:
        _store_fetch_run(connection, run_id, "portwatch.daily.ports", fetched_at,
                         "error", 0, {}, f"{type(exc).__name__}: {exc}")

    choke_started = datetime.now(timezone.utc)
    try:
        choke_latest = portwatch.latest_chokepoint_date()
        choke_nodes = [downloads.node("chokepoints", row) for row in chokes]
        result = downloads.collect(
            choke_nodes, "history", first=choke_latest - timedelta(days=89),
            last=choke_latest, derived=False,
            progress=lambda message: print(message, flush=True),
        )
        choke_rows = []
        for record in result["datasets"].get("chokepoints", []):
            choke_rows.append((
                "chokepoint", str(record["portid"]),
                date.fromisoformat(str(record["date"])[:10]), record.get("portname"),
                record.get("country"), fetched_at, None, None, None,
                _number(record.get("n_total")), _number(record.get("capacity")),
                _json(record),
            ))
        if choke_rows:
            connection.executemany("""
                INSERT INTO portwatch_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (node_kind, portid, observed_date) DO UPDATE SET
                    name=excluded.name, country=excluded.country, fetched_at=excluded.fetched_at,
                    choke_total_vessels=excluded.choke_total_vessels,
                    choke_capacity_dwt=excluded.choke_capacity_dwt, payload=excluded.payload
            """, choke_rows)
        details = {"endpoint": portwatch.CHOKEPOINT_DAILY, "mode": "verified_recent_window",
                   "window_days": 90, "coverage": result["coverage"],
                   "manifest": result["manifest"]}
        connection.execute("INSERT INTO source_payloads VALUES (?, ?, ?, ?, ?)",
                           (run_id, "portwatch.window_manifest", fetched_at,
                            "chokepoints_recent_90_days", _json(result["manifest"])))
        _store_fetch_run(connection, run_id, "portwatch.daily.chokepoints", choke_started,
                         "success", len(choke_rows), details)
    except Exception as exc:
        _store_fetch_run(connection, run_id, "portwatch.daily.chokepoints", choke_started,
                         "error", 0, {}, f"{type(exc).__name__}: {exc}")


def _insert_portwatch_risk(connection, run_id, portwatch, ports):
    started = datetime.now(timezone.utc)
    if ports is None:
        _store_fetch_run(connection, run_id, "portwatch.route_risk", started, "skipped", 0,
                          {}, "港口目录读取失败")
        return
    try:
        ids = tuple(sorted(str(row["portid"]) for row in ports
                           if portwatch.has_independent_statistics(row)))
        risk = portwatch.port_risk_capacity(ids)
        fetched_at = datetime.now(timezone.utc)
        values = [(port_id, fetched_at, value, _json({"portid": port_id, "daily_capacity_at_risk": value}))
                  for port_id, value in sorted(risk.items())]
        connection.execute("DELETE FROM portwatch_risk_capacity")
        connection.executemany("INSERT INTO portwatch_risk_capacity VALUES (?, ?, ?, ?)", values)
        connection.execute("INSERT INTO source_payloads VALUES (?, ?, ?, ?, ?)",
                           (run_id, "portwatch.risk_snapshot", fetched_at, "all_ports",
                            _json({"endpoint": portwatch.SPILLOVERS,
                                   "basis": "source historical route model",
                                   "port_capacity_at_risk": risk})))
        _store_fetch_run(connection, run_id, "portwatch.route_risk", started, "success", len(values),
                          {"endpoint": portwatch.SPILLOVERS, "basis": "source historical route model"})
    except Exception as exc:
        _store_fetch_run(connection, run_id, "portwatch.route_risk", started, "error", 0,
                          {}, f"{type(exc).__name__}: {exc}")


def _insert_openwaters(connection, run_id, ais):
    started = datetime.now(timezone.utc)
    groups = ais.openwaters_bbox_groups()
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=len(groups)) as pool:
        futures = {pool.submit(ais._fetch_openwaters_group, group, 120): (index, group)
                   for index, group in enumerate(groups)}
        for future in as_completed(futures):
            index, group = futures[future]
            try:
                results.append((index, group, future.result()))
            except Exception as exc:
                errors.append(f"group {index + 1}: {type(exc).__name__}: {exc}")
    fetched_at = datetime.now(timezone.utc)
    attribution = {}
    for _, _, response in results:
        values = response.get("attribution") or {}
        if isinstance(values, dict):
            attribution.update({str(key): str(value) for key, value in values.items()})
    positions = {}
    for index, group, response in results:
        connection.execute("INSERT INTO source_payloads VALUES (?, ?, ?, ?, ?)",
                           (run_id, "openwaters.geojson", fetched_at,
                            f"bbox_group_{index + 1}", _json(response)))
        for feature in response.get("features") or []:
            if not isinstance(feature, dict):
                continue
            normalized = ais.openwaters_feature_to_vessel(feature, attribution, fetched_at)
            if normalized is None:
                continue
            normalized["source_attribution"] = attribution.get(normalized.get("source"))
            observed = normalized.get("observed_at")
            observation_key = observed or fetched_at.isoformat()
            key = (f"Open Waters/{normalized.get('source') or 'unknown'}",
                   normalized["mmsi"], observation_key)
            positions[key] = (key[0], key[1], observation_key, observed, fetched_at,
                              _number(normalized.get("lat")), _number(normalized.get("lon")),
                              normalized.get("region"), normalized.get("category"),
                              _json({"feature": feature, "normalized": normalized,
                                     "source_attribution": attribution.get(normalized.get("source"))}))
    values = list(positions.values())
    if values:
        connection.executemany("""
            INSERT INTO vessel_positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, mmsi, observation_key) DO UPDATE SET
                observed_at=excluded.observed_at, collected_at=excluded.collected_at,
                latitude=excluded.latitude, longitude=excluded.longitude,
                region=excluded.region, vessel_type=excluded.vessel_type,
                payload=excluded.payload
        """, values)
    status = "success" if not errors else ("partial" if results else "error")
    details = {"endpoint": ais.OPENWATERS_API, "max_age_minutes": 120,
               "bbox_groups": len(groups), "successful_groups": len(results),
               "failed_groups": errors, "raw_feature_count": sum(
                   len(response.get("features") or []) for _, _, response in results),
               "attribution": attribution}
    _store_fetch_run(connection, run_id, "openwaters.positions", started, status, len(values),
                      details, "; ".join(errors) if errors else None)


def _aisstream_api_key():
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("AISSTREAM_API_KEY") or "").strip()
    except Exception:
        return ""


def _insert_aisstream(connection, run_id, ais):
    started = datetime.now(timezone.utc)
    api_key = _aisstream_api_key()
    if not api_key:
        _store_fetch_run(connection, run_id, "aisstream.positions", started,
                          "skipped", 0, {}, "未配置 AISSTREAM_API_KEY")
        return
    collector = None
    try:
        capture_seconds = max(15, min(300, int(os.environ.get("AISSTREAM_CAPTURE_SECONDS", "60"))))
        collector = ais.AISCollector(api_key).start()
        deadline = __import__("time").monotonic() + capture_seconds
        positions = []
        while __import__("time").monotonic() < deadline:
            positions = collector.snapshot(max_age_minutes=120)
            __import__("time").sleep(0.5)
        fetched_at = datetime.now(timezone.utc)
        values = []
        for position in positions:
            observed = position.get("observed_at")
            observation_key = observed or position.get("received_at") or fetched_at.isoformat()
            values.append((
                "AISStream", str(position["mmsi"]), observation_key, _utc(observed),
                fetched_at, _number(position.get("lat")), _number(position.get("lon")),
                position.get("region"), position.get("category"), _json(position),
            ))
        if values:
            connection.executemany("""
                INSERT INTO vessel_positions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source, mmsi, observation_key) DO UPDATE SET
                    observed_at=excluded.observed_at, collected_at=excluded.collected_at,
                    latitude=excluded.latitude, longitude=excluded.longitude,
                    region=excluded.region, vessel_type=excluded.vessel_type,
                    payload=excluded.payload
            """, values)
        status = collector.status()
        has_subscription = bool(status.get("subscription_confirmed_at"))
        result_status = "success" if positions else ("empty" if has_subscription else "error")
        details = {"provider": "AISStream", "max_age_minutes": 120,
                   "capture_seconds": capture_seconds,
                   "collector_status": status.get("status"),
                   "subscription_confirmed_at": status.get("subscription_confirmed_at"),
                   "message_count": status.get("message_count"),
                   "position_message_count": status.get("position_message_count"),
                   "static_message_count": status.get("static_message_count"),
                   "rejected_event_count": status.get("rejected_event_count")}
        _store_fetch_run(connection, run_id, "aisstream.positions", started,
                          result_status, len(values), details,
                          "AISStream已确认订阅，但采集窗口内没有有效位置报文" if result_status == "empty"
                          else "AISStream未确认订阅" if result_status == "error" else None)
    except Exception as exc:
        _store_fetch_run(connection, run_id, "aisstream.positions", started,
                          "error", 0, {}, type(exc).__name__)
    finally:
        if collector is not None:
            collector.stop()


def _source_config():
    keys = ("SEA_HISTORY_ARCHIVE_PATH", "SEA_HISTORY_BUNDLE_PATH",
            "SEA_HISTORY_BUNDLE_URL", "SEA_HISTORY_BEARER_TOKEN")
    config = {key: os.environ.get(key, "").strip() for key in keys}
    try:
        import streamlit as st
        for key in keys:
            config[key] = config[key] or str(st.secrets.get(key) or "").strip()
    except Exception:
        pass
    return config


def _insert_sea_history(connection, run_id, *, offline=False):
    started = datetime.now(timezone.utc)
    from monitor.vessels import sea_history
    config = _source_config()
    configured_bundle = config.get("SEA_HISTORY_BUNDLE_PATH") or config.get("SEA_HISTORY_BUNDLE_URL")
    archive = sea_history.archive_path(config)
    try:
        if configured_bundle and (not offline or config.get("SEA_HISTORY_BUNDLE_PATH")):
            sea_history.sync_source(config)
        if not archive.exists():
            _store_fetch_run(connection, run_id, "sea_history.authorized_events", started,
                              "skipped", 0, {}, "未配置授权交付源，且未找到已导入的事件档案")
            return
        with sqlite3.connect(archive.resolve().as_uri() + "?mode=ro", uri=True) as db:
            metadata = db.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()
            manifest = json.loads(metadata[0]) if metadata and metadata[0] else {}
            rows = db.execute("SELECT sea,mmsi,entered_at,day FROM entries").fetchall()
        values = [(sea, mmsi, entered_at, day,
                   manifest.get("source"), manifest.get("definition_id"),
                   _json(manifest)) for sea, mmsi, entered_at, day in rows]
        if values:
            connection.executemany("""
                INSERT INTO sea_history_events VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (sea, mmsi, entered_at) DO UPDATE SET
                    day=excluded.day, source=excluded.source,
                    definition_id=excluded.definition_id, manifest=excluded.manifest
            """, values)
        _store_fetch_run(connection, run_id, "sea_history.authorized_events", started,
                          "success", len(values), {"source": manifest.get("source"),
                          "definition_id": manifest.get("definition_id"),
                          "time_zone": manifest.get("timezone")})
    except Exception as exc:
        _store_fetch_run(connection, run_id, "sea_history.authorized_events", started,
                          "error", 0, {}, f"{type(exc).__name__}: {exc}")


def _insert_ais_archive(connection, run_id, additional_archives=()):
    started = datetime.now(timezone.utc)
    from monitor.vessels.ais_history import archive_path
    archives = list(dict.fromkeys([archive_path(), *additional_archives]))
    archives = [path for path in archives if path.exists()]
    if not archives:
        _store_fetch_run(connection, run_id, "ais.local_history_archive", started,
                          "skipped", 0, {}, "未找到已归档的 AIS 报告数据库")
        return
    try:
        values = []
        for archive in archives:
            with sqlite3.connect(archive.resolve().as_uri() + "?mode=ro", uri=True) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='reports'").fetchone()
                if not exists:
                    raise ValueError("现有 AIS 归档缺少 reports 表")
                rows = db.execute("SELECT mmsi,observed,source,payload FROM reports").fetchall()
            for mmsi, observed, source, payload in rows:
                record = json.loads(payload)
                values.append((str(source), str(mmsi), str(observed),
                               record.get("received_at"), _json(record)))
        if values:
            connection.executemany("""
                INSERT INTO ais_reports VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (source, mmsi, observed_at) DO UPDATE SET
                    received_at=excluded.received_at, payload=excluded.payload
            """, values)
        _store_fetch_run(connection, run_id, "ais.local_history_archive", started,
                          "success", len(values), {"source_archives": len(archives)})
    except Exception as exc:
        _store_fetch_run(connection, run_id, "ais.local_history_archive", started,
                          "error", 0, {}, f"{type(exc).__name__}: {exc}")


def _carry_forward_live_data(connection, previous):
    if previous is None:
        return
    previous_tables = {row[0] for row in previous.execute("SHOW TABLES").fetchall()}
    for table in LIVE_TABLES:
        if table not in previous_tables:
            continue
        rows = previous.execute(f'SELECT * FROM "{table}"').fetchall()
        if not rows:
            continue
        columns = len(connection.execute(f'DESCRIBE "{table}"').fetchall())
        if any(len(row) != columns for row in rows):
            continue
        placeholders = ",".join(["?"] * columns)
        connection.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)


def _collect_live_sources(connection, run_id, *, offline=False):
    from monitor.vessels.ais_history import archive_path as ais_archive_path
    preconfigured_ais_archive = ais_archive_path()
    os.environ.setdefault("AIS_ARCHIVE_PATH", str(runtime_path("ais-history.sqlite3")))
    if offline:
        for source in ("portwatch.catalog", "portwatch.daily.ports",
                       "portwatch.daily.chokepoints", "portwatch.route_risk",
                       "openwaters.positions", "aisstream.positions"):
            _store_fetch_run(connection, run_id, source, datetime.now(timezone.utc),
                              "skipped", 0, {}, "本次构建指定离线模式")
    else:
        try:
            portwatch, ais = _load_live_modules()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            for source in ("portwatch.catalog", "portwatch.daily.ports",
                           "portwatch.daily.chokepoints", "portwatch.route_risk",
                           "openwaters.positions", "aisstream.positions"):
                _store_fetch_run(connection, run_id, source, datetime.now(timezone.utc),
                                  "error", 0, {}, error)
        else:
            ports, chokes = _insert_portwatch_catalog(connection, run_id, portwatch)
            _insert_portwatch_activity(connection, run_id, portwatch, ports, chokes)
            _insert_portwatch_risk(connection, run_id, portwatch, ports)
            try:
                _insert_openwaters(connection, run_id, ais)
            except Exception as exc:
                _store_fetch_run(connection, run_id, "openwaters.positions",
                                  datetime.now(timezone.utc), "error", 0, {},
                                  f"{type(exc).__name__}: {exc}")
            _insert_aisstream(connection, run_id, ais)
    _insert_ais_archive(connection, run_id, (preconfigured_ais_archive,))
    _insert_sea_history(connection, run_id, offline=offline)


def build_database(destination: Path | None = None, *, offline: bool = False) -> tuple[Path, dict[str, int]]:
    """Refresh configured sources, then atomically replace the local database."""
    destination = (destination or runtime_path("oil-field-map.duckdb")).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".building")
    temporary.unlink(missing_ok=True)
    counts: dict[str, int] = {}
    documents = _local_documents()
    run_id = str(uuid.uuid4())
    previous = duckdb.connect(str(destination), read_only=True) if destination.exists() else None

    try:
        connection = duckdb.connect(str(temporary))
        try:
            connection.execute("BEGIN TRANSACTION")
            connection.execute("""
                CREATE TABLE database_info(key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL);
                CREATE TABLE data_sources(
                    dataset VARCHAR, source_path VARCHAR, file_bytes BIGINT,
                    sha256 VARCHAR, source_rows BIGINT
                );
                CREATE TABLE source_documents(
                    source_path VARCHAR, sha256 VARCHAR, source_kind VARCHAR,
                    source_format VARCHAR, file_bytes BIGINT, source_rows BIGINT,
                    loaded_at TIMESTAMPTZ, payload JSON,
                    PRIMARY KEY (source_path, sha256)
                );
                CREATE TABLE oilgas_assets(
                    asset_id VARCHAR, country VARCHAR, name VARCHAR, name_cn VARCHAR,
                    asset_level VARCHAR, parent_asset VARCHAR, commodity VARCHAR,
                    operating_status VARCHAR, metric_type VARCHAR, value_text VARCHAR,
                    value_number DOUBLE, unit VARCHAR, data_date VARCHAR,
                    latitude DOUBLE, longitude DOUBLE, map_drawable BOOLEAN,
                    source VARCHAR, source_url VARCHAR, payload JSON
                );
                CREATE TABLE oilgas_asset_audits(
                    review_date DATE, row_number INTEGER, country VARCHAR, name VARCHAR,
                    asset_level VARCHAR, parent_asset VARCHAR, commodity VARCHAR,
                    value_text VARCHAR, unit VARCHAR, metric_type VARCHAR,
                    operating_status VARCHAR, latitude DOUBLE, longitude DOUBLE,
                    payload JSON, source_file VARCHAR
                );
                CREATE TABLE port_activity_audits(
                    review_date DATE, observed_date DATE, row_number INTEGER,
                    sea VARCHAR, country VARCHAR, port VARCHAR, portwatch_id VARCHAR,
                    tanker_calls DOUBLE, other_cargo_calls DOUBLE,
                    latitude DOUBLE, longitude DOUBLE, payload JSON, source_file VARCHAR
                );
                CREATE TABLE port_catalog(
                    source_name VARCHAR, row_number INTEGER, name VARCHAR, country VARCHAR,
                    region VARCHAR, external_id VARCHAR, latitude DOUBLE, longitude DOUBLE,
                    payload JSON, source_file VARCHAR
                );
                CREATE TABLE portwatch_catalog(
                    node_kind VARCHAR, portid VARCHAR, name VARCHAR, country VARCHAR,
                    region VARCHAR, latitude DOUBLE, longitude DOUBLE,
                    statistics_available BOOLEAN, fetched_at TIMESTAMPTZ, payload JSON,
                    PRIMARY KEY (node_kind, portid)
                );
                CREATE TABLE portwatch_daily(
                    node_kind VARCHAR, portid VARCHAR, observed_date DATE, name VARCHAR,
                    country VARCHAR, fetched_at TIMESTAMPTZ, calls DOUBLE,
                    import_tonnes DOUBLE, export_tonnes DOUBLE,
                    choke_total_vessels DOUBLE, choke_capacity_dwt DOUBLE, payload JSON,
                    PRIMARY KEY (node_kind, portid, observed_date)
                );
                CREATE TABLE portwatch_risk_capacity(
                    portid VARCHAR PRIMARY KEY, fetched_at TIMESTAMPTZ,
                    daily_capacity_at_risk DOUBLE, payload JSON
                );
                CREATE TABLE vessel_positions(
                    source VARCHAR, mmsi VARCHAR, observation_key VARCHAR,
                    observed_at TIMESTAMPTZ, collected_at TIMESTAMPTZ,
                    latitude DOUBLE, longitude DOUBLE, region VARCHAR,
                    vessel_type VARCHAR, payload JSON,
                    PRIMARY KEY (source, mmsi, observation_key)
                );
                CREATE TABLE ais_reports(
                    source VARCHAR, mmsi VARCHAR, observed_at VARCHAR,
                    received_at VARCHAR, payload JSON,
                    PRIMARY KEY (source, mmsi, observed_at)
                );
                CREATE TABLE sea_history_events(
                    sea VARCHAR, mmsi VARCHAR, entered_at VARCHAR, day DATE,
                    source VARCHAR, definition_id VARCHAR, manifest JSON,
                    PRIMARY KEY (sea, mmsi, entered_at)
                );
                CREATE TABLE source_payloads(
                    run_id UUID, source_name VARCHAR, fetched_at TIMESTAMPTZ,
                    partition_key VARCHAR, payload JSON,
                    PRIMARY KEY (run_id, source_name, partition_key)
                );
                CREATE TABLE source_fetch_runs(
                    run_id UUID, source_name VARCHAR, started_at TIMESTAMPTZ,
                    finished_at TIMESTAMPTZ, status VARCHAR, record_count BIGINT,
                    error_message VARCHAR, details JSON,
                    PRIMARY KEY (run_id, source_name)
                );
            """)
            _carry_forward_live_data(connection, previous)
            counts["local_source_documents"] = _insert_local_documents(connection, documents)
            counts["portwatch_snapshot_rows"] = _insert_portwatch_snapshots(connection, documents)

            asset_rows = []
            for asset in ASSETS:
                asset_rows.append((
                    f"{asset['country']}/{asset['name']}", asset["country"], asset["name"],
                    asset.get("name_cn"), asset.get("asset_level"), asset.get("parent_asset"),
                    asset.get("commodity"), asset.get("operating_status"), asset.get("metric_type"),
                    asset.get("value_raw") or asset.get("value"), _number(asset.get("value_numeric")),
                    asset.get("unit"), asset.get("data_date"), _number(asset.get("map_lat")),
                    _number(asset.get("map_lon")), bool(asset.get("map_drawable")),
                    asset.get("source"), asset.get("source_url"), _json(asset),
                ))
            connection.executemany("INSERT INTO oilgas_assets VALUES (" + ",".join(["?"] * 19) + ")", asset_rows)
            counts["oilgas_assets"] = len(asset_rows)

            audit_rows = list(_asset_rows())
            connection.executemany("INSERT INTO oilgas_asset_audits VALUES (" + ",".join(["?"] * 15) + ")", audit_rows)
            counts["oilgas_asset_audits"] = len(audit_rows)

            activity_rows = list(_port_rows())
            connection.executemany("INSERT INTO port_activity_audits VALUES (" + ",".join(["?"] * 13) + ")", activity_rows)
            counts["port_activity_audits"] = len(activity_rows)

            catalog_rows = list(_catalog_rows())
            connection.executemany("INSERT INTO port_catalog VALUES (" + ",".join(["?"] * 10) + ")", catalog_rows)
            counts["port_catalog"] = len(catalog_rows)

            source_rows = _source_rows(documents)
            connection.executemany("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?)", source_rows)
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                capture_output=True, text=True, check=False,
            ).stdout.strip()
            info = (
                ("generated_at_utc", datetime.now(timezone.utc).isoformat()),
                ("source_revision", revision),
                ("schema_version", "3"),
                ("contents", "oilgas; versioned local source documents; PortWatch raw snapshots and latest 90-day regional activity; current PortWatch catalog and risk with appended snapshots; Open Waters; configured AISStream; local AIS and authorized sea-history archives"),
                ("live_refresh", str(not offline).lower()),
            )
            connection.executemany("INSERT INTO database_info VALUES (?, ?)", info)
            _collect_live_sources(connection, run_id, offline=offline)
            connection.execute("""
                CREATE OR REPLACE VIEW latest_vessel_positions AS
                SELECT * EXCLUDE (position_rank) FROM (
                    SELECT *, row_number() OVER (
                        PARTITION BY mmsi ORDER BY observed_at DESC NULLS LAST,
                        collected_at DESC) AS position_rank
                    FROM vessel_positions
                ) WHERE position_rank = 1
            """)
            for table in LIVE_TABLES:
                counts[table] = connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
            if previous is not None:
                previous.close()
        temporary.replace(destination)
    except Exception:
        if previous is not None:
            previous.close()
        temporary.unlink(missing_ok=True)
        raise

    return destination, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Output DuckDB path (default: runtime/oil-field-map.duckdb)")
    parser.add_argument("--offline", action="store_true",
                        help="Rebuild from saved sources only; retain prior live tables")
    args = parser.parse_args()
    path, counts = build_database(args.output, offline=args.offline)
    with duckdb.connect(str(path), read_only=True) as connection:
        statuses = connection.execute("""
            SELECT source_name, status, record_count, error_message
            FROM source_fetch_runs WHERE run_id = (
                SELECT run_id FROM source_fetch_runs
                GROUP BY run_id ORDER BY max(started_at) DESC LIMIT 1
            ) ORDER BY source_name
        """).fetchall()
    print(json.dumps({"database": str(path), "tables": counts,
                      "source_fetches": statuses}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
