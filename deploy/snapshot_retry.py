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


def decision(snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Retry clock must include a timezone")
    local_now = now.astimezone(LOCAL_ZONE)
    start = datetime.combine(local_now.date(), time(8), LOCAL_ZONE)
    if local_now < start:
        start -= timedelta(days=1)
    result = {"status": "retry_due", "primary_window_start": start.isoformat(),
              "reason": "本主执行时段尚无成功发布的完整采集快照"}
    if not isinstance(snapshot, dict) or not snapshot.get("completed_at"):
        return result
    completed = datetime.fromisoformat(snapshot["completed_at"].replace("Z", "+00:00"))
    if completed.tzinfo is None or completed > now + timedelta(minutes=5):
        raise ValueError("Published collection time is missing its timezone or lies in the future")
    # A catalog edit, source publication date, or run notification is not a
    # successful full collection. The publisher writes this full marker only
    # after source/freshness/history checks; read it from the pulled main DB.
    after = snapshot.get("after") or {}
    if completed >= start and after.get("latest_vessel") and after.get("counts"):
        result.update(status="skipped_already_published",
                      last_successful_collection=completed.astimezone(LOCAL_ZONE).isoformat(),
                      reason="该主执行时段已有完整采集快照发布；不重复采集或推送")
    return result


def main():
    with duckdb.connect(str(ROOT / "runtime" / "monitoring.duckdb"), read_only=True) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key='published_snapshot'").fetchone()
    result = decision(json.loads(row[0]) if row else None)
    print(json.dumps(result, ensure_ascii=False))
    return 3 if result["status"] == "skipped_already_published" else 0


if __name__ == "__main__":
    raise SystemExit(main())
