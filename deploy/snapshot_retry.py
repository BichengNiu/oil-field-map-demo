"""Read-only gate for the existing publisher's backup scheduled invocation.

Exit 0: a full collection is still due. Exit 3: already published in this
primary window. Other exits are errors, never permission to bypass validation.
"""
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb


ROOT = Path(__file__).resolve().parents[1]
LOCAL_ZONE = ZoneInfo("Asia/Dubai")
SOURCES = ('ais', 'ports', 'chokepoints')


def successful_sources(snapshot, now):
    """Read per-source checkpoints; old complete snapshots remain compatible."""
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    after = snapshot.get('after') or {}
    legacy = (snapshot.get('completed_at') if after.get('latest_vessel') and after.get('counts')
              and snapshot.get('full_collection_complete', True) else None)
    results = snapshot.get('source_results')
    output = {}
    for source in SOURCES:
        checkpoint = ((results.get(source) or (results.get('portwatch') if source != 'ais' else None) or {})
                      if isinstance(results, dict) else {})
        value = (checkpoint.get('last_successful_collection')
                 if isinstance(results, dict) else legacy)
        if value:
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp > now + timedelta(minutes=5):
                raise ValueError('Published source time is missing its timezone or lies in the future')
            output[source] = stamp
    return output


def decision(snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Retry clock must include a timezone")
    local_now = now.astimezone(LOCAL_ZONE)
    start = datetime.combine(local_now.date(), time(8), LOCAL_ZONE)
    if local_now < start:
        start -= timedelta(days=1)
    result = {"status": "retry_due", "primary_window_start": start.isoformat(),
              "reason": "本主执行时段仍有数据源未成功发布"}
    successes = successful_sources(snapshot, now)
    pending = [source for source in SOURCES if source not in successes or successes[source] < start]
    result['pending_sources'] = pending
    if not pending:
        result.update(status="skipped_already_published",
                      last_successful_collection=max(successes.values()).astimezone(LOCAL_ZONE).isoformat(),
                      reason="该主执行时段各数据源均已成功发布；不重复采集或推送")
    return result


def main():
    with duckdb.connect(str(ROOT / "runtime" / "monitoring.duckdb"), read_only=True) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key='published_snapshot'").fetchone()
    result = decision(json.loads(row[0]) if row else None)
    print(json.dumps(result, ensure_ascii=False))
    return 3 if result["status"] == "skipped_already_published" else 0


if __name__ == "__main__":
    raise SystemExit(main())
