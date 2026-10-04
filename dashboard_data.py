"""Cached data boundaries and refresh callbacks for the dashboard."""

from __future__ import annotations

import os
import uuid
from datetime import date

import streamlit as st

import ais as AIS
import ais_history
import portwatch as PORTWATCH


def read_ais_api_key() -> str:
    """Read the key server-side without requiring or exposing it in the UI."""

    try:
        secret = st.secrets.get("AISSTREAM_API_KEY")
    except Exception:
        secret = None
    return str(secret or os.environ.get("AISSTREAM_API_KEY") or "").strip()


def refresh_portwatch_data() -> None:
    """Invalidate PortWatch data before Streamlit reruns the page."""
    PORTWATCH.clear_live_cache()
    portwatch_state.clear()
    st.session_state["portwatch_report_revision"] = uuid.uuid4().hex


def refresh_vessel_data() -> None:
    """Refresh the public snapshot without restarting the shared AISStream feed."""
    openwaters_snapshot.clear()


@st.cache_resource(max_entries=1, show_spinner=False, on_release=lambda collector: collector.stop())
def ais_collector(api_key: str, collector_version: int) -> AIS.AISCollector:
    return AIS.AISCollector(api_key).start()


@st.cache_data(ttl=15, show_spinner=False)
def openwaters_snapshot(max_age_minutes: int, collector_version: int) -> dict:
    return AIS.openwaters_snapshot(max_age_minutes=max_age_minutes)


@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def archive_public_snapshot(rows: list[dict]) -> int:
    """Archive each identical polled snapshot at most once per five minutes."""
    return ais_history.archive_reports(rows)


@st.cache_data(ttl=60, max_entries=8, show_spinner=False)
def portwatch_state(kind: str, resource: str, module_version: int):
    """Cache both source values and short-lived failures across page reruns."""
    readers = {
        ("ports", "catalog"): PORTWATCH.port_catalog,
        ("chokepoints", "catalog"): PORTWATCH.chokepoint_catalog,
        ("ports", "latest_date"): PORTWATCH.latest_date,
        ("chokepoints", "latest_date"): PORTWATCH.latest_chokepoint_date,
    }
    reader = readers[kind, resource]
    try:
        return reader(), None
    except Exception as exc:
        return ([] if resource == "catalog" else None), f"{type(exc).__name__}: {exc}"


def collector_status(collector: AIS.AISCollector | None) -> dict:
    """Return the collector status with one stable shape when it is optional."""

    if collector is not None:
        return collector.status()
    return {
        "status": "未配置（可选）",
        "last_error": None,
        "last_message_at": None,
        "last_position_message_at": None,
        "raw_event_count": 0,
        "rejected_event_count": 0,
        "message_count": 0,
        "position_message_count": 0,
        "static_message_count": 0,
        "tracked_vessels": 0,
        "compression_enabled": None,
    }


def load_ports(
    available_ports: list[dict],
    selected_day: date,
    selected_port_countries: list[str],
    selected_port_ids: list[str],
    rolling_days: int,
    *,
    with_risk: bool = False,
) -> tuple[list[dict], str | None, str | None]:
    ports = []
    port_error = None
    port_risk_error = None
    countries = set(selected_port_countries)
    chosen_ids = set(selected_port_ids)
    try:
        catalog = [
            port
            for port in available_ports
            if port["country"] in countries and port["portid"] in chosen_ids
        ]
        ids = tuple(p["portid"] for p in catalog)
        statistical_ids = tuple(
            sorted(
                str(port["portid"])
                for port in available_ports
                if PORTWATCH.has_independent_statistics(port)
            )
        )
        if ids:
            activity_all = (
                PORTWATCH.daily_activity(selected_day, statistical_ids) if statistical_ids else {}
            )
            rolling_all = (
                PORTWATCH.rolling_activity(selected_day, statistical_ids, rolling_days)
                if statistical_ids
                else {}
            )
            # The historical route-risk model is slower and is only used in
            # the detailed port table; do not block the default map on it.
            risk_all = {}
            if with_risk and statistical_ids:
                try:
                    risk_all = PORTWATCH.port_risk_capacity(statistical_ids)
                except Exception as exc:
                    port_risk_error = str(exc)
            activity = {
                port_id: activity_all[port_id] for port_id in ids if port_id in activity_all
            }
            rolling = {port_id: rolling_all[port_id] for port_id in ids if port_id in rolling_all}
            risk_capacity = (
                {port_id: risk_all.get(port_id) for port_id in ids} if with_risk else None
            )
            ports = PORTWATCH.decorate(catalog, activity, rolling, risk_capacity)
    except Exception as exc:
        port_error = str(exc)

    return ports, port_error, port_risk_error


def load_chokepoints(
    available_chokepoints: list[dict],
    selected_chokepoint_day: date,
    selected_chokepoint_ids: list[str],
) -> tuple[list[dict], str | None]:
    chokepoints = []
    chokepoint_error = None
    try:
        chosen_chokepoint_ids = set(selected_chokepoint_ids)
        chokepoint_catalog = [
            point
            for point in available_chokepoints
            if str(point["portid"]) in chosen_chokepoint_ids
        ]
        chokepoint_ids = tuple(str(point["portid"]) for point in available_chokepoints)
        if chokepoint_ids:
            chokepoint_values_all = PORTWATCH.chokepoint_activity(
                selected_chokepoint_day, chokepoint_ids
            )
            chokepoints = PORTWATCH.decorate_chokepoints(chokepoint_catalog, chokepoint_values_all)
    except Exception as exc:
        chokepoint_error = str(exc)

    return chokepoints, chokepoint_error
