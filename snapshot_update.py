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
    # An interrupted source may have written unvalidated facts. Never seed a
    # new publication from the old all-or-nothing failure checkpoint.
    if not metadata.get('validated_for_resume'):
        return None
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


def validate_progress(before, after):
    for table in ('portwatch_daily', 'sea_entries', 'ais_reports'):
        if after['counts'][table] < before['counts'][table]:
            raise RuntimeError('历史记录减少，拒绝发布：' + table)
    for kind, day in before['latest_days'].items():
        if after['latest_days'].get(kind, day) < day:
            raise RuntimeError('来源数据日期倒退：' + kind)
    if before['latest_vessel'] and (not after['latest_vessel'] or after['latest_vessel'] < before['latest_vessel']):
        raise RuntimeError('船位日期倒退')


@contextmanager
def source_checkpoint(candidate):
    """Roll back every write by a failed source, including its catalog/meta."""
    with tempfile.TemporaryDirectory(prefix='source-checkpoint-', dir=candidate.parent) as temporary:
        checkpoint = Path(temporary) / 'before.duckdb'
        shutil.copy2(candidate, checkpoint)
        try:
            yield
        except Exception:
            Path(str(candidate) + '.wal').unlink(missing_ok=True)
            shutil.copy2(checkpoint, candidate)
            raise


