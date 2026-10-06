"""Entry point: sidebar choices, data preparation, and page dispatch."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import ais as AIS
import field_catalog as CATALOG
import map_renderer
import port_inventory
import portwatch as PORTWATCH
from dashboard_data import (
    ais_collector,
    archive_public_snapshot,
    collector_status,
    load_chokepoints,
    load_ports,
    openwaters_snapshot,
    portwatch_state,
    read_ais_api_key,
    refresh_portwatch_data,
    refresh_vessel_data,
)
from dashboard_state import DashboardViewState
from dashboard_views import (
    render_ais_panel,
    render_assets_panel,
    render_map_panel,
    prepare_monitoring_cards,
    render_method_panel,
    render_ports_panel,
    render_print_panel,
)
from download_panel import render_download_panel
from map_popups import METRIC_LABELS
from ui_controls import multiselect_with_all, selected_values

ASSETS = CATALOG.ASSETS
LEVEL_LABELS = CATALOG.ASSET_LEVEL_LABELS
STATUS_LABELS = CATALOG.OPERATING_STATUS_LABELS
MAP_LAYER_LABELS = map_renderer.MAP_LAYER_LABELS
APP_STYLE = Path(__file__).with_name("dashboard.css").read_text()


def main() -> None:
    st.set_page_config(
        page_title="中东能源与战略通道运输监测",
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="expanded",
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

    country_options = sorted({country for asset in ASSETS for country in asset["countries"]})
    level_options = list(LEVEL_LABELS)
    type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
    metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})
    status_options = list(STATUS_LABELS)
    ais_api_key = read_ais_api_key()
    ais_collector_instance: AIS.AISCollector | None = None

    with st.sidebar:
        st.session_state.pop("monitor_regions", None)
        st.markdown("### 中东能源与战略通道运输监测")
        print_mode = st.toggle(
            "打印模式",
            value=False,
            key="print_mode",
            help="开启后读取港口和咽喉点最近90天数据并生成全项目报告。可下载独立HTML报告，再打印或保存为PDF。",
        )
        map_layers_selection = multiselect_with_all(
            "地图内容",
            list(MAP_LAYER_LABELS),
            key="map_layers",
            default_all=False,
            default=["ports"],
            format_func=lambda value: MAP_LAYER_LABELS[value],
            placeholder="全选或选择图层",
            help="“全选”显示所有图层；清空选择时地图不显示任何图层。",
        )
        selected_map_layers = selected_values(map_layers_selection, list(MAP_LAYER_LABELS))

        available_ports, port_catalog_error = portwatch_state(
            "ports", "catalog", PORTWATCH.MODULE_VERSION
        )
        available_chokepoints, chokepoint_catalog_error = portwatch_state(
            "chokepoints", "catalog", PORTWATCH.MODULE_VERSION
        )

        with st.expander("港口筛选", expanded=False):
            port_country_options = sorted(
                {port["country"] for port in available_ports}, key=port_inventory.country_label
            )
            port_countries_selection = multiselect_with_all(
                "国家",
                port_country_options,
                key="port_countries",
                format_func=port_inventory.country_label,
                placeholder="全选或选择国家",
                help="“全选”表示所有国家；清空选择时不显示港口。",
            )
            selected_port_countries = selected_values(
                port_countries_selection, port_country_options
            )
            country_port_catalog = [
                port for port in available_ports if port["country"] in selected_port_countries
            ]
            port_labels = {
                port["portid"]: port_inventory.port_label(port) for port in country_port_catalog
            }
            port_id_options = [
                port["portid"]
                for port in sorted(
                    country_port_catalog,
                    key=lambda port: (
                        port_inventory.country_label(port["country"]),
                        port_inventory.port_label(port),
                    ),
                )
            ]
            port_ids_selection = multiselect_with_all(
                "港口",
                port_id_options,
                key="port_ids",
                format_func=lambda port_id: port_labels.get(port_id, port_id),
                placeholder="全选或选择港口",
                disabled=not bool(selected_port_countries),
                help="“全选”表示所选国家中的所有港口；清空选择时不显示港口。",
            )
            selected_port_ids = selected_values(port_ids_selection, port_id_options)
            show_only_ports_with_data = st.checkbox(
                "仅在地图上显示有最新数据的港口",
                value=False,
                key="ports_latest_data_only",
                help="只显示在 PortWatch 最新观测日有日度记录的港口；不影响港口列表和统计。",
            )
            if port_catalog_error:
                st.warning(f"港口目录暂时不可用：{port_catalog_error}")
            newest_day, port_latest_error = portwatch_state(
                "ports", "latest_date", PORTWATCH.MODULE_VERSION
            )
            selected_day = newest_day
            if port_latest_error:
                st.warning(f"PortWatch 暂时不可用：{port_latest_error}")
            rolling_days = 7

        with st.expander("咽喉点筛选", expanded=False):
            if chokepoint_catalog_error:
                st.warning(f"咽喉点目录暂时不可用：{chokepoint_catalog_error}")
            chokepoint_id_options = [str(point["portid"]) for point in available_chokepoints]
            chokepoint_labels = {
                str(point["portid"]): point.get(
                    "name_cn", point.get("portname", str(point["portid"]))
                )
                for point in available_chokepoints
            }
            chokepoints_selection = multiselect_with_all(
                "咽喉点",
                chokepoint_id_options,
                key="chokepoint_ids",
                format_func=lambda point_id: chokepoint_labels.get(point_id, point_id),
                placeholder="全选或选择咽喉点",
                help="此筛选独立于港口国家与港口筛选；清空选择时不显示咽喉点。",
            )
            selected_chokepoint_ids = selected_values(chokepoints_selection, chokepoint_id_options)
            newest_chokepoint_day, chokepoint_latest_error = portwatch_state(
                "chokepoints", "latest_date", PORTWATCH.MODULE_VERSION
            )
            if chokepoint_latest_error:
                st.warning(f"咽喉点数据暂时不可用：{chokepoint_latest_error}")

        st.button(
            "刷新 PortWatch 数据", type="primary", width="stretch", on_click=refresh_portwatch_data
        )

        with st.expander("船舶", expanded=True):
            ais_enabled = st.toggle(
                "显示 AIS 实时船位",
                value=True,
                key="ais_enabled",
                help="开启后读取 Open Waters 当前船位快照，并合并已配置的 AISStream 数据；地图还需在“地图内容”中选中“船舶”图层。",
            )
            ais_categories_selection = multiselect_with_all(
                "船型",
                list(AIS.VESSEL_TYPE_LABELS),
                key="ais_categories",
                format_func=lambda key: AIS.VESSEL_TYPE_LABELS[key],
                placeholder="全选或选择船型",
            )
            selected_ais_categories = set(
                selected_values(ais_categories_selection, list(AIS.VESSEL_TYPE_LABELS))
            )
            ais_search = (
                st.text_input(
                    "搜索船名、MMSI或IMO", placeholder="例如 EVER GIVEN / 636…", key="ais_search"
                )
                .strip()
                .lower()
            )
            ais_moving_only = st.toggle("仅航行中（≥0.5节）", value=False, key="ais_moving_only")
            ais_max_age = st.select_slider(
                "最大数据年龄",
                options=[10, 30, 60, 120],
                value=30,
                format_func=lambda value: f"{value}分钟",
                key="ais_max_age",
            )
            open_state = {"vessels": [], "error": None}
            stream_status = "未配置（可选）"
            vessel_status_panel = st.empty()
            st.button(
                "刷新船舶数据",
                type="primary",
                width="stretch",
                disabled=not ais_enabled,
                on_click=refresh_vessel_data,
            )

        with st.expander("油气", expanded=False):
            asset_view = st.radio(
                "资产视图", ["战略生产节点", "完整资产目录"], horizontal=True, key="asset_view"
            )
            st.caption("战略视图按油田群／区块优先，避免组成资产与上级重复展示。")
            asset_search = (
                st.text_input("搜索资产", placeholder="输入中英文名称", key="asset_search")
                .strip()
                .lower()
            )
            selected_countries = selected_values(
                multiselect_with_all(
                    "国家",
                    country_options,
                    key="asset_countries",
                    format_func=port_inventory.country_label,
                    placeholder="全选或选择国家",
                ),
                country_options,
            )
            selected_levels = selected_values(
                multiselect_with_all(
                    "资产层级",
                    level_options,
                    key="asset_levels",
                    format_func=lambda key: LEVEL_LABELS[key],
                    placeholder="全选或选择层级",
                ),
                level_options,
            )
            selected_statuses = selected_values(
                multiselect_with_all(
                    "生产状态",
                    status_options,
                    key="asset_statuses",
                    format_func=lambda key: STATUS_LABELS[key],
                    placeholder="全选或选择状态",
                ),
                status_options,
            )
            values_only = st.toggle("只看有公开数值", value=False, key="values_only")
            output_only = st.toggle("只看有日产量", value=False, key="output_only")
            st.markdown("**高级筛选**")
            selected_types = selected_values(
                multiselect_with_all(
                    "资产类型", type_options, key="asset_types", placeholder="全选或选择资产类型"
                ),
                type_options,
            )
            selected_metrics = selected_values(
                multiselect_with_all(
                    "指标口径",
                    metric_options,
                    key="asset_metrics",
                    format_func=lambda key: METRIC_LABELS[key],
                    placeholder="全选或选择口径",
                ),
                metric_options,
            )

        st.caption(
            "港口和咽喉点在独立筛选区选择；多选器中的“全选”与单项互斥，清空选择表示无匹配结果。"
        )

    tab_map, tab_ports, tab_vessels, tab_assets, tab_download, tab_method = st.tabs(
        ["地图", "港口", "船舶", "油气", "数据下载", "数据与方法"],
        key="main_tabs",
        on_change="rerun",
    )
    selected_chokepoint_day = newest_chokepoint_day

    need_port_data = (tab_map.open and "ports" in selected_map_layers) or tab_ports.open
    need_chokepoint_data = tab_map.open and "chokepoints" in selected_map_layers
    need_ais_data = ais_enabled and (
        (tab_map.open and "vessels" in selected_map_layers) or tab_vessels.open or print_mode
    )
    live_positions = []
    if need_ais_data:
        if ais_api_key:
            ais_collector_instance = ais_collector(ais_api_key, AIS.MODULE_VERSION)
            ais_state = ais_collector_instance.status()
            stream_status = ais_state["status"]
            if ais_state.get("last_error"):
                with vessel_status_panel:
                    st.caption(f"最近 AISStream 错误：{ais_state['last_error']}")
        open_state = openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
        stream_rows = (
            ais_collector_instance.snapshot(max_age_minutes=ais_max_age)
            if ais_collector_instance is not None
            else []
        )
        live_positions = AIS.merge_vessel_snapshots(stream_rows, open_state.get("vessels", []))
        merged_count = len(live_positions)
        with vessel_status_panel:
            st.caption(
                f"数据状态：合并后 {merged_count:,} 艘"
                f"（公开快照 {len(open_state['vessels']):,}）· "
                f"AISStream {stream_status}"
            )
            if open_state.get("error"):
                st.caption(f"Open Waters 错误：{open_state['error']}")
    elif ais_enabled:
        with vessel_status_panel:
            st.caption("船位在地图显示船舶图层、打开船舶页或进入打印模式时读取。")

    ports: list[dict] = []
    port_error = port_catalog_error or port_latest_error
    port_risk_error = None
    if need_port_data and selected_day is not None and not port_error:
        ports, port_error, port_risk_error = load_ports(
            available_ports,
            selected_day,
            selected_port_countries,
            selected_port_ids,
            rolling_days,
            with_risk=tab_ports.open,
        )

    chokepoints: list[dict] = []
    chokepoint_error = chokepoint_catalog_error or chokepoint_latest_error
    if need_chokepoint_data and selected_chokepoint_day is not None and not chokepoint_error:
        chokepoints, chokepoint_error = load_chokepoints(
            available_chokepoints, selected_chokepoint_day, selected_chokepoint_ids
        )

    archive_error = None
    if open_state.get("vessels"):
        try:
            # AISStream positions are archived by its collector; only persist the
            # polled public snapshot here to avoid rewriting the same feed twice.
            archive_public_snapshot(open_state["vessels"])
        except Exception as exc:
            archive_error = f"船位归档失败：{exc}"

    selected_countries = set(selected_countries)
    selected_levels = set(selected_levels)
    selected_types = set(selected_types)
    selected_statuses = set(selected_statuses)
    selected_metrics = set(selected_metrics)
    filtered = [
        asset
        for asset in ASSETS
        if selected_countries.intersection(asset["countries"])
        and asset["asset_level"] in selected_levels
        and asset["asset_type"] in selected_types
        and asset["operating_status"] in selected_statuses
        and asset["metric_type"] in selected_metrics
        and (not values_only or asset["value"] is not None)
        and (not output_only or asset["is_daily_output"])
        and (
            not asset_search
            or asset_search in str(asset["name"]).lower()
            or asset_search in str(asset["name_cn"]).lower()
            or any(asset_search in alias.lower() for alias in asset["aliases"])
        )
        and (asset_view == "完整资产目录" or asset["strategic_default"] or bool(asset_search))
    ]
    visible_map_layers = set(selected_map_layers)
    map_asset_candidates = filtered if "assets" in visible_map_layers else []
    map_assets = [asset for asset in map_asset_candidates if asset["map_drawable"]]
    unlocated_map_assets = [asset for asset in map_asset_candidates if not asset["map_drawable"]]
    map_ports = ports if "ports" in visible_map_layers else []
    if show_only_ports_with_data:
        map_ports = [port for port in map_ports if port.get("has_data")]
    map_chokepoints = chokepoints if "chokepoints" in visible_map_layers else []

    filtered_vessels = (
        AIS.filter_vessels(
            live_positions,
            regions=set(PORTWATCH.REGIONS),
            categories=selected_ais_categories,
            moving_only=ais_moving_only,
            query=ais_search,
        )
        if selected_ais_categories
        else []
    )

    view_state = DashboardViewState(
        live_positions=live_positions,
        filtered_vessels=filtered_vessels,
        ais_status=collector_status(ais_collector_instance),
        open_state=open_state,
        ais_enabled=ais_enabled,
        archive_error=archive_error,
        port_error=port_error,
        chokepoint_error=chokepoint_error,
        map_assets=map_assets,
        map_ports=map_ports,
        map_chokepoints=map_chokepoints,
        visible_map_layers=visible_map_layers,
        selected_day=selected_day,
        selected_chokepoint_day=selected_chokepoint_day,
        focus_assets=bool(asset_search),
        unlocated_asset_count=len(unlocated_map_assets),
        unlocated_port_count=sum(port["lat"] is None or port["lon"] is None for port in map_ports),
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
            render_ports_panel(ports, selected_day, rolling_days, port_error, port_risk_error)
    if tab_download.open:
        with tab_download:
            render_download_panel(
                selected_port_countries,
                selected_port_ids,
                selected_chokepoint_ids,
                newest_day,
                newest_chokepoint_day,
            )
    if tab_vessels.open:
        with tab_vessels:
            render_ais_panel(view_state)
    if tab_assets.open:
        with tab_assets:
            render_assets_panel(filtered, asset_view)
    if tab_method.open:
        with tab_method:
            render_method_panel()
    if print_mode:
        render_print_panel(available_ports, available_chokepoints, view_state)


if __name__ == "__main__":
    main()
