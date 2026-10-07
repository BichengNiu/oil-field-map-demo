"""One DuckDB for source evidence, catalogs, daily facts, AIS and sea events.

Connections are short-lived. A process lock plus an OS file lock serializes
all readers/writers, including a standalone collector sharing the same disk.
No connection is held while fetching network data.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import zlib
from decimal import Decimal

import duckdb

ROOT = Path(__file__).resolve().parent
_LOCK = threading.RLock()
_LOCAL = threading.local()
_READY = set()


def setting(key, default=""):
    value = os.environ.get(key)
    if not value and "streamlit" in sys.modules:
        try:
            value = sys.modules["streamlit"].secrets.get(key)
        except Exception:
            pass
    return str(value or default).strip()


def database_path():
    return Path(setting("MONITORING_DB_PATH", str(ROOT / "runtime" / "monitoring.duckdb"))).expanduser().resolve()


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=str, allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS app_meta (key VARCHAR PRIMARY KEY, value JSON);
CREATE TABLE IF NOT EXISTS documents (
    path VARCHAR PRIMARY KEY, sha256 VARCHAR, media_type VARCHAR, content BLOB,
    row_count BIGINT, ingested_at TIMESTAMPTZ DEFAULT current_timestamp);
CREATE TABLE IF NOT EXISTS document_rows (
    path VARCHAR, section VARCHAR, row_no BIGINT, payload JSON,
    PRIMARY KEY(path,section,row_no));
CREATE TABLE IF NOT EXISTS catalogs (
    kind VARCHAR, id VARCHAR, payload JSON, updated_at TIMESTAMPTZ DEFAULT current_timestamp,
    PRIMARY KEY(kind,id));
CREATE TABLE IF NOT EXISTS portwatch_daily (
    kind VARCHAR, node_id VARCHAR, day DATE, payload JSON, source_url VARCHAR,
    fetched_at TIMESTAMPTZ DEFAULT current_timestamp, PRIMARY KEY(kind,node_id,day));
CREATE TABLE IF NOT EXISTS portwatch_cache (key VARCHAR PRIMARY KEY, saved DOUBLE, payload BLOB);
CREATE TABLE IF NOT EXISTS source_queries (
    id VARCHAR PRIMARY KEY, endpoint VARCHAR, params JSON, response JSON,
    retrieved_at TIMESTAMPTZ DEFAULT current_timestamp);
CREATE TABLE IF NOT EXISTS ais_reports (
    mmsi VARCHAR, observed TIMESTAMPTZ, source VARCHAR, payload JSON,
    PRIMARY KEY(mmsi,observed,source));
CREATE TABLE IF NOT EXISTS archive_imports (sha256 VARCHAR PRIMARY KEY, metadata JSON);
CREATE TABLE IF NOT EXISTS sea_manifests (provider VARCHAR PRIMARY KEY, manifest JSON);
CREATE TABLE IF NOT EXISTS sea_entries (
    provider VARCHAR, definition VARCHAR, sea VARCHAR, mmsi VARCHAR,
    entered_at TIMESTAMPTZ, day DATE, evidence JSON,
    PRIMARY KEY(provider,definition,sea,mmsi,entered_at));
CREATE TABLE IF NOT EXISTS sea_coverage (
    provider VARCHAR, definition VARCHAR, sea VARCHAR, day DATE, status VARCHAR,
    event_count BIGINT, PRIMARY KEY(provider,definition,sea,day));
CREATE TABLE IF NOT EXISTS sea_vessel_checkpoints (
    mmsi VARCHAR, definition VARCHAR, day DATE, through_at TIMESTAMPTZ, state JSON,
    PRIMARY KEY(mmsi,definition,day));
CREATE TABLE IF NOT EXISTS collection_runs (
    id VARCHAR PRIMARY KEY, provider VARCHAR, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
    status VARCHAR, reports BIGINT, details JSON);
CREATE INDEX IF NOT EXISTS ais_time ON ais_reports(observed);
CREATE INDEX IF NOT EXISTS sea_day ON sea_entries(provider,day);
CREATE VIEW IF NOT EXISTS ais_positions AS
    SELECT mmsi,observed,source,
           TRY_CAST(json_extract_string(payload,'$.lat') AS DOUBLE) AS lat,
           TRY_CAST(json_extract_string(payload,'$.lon') AS DOUBLE) AS lon,payload FROM ais_reports;
CREATE VIEW IF NOT EXISTS sea_daily_observed AS
    SELECT provider,definition,sea,day,COUNT(*) AS passages FROM sea_entries
    GROUP BY provider,definition,sea,day;
CREATE VIEW IF NOT EXISTS asset_catalog AS
    SELECT id,
           json_extract_string(payload,'$.country') AS country,
           json_extract_string(payload,'$.name') AS name,
           json_extract_string(payload,'$.asset_level') AS asset_level,
           json_extract_string(payload,'$.commodity') AS commodity,
           json_extract_string(payload,'$.data_date') AS measurement_date,
           json_extract_string(payload,'$.metric_type') AS metric_type,
           TRY_CAST(json_extract_string(payload,'$.value_numeric') AS DECIMAL(24,8)) AS value_numeric,
           json_extract_string(payload,'$.unit') AS unit,
           json_extract_string(payload,'$.source_url') AS source_url,payload
    FROM catalogs WHERE kind='assets';
CREATE VIEW IF NOT EXISTS portwatch_metrics AS
    SELECT kind,node_id,day,
           TRY_CAST(json_extract_string(payload,'$.portcalls') AS DOUBLE) AS portcalls,
           TRY_CAST(json_extract_string(payload,'$.n_total') AS DOUBLE) AS passages,
           source_url,payload FROM portwatch_daily;
"""


