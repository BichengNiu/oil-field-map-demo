"""Entry point: load the complete monitoring snapshot and render each page."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import streamlit as st

import ais as AIS
import ais_history as _ais_history_module
import data_store
from snapshot_store import configure_app_snapshot

# Establish the immutable snapshot before any catalog module is imported.
try:
    configure_app_snapshot()
except Exception as exc:
    st.error(f"数据库快照载入失败：{exc}")
    st.stop()

import portwatch as PORTWATCH
import data_store as _data_store_module
import dashboard_data as _dashboard_data_module
import dashboard_views as _dashboard_views_module
import dashboard_state as _dashboard_state_module
import download_panel as _download_panel_module
import portwatch_downloads as _portwatch_downloads_module
import report_data as _report_data_module
import sea_history_panel as _sea_history_panel_module
from dashboard_data import (
    collector_status,
    load_chokepoints,
    load_ports,
    openwaters_snapshot,
    portwatch_state,
    initialize_storage,
)
from dashboard_state import DashboardViewState
from dashboard_views import (
    render_ais_panel,
    render_assets_panel,
    render_map_panel,
    prepare_monitoring_cards,
    render_method_panel,
    render_ports_panel,
    render_print_report,
)
from download_panel import render_download_panel
from sea_history_panel import render_sea_history_panel

ASSETS = data_store.load_catalog("assets")
APP_STYLE = Path(__file__).with_name("dashboard.css").read_text()
_RUNTIME_SOURCE_FILES = (
    "app.py",
    "ais_history.py",
    "collector.py",
    "data_store.py",
    "dashboard_data.py",
    "dashboard_rows.py",
    "port_types.py",
    "pipeline_catalog.py",
    "port_metadata.py",
    "port_additions.py",
    "port_inventory.py",
    "port_charts.py",
    "ui_controls.py",
    "Ts/TsPlots/ts_plot.py",
    "Ts/TsPlots/style.py",
    "dashboard_state.py",
    "historical_dates.py",
    "dashboard_views.py",
    "download_panel.py",
    "map_renderer.py",
    "map_3d.py",
    "map_3d.js",
    "map_3d_workers.js",
    "map_satellite.js",
    "map_popups.py",
    "monitoring_cards.py",
    "portwatch.py",
    "portwatch_records.py",
    "portwatch_downloads.py",
    "print_report.py",
    "report_data.py",
    "sea_history.py",
    "sea_tracking.py",
    "sea_history_panel.py",
)


def _runtime_source_fingerprint() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for name in _RUNTIME_SOURCE_FILES:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


@st.cache_resource(max_entries=1, show_spinner=False)
def _load_runtime_modules(source_fingerprint: str) -> dict[str, object]:
    """Reload helper modules together when Streamlit reruns a changed entrypoint."""
    for module in (
        importlib.import_module("port_metadata"),
        importlib.import_module("port_additions"),
        importlib.import_module("port_inventory"),
        _data_store_module,
        _ais_history_module,
        importlib.import_module("portwatch_records"),
        PORTWATCH,
        _portwatch_downloads_module,
        importlib.import_module("map_3d"),
        importlib.import_module("map_renderer"),
        importlib.import_module("map_popups"),
        importlib.import_module("port_types"),
        importlib.import_module("pipeline_catalog"),
        importlib.import_module("port_charts"),
        importlib.import_module("ui_controls"),
        importlib.import_module("dashboard_rows"),
        importlib.import_module("monitoring_cards"),
        importlib.import_module("sea_history"),
        importlib.import_module("sea_tracking"),
        importlib.import_module("print_report"),
        importlib.import_module("historical_dates"),
        _report_data_module,
        _dashboard_data_module,
        _dashboard_state_module,
        _dashboard_views_module,
        _download_panel_module,
        _sea_history_panel_module,
    ):
        importlib.reload(module)

    return {
        "DashboardViewState": _dashboard_state_module.DashboardViewState,
        "collector_status": _dashboard_data_module.collector_status,
        "load_chokepoints": _dashboard_data_module.load_chokepoints,
        "load_ports": _dashboard_data_module.load_ports,
        "openwaters_snapshot": _dashboard_data_module.openwaters_snapshot,
        "vessel_tracks": _dashboard_data_module.vessel_tracks,
        "portwatch_state": _dashboard_data_module.portwatch_state,
        "snapshot_date_bounds": _dashboard_data_module.snapshot_date_bounds,
        "nearest_portwatch_day": _dashboard_data_module.nearest_portwatch_day,
        "initialize_storage": _dashboard_data_module.initialize_storage,
        "render_ais_panel": _dashboard_views_module.render_ais_panel,
        "render_assets_panel": _dashboard_views_module.render_assets_panel,
        "render_map_panel": _dashboard_views_module.render_map_panel,
        "prepare_monitoring_cards": _dashboard_views_module.prepare_monitoring_cards,
        "render_method_panel": _dashboard_views_module.render_method_panel,
        "render_ports_panel": _dashboard_views_module.render_ports_panel,
        "render_print_report": _dashboard_views_module.render_print_report,
        "render_download_panel": _download_panel_module.render_download_panel,
    }


def main() -> None:
    st.set_page_config(
        page_title="中东能源与战略通道运输监测",
        page_icon="◉",
        layout="wide",
    )
    globals().update(_load_runtime_modules(_runtime_source_fingerprint()))

    if (
        getattr(PORTWATCH, "MODULE_VERSION", 0) < 8
        or not hasattr(PORTWATCH, "has_independent_statistics")
        or not hasattr(PORTWATCH, "chokepoint_activity")
        or not hasattr(PORTWATCH, "port_risk_capacity")
    ):
        st.error("港口数据模块版本未同步。请在 Streamlit 管理页重启应用后重试。")
        st.stop()

    _render_dashboard("initial")


def _render_dashboard(refresh_revision: str) -> None:

    st.markdown(f"<style>{APP_STYLE}</style>", unsafe_allow_html=True)
    st.title("中东能源与战略通道运输监测")
    initialize_storage()

    revisions = data_store.revisions(("ports", "chokepoints"))
    state_requests = {
        "ports_catalog": ("ports", "catalog", PORTWATCH.MODULE_VERSION,
                          revisions["ports"], refresh_revision),
        "chokes_catalog": ("chokepoints", "catalog", PORTWATCH.MODULE_VERSION,
                           revisions["chokepoints"], refresh_revision),
        "ports_day": ("ports", "latest_date", PORTWATCH.MODULE_VERSION,
                      revisions["ports"], refresh_revision),
        "chokes_day": ("chokepoints", "latest_date", PORTWATCH.MODULE_VERSION,
                       revisions["chokepoints"], refresh_revision),
    }
    loaded = {key: portwatch_state(*args) for key, args in state_requests.items()}
    available_ports, port_catalog_error = loaded["ports_catalog"]
    available_chokepoints, chokepoint_catalog_error = loaded["chokes_catalog"]
    newest_day, port_latest_error = loaded["ports_day"]
    newest_chokepoint_day, chokepoint_latest_error = loaded["chokes_day"]

    tab_map, tab_ports, tab_vessels, tab_assets, tab_download, tab_method = st.tabs(
        ["地图", "港口", "船舶", "油气", "数据下载", "数据与方法"],
        key="main_tabs",
        on_change="rerun",
    )

    display_revisions = data_store.revisions(("ports", "chokepoints", "ais", "sea"))
    first_day, last_day = snapshot_date_bounds((str(data_store.database_path()), *display_revisions.values()))
    with tab_map:
        cards_placeholder = st.empty()
        with st.container(horizontal=True, horizontal_alignment="left"):
            snapshot_day = st.date_input(
                "选择日期", value=None, min_value=first_day, max_value=last_day,
                key="map_snapshot_day", format="YYYY-MM-DD", width=240,
                disabled=first_day is None,
            )
            map_search_placeholder = st.empty()
    snapshot_identity = (str(data_store.database_path()), *display_revisions.values())
    selected_day = nearest_portwatch_day("ports", snapshot_day, snapshot_identity) if snapshot_day else newest_day
    selected_chokepoint_day = nearest_portwatch_day("chokepoints", snapshot_day, snapshot_identity) if snapshot_day else newest_chokepoint_day
    selected_sea_day = (_report_data_module.card_sea_history(
        display_revisions["sea"], snapshot_day.isoformat()).get("selected_day") if snapshot_day else None)
    open_state = openwaters_snapshot(AIS.MODULE_VERSION, snapshot_day)
    live_positions = open_state.get("vessels", [])
    ais_status = collector_status()

    port_error = port_catalog_error or port_latest_error
    ports: list[dict] = []
    if selected_day is not None and available_ports:
        ports, activity_error, _ = load_ports(
            available_ports,
            selected_day,
            rolling_days=7,
            refresh_revision=refresh_revision,
            stored_revision=revisions["ports"],
        )
        port_error = "；".join(error for error in (port_error, activity_error) if error) or None
    else:
        ports = PORTWATCH.decorate(available_ports, {}, {}, None)

    chokepoint_error = chokepoint_catalog_error or chokepoint_latest_error
    chokepoints: list[dict] = []
    if selected_chokepoint_day is not None and available_chokepoints:
        chokepoints, activity_error = load_chokepoints(
            available_chokepoints,
            selected_chokepoint_day,
            refresh_revision,
            revisions["chokepoints"],
        )
        chokepoint_error = "；".join(error for error in (chokepoint_error, activity_error) if error) or None
    else:
        chokepoints = PORTWATCH.decorate_chokepoints(available_chokepoints, {})

    tracks = {}
    if tab_map.open and st.session_state.get("map_show_vessels", True):
        tracks = vessel_tracks(tuple((str(v["mmsi"]), v.get("observed_at"), v["lat"], v["lon"])
                                     for v in live_positions), display_revisions["ais"], str(data_store.database_path()))
    map_assets = [asset for asset in ASSETS if asset.get("map_drawable")]
    view_state = DashboardViewState(
        live_positions=live_positions,
        ais_status=ais_status,
        open_state=open_state,
        archive_error=open_state.get("archive_error"),
        port_error=port_error,
        chokepoint_error=chokepoint_error,
        map_assets=map_assets,
        map_ports=ports,
        map_chokepoints=chokepoints,
        selected_day=selected_day,
        selected_chokepoint_day=selected_chokepoint_day,
        snapshot_day=snapshot_day,
        selected_sea_day=selected_sea_day,
        vessel_tracks=tracks,
    )

    if tab_map.open:
        with tab_map:
            cards, card_errors = prepare_monitoring_cards(
                available_ports, available_chokepoints, view_state,
                data_revisions=display_revisions,
            )
            render_map_panel(view_state, cards, cards_placeholder=cards_placeholder,
                             search_placeholder=map_search_placeholder)
            for error in card_errors:
                st.warning(f"监测卡部分指标不可用：{error}")
    if tab_ports.open:
        with tab_ports:
            render_ports_panel(
                ports,
                selected_day,
                port_error,
            )
    if tab_download.open:
        with tab_download:
            render_sea_history_panel()
            render_download_panel(
                newest_day, newest_chokepoint_day,
                data_revisions=display_revisions,
                refresh_revision=refresh_revision,
            )
    if tab_vessels.open:
        with tab_vessels:
            render_ais_panel(view_state)
    if tab_assets.open:
        with tab_assets:
            render_assets_panel(ASSETS)
    if tab_method.open:
        with tab_method:
            render_method_panel()

    render_print_report(
        available_ports, available_chokepoints, view_state,
        data_revisions=display_revisions,
    )


if __name__ == "__main__":
    main()
