"""Complete, source-count-checked PortWatch downloads with dated provenance."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import zipfile
import zlib

import portwatch as pw

VERSION = 1
FIRST_DAY = date(2019, 1, 1)
PAGE_SIZE = 1000
BATCH_SIZE = 60
XLSX_ROW_LIMIT = 20_000
KINDS = {"ports": "港口", "chokepoints": "咽喉要道"}
TYPES = {"container": "集装箱船", "dry_bulk": "干散货船", "general_cargo": "普通货船",
         "roro": "滚装船", "tanker": "油轮/液货船", "cargo": "货船合计"}
PORT_METRICS = ["portcalls", "import", "export"] + [
    f"{metric}_{ship}" for metric in ("portcalls", "import", "export") for ship in TYPES]
CHOKE_METRICS = ["n_total", "capacity"] + [
    f"{metric}_{ship}" for metric in ("n", "capacity") for ship in TYPES]
BASE_FIELDS = ["date", "portid", "portname", "country", "ISO3", "region", "lat", "lon"]
CATALOG_FIELDS = ["node_kind", "portid", "node_name", "country", "region", "lat", "lon",
                  "statistics_available", "first_available_utc", "latest_available_utc",
                  "source_url", "coverage_note"]
COVERAGE_FIELDS = ["node_kind", "portid", "node_name", "status", "first_available_utc",
                   "latest_available_utc", "export_first_utc", "export_last_utc", "records",
                   "requested_days", "missing_days", "missing_intervals_utc", "null_metric_cells"]


class DownloadError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day(value) -> date:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).date()
    return date.fromisoformat(str(value))


def node(kind: str, raw: dict) -> dict:
    if kind not in KINDS:
        raise DownloadError("数据类型无效")
    pid = str(raw["portid"])
    supported = pw.valid_port_ids((pid,)) if kind == "ports" else pw.valid_chokepoint_ids((pid,))
    return {"node_kind": kind, "portid": pid,
            "node_name": raw.get("name_cn") or raw.get("name") or raw.get("portname") or pid,
            "country": raw.get("country"),
            "region": raw.get("region") or raw.get("name_cn"),
            "lat": raw.get("lat"), "lon": raw.get("lon"),
            "statistics_available": supported,
            "source_url": raw.get("inventory_source_url") or raw.get("source_url") or pw.SOURCE,
            "coverage_note": raw.get("coverage_note", "AIS推算日度活动；覆盖受信号与识别方法影响")}


def _endpoint(kind: str) -> str:
    return pw.endpoint_for(kind)


def _ids_where(ids: tuple[str, ...], kind: str) -> str:
    if kind not in ("ports", "chokepoints"):
        raise DownloadError("未知的PortWatch数据类型")
    valid = pw.valid_port_ids(ids) if kind == "ports" else pw.valid_chokepoint_ids(ids)
    if not ids or not valid or len(set(ids)) != len(ids):
        raise DownloadError("节点编号为空、重复或无效")
    return "portid IN (" + ",".join(f"'{pid}'" for pid in ids) + ")"


def bounds(kind: str, ids: tuple[str, ...]) -> tuple[dict, list[dict]]:
    output, queries = {}, []
    for offset in range(0, len(ids), BATCH_SIZE):
        batch = ids[offset:offset + BATCH_SIZE]
        where = _ids_where(batch, kind)
        statistics = [
            {"statisticType": "min", "onStatisticField": "date", "outStatisticFieldName": "first_date"},
            {"statisticType": "max", "onStatisticField": "date", "outStatisticFieldName": "last_date"},
            {"statisticType": "count", "onStatisticField": "ObjectId", "outStatisticFieldName": "records"},
        ]
        response = pw.query(_endpoint(kind), where=where, returnGeometry="false",
                             outStatistics=json.dumps(statistics), groupByFieldsForStatistics="portid",
                             resultRecordCount=PAGE_SIZE)
        if response.get("exceededTransferLimit"):
            raise DownloadError("节点日期范围查询被截断")
        for item in response.get("features", []):
            row = item["attributes"]
            pid = row["portid"]
            if pid not in batch or pid in output:
                raise DownloadError("日期范围查询返回未请求或重复节点")
            first, last = _day(row["first_date"]), _day(row["last_date"])
            if first > last or last > datetime.now(timezone.utc).date() or int(row["records"]) <= 0:
                raise DownloadError("源站日期范围或记录数无效")
            output[pid] = {"first": first.isoformat(), "last": last.isoformat(),
                           "records": int(row["records"])}
        queries.append({"endpoint": _endpoint(kind), "where": where, "operation": "node_date_bounds",
                        "retrieved_at_utc": _now()})
    return output, queries


def _cache_path() -> Path:
    return Path(os.environ.get("PORTWATCH_DOWNLOAD_CACHE") or
                Path(__file__).with_name("runtime") / "portwatch-download-cache.sqlite3")


def _cache(key: str, payload: dict | None = None) -> dict | None:
    """Cache only a validated complete query; a broken cache never hides source errors."""
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path, timeout=10) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS queries (key TEXT PRIMARY KEY, saved REAL, payload BLOB)")
            if payload is not None:
                conn.execute("INSERT OR REPLACE INTO queries VALUES (?, ?, ?)",
                             (key, datetime.now(timezone.utc).timestamp(),
                              zlib.compress(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())))
                conn.execute("DELETE FROM queries WHERE saved < ?", (datetime.now(timezone.utc).timestamp() - 7 * 86400,))
                return None
            row = conn.execute("SELECT saved,payload FROM queries WHERE key=?", (key,)).fetchone()
        if row and datetime.now(timezone.utc).timestamp() - row[0] < 86400:
            return json.loads(zlib.decompress(row[1]))
    except (OSError, sqlite3.Error, ValueError, zlib.error):
        pass
    return None


def fetch_window(kind: str, ids: tuple[str, ...], first: date, last: date,
                 force: bool = False, progress=None,
                 cache_revision: int = 0) -> tuple[list[dict], dict]:
    where = f"{_ids_where(ids, kind)} AND date >= DATE '{first}' AND date <= DATE '{last}'"
    endpoint = _endpoint(kind)
    metrics = PORT_METRICS if kind == "ports" else CHOKE_METRICS
    source_fields = ["ObjectId", "date", "portid", "portname"] + (["country", "ISO3"] if kind == "ports" else []) + metrics
    key = hashlib.sha256(json.dumps(
        [VERSION, endpoint, where, source_fields, cache_revision]).encode()).hexdigest()
    cached = None if force else _cache(key)
    if cached:
        return cached["rows"], {**cached["query"], "cache_hit": True}

    def count():
        value = pw.query(endpoint, where=where, returnGeometry="false", returnCountOnly="true")
        if "count" not in value:
            raise DownloadError("源站未返回用于核对分页的总记录数")
        return int(value["count"])

    expected = count()
    rows, keys = [], set()
    offset = 0
    while offset < expected:
        page = pw.query(endpoint, where=where, returnGeometry="false",
                         outFields=",".join(source_fields), orderByFields="portid ASC,date ASC,ObjectId ASC",
                         resultOffset=offset, resultRecordCount=PAGE_SIZE)
        items = page.get("features", [])
        if not items:
            raise DownloadError(f"{KINDS[kind]} {first}—{last} 分页提前结束（{offset}/{expected}）")
        for item in items:
            row = dict(item["attributes"])
            day = _day(row.get("date"))
            pid = row.get("portid")
            record_key = (pid, day)
            if pid not in ids or not first <= day <= last or record_key in keys:
                raise DownloadError(f"返回重复或超出请求范围的记录：{pid}/{day}")
            for metric in metrics:
                value = row.get(metric)
                if value is not None and (not isinstance(value, (int, float)) or
                                          not math.isfinite(value) or value < 0):
                    raise DownloadError(f"{pid}/{day} 的{metric}不是有效非负数值")
            row["date"] = day.isoformat()
            row.pop("ObjectId", None)
            rows.append(row)
            keys.add(record_key)
        offset += len(items)
        if progress:
            progress(f"{KINDS[kind]} {first}—{last}：{offset:,}/{expected:,} 条")
    if len(rows) != expected or count() != expected:
        raise DownloadError(f"{KINDS[kind]} {first}—{last} 源记录数发生变化或分页不完整，请重新生成")
    query = {"endpoint": endpoint, "where": where, "out_fields": source_fields,
             "retrieved_at_utc": _now(), "cache_hit": False, "source_count": expected,
             "exported_query_rows": len(rows), "count_verified": True}
    _cache(key, {"rows": rows, "query": query})
    return rows, query


def _years(first: date, last: date):
    current = first
    while current <= last:
        end = min(last, date(current.year, 12, 31))
        yield current, end
        current = end + timedelta(days=1)


def _missing_intervals(first: date, last: date, days: set[date]) -> str:
    intervals, beginning = [], None
    current = first
    while current <= last:
        if current not in days and beginning is None:
            beginning = current
        if current in days and beginning is not None:
            intervals.append(f"{beginning}/{current - timedelta(days=1)}")
            beginning = None
        current += timedelta(days=1)
    if beginning is not None:
        intervals.append(f"{beginning}/{last}")
    return ";".join(intervals)


def _derive(rows: list[dict], kind: str) -> None:
    metrics = ["portcalls", "import", "export"] if kind == "ports" else ["n_total", "capacity"]
    by_node = defaultdict(dict)
    for row in rows:
        by_node[row["portid"]][_day(row["date"])] = row
    for row in rows:
        day, series = _day(row["date"]), by_node[row["portid"]]
        for window in (7, 30):
            reports = [series.get(day - timedelta(days=i)) for i in range(window)]
            available = sum(report is not None for report in reports)
            row[f"observed_days_{window}d"] = available
            for metric in metrics:
                values = [report.get(metric) if report else None for report in reports]
                row[f"avg_{metric}_{window}d"] = (sum(values) / window if all(
                    value is not None for value in values) else None)


def collect(nodes: list[dict], mode: str, first: date | None = None, last: date | None = None,
            derived: bool = False, force: bool = False, progress=None) -> dict:
    if mode not in ("latest", "history", "all"):
        raise DownloadError("时间模式无效")
    if not nodes or any(n.get("node_kind") not in KINDS for n in nodes) or len(
        {(n['node_kind'], n['portid']) for n in nodes}) != len(nodes):
        raise DownloadError("请选择不重复的节点")
    if mode == "history" and (first is None or last is None or first > last or first < FIRST_DAY
                              or last > datetime.now(timezone.utc).date()):
        raise DownloadError("历史日期须在2019-01-01至今日UTC之间，开始日不得晚于结束日")
    datasets, metadata, coverage, catalog = {}, [], [], []
    for kind in KINDS:
        selected = [n for n in nodes if n["node_kind"] == kind]
        if not selected:
            continue
        ids = tuple(sorted(n["portid"] for n in selected if n["statistics_available"]))
        if progress:
            progress(f"查询{KINDS[kind]}各节点可用日期…")
        limits, queries = bounds(kind, ids)
        metadata.extend(queries)
        periods = defaultdict(list)
        wanted = {}
        for n in selected:
            limit = limits.get(n["portid"])
            entry = {**n, "first_available_utc": limit["first"] if limit else None,
                     "latest_available_utc": limit["last"] if limit else None}
            catalog.append(entry)
            if mode == "latest":
                begin = end = _day(limit["last"]) if limit else None
            elif mode == "all":
                begin, end = (_day(limit["first"]), _day(limit["last"])) if limit else (None, None)
            else:
                begin, end = first, last
            wanted[n["portid"]] = (begin, end)
            if not limit:
                continue
            fetch_first = max(_day(limit["first"]), begin - timedelta(days=29) if derived else begin)
            fetch_last = min(_day(limit["last"]), end)
            if fetch_first <= fetch_last:
                # Calendar years bound query size and make repeat downloads reusable.
                for a, b in _years(fetch_first, fetch_last):
                    periods[(a, b)].append(n["portid"])
        reports, all_keys = [], set()
        for (begin, end), pids in sorted(periods.items()):
            for offset in range(0, len(pids), BATCH_SIZE):
                chunk = tuple(sorted(pids[offset:offset + BATCH_SIZE]))
                rows, query = fetch_window(kind, chunk, begin, end,
                    force=force or mode == "latest" or end >= datetime.now(timezone.utc).date() - timedelta(days=7),
                    progress=progress)
                metadata.append(query)
                for row in rows:
                    key = (row["portid"], row["date"])
                    if key in all_keys:
                        raise DownloadError("分块查询间存在重复节点日期")
                    all_keys.add(key)
                    reports.append(row)
        if derived:
            _derive(reports, kind)
        selected_by_id = {n["portid"]: n for n in selected}
        exported = []
        for row in reports:
            begin, end = wanted[row["portid"]]
            if begin <= _day(row["date"]) <= end:
                n = selected_by_id[row["portid"]]
                exported.append({**row, "region": n["region"], "lat": n["lat"], "lon": n["lon"],
                                 "source_url": pw.SOURCE})
        exported.sort(key=lambda r: (r["portid"], r["date"]))
        by_id = defaultdict(list)
        for row in exported:
            by_id[row["portid"]].append(row)
        metrics = PORT_METRICS if kind == "ports" else CHOKE_METRICS
        for n in selected:
            pid = n["portid"]
            rows, limit = by_id[pid], limits.get(pid)
            begin, end = wanted[pid]
            expected = (end - begin).days + 1 if begin and end else 0
            dates = {_day(r["date"]) for r in rows}
            if mode == "latest" and limit and len(rows) != 1:
                raise DownloadError(f"{pid} 的最新可用日未取到唯一记录")
            if mode == "all" and limit and len(rows) != limit["records"]:
                raise DownloadError(f"{pid} 全历史记录数与节点统计不一致，请勾选重新读取源站后重试")
            coverage.append({"node_kind": kind, "portid": pid, "node_name": n["node_name"],
                "status": "no_independent_statistics" if not n["statistics_available"] else
                          "no_records_in_requested_window" if not rows else
                          "gaps" if len(rows) < expected else "complete",
                "first_available_utc": limit["first"] if limit else None,
                "latest_available_utc": limit["last"] if limit else None,
                "export_first_utc": min(dates).isoformat() if dates else None,
                "export_last_utc": max(dates).isoformat() if dates else None,
                "records": len(rows), "requested_days": expected, "missing_days": expected - len(dates),
                "missing_intervals_utc": _missing_intervals(begin, end, dates) if begin and end else "",
                "null_metric_cells": sum(r.get(m) is None for r in rows for m in metrics)})
        datasets[kind] = exported
    manifest = {"schema_version": VERSION, "source": "IMF PortWatch / UN Global Platform",
                "source_url": pw.SOURCE, "generated_at_utc": _now(), "timezone": "UTC",
                "mode": mode, "requested_start_utc": first.isoformat() if first else None,
                "requested_end_utc": last.isoformat() if last else None, "derived": derived,
                "node_count": len(nodes), "row_counts": {k: len(v) for k, v in datasets.items()},
                "fetch_complete": True, "coverage": coverage, "queries": metadata,
                "notes": ["最新指每节点自身最新可用日，保留实际日期及真实零值。",
                          "日表只含源站真实记录。缺失日不补零，见coverage.csv。",
                          "港口进出口是AIS推算货量（公吨）；要道capacity为通行运力（载重吨），不能当作实际贸易货量。",
                          "历史缓存最长24小时；queries记录实际抓取时间。上游数据会修订。",
                          "无独立统计的补充港口保留在节点目录。",
                          "7/30日均值须有连续窗口内全部有效数值，否则留空；前置日期只用于计算，不进入导出日表。",
                          "原始数字未转换成万吨；CSV以UTF-8 BOM保存，文本公式前缀加单引号避免误执行。",
                          "使用与再分发遵守IMF PortWatch来源条款；此下载不另授予数据许可。"]}
    return {"datasets": datasets, "catalog": catalog, "coverage": coverage,
            "manifest": manifest, "dictionary": dictionary(derived)}


def columns(kind: str, derived: bool = False) -> list[str]:
    metrics = PORT_METRICS if kind == "ports" else CHOKE_METRICS
    extra = []
    if derived:
        mean_metrics = ["portcalls", "import", "export"] if kind == "ports" else ["n_total", "capacity"]
        for window in (7, 30):
            extra += [f"observed_days_{window}d"] + [f"avg_{metric}_{window}d" for metric in mean_metrics]
    return BASE_FIELDS + metrics + extra + ["source_url"]


def dictionary(derived: bool) -> list[dict]:
    entries = []
    labels = {"date": ("观测日", "UTC日期"), "portid": ("稳定节点编号", "文本"),
              "portname": ("源站节点名称", "文本"), "country": ("源站国家", "文本"),
              "ISO3": ("国家三位代码", "文本"), "region": ("项目监测水域", "文本"),
              "lat": ("节点纬度", "度"), "lon": ("节点经度", "度"), "source_url": ("数据来源", "URL")}
    for kind in KINDS:
        for field in columns(kind, derived):
            if field in labels:
                label, unit = labels[field]
            elif field.startswith("observed_days"):
                label, unit = "对应连续窗口内有源记录的天数", "天"
            else:
                metric = field.removeprefix("avg_")
                window = ""
                if field.startswith("avg_"):
                    metric, window = metric.rsplit("_", 1)
                prefix = next((p for p in ("portcalls", "import", "export", "capacity", "n_total", "n")
                               if metric == p or metric.startswith(p + "_")), "")
                names = {"portcalls": "有效进港", "import": "估算进口货量", "export": "估算出口货量",
                         "capacity": "通行运力", "n_total": "总通行", "n": "通行"}
                ship = metric[len(prefix):].lstrip("_")
                label = names.get(prefix, metric) + ("（" + TYPES[ship] + "）" if ship in TYPES else "")
                unit = "艘次" if prefix in ("portcalls", "n", "n_total") else "载重吨" if prefix == "capacity" else "公吨"
                if window:
                    label += f"，{window[:-1]}日均值"
                    unit += "/日"
            entries.append({"dataset": kind, "field": field, "meaning": label, "unit": unit,
                            "missing": "空值为未报告或窗口不完整；0为源站报告零值"})
    return entries


def csv_bytes(rows: list[dict], fields: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: "'" + value if isinstance(value, str) and value.startswith(
            ("=", "+", "-", "@", "\t", "\r")) else value for key, value in row.items()})
    return buffer.getvalue().encode("utf-8-sig")


def zip_bytes(result: dict) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for kind, rows in result["datasets"].items():
            years = sorted({r["date"][:4] for r in rows})
            if len(years) > 1:
                for year in years:
                    archive.writestr(f"{kind}_daily_{year}.csv", csv_bytes(
                        [r for r in rows if r["date"].startswith(year)], columns(kind, result["manifest"]["derived"])))
            else:
                archive.writestr(f"{kind}_daily.csv", csv_bytes(rows, columns(kind, result["manifest"]["derived"])))
        archive.writestr("nodes.csv", csv_bytes(result["catalog"], CATALOG_FIELDS))
        archive.writestr("coverage.csv", csv_bytes(result["coverage"], COVERAGE_FIELDS))
        archive.writestr("data_dictionary.csv", csv_bytes(result["dictionary"], ["dataset", "field", "meaning", "unit", "missing"]))
        archive.writestr("manifest.json", json.dumps(result["manifest"], ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "IMF PortWatch 日度下载\n" + "\n".join(result["manifest"]["notes"]) +
                         "\n来源：" + pw.SOURCE + "\n生成UTC：" + result["manifest"]["generated_at_utc"])
    return output.getvalue()


def xlsx_bytes(result: dict) -> bytes:
    """Write a small, typed, filterable Excel workbook without extra runtime packages."""
    datasets = result["datasets"]
    records = sum(map(len, datasets.values()))
    if records > XLSX_ROW_LIMIT:
        raise DownloadError(f"Excel适合中小范围下载（最多{XLSX_ROW_LIMIT:,}条）；请用ZIP下载全量数据")
    sheets = []
    for kind, rows in datasets.items():
        sheets.append(("港口日表" if kind == "ports" else "要道日表",
                       columns(kind, result["manifest"]["derived"]), rows))
    manifest = result["manifest"]
    about = [{"项目": "来源", "内容": manifest["source"]},
             {"项目": "来源网址", "内容": manifest["source_url"]},
             {"项目": "生成时间（UTC）", "内容": manifest["generated_at_utc"]},
             {"项目": "时区", "内容": manifest["timezone"]},
             {"项目": "时间模式", "内容": manifest["mode"]},
             {"项目": "请求开始日（UTC）", "内容": manifest["requested_start_utc"]},
             {"项目": "请求结束日（UTC）", "内容": manifest["requested_end_utc"]},
             {"项目": "节点数", "内容": manifest["node_count"]},
             {"项目": "来源取数校验", "内容": "通过" if manifest["fetch_complete"] else "未通过"}]
    about.extend({"项目": f"说明 {index}", "内容": note}
                 for index, note in enumerate(manifest["notes"], 1))
    queries = []
    for query in manifest["queries"]:
        queries.append({field: (json.dumps(query.get(field), ensure_ascii=False)
                                if isinstance(query.get(field), (dict, list)) else query.get(field))
                        for field in ("operation", "endpoint", "where", "retrieved_at_utc",
                                      "source_count", "exported_query_rows", "count_verified",
                                      "cache_hit", "out_fields")})
    sheets.extend([
        ("下载说明", ["项目", "内容"], about),
        ("节点目录", CATALOG_FIELDS, result["catalog"]),
        ("覆盖情况", COVERAGE_FIELDS, result["coverage"]),
        ("数据字典", ["dataset", "field", "meaning", "unit", "missing"], result["dictionary"]),
        ("来源查询", ["operation", "endpoint", "where", "retrieved_at_utc", "source_count",
                      "exported_query_rows", "count_verified", "cache_hit", "out_fields"], queries),
    ])

    def xlcol(index: int) -> str:
        out = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            out = chr(65 + remainder) + out
        return out

    def xml_text(value) -> str:
        text = str(value)
        text = "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 32 and ord(ch) != 0xFFFE)
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace('"', "&quot;").replace("'", "&apos;"))

    def cell(value, address: str, style: int) -> str:
        if value is None or value == "":
            return f'<c r="{address}" s="{style}"/>'
        if isinstance(value, bool):
            return f'<c r="{address}" s="{style}" t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)) and math.isfinite(value):
            return f'<c r="{address}" s="{style}"><v>{value}</v></c>'
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                serial = (_day(value) - date(1899, 12, 30)).days
                return f'<c r="{address}" s="2"><v>{serial}</v></c>'
            except ValueError:
                pass
        return f'<c r="{address}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{xml_text(value)}</t></is></c>'

    files = {}
    files["[Content_Types].xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' +
        "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 for i in range(1, len(sheets) + 1)) + "</Types>")
    files["_rels/.rels"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')
    workbook_sheets, relationships = [], []
    for index, (name, fields, rows) in enumerate(sheets, 1):
        esc_name = xml_text(name)
        workbook_sheets.append(f'<sheet name="{esc_name}" sheetId="{index}" r:id="rId{index}"/>')
        relationships.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>')
        xml_rows = []
        for rownum, values in enumerate([fields, *rows], 1):
            cells = []
            for col, field in enumerate(fields, 1):
                val = field if rownum == 1 else values.get(field)
                numeric_style = 4 if field.startswith("avg_") else 3 if (
                    field in ("portcalls", "n_total", "capacity") or field.startswith(("portcalls_", "n_"))) else 5 if field in ("lat", "lon") else 0
                cells.append(cell(val, f"{xlcol(col)}{rownum}", 1 if rownum == 1 else numeric_style))
            xml_rows.append(f'<row r="{rownum}" spans="1:{max(1, len(fields))}">{"".join(cells)}</row>')
        lastcell = f"{xlcol(len(fields))}{max(1, len(rows) + 1)}"
        files[f"xl/worksheets/sheet{index}.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            '<cols>' + "".join(f'<col min="{i}" max="{i}" width="{min(38,max(12,len(field)+2))}" customWidth="1"/>'
                                for i, field in enumerate(fields, 1)) + '</cols>'
            + '<sheetData>' + "".join(xml_rows) + '</sheetData>'
            + (f'<autoFilter ref="A1:{lastcell}"/>' if rows else '')
            + '</worksheet>')
    files["xl/workbook.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<bookViews><workbookView/></bookViews><sheets>' + "".join(workbook_sheets) + '</sheets></workbook>')
    files["xl/_rels/workbook.xml.rels"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(relationships) +
        f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + '</Relationships>')
    files["xl/styles.xml"] = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<numFmts count="4"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/>'
        '<numFmt numFmtId="165" formatCode="#,##0"/><numFmt numFmtId="166" formatCode="#,##0.000"/>'
        '<numFmt numFmtId="167" formatCode="0.000000"/></numFmts>'
        '<fonts count="2"><font><sz val="10"/><name val="Arial"/></font>'
        '<font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Arial"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF29435C"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
        '<border><left/><right/><top/><bottom style="thin"><color rgb="FFFFFFFF"/></bottom><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
        '<xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()