@contextmanager
def connect(path=None):
    path = Path(path).resolve() if path is not None else database_path()
    nested = getattr(_LOCAL, "connections", {})
    if str(path) in nested:
        # Reuse the existing transaction; opening another OS-lock descriptor in
        # this same thread would block itself during lazy boundary/catalog reads.
        yield nested[str(path)]
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.with_suffix(path.suffix + ".lock").open("a+b") as lock:
            if os.name == "posix":
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            else:
                import msvcrt
                lock.seek(0)
                if not lock.read(1):
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            conn = None
            begun = False
            try:
                existed = path.exists()
                conn = duckdb.connect(str(path), config={"threads": 2, "memory_limit": "256MB"})
                if str(path) not in _READY or not existed:
                    conn.execute(SCHEMA)
                    _READY.add(str(path))
                conn.execute("BEGIN TRANSACTION")
                begun = True
                if not hasattr(_LOCAL, "connections"):
                    _LOCAL.connections = {}
                _LOCAL.connections[str(path)] = conn
                yield conn
                conn.execute("COMMIT")
            except Exception:
                if conn is not None and begun:
                    conn.execute("ROLLBACK")
                raise
            finally:
                getattr(_LOCAL, "connections", {}).pop(str(path), None)
                if conn is not None:
                    conn.close()
                if os.name == "posix":
                    fcntl.flock(lock, fcntl.LOCK_UN)
                else:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def meta(key, default=None, conn=None):
    if conn is None:
        with connect() as handle:
            return meta(key, default, handle)
    row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_meta(key, value, conn=None):
    if conn is None:
        with connect() as handle:
            return set_meta(key, value, handle)
    conn.execute("INSERT OR REPLACE INTO app_meta VALUES (?,?)", (key, encode(value)))


def _rows(value, section="$"):
    if isinstance(value, list):
        for i, item in enumerate(value):
            yield section, i, item
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                yield from _rows(item, section + "." + str(key))


