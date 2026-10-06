"""Cached data preparation for the full-project browser print report."""
from __future__ import annotations

from datetime import date, timedelta
import json

import streamlit as st

import portwatch_downloads
import print_report
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


@st.cache_data(
    ttl=900, max_entries=8, show_spinner=False,
    # Hash every input value using the C JSON encoder rather than recursively
    # traversing thousands of history dictionaries in Streamlit's hasher.
    # Dates and exact Decimal asset values retain their textual representation.
    hash_funcs={dict: lambda value: json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str)},
)
def cached_print_report(report_inputs: dict) -> str:
    """Reuse report HTML while its source data and report inputs are unchanged."""
    return print_report.build_report_html(**report_inputs)


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
