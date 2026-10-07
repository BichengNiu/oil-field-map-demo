"""Optional continuous collection worker; the Streamlit app only calls collect_once on click.

Run this as a supervised service only when continuous sampling is intended.
The command line works without Streamlit.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
import threading
import uuid

import ais
import ais_history
import data_store
import sea_tracking

logger = logging.getLogger(__name__)


def collect_once():
    sea_tracking.start_collection()
    started = datetime.now(timezone.utc)
    details, rows, inserted, snapshot = {}, [], 0, None
    status = "error"
    try:
        snapshot = ais.openwaters_snapshot(max_age_minutes=120)
        rejected = 0
        for row in snapshot.get("reports", snapshot.get("vessels", [])):
            try:
                rows.append(ais_history.normalize_report(row))
            except ValueError:
                rejected += 1
        inserted = ais_history.archive_reports(rows)
        details = {"source_error": snapshot.get("error"), "truncated": snapshot.get("truncated"),
                   "requested_groups": snapshot.get("requested_groups"),
                   "successful_groups": snapshot.get("successful_groups"),
                   "rejected_reports": rejected, "inserted_reports": inserted,
                   "attribution": snapshot.get("attribution"), "coverage": "observed AIS sample"}
        status = "ok" if not snapshot.get("error") and not snapshot.get("truncated") and not rejected else "partial"
    except Exception as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning("AIS collection failed: %s", type(exc).__name__)
    finished = datetime.now(timezone.utc)
    with data_store.connect() as conn:
        conn.execute("INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, "Open Waters", started, finished, status, len(rows), data_store.encode(details)))
        if not inserted:
            data_store.bump_revision("sea", conn)
    snapshot = snapshot or {"vessels": [], "error": details.get("error"), "fetched_at": finished.isoformat()}
    if status != "ok":
        snapshot["archive_error"] = details.get("error") or details.get("source_error") or "上游截断或报告未通过校验"
    else:
        snapshot["archive_error"] = None
    # The map receives only the latest display positions, not an archive-sized payload.
    snapshot.pop("reports", None)
    snapshot["refresh_summary"] = {
        "fetched": len(rows),
        "inserted": inserted,
        "rejected": details.get("rejected_reports", 0),
        "truncated": bool(details.get("truncated")),
    }
    return snapshot


class CollectionService:
    def __init__(self, interval=60, with_portwatch=True):
        self.interval = max(60, interval)
        self.with_portwatch = with_portwatch
        self._stop = threading.Event()
        self._refresh = threading.Event()
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._snapshot = {"vessels": [], "error": None, "archive_error": None}
        self._thread = None
        self._port_thread = None

    def start(self):
        if self._thread is None or not self._thread.is_alive():
            sea_tracking.start_collection()
            self._thread = threading.Thread(target=self._run, name="four-sea-collector", daemon=True)
            self._thread.start()
            if self.with_portwatch:
                self._port_thread = threading.Thread(target=self._run_ports, name="portwatch-collector", daemon=True)
                self._port_thread.start()
        return self

    def _run_ports(self):
        # Give the first page a chance to render from persisted facts before
        # this worker competes for the shared PortWatch request lock.
        if self._stop.wait(30):
            return
        while not self._stop.is_set():
            collect_portwatch_run()
            self._stop.wait(3600)

    def _run(self):
        while not self._stop.is_set():
            try:
                snapshot = collect_once()
                with self._lock:
                    self._snapshot = snapshot
                self._ready.set()
            except Exception as exc:
                logger.warning("Collection worker failed: %s", type(exc).__name__)
                with self._lock:
                    self._snapshot["archive_error"] = f"采集失败：{type(exc).__name__}"
                self._ready.set()
            self._refresh.wait(self.interval)
            self._refresh.clear()

    def snapshot(self):
        # Bound the first read; the worker continues even with no active page.
        self._ready.wait(timeout=12)
        with self._lock:
            return deepcopy(self._snapshot)

    def refresh(self):
        self._refresh.set()

    def stop(self):
        self._stop.set()
        self._refresh.set()
        if self._thread:
            self._thread.join(timeout=3)


def collect_portwatch():
    """Archive latest validated daily facts, with source-dated backfill windows."""
    import portwatch
    import portwatch_downloads
    for kind, catalog_reader, latest_reader in (
        ("ports", portwatch.port_catalog, portwatch.latest_date),
        ("chokepoints", portwatch.chokepoint_catalog, portwatch.latest_chokepoint_date),
    ):
        catalog = catalog_reader()
        ids = tuple(sorted(str(row["portid"]) for row in catalog
                           if kind == "chokepoints" or portwatch.has_independent_statistics(row)))
        end = latest_reader()
        from datetime import timedelta
        portwatch_downloads.fetch_window(kind, ids, end - timedelta(days=13), end)


def collect_portwatch_run():
    started = datetime.now(timezone.utc)
    status, details = "ok", {}
    try:
        collect_portwatch()
    except Exception as exc:
        status = "error"
        details["error"] = str(exc)
        logger.warning("PortWatch collection failed: %s", type(exc).__name__)
    with data_store.connect() as conn:
        conn.execute("INSERT INTO collection_runs VALUES (?,?,?,?,?,?,?)",
                     (uuid.uuid4().hex, "PortWatch", started, datetime.now(timezone.utc), status, 0, data_store.encode(details)))


if __name__ == "__main__":
    import argparse
    import time
    parser = argparse.ArgumentParser(description="四海域AIS持续归档到单一DuckDB")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--with-portwatch", action="store_true")
    args = parser.parse_args()
    data_store.initialize()
    # This service can also maintain AISStream without a browser session.
    key = data_store.setting("AISSTREAM_API_KEY")
    stream = ais.AISCollector(key).start() if key else None
    service = None if args.once else CollectionService(args.poll_seconds, args.with_portwatch).start()
    try:
        while True:
            snapshot = collect_once() if args.once else service.snapshot()
            print(data_store.encode({"vessels": len(snapshot.get("vessels", [])), "error": snapshot.get("error"),
                                     "archive_error": snapshot.get("archive_error"), "storage": data_store.status()}), flush=True)
            if args.once and args.with_portwatch:
                collect_portwatch_run()
            if args.once:
                break
            time.sleep(max(60, args.poll_seconds))
    except KeyboardInterrupt:
        pass
    finally:
        if service:
            service.stop()
        if stream:
            stream.stop()
