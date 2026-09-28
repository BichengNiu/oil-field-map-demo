"""Recheck every mapped port against raw PortWatch day, 7-day and 30-day data.

Run: python audit_ports.py (writes a dated CSV in the current directory).
"""

from __future__ import annotations

import csv

import portwatch


def main() -> None:
    ports = portwatch.port_catalog()
    day = portwatch.latest_date()
    ids = tuple(port["portid"] for port in ports)
    daily = portwatch.daily_activity(day, ids)
    week = portwatch.rolling_activity(day, ids, 7)
    month = portwatch.rolling_activity(day, ids, 30)
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
            flags.append("当日缺报")
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
            "来源": portwatch.SOURCE,
        })
    filename = f"PORT_ACTIVITY_AUDIT_{day.isoformat()}.csv"
    with open(filename, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(filename, "ports", len(rows), "today tanker zero", sum(r["当日油轮艘次"] == 0 for r in rows),
          "30d tanker zero", sum(r["30日油轮日均艘次"] == 0 for r in rows),
          "30d both zero", sum(r["30日油轮日均艘次"] == 0 and r["30日其他货轮日均艘次"] == 0 for r in rows))


if __name__ == "__main__":
    main()