def ingest_document(relative, path=None):
    """Versioned source files are bootstrap evidence; runtime reads use DuckDB."""
    original = ROOT / relative
    content = original.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    with connect(path) as conn:
        old = conn.execute("SELECT sha256 FROM documents WHERE path=?", (relative,)).fetchone()
        if old and old[0] == digest:
            return
        suffix = original.suffix.lower()
        if suffix in (".json", ".geojson"):
            values = list(_rows(json.loads(content.decode("utf-8-sig"))))
            media = "application/json"
        elif suffix == ".csv":
            values = [("$", i, row) for i, row in enumerate(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))]
            media = "text/csv"
        else:
            values, media = [], "application/octet-stream"
        conn.execute("DELETE FROM document_rows WHERE path=?", (relative,))
        if values:
            conn.executemany("INSERT INTO document_rows VALUES (?,?,?,?)",
                             [(relative, section, i, encode(row)) for section, i, row in values])
        conn.execute("INSERT OR REPLACE INTO documents(path,sha256,media_type,content,row_count) VALUES (?,?,?,?,?)",
                     (relative, digest, media, content, len(values)))


def read_json(relative):
    # Re-bootstrap changed version-controlled evidence, never overwrite live facts.
    original = ROOT / relative
    if original.exists():
        ingest_document(relative)
    with connect() as conn:
        row = conn.execute("SELECT content FROM documents WHERE path=?", (relative,)).fetchone()
    if row is None:
        raise FileNotFoundError(relative)
    return json.loads(bytes(row[0]).decode("utf-8-sig"))


def save_catalog(kind, rows, key="portid"):
    with connect() as conn:
        if kind == "assets":
            pairs = [(row["country"] + "\x1f" + row["name"], row) for row in rows]
        else:
            pairs = [(str(row[key]), row) for row in rows]
        if len({pid for pid, _ in pairs}) != len(pairs):
            raise ValueError("目录主键重复：" + kind)
        conn.execute("DELETE FROM catalogs WHERE kind=?", (kind,))
        if pairs:
            conn.executemany("INSERT INTO catalogs(kind,id,payload) VALUES (?,?,?)",
                             [(kind, pid, encode(row)) for pid, row in pairs])


