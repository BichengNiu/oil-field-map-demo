"""Cached data preparation for the full-project browser print report."""
from __future__ import annotations

from datetime import date, timedelta
import json
import os

import streamlit as st

import portwatch_downloads
import print_report
from portwatch_records import latest_by_node
import data_store
from monitoring_cards import windows


@st.cache_data(ttl=900, max_entries=12, show_spinner=False)
def history_window(kind: str, node_ids: tuple[str, ...], end_day: str,
                   data_revision: int = 0, allow_network: bool = False) -> list[dict]:
    """Return cached report history, using the upstream only when explicitly enabled."""
    if not node_ids:
        return []
    end = date.fromisoformat(end_day)
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, end - timedelta(days=89), end,
        cache_revision=0, cache_ttl_seconds=86_400,
        allow_stale=True, cache_only=not allow_network)
    return rows


@st.cache_data(ttl=900, max_entries=24, show_spinner=False)
def card_activity_history(kind: str, node_ids: tuple[str, ...], end_day: str,
                          data_revision: int = 0) -> list[dict]:
    """Read only locally present rows for the card's five indicator windows."""
    if not node_ids:
        return []
    selected = date.fromisoformat(end_day)
    rows = data_store.cached_portwatch_periods(
        kind, node_ids, windows(selected)
    )
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
                       data_revision: int = 0, allow_network: bool = False) -> list[dict]:
    """Read last year's matching month for the cover card year-on-year comparison."""
    start, end = windows(date.fromisoformat(end_day))[-1]
    rows, _ = portwatch_downloads.fetch_window(
        kind, node_ids, start, end, cache_revision=0, cache_ttl_seconds=86_400,
        allow_stale=True, cache_only=not allow_network)
    return rows


def sea_history_config() -> dict:
    config = {}
    for key in ("SEA_HISTORY_ARCHIVE_PATH", "SEA_HISTORY_BUNDLE_PATH",
                "SEA_HISTORY_BUNDLE_URL", "SEA_HISTORY_BEARER_TOKEN", "SEA_HISTORY_IMPORT_TOKEN"):
        try:
            secret = st.secrets.get(key)
        except Exception:
            secret = None
        config[key] = str(secret or os.environ.get(key) or "").strip()
    return config


@st.cache_data(ttl=60, show_spinner=False)
def card_sea_history(data_revision: int = 0) -> dict:
    """Read the shared event archive without synchronizing its delivery source."""
    import sea_history
    config = sea_history_config()
    result = sea_history.read_history(sea_history.archive_path(config))
    if not result["source"]:
        import sea_tracking
        result = sea_tracking.observation_summary()
    return {**result, "error": None}
