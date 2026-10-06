"""Data preparation for the on-demand full-project print report."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

import portwatch_downloads
from portwatch_records import latest_by_node


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
    latest = latest_by_node(history, require_date=False)
    return [
        {**point, **latest.get(str(point.get("portid")), {})}
        for point in catalog
    ]


@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def comparison_history(kind: str, node_ids: tuple[str, ...], end_day: str,
                       refresh_revision: str = "initial") -> list[dict]:
    """Read last year's matching month for the cover card year-on-year comparison."""
    from monitoring_cards import windows
    start, end = windows(date.fromisoformat(end_day))[-1]
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, start, end, cache_revision=refresh_revision, cache_ttl_seconds=900)
    return rows


@st.cache_data(ttl=60, show_spinner=False)
def card_vessel_history() -> list[dict]:
    """Read the existing local archive without creating or backfilling it."""
    import sqlite3
    import ais_history
    path = ais_history.archive_path()
    if not path.exists():
        return []
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as conn:
        return [json.loads(row[0]) for row in conn.execute(
            'SELECT payload FROM reports WHERE observed >= ?',
            ((date.today() - timedelta(days=400)).isoformat(),))]
