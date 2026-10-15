"""Repair node/day holes from the retained archive start, with source evidence.

Only verified empty upstream results may remain missing; never manufacture zeros.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import re

import data_store

AUDIT_PREFIX = "portwatch_history_coverage:"
SOURCE_GAP_TTL = timedelta(days=7)
MAX_CHUNK_DAYS = 90


def _dates(first, last):
    for offset in range((last - first).days + 1):
        yield first + timedelta(days=offset)


def _intervals(days):
    first = previous = None
    for day in sorted(days):
        if previous is not None and day != previous + timedelta(days=1):
            yield first, previous
            first = None
        if first is None:
            first = day
        previous = day
    if first is not None:
        yield first, previous


def _ids(kind):
    return tuple(sorted(str(row["portid"]) for row in data_store.load_catalog(kind)
                        if kind == "chokepoints" or row.get("statistics_available", bool(
                            re.fullmatch(r"(?:port|fso)\d+", str(row.get("portid", "")))))))


def _state(kind, ids=None, end=None):
    ids = _ids(kind) if ids is None else tuple(sorted(set(ids)))
    audit = data_store.meta(AUDIT_PREFIX + kind, {})
    with data_store.connect() as conn:
        earliest, latest = conn.execute(
            "SELECT MIN(day),MAX(day) FROM portwatch_daily WHERE kind=?", [kind]
        ).fetchone()
        if end is None:
            end = max(filter(None, (latest, date.fromisoformat(audit["last_day"])
                                    if audit.get("last_day") else None)), default=None)
        if not ids or end is None:
            raise ValueError(f"{kind} 缺少历史范围或统计节点")
        first = min(filter(None, (earliest, end.replace(year=end.year - 1, day=1),
                                  date.fromisoformat(audit["first_day"])
                                  if audit.get("first_day") else None)))
        stored = set(conn.execute(
            "SELECT node_id,day FROM portwatch_daily WHERE kind=? AND day BETWEEN ? AND ? "
            "AND node_id IN (" + ",".join("?" for _ in ids) + ")",
            [kind, first, end, *ids],
        ).fetchall())
    expected = {(node, day) for node in ids for day in _dates(first, end)}
    return {"kind": kind, "ids": ids, "first": first, "last": end,
            "expected": expected, "missing": expected - stored, "audit": audit}


def _verified_missing(audit, now):
    verified = {}
    for gap in audit.get("source_missing", []):
        checked = datetime.fromisoformat(gap["verified_at"])
        if timedelta(0) <= now - checked < SOURCE_GAP_TTL:
            for day in _dates(date.fromisoformat(gap["first"]), date.fromisoformat(gap["last"])):
                verified[gap["node_id"], day] = checked
    return verified


def _report(state, verified):
    missing = state["missing"]
    unverified = missing - verified.keys()
    return {"first_day": state["first"].isoformat(), "last_day": state["last"].isoformat(),
            "nodes": len(state["ids"]), "expected_records": len(state["expected"]),
            "stored_records": len(state["expected"]) - len(missing),
            "source_missing_records": len(missing) - len(unverified),
            "unverified_missing_records": len(unverified),
            "status": "unverified_gaps" if unverified else "source_gaps" if missing else "complete"}


def needs_repair(now=None):
    now = now or datetime.now(timezone.utc)
    for kind in ("ports", "chokepoints"):
        try:
            state = _state(kind)
        except ValueError:
            return True
        if not state["audit"] or state["missing"] - _verified_missing(state["audit"], now).keys():
            return True
    return False


def repair(kind, ids, end, now=None):
    import portwatch_downloads
    now = now or datetime.now(timezone.utc)
    state = _state(kind, ids, end)
    verified = _verified_missing(state["audit"], now)
    unknown = state["missing"] - verified.keys()
    by_node = defaultdict(set)
    for node, day in unknown:
        by_node[node].add(day)
    batches = defaultdict(list)
    for node, days in by_node.items():
        for first, last in _intervals(days):
            while first <= last:
                stop = min(last, first + timedelta(days=MAX_CHUNK_DAYS - 1))
                batches[first, stop].append(node)
                first = stop + timedelta(days=1)
    queries, returned = [], set()
    for (first, last), nodes in sorted(batches.items()):
        nodes.sort()
        for offset in range(0, len(nodes), portwatch_downloads.BATCH_SIZE):
            chunk = tuple(nodes[offset:offset + portwatch_downloads.BATCH_SIZE])
            rows, query = portwatch_downloads.fetch_window(kind, chunk, first, last, force=True)
            if not query.get("count_verified"):
                raise ValueError(f"{kind} 历史补缺未完成上游记录数校验")
            requested = {(node, day) for node in chunk for day in _dates(first, last)}
            keys = {(str(row["portid"]), date.fromisoformat(str(row["date"])[:10])) for row in rows}
            if not keys <= requested or len(keys) != len(rows):
                raise ValueError(f"{kind} 历史补缺返回重复或越界记录")
            returned.update(keys)
            for key in requested:
                verified[key] = now
            queries.append(query)
    after = _state(kind, ids, end)
    if returned & after["missing"]:
        raise ValueError(f"{kind} 上游已返回记录但未成功入库")
    report = _report(after, verified)
    if report["unverified_missing_records"]:
        raise ValueError(f"{kind} 仍有未校验的历史日期缺口")
    # Retain dated evidence only for actual source omissions; retry after 7 days.
    remaining = defaultdict(set)
    for node, day in after["missing"]:
        remaining[node, verified[node, day]].add(day)
    gaps = [{"node_id": node, "first": first.isoformat(), "last": last.isoformat(),
             "verified_at": checked.isoformat()}
            for (node, checked), days in sorted(remaining.items())
            for first, last in _intervals(days)]
    report.update({"node_ids": list(ids), "checked_at": now.isoformat(), "source_missing": gaps,
                   "repaired_records": len(state["missing"]) - len(after["missing"]),
                   "repair_queries": queries})
    data_store.set_meta(AUDIT_PREFIX + kind, report)
    return report


def validate_all(now=None):
    now = now or datetime.now(timezone.utc)
    reports = {}
    for kind in ("ports", "chokepoints"):
        state = _state(kind)
        report = _report(state, _verified_missing(state["audit"], now))
        if not state["audit"] or report["unverified_missing_records"]:
            raise ValueError(f"{kind} 历史完整性校验失败：未校验缺口 {report['unverified_missing_records']} 条")
        reports[kind] = report
    return reports
