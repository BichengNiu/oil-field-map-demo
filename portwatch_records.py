"""Shared PortWatch field definitions and daily-record indexing."""

from __future__ import annotations

SHIP_TYPE_LABELS = {
    "container": "集装箱船",
    "dry_bulk": "干散货船",
    "general_cargo": "普通货船",
    "roro": "滚装船",
    "tanker": "油轮/液货船",
}
SHIP_TYPES = tuple(SHIP_TYPE_LABELS)
EXPORT_SHIP_LABELS = {**SHIP_TYPE_LABELS, "cargo": "货船合计"}
PORT_METRICS = ["portcalls", "import", "export"] + [
    f"{metric}_{ship}"
    for metric in ("portcalls", "import", "export")
    for ship in EXPORT_SHIP_LABELS
]
CHOKE_METRICS = ["n_total", "capacity"] + [
    f"{metric}_{ship}" for metric in ("n", "capacity") for ship in EXPORT_SHIP_LABELS
]


def latest_by_node(rows: list[dict], *, require_date: bool = True) -> dict[str, dict]:
    """Keep the first record on ties; optionally retain undated catalog records."""
    latest = {}
    for row in rows:
        node_id = str(row.get("portid", ""))
        day = str(row.get("date", ""))
        if (
            node_id
            and (day or not require_date)
            and (node_id not in latest or day > str(latest[node_id].get("date", "")))
        ):
            latest[node_id] = row
    return latest


def port_status_label(port: dict, day) -> str:
    status = {
        "normal": "正常", "operating": "正常", "open": "正常",
        "stopped": "停运", "closed": "停运", "suspended": "停运", "shutdown": "停运",
    }.get(port.get("port_operating_status"), "未知")
    evidence_day = str(port.get("port_operating_status_as_of") or "")[:10]
    if day and len(evidence_day) == 10 and evidence_day[4:5] == "-" and evidence_day > str(day):
        return "未知"
    return status
