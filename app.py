"""Entry point: load the complete monitoring snapshot and render each page."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import streamlit as st

import ais as AIS
import ais_history as _ais_history_module
import field_catalog as CATALOG
import portwatch as PORTWATCH
import collector as _collector_module
import data_store as _data_store_module
import dashboard_data as _dashboard_data_module
import dashboard_views as _dashboard_views_module
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

ASSETS = CATALOG.ASSETS
APP_STYLE = Path(__file__).with_name("dashboard.css").read_text()
_RUNTIME_SOURCE_FILES = (
    "app.py",
    "ais_history.py",
    "collector.py",
    "data_store.py",
    "dashboard_data.py",
    "dashboard_views.py",
    "download_panel.py",
    "portwatch.py",
    "portwatch_downloads.py",
    "report_data.py",
    "sea_history_panel.py",
)


def _runtime_source_fingerprint() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).resolve().parent
    for name in _RUNTIME_SOURCE_FILES:
        digest.update(name.encode())
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


@st.cache_resource(max_entries=2, show_spinner=False)
def _load_runtime_modules(source_fingerprint: str) -> dict[str, object]:
    """Reload helper modules together when Streamlit reruns a changed entrypoint."""
    for module in (
        _data_store_module,
        _ais_history_module,
        PORTWATCH,
        _portwatch_downloads_module,
        _collector_module,
        _report_data_module,
        _dashboard_data_module,
        _dashboard_views_module,
        _download_panel_module,
        _sea_history_panel_module,
    ):
        importlib.reload(module)

    return {
        "collector_status": _dashboard_data_module.collector_status,
        "load_chokepoints": _dashboard_data_module.load_chokepoints,
        "load_ports": _dashboard_data_module.load_ports,
        "openwaters_snapshot": _dashboard_data_module.openwaters_snapshot,
        "portwatch_state": _dashboard_data_module.portwatch_state,
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
        getattr(PORTWATCH, "MODULE_VERSION", 0) < 5
        or not hasattr(PORTWATCH, "has_independent_statistics")
        or not hasattr(PORTWATCH, "chokepoint_activity")
        or not hasattr(PORTWATCH, "port_risk_capacity")
    ):
        st.error("港口数据模块版本未同步。请在 Streamlit 管理页重启应用后重试。")
        st.stop()

    st.markdown(f"<style>{APP_STYLE}</style>", unsafe_allow_html=True)
    st.title("中东能源与战略通道运输监测")
    initialize_storage()
    st.caption("数据仅在点击刷新按钮时从上游更新；页面载入仅读取本地缓存和档案。")

    available_ports, port_catalog_error = portwatch_state(
        "ports", "catalog", PORTWATCH.MODULE_VERSION
    )
    available_chokepoints, chokepoint_catalog_error = portwatch_state(
        "chokepoints", "catalog", PORTWATCH.MODULE_VERSION
    )
    newest_day, port_latest_error = portwatch_state(
        "ports", "latest_date", PORTWATCH.MODULE_VERSION
    )
    newest_chokepoint_day, chokepoint_latest_error = portwatch_state(
        "chokepoints", "latest_date", PORTWATCH.MODULE_VERSION
    )

    tab_map, tab_ports, tab_vessels, tab_assets, tab_download, tab_method = st.tabs(
        ["地图", "港口", "船舶", "油气", "数据下载", "数据与方法"],
        key="main_tabs",
        on_change="rerun",
    )

    st.session_state.setdefault("portwatch_report_revision", "initial")
    selected_day = newest_day
    selected_chokepoint_day = newest_chokepoint_day
    open_state = openwaters_snapshot(AIS.MODULE_VERSION)
    live_positions = open_state.get("vessels", [])
    ais_status = collector_status()

    port_error = port_catalog_error or port_latest_error
    port_risk_error = None
    ports: list[dict] = []
    if (
        (tab_map.open or tab_ports.open)
        and selected_day is not None
        and not port_error
    ):
        ports, port_error, port_risk_error = load_ports(
            available_ports,
            selected_day,
            rolling_days=7,
            with_risk=tab_ports.open,
        )

    chokepoint_error = chokepoint_catalog_error or chokepoint_latest_error
    chokepoints: list[dict] = []
    if tab_map.open and selected_chokepoint_day is not None and not chokepoint_error:
        chokepoints, chokepoint_error = load_chokepoints(
            available_chokepoints,
            selected_chokepoint_day,
        )

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
    )

    prepare_report = False
    if tab_map.open:
        with tab_map:
            cards, card_errors = prepare_monitoring_cards(
                available_ports, available_chokepoints, view_state
            )
            prepare_report = render_map_panel(view_state, cards)
            for error in card_errors:
                st.warning(f"监测卡部分指标不可用：{error}")
    if tab_ports.open:
        with tab_ports:
            render_ports_panel(
                ports,
                selected_day,
                7,
                port_error,
                port_risk_error,
            )
    if tab_download.open:
        with tab_download:
            render_sea_history_panel()
            render_download_panel(newest_day, newest_chokepoint_day)
    if tab_vessels.open:
        with tab_vessels:
            render_ais_panel(view_state)
    if tab_assets.open:
        with tab_assets:
            render_assets_panel(ASSETS)
    if tab_method.open:
        with tab_method:
            render_method_panel()

    if prepare_report:
        render_print_report(available_ports, available_chokepoints, view_state)


if __name__ == "__main__":
    main()
