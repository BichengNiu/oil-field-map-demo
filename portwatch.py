"""IMF PortWatch port and chokepoint indicators for the map.

The region boxes are an explicit, editable definition of "near" the five waters.
The catalog also includes source-backed supplementary ports with unknown activity.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st
import port_inventory

ROOT = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS = f"{ROOT}/PortWatch_ports_database/FeatureServer/0/query"
DAILY = f"{ROOT}/Daily_Ports_Data/FeatureServer/0/query"
CHOKEPOINTS = f"{ROOT}/PortWatch_chokepoints_database/FeatureServer/0/query"
CHOKEPOINT_DAILY = f"{ROOT}/Daily_Chokepoints_Data/FeatureServer/0/query"
SPILLOVERS = f"{ROOT}/spillovers_port_level_impact/FeatureServer/0/query"
SOURCE = "https://portwatch.imf.org/pages/data-and-methodology"
MODULE_VERSION = 5

SHIP_TYPES = ("container", "dry_bulk", "general_cargo", "roro", "tanker")
FOCUS_CHOKEPOINT_IDS = ("chokepoint1", "chokepoint4", "chokepoint6")
CHOKEPOINT_LABELS = {
    "chokepoint1": "苏伊士运河",
    "chokepoint4": "曼德海峡",
    "chokepoint6": "霍尔木兹海峡",
}


def _valid_port_ids(ids: tuple[str, ...]) -> bool:
    return all(re.fullmatch(r"(?:port|fso)\d+", port_id) for port_id in ids)


def _activity_ids(ids: tuple[str, ...]) -> tuple[str, ...]:
    unknown = [pid for pid in ids if not _valid_port_ids((pid,))
               and pid not in port_inventory.SUPPLEMENTAL_IDS]
    if unknown:
        raise ValueError("无效或未登记的港口编号")
    return tuple(pid for pid in ids if _valid_port_ids((pid,)))


def _valid_chokepoint_ids(ids: tuple[str, ...]) -> bool:
    return all(re.fullmatch(r"chokepoint\d+", point_id) for point_id in ids)

# south, north, west, east. Order assigns ports in overlapping boxes only once.
REGIONS = {
    "霍尔木兹海峡": (25.7, 27.4, 55.9, 57.5),
    "阿曼湾": (22.0, 26.6, 56.0, 61.8),
    "波斯湾": (23.5, 30.9, 47.0, 56.8),
    "苏伊士运河": (29.4, 31.6, 31.7, 33.5),
    "曼德海峡": (11.0, 15.4, 42.0, 45.7),
}


def _query(url: str, **params: object) -> dict:
    request = Request(f"{url}?{urlencode({**params, 'f': 'json'})}",
                      headers={"User-Agent": "oil-field-map-demo/1.0"})
    with urlopen(request, timeout=35) as response:
        result = json.load(response)
    if "error" in result:
        raise ValueError(f"PortWatch API: {result['error'].get('message', result['error'])}")
    return result


def region_for(lat: float, lon: float) -> str | None:
    for name, (south, north, west, east) in REGIONS.items():
        if south <= lat <= north and west <= lon <= east:
            return name
    return None


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def port_catalog() -> list[dict]:
    # Query only the union of the documented geographic boxes. ArcGIS pages results.
    where = " OR ".join(
        f"(lat >= {south} AND lat <= {north} AND lon >= {west} AND lon <= {east})"
        for south, north, west, east in REGIONS.values()
    )
    found = []
    offset = 0
    while True:
        page = _query(PORTS, where=where, outFields="portid,portname,country,lat,lon",
                      returnGeometry="false", resultOffset=offset, resultRecordCount=1000,
                      orderByFields="portid ASC")
        items = page.get("features", [])
        found.extend(item["attributes"] for item in items)
        if len(items) < 1000:
            break
        offset += len(items)
    if len({item["portid"] for item in found}) != len(found):
        raise ValueError("PortWatch点位库出现重复编号")
    ports = []
    for item in found:
        if item["lat"] is None or item["lon"] is None:
            continue
        region = region_for(item["lat"], item["lon"])
        if region:
            ports.append({"portid": item["portid"], "name": item["portname"],
                          "country": item["country"], "lat": item["lat"],
                          "lon": item["lon"], "region": region})
    return port_inventory.enrich(ports)


@st.cache_data(ttl=3600, show_spinner=False)
def latest_date() -> date:
    data = _query(DAILY, where="1=1", returnGeometry="false",
                  outStatistics=json.dumps([{"statisticType": "max", "onStatisticField": "date",
                                             "outStatisticFieldName": "latest_date"}]))
    value = data["features"][0]["attributes"]["latest_date"]
    if not value:
        raise ValueError("PortWatch 尚无可用日期")
    return date.fromisoformat(value)


@st.cache_data(ttl=3600, show_spinner=False)
def daily_activity(day: date, port_ids: tuple[str, ...]) -> dict[str, dict]:
    # DateOnly SQL literal; never interpolate user text into the where clause.
    result = {}
    port_ids = _activity_ids(port_ids)
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not _valid_port_ids(ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{p}'" for p in ids)
        where = f"date = DATE '{day.isoformat()}' AND portid IN ({quoted})"
        offset = 0
        while True:
            page = _query(DAILY, where=where, returnGeometry="false", resultOffset=offset,
                          resultRecordCount=1000, orderByFields="portid ASC",
                          outFields="date,portid,portname,country,ISO3,portcalls,"
                                    "portcalls_container,portcalls_dry_bulk,"
                                    "portcalls_general_cargo,portcalls_roro,portcalls_tanker,"
                                    "portcalls_cargo,import,export,import_container,export_container,"
                                    "import_dry_bulk,export_dry_bulk,"
                                    "import_general_cargo,export_general_cargo,"
                                    "import_roro,export_roro,import_tanker,export_tanker,"
                                    "import_cargo,export_cargo")
            items = page.get("features", [])
            for item in items:
                values = item["attributes"]
                if values["portid"] in result:
                    raise ValueError(f"PortWatch 日活动出现重复港口记录：{values['portid']}")
                result[values["portid"]] = values
            if len(items) < 1000:
                break
            offset += len(items)
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def rolling_activity(day: date, port_ids: tuple[str, ...], days: int = 7) -> dict[str, dict]:
    """Return complete-window port indicators and the preceding-window baseline.

    Do not turn missing days into zeros; keep raw zero-valued source records.
    """
    if days not in (7, 30):
        raise ValueError("仅支持 7 天或 30 天窗口")
    grouped: dict[str, dict[date, dict]] = {port_id: {} for port_id in port_ids}
    port_ids = _activity_ids(port_ids)
    current_first = day - timedelta(days=days - 1)
    previous_first = day - timedelta(days=2 * days - 1)
    previous_last = current_first - timedelta(days=1)
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not _valid_port_ids(ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{p}'" for p in ids)
        where = (f"date >= DATE '{previous_first.isoformat()}' AND date <= DATE '{day.isoformat()}' "
                 f"AND portid IN ({quoted})")
        offset = 0
        while True:
            page = _query(DAILY, where=where, returnGeometry="false", resultOffset=offset,
                          resultRecordCount=1000, orderByFields="portid ASC,date ASC",
                          outFields="date,portid,portname,country,ISO3,portcalls,"
                                    "portcalls_container,portcalls_dry_bulk,"
                                    "portcalls_general_cargo,portcalls_roro,portcalls_tanker,"
                                    "portcalls_cargo,import,export,import_container,export_container,"
                                    "import_dry_bulk,export_dry_bulk,"
                                    "import_general_cargo,export_general_cargo,"
                                    "import_roro,export_roro,import_tanker,export_tanker,"
                                    "import_cargo,export_cargo")
            items = page.get("features", [])
            for item in items:
                value = item["attributes"]
                value_day = date.fromisoformat(value["date"])
                if value["portid"] not in grouped or not previous_first <= value_day <= day:
                    raise ValueError("PortWatch返回窗口之外或未请求的记录")
                if value_day in grouped[value["portid"]]:
                    raise ValueError(f"PortWatch重复港口/日期：{value['portid']}/{value_day}")
                grouped[value["portid"]][value_day] = value
            if len(items) < 1000:
                break
            offset += len(items)
    summary = {}
    for port_id, by_day in grouped.items():
        values = [value for value_day, value in by_day.items()
                  if current_first <= value_day <= day]
        previous = [value for value_day, value in by_day.items()
                    if previous_first <= value_day <= previous_last]
        current_complete = len(values) == days
        previous_complete = len(previous) == days
        calls_complete = current_complete and all(v.get("portcalls") is not None for v in values)
        def positive_days(field):
            return (sum(v[field] > 0 for v in values)
                    if current_complete and all(v.get(field) is not None for v in values) else None)
        result = {"observed_days": len(values), "previous_observed_days": len(previous),
                  "window_days": days, "active_days": positive_days("portcalls"),
                  "tanker_positive_days": positive_days("portcalls_tanker"),
                  "cargo_positive_days": positive_days("portcalls_cargo"),
                  "tanker_calls_zero_volume_days": (sum(
                      v["portcalls_tanker"] > 0 and v["import_tanker"] + v["export_tanker"] == 0
                      for v in values) if current_complete and all(v.get(f) is not None
                      for v in values for f in ("portcalls_tanker", "import_tanker", "export_tanker")) else None)}
        for kind in (*SHIP_TYPES, "cargo"):
            call_field, import_field, export_field = (f"portcalls_{kind}", f"import_{kind}", f"export_{kind}")
            calls_ok = current_complete and all(v.get(call_field) is not None for v in values)
            volume_ok = current_complete and all(v.get(f) is not None
                                                 for v in values for f in (import_field, export_field))
            result[f"avg_calls_{kind}"] = sum(v[call_field] for v in values) / days if calls_ok else None
            result[f"avg_handled_{kind}"] = (sum(v[import_field] + v[export_field] for v in values) / days
                                            if volume_ok else None)
            result[f"window_calls_{kind}"] = sum(v[call_field] for v in values) if calls_ok else None

        previous_ok = previous_complete and all(
            value.get("portcalls") is not None for value in previous)
        total_calls = sum(value["portcalls"] for value in values) if calls_complete else None
        total_import = sum(value["import"] for value in values) if current_complete and all(v.get("import") is not None for v in values) else None
        total_export = sum(value["export"] for value in values) if current_complete and all(v.get("export") is not None for v in values) else None
        previous_calls = (sum(value["portcalls"] for value in previous)
                          if previous_ok else None)
        result["avg_calls"] = total_calls / days if total_calls is not None else None
        result["avg_handled"] = ((total_import + total_export) / days
                                 if total_import is not None and total_export is not None else None)
        result["active_day_rate"] = (result["active_days"] / days * 100
                                     if calls_complete else None)
        result["average_cargo_per_call"] = (
            (total_import + total_export) / total_calls
            if total_calls and total_import is not None and total_export is not None else None)
        total_trade = ((total_import + total_export)
                       if total_import is not None and total_export is not None else None)
        result["trade_balance_index"] = (
            (total_export - total_import) / total_trade * 100 if total_trade else None)
        result["activity_index"] = (
            total_calls / previous_calls * 100
            if total_calls is not None and previous_calls else None)
        result["window_import"] = total_import
        result["window_export"] = total_export
        for kind in SHIP_TYPES:
            kind_calls = result.get(f"window_calls_{kind}")
            result[f"share_{kind}"] = (
                kind_calls / total_calls * 100
                if kind_calls is not None and total_calls else None)
        summary[port_id] = result
    return summary


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def port_risk_capacity(port_ids: tuple[str, ...]) -> dict[str, float | None]:
    """Aggregate historical daily at-risk capacity over each port's outbound routes."""
    totals: dict[str, float | None] = {port_id: None for port_id in port_ids}
    port_ids = _activity_ids(port_ids)
    statistic = json.dumps([{
        "statisticType": "sum", "onStatisticField": "daily_capacity_at_risk",
        "outStatisticFieldName": "risk_capacity",
    }])
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not _valid_port_ids(ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{port_id}'" for port_id in ids)
        where = f"from_portid IN ({quoted})"
        page = _query(SPILLOVERS, where=where, returnGeometry="false",
                      groupByFieldsForStatistics="from_portid", outStatistics=statistic,
                      orderByFields="from_portid ASC", outFields="from_portid")
        for item in page.get("features", []):
            value = item["attributes"]
            capacity = value.get("risk_capacity")
            totals[value["from_portid"]] = float(capacity) if capacity is not None else None
    return totals


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def chokepoint_catalog() -> list[dict]:
    ids = FOCUS_CHOKEPOINT_IDS
    quoted = ",".join(f"'{point_id}'" for point_id in ids)
    page = _query(CHOKEPOINTS, where=f"portid IN ({quoted})", returnGeometry="false",
                  outFields="portid,portname,fullname,lat,lon", resultRecordCount=100)
    found = {item["attributes"]["portid"]: item["attributes"]
             for item in page.get("features", [])}
    output = []
    for point_id in ids:
        if point_id in found:
            row = dict(found[point_id])
            row["name_cn"] = CHOKEPOINT_LABELS[point_id]
            output.append(row)
    return output


@st.cache_data(ttl=3600, show_spinner=False)
def latest_chokepoint_date() -> date:
    data = _query(CHOKEPOINT_DAILY, where="1=1", returnGeometry="false",
                  outStatistics=json.dumps([{"statisticType": "max", "onStatisticField": "date",
                                             "outStatisticFieldName": "latest_date"}]))
    value = data["features"][0]["attributes"]["latest_date"]
    if not value:
        raise ValueError("PortWatch 尚无可用咽喉点日期")
    return date.fromisoformat(value)


@st.cache_data(ttl=3600, show_spinner=False)
def chokepoint_activity(day: date, chokepoint_ids: tuple[str, ...]) -> dict[str, dict]:
    if not _valid_chokepoint_ids(chokepoint_ids):
        raise ValueError("无效的 PortWatch 咽喉点编号")
    quoted = ",".join(f"'{point_id}'" for point_id in chokepoint_ids)
    where = f"date = DATE '{day.isoformat()}' AND portid IN ({quoted})"
    page = _query(
        CHOKEPOINT_DAILY, where=where, returnGeometry="false", resultRecordCount=100,
        outFields="date,portid,portname,n_total,n_container,n_dry_bulk,"
                  "n_general_cargo,n_roro,n_tanker,n_cargo,capacity,"
                  "capacity_container,capacity_dry_bulk,capacity_general_cargo,"
                  "capacity_roro,capacity_tanker,capacity_cargo")
    result = {}
    for item in page.get("features", []):
        value = item["attributes"]
        if value["portid"] in result:
            raise ValueError(f"PortWatch 咽喉点日活动出现重复记录：{value['portid']}")
        result[value["portid"]] = value
    return result


def decorate_chokepoints(points: list[dict], activity: dict[str, dict]) -> list[dict]:
    output = []
    for point in points:
        row = dict(point)
        values = activity.get(point["portid"])
        row["has_data"] = values is not None
        if values:
            row.update(values)
        output.append(row)
    return output


def decorate(ports: list[dict], activity: dict[str, dict],
             rolling: dict[str, dict] | None = None,
             risk_capacity: dict[str, float] | None = None) -> list[dict]:
    output = []
    for port in ports:
        row = dict(port)
        values = activity.get(port["portid"])
        row["has_data"] = values is not None
        if rolling is not None:
            row.update(rolling.get(port["portid"], {}))
        if risk_capacity is not None:
            row["risk_capacity"] = risk_capacity.get(port["portid"])
        if values:
            row.update({key: values.get(key) for key in (
                "portcalls", "portcalls_container", "portcalls_dry_bulk",
                "portcalls_general_cargo", "portcalls_roro", "portcalls_tanker",
                "portcalls_cargo", "import", "export", "import_tanker",
                "export_tanker", "import_cargo", "export_cargo")})
            # 'cargo' is the PortWatch non-tanker vessel category, including
            # container, dry bulk, general cargo and Ro-Ro. Do not sum with tanker.
            # Missing observations stay missing; an observed zero stays zero.
            for kind in ("tanker", "cargo"):
                imported, exported = row[f"import_{kind}"], row[f"export_{kind}"]
                row[f"handled_{kind}"] = (imported + exported
                                           if imported is not None and exported is not None else None)
            row["handled"] = (row["import"] + row["export"]
                              if row["import"] is not None and row["export"] is not None else None)
        output.append(row)
    return output
