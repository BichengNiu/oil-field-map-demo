"""Collect into a candidate database; validate before atomically publishing it.

Run on main after git pull --ff-only. Only --publish commits and pushes.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import duckdb
import data_store

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "runtime" / "monitoring.duckdb"
STAGING = ROOT / "runtime" / "history-staging.duckdb"
STAGING_META = ROOT / "runtime" / "history-staging.json"


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resumable_seed(original):
    if not STAGING.exists() or not STAGING_META.exists():
        return None
    metadata = json.loads(STAGING_META.read_text())
    if metadata.get("base_sha256") != file_digest(original):
        return None
    if metadata.get("candidate_sha256") != file_digest(STAGING):
        raise ValueError("未发布回补进度校验失败，保留文件供检查")
    return STAGING


def git(*args):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Git {args[0]} 失败：{result.stderr.strip()}")
    return result.stdout.strip()


@contextmanager
def exclusive_update():
    import fcntl
    directory = Path(git("rev-parse", "--absolute-git-dir"))
    with (directory / "monitoring-update.lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("另一个数据库更新任务正在执行") from None
        yield


def inspect(path):
    with duckdb.connect(str(path), read_only=True) as conn:
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("portwatch_daily", "ais_reports", "sea_entries", "catalogs", "documents")}
        latest = dict(conn.execute("SELECT kind,MAX(day) FROM portwatch_daily GROUP BY kind").fetchall())
        vessel = conn.execute("SELECT MAX(observed) FROM ais_reports").fetchone()[0]
        # Read/decode the tables used by the dashboard, not just their schema.
        conn.execute("SELECT SUM(LENGTH(CAST(payload AS VARCHAR))) FROM catalogs").fetchone()
        conn.execute("SELECT COUNT(*) FROM asset_catalog").fetchone()
    return {"counts": counts, "latest_days": latest, "latest_vessel": vessel}


def collect_candidate(original: Path, candidate: Path, *, force_ports=False, now=None, seed=None):
    now = now or datetime.now(timezone.utc)
    before = inspect(original)
    shutil.copy2(seed or original, candidate)
    previous_path = os.environ.get("MONITORING_DB_PATH")
    previous_mode = os.environ.get("MONITORING_READ_ONLY")
    os.environ["MONITORING_DB_PATH"] = str(candidate)
    os.environ["MONITORING_READ_ONLY"] = "false"
    try:
        import ais
        import collector
        import portwatch
        import portwatch_history
        data_store.initialize()
        # Persist code-defined asset rules into the same candidate.
        import importlib
        import field_catalog
        importlib.reload(field_catalog)
        snapshot = collector.collect_once()
        if snapshot.get("error") or snapshot.get("archive_error") or not snapshot.get("vessels"):
            raise RuntimeError("船位采集未完整成功：" + str(snapshot.get("archive_error") or snapshot.get("error")))
        observed = [ais.parse_utc(row.get("observed_at")) for row in snapshot["vessels"]]
        if not any(value and now - timedelta(hours=2) <= value <= now + timedelta(minutes=5) for value in observed):
            raise RuntimeError("未取得最近两小时的有效船位")
        last_ports = data_store.meta("snapshot_portwatch_completed_at", "")
        history_due = portwatch_history.needs_repair(now)
        due = force_ports or history_due or not last_ports or datetime.fromisoformat(last_ports).date() < now.date()
        port_result = None
        if due:
            with portwatch.request_budget(3600 if history_due else 240):
                port_result = collector.collect_portwatch_run(strict=True, force=True, include_history=True)
            data_store.set_meta("snapshot_portwatch_completed_at", now.isoformat())
        history_coverage = portwatch_history.validate_all()
        # Only expendable raw responses/caches expire. Facts and events accumulate.
        with data_store.connect() as conn:
            conn.execute("DELETE FROM source_queries WHERE retrieved_at < ?", [now - timedelta(days=7)])
            conn.execute("DELETE FROM portwatch_cache WHERE saved < ?", [(now - timedelta(days=7)).timestamp()])
        after = inspect(candidate)
        for table in ("portwatch_daily", "sea_entries", "ais_reports"):
            if after["counts"][table] < before["counts"][table]:
                raise RuntimeError("历史记录减少，拒绝发布：" + table)
        for kind, day in before["latest_days"].items():
            if after["latest_days"].get(kind, day) < day:
                raise RuntimeError("来源数据日期倒退：" + kind)
        if before["latest_vessel"] and (not after["latest_vessel"] or after["latest_vessel"] < before["latest_vessel"]):
            raise RuntimeError("船位日期倒退")
        if not after["counts"]["catalogs"] or not after["counts"]["documents"]:
            raise RuntimeError("数据库目录或来源材料为空")
        summary = {"completed_at": now.isoformat(), "portwatch_updated": due,
                   "portwatch": port_result, "history_coverage": history_coverage,
                   "before": before, "after": after}
        data_store.set_meta("published_snapshot", summary)
        # Every connection has closed: the file is checkpointed and portable.
        inspect(candidate)
        return summary
    finally:
        for key, value in (("MONITORING_DB_PATH", previous_path), ("MONITORING_READ_ONLY", previous_mode)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run(*, publish=False, force_ports=False):
    with exclusive_update():
        base = None
        if publish:
            if git("branch", "--show-current") != "main" or git("status", "--porcelain"):
                raise RuntimeError("发布要求 main 分支且工作区干净")
            git("fetch", "origin", "main")
            base = git("rev-parse", "HEAD")
            if base != git("rev-parse", "origin/main"):
                raise RuntimeError("请先 git pull --ff-only，再运行更新")
            git("lfs", "pull", "--include=runtime/monitoring.duckdb")
        from snapshot_store import materialize
        original = materialize(DATABASE)
        with tempfile.TemporaryDirectory(prefix="monitoring-update-", dir=DATABASE.parent) as temporary:
            candidate = Path(temporary) / "monitoring.duckdb"
            seed = resumable_seed(original) if publish else None
            try:
                options = {"force_ports": force_ports}
                if seed is not None:
                    options["seed"] = seed
                summary = collect_candidate(original, candidate, **options)
            except Exception:
                if publish and candidate.exists():
                    # Connections and worker threads are closed before copying.
                    inspect(candidate)
                    shutil.copy2(candidate, STAGING)
                    STAGING_META.write_text(json.dumps({
                        "base_sha256": file_digest(original),
                        "candidate_sha256": file_digest(STAGING),
                    }))
                    logging.warning("已保留未发布的回补进度，下次从同一基线继续")
                raise
            if publish:
                git("fetch", "origin", "main")
                if base != git("rev-parse", "origin/main"):
                    raise RuntimeError("采集期间 main 已变化；保留远端数据库，下次任务重新采集")
                if base != git("rev-parse", "HEAD") or git("status", "--porcelain"):
                    raise RuntimeError("采集期间工作区发生变化，拒绝覆盖或提交")
                os.replace(candidate, DATABASE)
                # The database is already tracked inside an ignored directory.
                git("add", "-u", "--", "runtime/monitoring.duckdb")
                git("commit", "-m", "Update validated monitoring snapshot")
                git("push", "origin", "main")
                STAGING.unlink(missing_ok=True)
                STAGING_META.unlink(missing_ok=True)
            # Dry runs validate source data without changing the published file.
        return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--force-ports", action="store_true")
    args = parser.parse_args()
    try:
        print(data_store.encode(run(publish=args.publish, force_ports=args.force_ports)))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
