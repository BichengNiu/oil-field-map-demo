"""IMF PortWatch daily port activity, joined to its official port locations.

The region boxes are an explicit, editable definition of "near" the five waters.
Only ports in PortWatch's coverage are included, not every berth or oil terminal.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import streamlit as st

ROOT = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS = f"{ROOT}/PortWatch_ports/FeatureServer/1/query"
DAILY = f"{ROOT}/Daily_Ports_Data/FeatureServer/0/query"
SOURCE = "https://portwatch.imf.org/pages/data-and-methodology"

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
        f"(lat >= {south} AND lat <= {north} AND long >= {west} AND long <= {east})"
        for south, north, west, east in REGIONS.values()
    )
    found = []
    offset = 0
    while True:
        page = _query(PORTS, where=where, outFields="portid,portname,country,lat,long",
                      returnGeometry="false", resultOffset=offset, resultRecordCount=1000)
        items = page.get("features", [])
        found.extend(item["attributes"] for item in items)
        if len(items) < 1000:
            break
        offset += len(items)
    ports = []
    for item in found:
        if item["lat"] is None or item["long"] is None:
            continue
        region = region_for(item["lat"], item["long"])
        if region:
            ports.append({"portid": item["portid"], "name": item["portname"],
                          "country": item["country"], "lat": item["lat"],
                          "lon": item["long"], "region": region})
    return sorted(ports, key=lambda p: (p["region"], p["country"], p["name"]))


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
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not all(p.startswith("port") and p[4:].isdigit() for p in ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{p}'" for p in ids)
        where = f"date = DATE '{day.isoformat()}' AND portid IN ({quoted})"
        offset = 0
        while True:
            page = _query(DAILY, where=where, returnGeometry="false", resultOffset=offset,
                          resultRecordCount=1000,
                          outFields="date,portid,portcalls_tanker,portcalls_cargo,"
                                    "import_tanker,export_tanker,import_cargo,export_cargo")
            items = page.get("features", [])
            for item in items:
                values = item["attributes"]
                result[values["portid"]] = values
            if len(items) < 1000:
                break
            offset += len(items)
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def rolling_activity(day: date, port_ids: tuple[str, ...], days: int = 7) -> dict[str, dict]:
    """Return calendar-day averages only when every day has a source record.

    Do not turn missing days into zeros; keep raw zero-valued source records.
    """
    if days not in (7, 30):
        raise ValueError("仅支持 7 天或 30 天窗口")
    grouped: dict[str, dict[date, dict]] = {port_id: {} for port_id in port_ids}
    for start in range(0, len(port_ids), 80):
        ids = port_ids[start:start + 80]
        if not all(p.startswith("port") and p[4:].isdigit() for p in ids):
            raise ValueError("无效的 PortWatch 港口编号")
        quoted = ",".join(f"'{p}'" for p in ids)
        first = day - timedelta(days=days - 1)
        where = (f"date >= DATE '{first.isoformat()}' AND date <= DATE '{day.isoformat()}' "
                 f"AND portid IN ({quoted})")
        offset = 0
        while True:
            page = _query(DAILY, where=where, returnGeometry="false", resultOffset=offset,
                          resultRecordCount=1000,
                          outFields="date,portid,portcalls_tanker,portcalls_cargo,"
                                    "import_tanker,export_tanker,import_cargo,export_cargo")
            items = page.get("features", [])
            for item in items:
                value = item["attributes"]
                grouped[value["portid"]][date.fromisoformat(value["date"])] = value
            if len(items) < 1000:
                break
            offset += len(items)
    summary = {}
    for port_id, by_day in grouped.items():
        values = list(by_day.values())
        result = {"observed_days": len(values), "window_days": days,
                  "tanker_positive_days": sum((v["portcalls_tanker"] or 0) > 0 for v in values),
                  "cargo_positive_days": sum((v["portcalls_cargo"] or 0) > 0 for v in values),
                  "tanker_calls_zero_volume_days": sum(
                      (v["portcalls_tanker"] or 0) > 0
                      and (v["import_tanker"] or 0) + (v["export_tanker"] or 0) == 0
                      for v in values)}
        for kind in ("tanker", "cargo"):
            fields = (f"portcalls_{kind}", f"import_{kind}", f"export_{kind}")
            complete = len(values) == days and all(
                v.get(field) is not None for v in values for field in fields)
            result[f"avg_calls_{kind}"] = (
                sum(v[fields[0]] for v in values) / days if complete else None)
            result[f"avg_handled_{kind}"] = (
                sum(v[fields[1]] + v[fields[2]] for v in values) / days if complete else None)
        summary[port_id] = result
    return summary


def decorate(ports: list[dict], activity: dict[str, dict],
             rolling: dict[str, dict] | None = None) -> list[dict]:
    output = []
    for port in ports:
        row = dict(port)
        values = activity.get(port["portid"])
        row["has_data"] = values is not None
        if rolling is not None:
            row.update(rolling.get(port["portid"], {}))
        if values:
            row.update({key: values.get(key) for key in (
                "portcalls_tanker", "portcalls_cargo", "import_tanker",
                "export_tanker", "import_cargo", "export_cargo")})
            # 'cargo' is the PortWatch non-tanker vessel category, including
            # container, dry bulk, general cargo and Ro-Ro. Do not sum with tanker.
            # Missing observations stay missing; an observed zero stays zero.
            for kind in ("tanker", "cargo"):
                imported, exported = row[f"import_{kind}"], row[f"export_{kind}"]
                row[f"handled_{kind}"] = (imported + exported
                                           if imported is not None and exported is not None else None)
        output.append(row)
    return output
