"""Data preparation for the on-demand full-project print report."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import portwatch_downloads


@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def history_window(kind: str, node_ids: tuple[str, ...], end_day: str,
                   refresh_revision: str = "initial") -> list[dict]:
    """Return a verified 90-day window; failed reads are not cached."""
    if not node_ids:
        return []
    end = date.fromisoformat(end_day)
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, end - timedelta(days=89), end,
        cache_revision=refresh_revision, cache_ttl_seconds=900)
    return rows


def merge_latest_rows(catalog: list[dict], history: list[dict]) -> list[dict]:
    """Attach each node's latest observed historical row, preserving empty nodes."""
    latest: dict[str, dict] = {}
    for row in history:
        node_id = str(row.get("portid", ""))
        if node_id and (node_id not in latest or
                        str(row.get("date", "")) > str(latest[node_id].get("date", ""))):
            latest[node_id] = row
    return [
        {**point, **latest.get(str(point.get("portid")), {})}
        for point in catalog
    ]