def collect_candidate(original: Path, candidate: Path, *, force_ports=False, now=None, seed=None, retry_only=False):
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
        import pipeline_catalog
        pipelines = pipeline_catalog.load()
        gas_connections = pipeline_catalog.load_gas_connections()
        unmapped_projects = pipeline_catalog.load_unmapped_projects()
        # Persist code-defined asset rules into the same candidate.
        import importlib
        import field_catalog
        importlib.reload(field_catalog)
        from entity_names import validate_catalogs
        # Enrich even when PortWatch is not due; identities and daily facts stay intact.
        for kind in ("assets", "ports", "chokepoints"):
            catalog = data_store.load_catalog(kind)
            if kind == "ports":
                from port_additions import extend_inventory
                catalog = extend_inventory(catalog)
            data_store.save_catalog(kind, catalog)
        validate_catalogs({kind: data_store.load_catalog(kind) for kind in ("assets", "ports", "chokepoints")})
        from deploy.snapshot_retry import decision, successful_sources, SOURCES
        previous = data_store.meta('published_snapshot', {})
        successes = successful_sources(previous, now)
        pending = set(decision(previous, now)['pending_sources'])
        source_results = {name: {'status': 'skipped', 'last_successful_collection':
                          successes[name].isoformat() if name in successes else None}
                          for name in SOURCES}
        if not retry_only or 'ais' in pending:
            try:
                with source_checkpoint(candidate):
                    source_before = inspect(candidate)
                    snapshot = collector.collect_once()
                    if snapshot.get('error') or snapshot.get('archive_error') or not snapshot.get('vessels'):
                        raise RuntimeError('船位采集未完整成功：' + str(snapshot.get('archive_error') or snapshot.get('error')))
                    observed = [ais.parse_utc(row.get('observed_at')) for row in snapshot['vessels']]
                    if not any(value and now - timedelta(hours=2) <= value <= now + timedelta(minutes=5) for value in observed):
                        raise RuntimeError('未取得最近两小时的有效船位')
                    validate_progress(source_before, inspect(candidate))
                source_results['ais'].update(status='ok', last_successful_collection=now.isoformat())
            except Exception as exc:
                source_results['ais'].update(status='error', error=f'{type(exc).__name__}: {exc}')
                logging.warning('船位更新失败，保留上次船位；继续港口更新：%s', exc)
        port_result = {'sources': {}}
        history_coverage = dict(previous.get('history_coverage', {}))
        for kind in ('ports', 'chokepoints'):
            try:
                with source_checkpoint(candidate):
                    last_source = data_store.meta(f'snapshot_portwatch_{kind}_completed_at',
                                                  data_store.meta('snapshot_portwatch_completed_at', ''))
                    history_due = portwatch_history.needs_repair(now, kind=kind)
                    due = (force_ports or history_due or (kind in pending if retry_only else
                           not last_source or datetime.fromisoformat(last_source).date() < now.date()))
                    if due:
                        source_before = inspect(candidate)
                        with portwatch.request_budget(3600 if history_due else 900):
                            result = collector.collect_portwatch_run(strict=True, force=True, include_history=True, kind=kind)
                        if result.get('status') != 'ok':
                            raise RuntimeError('PortWatch未返回成功状态')
                        validate_catalogs({name: data_store.load_catalog(name) for name in ('assets', 'ports', 'chokepoints')})
                        coverage = portwatch_history.validate_kind(kind)
                        validate_progress(source_before, inspect(candidate))
                        data_store.set_meta(f'snapshot_portwatch_{kind}_completed_at', now.isoformat())
                if due:
                    source_results[kind].update(status='ok', last_successful_collection=now.isoformat())
                    history_coverage[kind] = coverage
                    port_result['sources'][kind] = result.get('sources', {}).get(kind, {})
            except Exception as exc:
                source_results[kind].update(status='error', error=f'{type(exc).__name__}: {exc}')
                port_result['sources'][kind] = {'status': 'error', 'error': f'{type(exc).__name__}: {exc}'}
                logging.warning('%s更新失败，保留该类数据；不阻止其他数据发布：%s', kind, exc)
        port_result['status'] = ('partial' if any(source_results[k]['status'] == 'error' for k in ('ports', 'chokepoints')) else 'ok')
        if not (set(decision({'source_results': source_results}, now)['pending_sources']) & {'ports', 'chokepoints'}):
            data_store.set_meta('snapshot_portwatch_completed_at', min(
                source_results[k]['last_successful_collection'] for k in ('ports', 'chokepoints')))
        if not any(result['status'] == 'ok' for result in source_results.values()):
            if any(result['status'] == 'error' for result in source_results.values()):
                raise RuntimeError('本次没有数据源更新成功：' + json.dumps(source_results, ensure_ascii=False))
        validate_catalogs({kind: data_store.load_catalog(kind) for kind in ("assets", "ports", "chokepoints")})
        # Only expendable raw responses/caches expire. Facts and events accumulate.
        with data_store.connect() as conn:
            conn.execute("DELETE FROM source_queries WHERE retrieved_at < ?", [now - timedelta(days=7)])
            conn.execute("DELETE FROM portwatch_cache WHERE saved < ?", [(now - timedelta(days=7)).timestamp()])
        after = inspect(candidate)
        validate_progress(before, after)
        if not after["counts"]["catalogs"] or not after["counts"]["documents"]:
            raise RuntimeError("数据库目录或来源材料为空")
        summary = {"completed_at": now.isoformat(),
                   "status": 'partial' if any(r['status'] == 'error' for r in source_results.values()) else 'ok',
                   "source_results": source_results,
                   "full_collection_complete": not decision({'source_results': source_results}, now)['pending_sources'],
                   "ais_updated": source_results['ais']['status'] == 'ok',
                   "portwatch_updated": any(source_results[k]['status'] == 'ok' for k in ('ports', 'chokepoints')),
                   "ports_updated": source_results['ports']['status'] == 'ok',
                   "chokepoints_updated": source_results['chokepoints']['status'] == 'ok',
                   "pipelines": {"segments": len(pipelines["features"]), "drawable_segments": sum(f["properties"].get("map_drawable", True) for f in pipelines["features"]), "gas_connection_records": len(gas_connections["features"]), "unmapped_projects": len(unmapped_projects), "source": pipelines["metadata"]},
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


def collect_catalog_candidate(original, candidate):
    """Publish reviewed catalog rules through the existing single writer.

    No network collection or observation timestamp advancement is implied.
    All vessel/port history and source documents remain in the copied snapshot.
    """
    before = inspect(original)
    shutil.copy2(original, candidate)
    previous = {key: os.environ.get(key) for key in ("MONITORING_DB_PATH", "MONITORING_READ_ONLY")}
    os.environ["MONITORING_DB_PATH"] = str(candidate)
    os.environ["MONITORING_READ_ONLY"] = "false"
    try:
        import importlib
        import field_catalog
        importlib.reload(field_catalog)
        from entity_names import validate_catalogs
        validate_catalogs({"assets": data_store.load_catalog("assets")})
        after = inspect(candidate)
        if before != after:
            raise ValueError("目录复核不得改变历史行数或船舶/港口观察日期")
        return {"mode": "catalog_review", "before": before, "after": after}
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run(*, publish=False, force_ports=False, catalog_only=False, retry_only=False):
    if catalog_only and force_ports:
        raise ValueError("目录复核与强制港口采集不可同时使用")
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
            seed = resumable_seed(original) if publish and not catalog_only else None
            try:
                options = {"force_ports": force_ports}
                if retry_only:
                    options['retry_only'] = True
                if seed is not None:
                    options["seed"] = seed
                summary = (collect_catalog_candidate(original, candidate) if catalog_only
                           else collect_candidate(original, candidate, **options))
            except Exception:
                if publish and not catalog_only and candidate.exists():
                    # Connections and worker threads are closed before copying.
                    inspect(candidate)
                    shutil.copy2(candidate, STAGING)
                    STAGING_META.write_text(json.dumps({
                        'validated_for_resume': False,
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
                if not catalog_only:
                    STAGING.unlink(missing_ok=True)
                    STAGING_META.unlink(missing_ok=True)
            # Dry runs validate source data without changing the published file.
        return summary


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--force-ports", action="store_true")
    parser.add_argument('--retry', action='store_true', help='仅补采本主执行时段尚未成功的数据源')
    parser.add_argument("--catalog-only", action="store_true", help="仅发布已审核目录规则，保留船舶/港口实测历史")
    args = parser.parse_args()
    try:
        summary = run(publish=args.publish, force_ports=args.force_ports, catalog_only=args.catalog_only, retry_only=args.retry)
        print(data_store.encode(summary))
        if summary.get('source_results') and os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
                stream.write('Data source publication results\n\n| Source | Result | Last successful collection |\n| --- | --- | --- |\n')
                for source, result in summary['source_results'].items():
                    stream.write(f"| {source} | {result['status']} | {result.get('last_successful_collection') or 'none'} |\n")
        if summary.get('status') == 'partial' and os.environ.get('GITHUB_ACTIONS'):
            print('::warning::Partial data update published. Failed source data was retained; see source_results for details.')
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
