"""Recheck every mapped port against raw PortWatch day, 7-day and 30-day data.

Run: python audit_ports.py (writes a dated CSV in the current directory).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import argparse
from datetime import timedelta, date
from pathlib import Path

import portwatch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-date", type=date.fromisoformat, default=date(2026, 10, 1))
    review_date = parser.parse_args().review_date.isoformat()
    # Capture the actual source rows used in this run, even when run repeatedly.
    for func in (portwatch.port_catalog, portwatch.latest_date, portwatch.daily_activity,
                 portwatch.rolling_activity, portwatch.chokepoint_activity,
                 portwatch.latest_chokepoint_date):
        func.clear()
    original_query = portwatch._query
    raw = {}
    def capture(url, **params):
        page = original_query(url, **params)
        if url == portwatch.DAILY:
            for feature in page.get("features", []):
                row = feature["attributes"]
                if "date" in row and "portid" in row:
                    key = (row["portid"], row["date"])
                    if key in raw and raw[key] != row:
                        raise ValueError(f"同次审计源记录发生变化：{key}，需重跑")
                    raw[key] = row
        return page
    portwatch._query = capture
    ports = portwatch.port_catalog()
    day = portwatch.latest_date()
    ids = tuple(port["portid"] for port in ports)
    daily = portwatch.daily_activity(day, ids)
    week = portwatch.rolling_activity(day, ids, 7)
    month = portwatch.rolling_activity(day, ids, 30)
    # Independently reconcile all source catalog pages to the spatial query.
    global_rows = []
    offset = 0
    while True:
        page = original_query(portwatch.PORTS, where="1=1", outFields="portid,portname,country,lat,lon",
                              returnGeometry="false", orderByFields="portid ASC",
                              resultOffset=offset, resultRecordCount=1000)
        items = page.get("features", [])
        global_rows.extend(f["attributes"] for f in items)
        if not page.get("exceededTransferLimit") and len(items) < 1000:
            break
        if not items:
            raise ValueError("PortWatch全球点位分页未前进")
        offset += len(items)
    assert len({r["portid"] for r in global_rows}) == len(global_rows), "全球点位分页重复"
    regional = {r["portid"] for r in global_rows if r.get("lat") is not None
                and r.get("lon") is not None and (r["country"] in portwatch.GULF_COUNTRIES
                or portwatch.region_for(r["lat"], r["lon"]))}
    assert regional == {p["portid"] for p in ports if portwatch._valid_port_ids((p["portid"],))}
    # Independent arithmetic on saved raw rows, not equality with a second call
    # to the same aggregation function.
    consistency_issues = []
    rounding_differences = []
    for row in raw.values():
        for prefix in ("portcalls", "import", "export"):
            components = [row.get(f"{prefix}_{kind}") for kind in portwatch.SHIP_TYPES]
            total = row.get(prefix)
            if total is not None and all(v is not None for v in components):
                difference = total - sum(components)
                if difference:
                    rounding_differences.append([row["portid"], row["date"], prefix, difference])
                # Calls must reconcile exactly. Volume fields arrive as integer
                # tonnes: allow <5t across five components; do not change source values.
                if abs(difference) >= (5 if prefix != "portcalls" else 0.0001):
                    consistency_issues.append([row["portid"], row["date"], prefix, difference])
    for days, calculated in ((7, week), (30, month)):
        for pid in ids:
            observed = [r for (rp, rd), r in raw.items() if rp == pid
                        and (day - timedelta(days=days - 1)).isoformat() <= rd <= day.isoformat()]
            for kind in portwatch.SHIP_TYPES:
                field = f"portcalls_{kind}"
                expected = (sum(r[field] for r in observed) / days
                            if len(observed) == days and all(r.get(field) is not None for r in observed) else None)
                assert calculated[pid][f"avg_calls_{kind}"] == expected, (pid, days, kind)
            for field, key in (("import", "window_import"), ("export", "window_export")):
                expected = (sum(r[field] for r in observed) if len(observed) == days
                            and all(r.get(field) is not None for r in observed) else None)
                assert calculated[pid][key] == expected, (pid, days, field)
    rows = []
    for port in ports:
        pid = port["portid"]
        d, w, m = daily.get(pid, {}), week[pid], month[pid]
        def handled(kind: str):
            imported, exported = d.get(f"import_{kind}"), d.get(f"export_{kind}")
            return imported + exported if imported is not None and exported is not None else None

        day_tanker = d.get("portcalls_tanker")
        month_tanker = m.get("avg_calls_tanker")
        flags = []
        if not d:
            flags.append("无独立PortWatch统计；不可填0" if not portwatch._valid_port_ids((pid,)) else "当日缺报")
        elif d.get("portname") != port["name"] or d.get("country") != port["country"]:
            flags.append("点位与日表名称或国家不一致")
        if w["observed_days"] < 7 or m["observed_days"] < 30:
            flags.append("窗口源记录不全")
        if day_tanker == 0 and (w["tanker_positive_days"] or 0) > 0:
            flags.append("当日油轮零但7日有挂靠")
        if day_tanker and handled("tanker") == 0:
            flags.append("当日有油轮挂靠但估算货量零")
        if month_tanker == 0:
            flags.append("30日油轮挂靠全零：源覆盖待核")
        if m["avg_calls_cargo"] == 0 and month_tanker == 0:
            flags.append("30日两类挂靠全零：源覆盖待核")
        if m["tanker_calls_zero_volume_days"]:
            flags.append("30日内存在有油轮挂靠但估算货量零")
        rows.append({
            "水域": port["region"], "国家": port["country"], "港口": port["name"],
            "PortWatch ID": pid, "日期UTC": day.isoformat(),
            "点位库港名": port["name"], "日活动港名": d.get("portname"),
            "点位库国家": port["country"], "日活动国家": d.get("country"),
            "当日油轮艘次": day_tanker, "当日油轮卸货吨": d.get("import_tanker"),
            "当日油轮装货吨": d.get("export_tanker"), "当日油轮装卸吨": handled("tanker"),
            "当日其他货轮艘次": d.get("portcalls_cargo"),
            "当日其他货轮卸货吨": d.get("import_cargo"),
            "当日其他货轮装货吨": d.get("export_cargo"),
            "当日其他货轮装卸吨": handled("cargo"),
            "7日有效天数": w["observed_days"],
            "7日油轮有挂靠天数": w["tanker_positive_days"],
            "7日油轮日均艘次": w["avg_calls_tanker"],
            "7日油轮日均装卸吨": w["avg_handled_tanker"],
            "7日其他货轮有挂靠天数": w["cargo_positive_days"],
            "7日其他货轮日均艘次": w["avg_calls_cargo"],
            "7日其他货轮日均装卸吨": w["avg_handled_cargo"],
            "30日有效天数": m["observed_days"],
            "30日油轮有挂靠天数": m["tanker_positive_days"],
            "30日油轮日均艘次": m["avg_calls_tanker"],
            "30日油轮日均装卸吨": m["avg_handled_tanker"],
            "30日油轮有挂靠但估算货量零天数": m["tanker_calls_zero_volume_days"],
            "30日其他货轮有挂靠天数": m["cargo_positive_days"],
            "30日其他货轮日均艘次": m["avg_calls_cargo"],
            "30日其他货轮日均装卸吨": m["avg_handled_cargo"],
            "复核提示": "；".join(flags) or "当日记录与窗口记录已核对",
            "目录覆盖": port.get("coverage_note"),
            "纬度": port["lat"], "经度": port["lon"],
            "停复运状态": port["port_operating_status_label"],
            "状态截至": port["port_operating_status_as_of"],
            "状态依据": port["port_status_basis"],
            "状态证据": port["port_status_evidence_url"],
            "来源": port.get("source_url", portwatch.SOURCE),
        })
    filename = f"PORT_ACTIVITY_AUDIT_{review_date}_OBS_{day.isoformat()}.csv"
    with open(filename, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    raw_file = Path(f"PORTWATCH_RAW_{review_date}_OBS_{day.isoformat()}.json.gz")
    raw_bytes = (json.dumps(sorted(raw.values(), key=lambda r: (r["portid"], r["date"])),
                           ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    raw_file.write_bytes(gzip.compress(raw_bytes, mtime=0))
    choke_day = portwatch.latest_chokepoint_date()
    chokes = portwatch.chokepoint_activity(choke_day, portwatch.FOCUS_CHOKEPOINT_IDS)
    assert set(chokes) == set(portwatch.FOCUS_CHOKEPOINT_IDS)
    Path(f"PORT_AUDIT_SUMMARY_{review_date}.json").write_text(json.dumps({
        "review_date": review_date,
        "port_date": day.isoformat(), "chokepoint_date": choke_day.isoformat(),
        "world_portwatch_rows": len(global_rows), "regional_portwatch_rows": len(regional),
        "scope": "原五水域经纬度框并海湾八国全境；具名设施单列且不借用邻港统计",
        "gulf_portwatch_rows": sum(r["country"] in portwatch.GULF_COUNTRIES for r in global_rows),
        "supplemental_rows": sum(not p["statistics_available"] for p in ports),
        "combined_catalog_rows": len(ports), "raw_daily_rows": len(raw),
        "raw_file": raw_file.name, "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "sum_consistency_issues": consistency_issues, "rounding_differences": rounding_differences,
        "volume_check_tolerance_tonnes": "绝对差<5，五类整吨字段；仅检查阈值，不修正源值",
        "chokepoints": list(chokes.values()),
        "limitations": "PortWatch AIS识别与货量估算，非实际船舶逐艘或海关吞吐验证；NGA快照无观测日期",
    }, ensure_ascii=False, indent=2) + "\n")
    print(filename, "ports", len(rows), "today tanker zero", sum(r["当日油轮艘次"] == 0 for r in rows),
          "30d tanker zero", sum(r["30日油轮日均艘次"] == 0 for r in rows),
          "30d both zero", sum(r["30日油轮日均艘次"] == 0 and r["30日其他货轮日均艘次"] == 0 for r in rows))


if __name__ == "__main__":
    main()
