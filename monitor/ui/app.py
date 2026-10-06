"""Entry point: load the complete monitoring snapshot and render each page."""

from __future__ import annotations

import streamlit as st

import monitor.vessels.ais as AIS
import monitor.oilgas.field_catalog as CATALOG
import monitor.ports.portwatch as PORTWATCH
from monitor.ui.dashboard_data import (
    ais_collector,
    collector_status,
    load_chokepoints,
    load_ports,
    openwaters_snapshot,
    portwatch_state,
    read_ais_api_key,
)
from monitor.ui.dashboard_state import DashboardViewState
from monitor.ui.dashboard_views import (
    render_ais_panel,
    render_assets_panel,
    render_map_panel,
    prepare_monitoring_cards,
    render_method_panel,
    render_ports_panel,
    render_print_report,
)
from monitor.ui.download_panel import render_download_panel
from monitor.ui.sea_history_panel import render_sea_history_panel
from monitor.common.paths import asset_path

ASSETS = CATALOG.ASSETS
APP_STYLE = asset_path("styles", "dashboard.css").read_text()


def main() -> None:
    st.set_page_config(
        page_title="中东能源与战略通道运输监测",
        page_icon="◉",
        layout="wide",
    )

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

    selected_day = newest_day
    selected_chokepoint_day = newest_chokepoint_day
    ais_api_key = read_ais_api_key()
    ais_collector_instance: AIS.AISCollector | None = None
    if ais_api_key:
        ais_collector_instance = ais_collector(ais_api_key, AIS.MODULE_VERSION)

    open_state = openwaters_snapshot(AIS.MODULE_VERSION)
    stream_rows = (
        ais_collector_instance.snapshot(max_age_minutes=120)
        if ais_collector_instance is not None
        else []
    )
    live_positions = AIS.merge_vessel_snapshots(
        stream_rows, open_state.get("vessels", [])
    )
    ais_status = collector_status(ais_collector_instance)

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

    if tab_map.open:
        with tab_map:
            cards, card_errors = prepare_monitoring_cards(
                available_ports, available_chokepoints, view_state
            )
            render_map_panel(view_state, cards)
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

    render_print_report(available_ports, available_chokepoints, view_state)


if __name__ == "__main__":
    main()