def load_catalog(kind):
    with connect() as conn:
        rows = [json.loads(r[0]) for r in conn.execute("SELECT payload FROM catalogs WHERE kind=? ORDER BY id", (kind,)).fetchall()]
    if kind == "assets":
        def restore(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key == "value_numeric" and item is not None:
                        value[key] = Decimal(str(item))
                    else:
                        restore(item)
            elif isinstance(value, list):
                for item in value:
                    restore(item)
        restore(rows)
    return rows


def cached_catalog(kind, max_age_seconds=86_400, allow_stale=False):
    """Return a persisted catalog, optionally regardless of its age."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload, updated_at FROM catalogs WHERE kind=? ORDER BY id", (kind,)
        ).fetchall()
    if not rows:
        return None
    updated_at = min(row[1] for row in rows)
    if not allow_stale and (datetime.now(timezone.utc) - updated_at).total_seconds() > max_age_seconds:
        return None
    return [json.loads(row[0]) for row in rows]


def put_binary_document(relative, content, media, conn=None):
    if conn is None:
        with connect() as handle:
            return put_binary_document(relative, content, media, handle)
    conn.execute("INSERT OR REPLACE INTO documents(path,sha256,media_type,content,row_count) VALUES (?,?,?,?,0)",
                 (relative, hashlib.sha256(content).hexdigest(), media, content))


def binary_document(relative):
    with connect() as conn:
        row = conn.execute("SELECT content FROM documents WHERE path=?", (relative,)).fetchone()
    return bytes(row[0]) if row else None


def save_portwatch(kind, rows, source_url, conn=None):
    if conn is None:
        with connect() as handle:
            return save_portwatch(kind, rows, source_url, handle)
    if rows:
        statement = "INSERT OR REPLACE INTO portwatch_daily(kind,node_id,day,payload,source_url) VALUES (?,?,?,?,?)"
        for start in range(0, len(rows), 500):
            batch = rows[start:start + 500]
            conn.executemany(
                statement,
                [(kind, str(row["portid"]), str(row["date"])[:10], encode(row), source_url)
                 for row in batch],
            )


def cached_portwatch_window(kind, node_ids, first, last, max_age_seconds=86_400,
                            with_metadata=False, allow_stale=False):
    """Read a fully populated node/day window from the persistent fact table.

    A partially stored window is not a cache hit: missing days must remain
    distinguishable from zero-valued observations, so callers can fetch and
    verify the complete source window instead.
    """
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids or first > last:
        return None

    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        result = conn.execute(
            f"""SELECT node_id, day, payload, fetched_at FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders})
                  AND day BETWEEN ? AND ? ORDER BY day, node_id""",
            [kind, *node_ids, first, last],
        ).fetchall()

    expected = {
        (node_id, (first + timedelta(days=offset)).isoformat())
        for node_id in node_ids
        for offset in range((last - first).days + 1)
    }
    rows_by_key = {}
    last_day_fetched = []
    for node_id, day, payload, fetched_at in result:
        key = (str(node_id), day.isoformat())
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", key[1])
        rows_by_key[key] = row
        if day == last:
            last_day_fetched.append(fetched_at)
    if rows_by_key.keys() != expected:
        return None
    if not last_day_fetched or (not allow_stale and (
        datetime.now(timezone.utc) - min(last_day_fetched)
    ).total_seconds() > max_age_seconds):
        return None
    rows = [rows_by_key[key] for key in sorted(expected)]
    if with_metadata:
        return rows, min(row[3] for row in result)
    return rows


def cached_portwatch_observations(kind, node_ids, first, last):
    """Return whatever local daily facts exist in a date window, including gaps.

    This is for read-only initial page rendering. Missing days remain missing;
    callers must not interpret them as zero or fall back to the network.
    """
    node_ids = tuple(sorted(set(str(node_id) for node_id in node_ids)))
    if kind not in ("ports", "chokepoints") or not node_ids or first > last:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    with connect() as conn:
        result = conn.execute(
            f"""SELECT node_id, day, payload FROM portwatch_daily
                WHERE kind=? AND node_id IN ({placeholders})
                  AND day BETWEEN ? AND ? ORDER BY day, node_id""",
            [kind, *node_ids, first, last],
        ).fetchall()
    rows = []
    for node_id, day, payload in result:
        row = json.loads(payload) if isinstance(payload, str) else dict(payload)
        row.setdefault("portid", str(node_id))
        row.setdefault("date", day.isoformat())
        rows.append(row)
    return rows


def cached_portwatch_latest_day(kind, max_age_seconds=86_400, allow_stale=False):
    """Return the latest persisted source day, optionally regardless of age."""
    if kind not in ("ports", "chokepoints"):
        return None
    with connect() as conn:
        result = conn.execute(
            """SELECT MAX(day), MIN(fetched_at) FROM portwatch_daily
               WHERE kind=? AND day=(SELECT MAX(day) FROM portwatch_daily WHERE kind=?)""",
            [kind, kind],
        ).fetchone()
    day, fetched_at = result
    if day is None or fetched_at is None:
        return None
    if not allow_stale and (datetime.now(timezone.utc) - fetched_at).total_seconds() > max_age_seconds:
        return None
    return day


def save_query(endpoint, params, response):
    key = hashlib.sha256(encode([endpoint, params, response]).encode()).hexdigest()
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO source_queries(id,endpoint,params,response) VALUES (?,?,?,?)",
                     (key, endpoint, encode(params), encode(response)))


def _legacy_paths():
    home = Path.home()
    return {
        "ais": Path(setting("AIS_ARCHIVE_PATH", str(Path(os.environ.get("XDG_STATE_HOME") or home / ".local/state") / "oil-field-map-demo/ais-history.sqlite3"))),
        "portwatch": Path(setting("PORTWATCH_DOWNLOAD_CACHE", str(Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache") / "oil-field-map-demo/portwatch-download-cache.sqlite3"))),
        "sea": Path(setting("SEA_HISTORY_ARCHIVE_PATH", str(ROOT / "runtime/sea-history.sqlite3"))),
    }


def migrate_legacy(path=None, sources=None):
    """Copy read-only SQLite sources atomically, keep originals as rollback backups."""
    counts = {}
    for kind, original in (sources or _legacy_paths()).items():
        original = Path(original).expanduser().resolve()
        if not original.exists():
            continue
        with original.open("rb") as handle:
            if handle.read(16) != b"SQLite format 3\x00":
                continue
        marker = "sqlite-migrated:" + str(original)
        with connect(path) as conn:
            if meta(marker, conn=conn):
                continue
            old = sqlite3.connect(original.as_uri() + "?mode=ro", uri=True)
            try:
                tables = {row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                count = 0
                if kind == "ais" and "reports" in tables:
                    cursor = old.execute("SELECT mmsi,observed,source,payload FROM reports")
                    while batch := cursor.fetchmany(1000):
                        conn.executemany("INSERT OR IGNORE INTO ais_reports VALUES (?,?,?,?)", batch)
                        count += len(batch)
                    if "archive_imports" in tables:
                        imports = list(old.execute("SELECT sha256,metadata FROM archive_imports"))
                        if imports:
                            conn.executemany("INSERT OR IGNORE INTO archive_imports VALUES (?,?)", imports)
                if kind == "portwatch" and "queries" in tables:
                    for key, saved, payload in old.execute("SELECT key,saved,payload FROM queries"):
                        conn.execute("INSERT OR IGNORE INTO portwatch_cache VALUES (?,?,?)", (key, saved, payload))
                        data = json.loads(zlib.decompress(payload))
                        endpoint = data.get("query", {}).get("endpoint", "")
                        node_kind = "chokepoints" if "Chokepoints" in endpoint else "ports"
                        save_portwatch(node_kind, data.get("rows", []), endpoint, conn)
                        count += len(data.get("rows", []))
                if kind == "sea" and "metadata" in tables:
                    item = old.execute("SELECT manifest FROM metadata WHERE id=1").fetchone()
                    if item:
                        manifest = json.loads(item[0])
                        provider, definition = manifest["source"], manifest["definition_id"]
                        existing = conn.execute("SELECT manifest FROM sea_manifests WHERE provider=?", (provider,)).fetchone()
                        if existing and json.loads(existing[0])["definition_id"] != definition:
                            raise ValueError("旧海域库边界版本冲突，未迁移")
                        conn.execute("INSERT OR REPLACE INTO sea_manifests VALUES (?,?)", (provider, item[0]))
                        set_meta("selected_sea_history_provider", provider, conn)
                        for sea, mmsi, stamp, day in old.execute("SELECT sea,mmsi,entered_at,day FROM entries"):
                            conn.execute("INSERT OR IGNORE INTO sea_entries VALUES (?,?,?,?,?,?,?)",
                                         (provider, definition, sea, mmsi, stamp, day, encode({"migration": str(original)})))
                            count += 1
                        coverage = [(provider, definition, sea, day, "complete", count) for sea, day, count in old.execute("SELECT sea,day,event_count FROM coverage")]
                        if coverage:
                            conn.executemany("INSERT OR REPLACE INTO sea_coverage VALUES (?,?,?,?,?,?)", coverage)
                set_meta(marker, {"rows": count, "migrated_at": datetime.now(timezone.utc).isoformat()}, conn)
                counts[kind] = count
            finally:
                old.close()
    return counts


def initialize():
    counts = migrate_legacy()
    files = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in (".json", ".csv")]
    if (ROOT / "data").exists():
        files += [p for p in (ROOT / "data").iterdir() if p.is_file() and p.suffix in (".json", ".csv", ".geojson")]
    for original in files:
        ingest_document(original.relative_to(ROOT).as_posix())
    return {"source_files": len(files), "legacy": counts, "database": str(database_path())}


def status():
    with connect() as conn:
        counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                  for name in ("documents", "document_rows", "catalogs", "portwatch_daily", "ais_reports", "sea_entries", "collection_runs")}
        start = meta("local_collection_started_at", conn=conn)
        latest = conn.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]
    return {"counts": counts, "started_at": start, "latest_observed_at": latest.isoformat() if latest else None}


def backup_bytes():
    """Consistent portable database snapshot under the same reader/writer lock."""
    with connect() as conn:
        conn.execute("CHECKPOINT")
        return database_path().read_bytes()


if __name__ == "__main__":
    print(encode({"migration": initialize(), "status": status()}))
