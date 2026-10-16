"""Versioned, source-backed facility classification; independent of AIS activity.

Explicit WPI terminal names establish the facility type only. They do not
establish cargo shares, hub rank or present operating status.
"""
from __future__ import annotations

REVIEWED_PORT_TYPES = {
    "port744": {
        "label": "综合港 / 集装箱枢纽（集装箱业务突出，同时处理散货、液体货物和车辆）",
        "source_url": "https://www.dpworld.com/en/ports-terminals/uae/jebel-ali-port",
        "reviewed_at": "2026-10-16",
    },
    "port362": {
        "label": "综合港 / 油品枢纽（石油储运、加油、干散货、集装箱等）",
        "source_url": "https://fujairahport.ae/",
        "reviewed_at": "2026-10-16",
    },
}


def port_type_label(port: dict) -> str:
    reviewed = REVIEWED_PORT_TYPES.get(str(port.get("portid", "")))
    if reviewed:
        return reviewed["label"]
    # Source names are retained in the published catalog, including WPI aliases.
    names = [port.get("name"), *port.get("wpi_names", [])]
    names = " | ".join(str(name or "").casefold() for name in names)
    if "lng" in names and "terminal" in names:
        return "液化天然气码头"
    if "lpg" in names and "terminal" in names:
        return "液化石油气码头"
    if "crude" in names and "terminal" in names:
        return "原油码头"
    if "refined product" in names and "terminal" in names:
        return "成品油码头"
    if "oil" in names and ("terminal" in names or "oil-loading" in names):
        return "油品码头"
    if "gas tanker terminal" in names:
        return "气体船码头"
    return "待核实"
