"""Read-only AIS history: count observed vessels, never position messages."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import json

import streamlit as st
import ais
import data_store
import port_charts


def flag_label(row):
    return row.get("flag_country") or row.get("flag") or "未知船籍"


def destination_label(row):
    return str(row.get("destination") or "").strip() or "未知目的地"


def matches(row, flags, destinations):
    return flag_label(row) in flags and destination_label(row) in destinations


def metrics(vessels, available):
    def count(predicate):
        return sum(predicate(row) for row in vessels) if available else "—"
    return [
        ("航行中", count(lambda r: r.get("sog") is not None and r["sog"] >= .5)),
        ("停泊中", count(lambda r: r.get("sog") is not None and r["sog"] < .5)),
        ("油轮/液货船", count(lambda r: r.get("category") == "tanker")),
        ("货船", count(lambda r: r.get("category") == "cargo")),
        ("其他/未知船型", count(lambda r: r.get("category") not in ("tanker", "cargo"))),
        ("中国籍船", count(lambda r: r.get("flag") == "CN")),
    ]


@st.cache_data(max_entries=12, show_spinner=False)
def history(last: date, snapshot_identity: tuple) -> list[dict]:
    with data_store.connect() as conn:
        rows = conn.execute("""SELECT payload FROM ais_reports
            WHERE observed < CAST(? AS DATE) + INTERVAL 1 DAY
            ORDER BY observed, source""", [last]).fetchall()
    return [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in rows]


def bucket(day, aggregation):
    if aggregation == "周度":
        return day-timedelta(days=day.weekday())
    if aggregation == "月度":
        return day.replace(day=1)
    if aggregation == "年度":
        return day.replace(month=1, day=1)
    if aggregation != "日度":
        raise ValueError("未知聚合方式")
    return day


def aggregate(rows, first, last, aggregation, flags, destinations):
    observed = defaultdict(set)
    vessels = defaultdict(set)
    for row in rows:
        timestamp = ais.parse_utc(row.get("observed_at"))
        if timestamp is None or not first <= timestamp.date() <= last:
            continue
        region = row.get("region")
        start = bucket(timestamp.date(), aggregation)
        observed[start].add(region)
        if matches(row, flags, destinations) and row.get("mmsi"):
            vessels[start, region].add(str(row["mmsi"]))
    result = []
    cursor = bucket(first, aggregation)
    while cursor <= last:
        end = (cursor+timedelta(days=6) if aggregation == "周度" else
               cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1]) if aggregation == "月度" else
               cursor.replace(month=12, day=31) if aggregation == "年度" else cursor)
        record = {"date": cursor, "period_start": max(first, cursor), "period_end": min(last, end)}
        for region in ais.REGIONS:
            record[region] = len(vessels[cursor, region]) if region in observed[cursor] else None
        result.append(record)
        cursor = end+timedelta(days=1)
    return result


@st.cache_data(max_entries=12, show_spinner=False)
def chart_images(rows: tuple, aggregation):
    fields = ("date", "period_start", "period_end", *ais.REGIONS)
    records = [dict(zip(fields, row)) for row in rows]
    labels = {region: f"{region}观测船舶数" for region in ais.REGIONS}
    return port_charts.render_chart_images(records, labels, aggregation, ytitle="艘", point_markers=True)
