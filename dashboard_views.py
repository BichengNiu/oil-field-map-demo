"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

from datetime import date

import streamlit as st

import ais as AIS
import csv_export
import dashboard_rows
import field_catalog as CATALOG
import map_renderer
import monitoring_cards
import portwatch_downloads
from datetime import datetime
from zoneinfo import ZoneInfo
import portwatch as PORTWATCH
import print_report
import report_data
from dashboard_state import DashboardViewState
from dashboard_data import refresh_portwatch_data, refresh_portwatch_risk, refresh_vessel_data
from download_panel import open_download_tab
from map_popups import asset_popup, chokepoint_popup, port_popup

ASSETS = CATALOG.ASSETS


def queue_map_screenshot() -> None:
    st.session_state["map_screenshot_requested"] = True


def render_map_panel(state: DashboardViewState, summary_cards: list) -> bool:
    screenshot_requested = st.session_state.pop("map_screenshot_requested", False)
    st.html(monitoring_cards.cards_html(summary_cards))
    with st.container(horizontal=True, key="map_layer_filters"):
        show_assets = st.checkbox("油气", value=True, key="map_show_assets")
        show_ports = st.checkbox("港口", value=True, key="map_show_ports",
                                 help="同时显示港口与咽喉点")
        show_vessels = st.checkbox("船舶", value=True, key="map_show_vessels")
    stream_state = state.ais_status
    if state.port_error:
        st.error(f"港口数据加载失败：{state.port_error}")
    if state.chokepoint_error:
        st.error(f"咽喉点数据加载失败：{state.chokepoint_error}")
    if state.archive_error:
        st.error(state.archive_error)
    if state.open_state.get("error"):
        st.error(f"Open Waters 快照加载失败：{state.open_state['error']}")
    elif not state.live_positions:
        st.caption("暂无最近两小时的本地船位；点击“刷新船舶数据”读取一次上游快照。")
    if summary := state.open_state.get("refresh_summary"):
        st.caption(
            f"最近一次手动船位刷新：读取 {summary['fetched']:,} 条有效报告，"
            f"新增归档 {summary['inserted']:,} 条。"
        )
    if stream_state.get("last_error") and not state.live_positions:
        st.error(f"AISStream 暂无可用船位：{stream_state['last_error']}")
    st.iframe(
        map_renderer.build_map_html(
            state.map_assets if show_assets else [],
            state.map_ports if show_ports else [],
            state.map_chokepoints if show_ports else [],
            state.live_positions if show_vessels else [],
            state.selected_day.isoformat() if state.selected_day else "无数据",
            state.selected_chokepoint_day.isoformat()
            if state.selected_chokepoint_day
            else "无数据",
            visible_categories={name for name, selected in (
                ("assets", show_assets), ("ports", show_ports), ("vessels", show_vessels)
            ) if selected},
            asset_popup=asset_popup,
            port_popup=port_popup,
            chokepoint_popup=chokepoint_popup,
            screenshot_requested=screenshot_requested,
        ),
        height=735,
    )
    with st.container(horizontal=True, key="map_refresh_actions"):
        st.button("刷新港口数据", type="primary", width="content",
                  on_click=refresh_portwatch_data)
        st.button("刷新船舶数据", type="primary", width="content",
                  on_click=refresh_vessel_data)
        st.button("保存地图PNG", type="primary", width="content",
                  on_click=queue_map_screenshot)
        prepare_report = st.button("准备打印报告", width="content")
    return prepare_report


def render_ais_panel(state: DashboardViewState) -> None:
    st.subheader("船舶")
    all_positions = state.live_positions
    vessels = all_positions
    rows = dashboard_rows.vessel_rows(vessels)
    ais_status = state.ais_status
    has_position_data = bool(all_positions)
    region_counts = {
        region: {
            "open_waters": sum(
                vessel.get("region") == region
                and str(vessel.get("data_source") or "").startswith("Open Waters")
                for vessel in all_positions
            ),
            "aisstream": sum(
                vessel.get("region") == region
                and vessel.get("data_source") == "AISStream"
                for vessel in all_positions
            ),
        }
        for region in AIS.REGIONS
    }
    if state.archive_error:
        st.error(state.archive_error)
    vessel_metric = len(vessels) if has_position_data else "—"
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("当前船位", vessel_metric)
    v2.metric("航行中", sum(bool(v.get("moving")) for v in vessels) if has_position_data else "—")
    v3.metric(
        "油轮/液货船",
        sum(v.get("category") == "tanker" for v in vessels) if has_position_data else "—",
    )
    v4.metric(
        "货船", sum(v.get("category") == "cargo" for v in vessels) if has_position_data else "—"
    )
    v5.metric(
        "船型待识别",
        sum(v.get("category") == "unknown" for v in vessels) if has_position_data else "—",
    )
    if state.open_state.get("error"):
        st.error(f"Open Waters 快照错误：{state.open_state['error']}")
    if ais_status.get("last_error"):
        st.error(f"最近连接错误：{ais_status['last_error']}")
    st.markdown("**各监测水域当前船位**")
    region_rows = []
    for region, counts in region_counts.items():
        if has_position_data:
            open_waters_count = (
                "不可用" if state.open_state.get("error") else counts["open_waters"]
            )
            aisstream_count = (
                "已暂停"
                if ais_status.get("status") == "已暂停（手动刷新模式）"
                else counts["aisstream"]
            )
            total_count = counts["open_waters"] + counts["aisstream"]
        else:
            open_waters_count = "不可用" if state.open_state.get("error") else "—"
            aisstream_count = (
                "已暂停" if ais_status.get("status") == "已暂停（手动刷新模式）" else "—"
            )
            total_count = "—"
        region_rows.append(
            {
                "水域": region,
                "Open Waters": open_waters_count,
                "AISStream": aisstream_count,
                "合计": total_count,
            }
        )
    st.dataframe(
        region_rows,
        width="stretch",
        hide_index=True,
    )
    if rows:
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
            height=570,
            column_config={"来源": st.column_config.LinkColumn("来源")},
        )
        st.download_button(
            "下载当前船位快照 CSV",
            csv_export.csv_bytes(rows, list(rows[0])),
            file_name="ais_vessel_snapshot.csv",
            mime="text/csv",
            type="primary",
        )
    else:
        st.caption("暂无最近两小时的本地船位；可在地图页点击“刷新船舶数据”读取一次上游快照。")


def render_ports_panel(
    ports: list[dict],
    selected_day: date | None,
    rolling_days: int,
    port_error: str | None,
    port_risk_error: str | None,
) -> None:
    port_rows = dashboard_rows.port_rows(ports, selected_day, rolling_days)
    st.subheader("港口日活动")
    st.button("刷新风险运力", key="refresh_port_risk", on_click=refresh_portwatch_risk,
              help="仅在点击时请求历史航线风险运力模型。")
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    elif port_rows:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("港口总数", len(port_rows))
        p2.metric("当日有进港", sum((p.get("portcalls") or 0) > 0 for p in ports))
        p3.metric(
            f"{rolling_days}天持续活跃", sum((p.get("active_day_rate") or 0) >= 50 for p in ports)
        )
        risk_values = [p["risk_capacity"] for p in ports if p.get("risk_capacity") is not None]
        p4.metric(
            "风险运力合计",
            "—"
            if port_risk_error or not risk_values
            else f"{sum(risk_values) / 10000:,.1f} 万吨/日",
        )
        if port_risk_error:
            st.error(f"历史风险运力暂不可用：{port_risk_error}")
        st.dataframe(
            port_rows,
            width="stretch",
            hide_index=True,
            height=560,
            column_config={
                "来源": st.column_config.LinkColumn("来源"),
                "坐标来源": st.column_config.LinkColumn("坐标来源"),
            },
        )
        st.download_button(
            "下载港口列表 CSV",
            csv_export.csv_bytes(port_rows, list(port_rows[0])),
            file_name=f"portwatch_ports_{selected_day.isoformat()}.csv",
            mime="text/csv",
            type="primary",
        )
        st.button(
            "下载所列港口历史",
            key="download_port_history",
            on_click=open_download_tab,
            args=("ports", tuple(p["portid"] for p in ports)),
        )


def render_assets_panel(assets: list[dict]) -> None:
    asset_rows = dashboard_rows.asset_rows(assets)
    st.subheader("油气资产目录")
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("资产总数", len(assets))
    a2.metric("可绘制", sum(bool(a["map_drawable"]) for a in assets))
    a3.metric("有产量记录", sum(bool(a["is_daily_output"]) for a in assets))
    a4.metric(
        "产能／目标", sum(a["value"] is not None and not a["is_daily_output"] for a in assets)
    )
    a5.metric("含公开目录参考", sum(bool(a.get("public_metadata")) for a in assets))
    st.dataframe(
        asset_rows,
        width="stretch",
        hide_index=True,
        height=620,
        column_config={
            "状态证据链接": st.column_config.LinkColumn("状态证据"),
            "坐标来源链接": st.column_config.LinkColumn("坐标来源"),
            "来源链接": st.column_config.LinkColumn("目录来源"),
            "参考资料链接": st.column_config.LinkColumn("GEM公开镜像（固定版本）"),
            "参考资产页面": st.column_config.LinkColumn("GEM资产／项目页面"),
            "发现年（目录参考）": st.column_config.NumberColumn(format="%d"),
            "商业投产年（目录参考）": st.column_config.NumberColumn(format="%d"),
        },
    )


def render_method_panel() -> None:
    st.subheader("范围、口径与数据限制")
    st.markdown(
        "**更新方式。** 页面载入只读本地缓存；地图下方按钮手动刷新 PortWatch 和船舶数据，港口页按钮单独刷新风险运力。"
    )
    st.dataframe(
        [
            {
                "数据": "港口 / 咽喉点日度记录",
                "当前更新": "页面只读本地缓存；点击地图刷新按钮时拉取一次",
                "进一步自动化": "源站发布时间决定最新观测日；缺失仍保持未知",
            },
            {
                "数据": "实时船位",
                "当前更新": "只读本地最近两小时档案；点击地图刷新按钮时查询一次 Open Waters",
                "进一步自动化": "AISStream 当前暂停；单独运行采集服务才会持续采集",
            },
            {
                "数据": "港口 / 咽喉点官方目录",
                "当前更新": "本地缓存；点击地图刷新按钮更新",
                "进一步自动化": "补充 WPI / 运营商名录仍需版本核验",
            },
            {
                "数据": "港口风险运力",
                "当前更新": "点击港口页“刷新风险运力”按钮时读取",
                "进一步自动化": "源为历史航线模型；重新抓取不代表实时风险",
            },
            {
                "数据": "油气产量、产能、状态和坐标",
                "当前更新": "带来源的静态披露；公开目录参考点另标版本和精度限制",
                "进一步自动化": "接运营商 / 监管机构 API 或公告抓取，校验资产、日期、单位、产量 / 产能后更新",
            },
            {
                "数据": "油气运营商、权益、发现年和投产年",
                "当前更新": "Global Energy Monitor 2026-03公开镜像参考（CC BY 4.0）；不代表当前在产",
                "进一步自动化": "新版本需核对名称和层级；原字段缺失保持为空，不填补日产量",
            },
            {
                "数据": "船位归档",
                "当前更新": "只归档有明确观测时间的上游快照；接收时间另存，地图与船舶页只展示当前船位",
                "进一步自动化": "统一MONITORING_DB_PATH持久盘；需要连续采样时显式运行独立服务；免费AIS仅为观测覆盖",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "**地图与截图。** 港口和咽喉点分别使用源站最新观测日，船舶图层显示当前AIS快照；油气保留披露日期。地图下方的“保存地图PNG”按钮可导出当前视野、图例、日期、弹窗及底图署名。"
    )
    st.markdown(
        "**港口覆盖。** 地图读取 IMF 当前维护的 PortWatch 港口点位数据库，"
        "覆盖下表五个水域框及沙特、阿联酋、伊拉克、伊朗、科威特、卡塔尔、阿曼、巴林全境的源库港口。"
        "另补港务局、运营商及NGA具名设施；无独立统计的设施保留未知，无可靠坐标时仅列目录。"
    )
    st.dataframe(
        [
            {"水域": name, "南界": b[0], "北界": b[1], "西界": b[2], "东界": b[3]}
            for name, b in PORTWATCH.REGIONS.items()
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        f"[IMF PortWatch 方法说明]({PORTWATCH.SOURCE}) · "
        "[当前港口点位 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) · "
        "[每日港口活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0) · "
        "[每日咽喉点 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0) · "
        "[风险运力网络 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/spillovers_port_level_impact/FeatureServer/0)"
    )
    st.markdown("**港口派生指标。** 所有窗口指标固定使用最新观测日及此前6个日历日；缺报不补零。")
    st.dataframe(
        [
            {
                "指标": "港口活动指数",
                "计算": "当前窗口日均有效进港艘次 ÷ 前一等长窗口日均值 × 100",
                "解释": "100持平；高于100表示进港活动增加",
            },
            {
                "指标": "船型结构",
                "计算": "窗口内各船型进港艘次 ÷ 全部进港艘次",
                "解释": "集装箱、干散货、普通货物、滚装、油轮/液货船",
            },
            {
                "指标": "活跃天数率",
                "计算": "窗口内有效进港艘次大于0的天数 ÷ 窗口天数",
                "解释": "反映港口活动连续性",
            },
            {
                "指标": "单船平均货量",
                "计算": "窗口内估算进口量与出口量之和 ÷ 有效进港艘次",
                "解释": "单位万吨/艘次；属于AIS载荷估算",
            },
            {
                "指标": "进出口平衡指数",
                "计算": "(出口量−进口量) ÷ (出口量+进口量) × 100",
                "解释": "−100进口导向；+100出口导向",
            },
            {
                "指标": "风险运力",
                "计算": "该港所有出港航线 daily_capacity_at_risk 之和",
                "解释": "2019—2024历史航线网络冲击暴露，非实时值",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "PortWatch 的 portcalls 是进入港界并通过贸易挂靠筛选的有效进港艘次，不是在港船舶存量；"
        "货量根据 AIS、载重和吃水估算。单日 0 只表示源表当日为 0；窗口不完整或比较基期为 0 时，"
        "派生指标保持为空，不以 0 替代。tanker 可能包含原油、成品油及其他液体货物。"
    )
    st.markdown(
        f"**船舶数据。** 免费快照来自[Open Waters开放AIS网络]({AIS.OPENWATERS_SOURCE})，"
        f"可选[AISStream WebSocket API]({AIS.SOURCE})在服务器端接收五个监测水域及红海北、南段的船级广播；"
        "船位快照用于地图、船舶页和后台打印报告；仅显示两小时内有时间戳的报文，可点击地图下方按钮刷新。"
        "浏览器只接收标准化的每船最新位置，不接收API Key。"
        "多源位置按MMSI合并，航行阈值为0.5节；"
        "上游来源署名随船舶表及弹窗显示。"
    )
    st.markdown(
        "AIS 基础船型只能可靠区分油轮／液货船、货船、客船等大类，不能直接识别集装箱船、干散货船、"
        "原油油轮或成品油轮。AIS 是事件驱动广播，覆盖中断、设备关闭、错误 MMSI、延迟或位置欺骗都会造成缺失；"
        "未收到报文不等于水域内船舶数为 0。实时船位不能替代 PortWatch 按港界和贸易规则处理的日度挂靠指标。"
    )
    st.markdown(
        "**咽喉点。** 打印地图的空心紫色圆点标示全部监测咽喉点。"
        "popup列示总通过船数、估算承载货量及五类船型分解；港口和咽喉点分别使用源站最新观测日，缺报不补零。"
    )
    st.markdown(
        f"**资产覆盖与战略层级（公开目录，非全量保证）。** 目录保留全部{len(ASSETS)}项公开命名的生产、开发、发现或历史资产；"
        f"地图显示其中{sum(a['map_drawable'] for a in ASSETS)}个具备可绘制坐标的资产。"
        "上级油田群、区块或特许区有"
        "直接披露值时，地图和目录按资产层级分别列示；上级缺坐标时可使用已定位组成"
        "资产的几何中心，并在弹窗中明确标注。"
    )
    st.markdown(
        "**坐标质量。** 地图优先使用资产级公开WGS84点位；区块缺少直接点位时，可使用组成油田"
        "或公开设施的代表点／几何中心；组成单田仍缺点位时，可使用最近上级资产代表点。此类坐标"
        "明确标为“近似”，只用于地图定位，不代表区块边界、储层范围或精确井位。坐标证据链接可在"
        "popup和资产表中追溯。"
    )
    st.markdown(
        "**产量与产能。** 油气统一使用橙色叉号；指标性质、数据日期和披露情况在弹窗及表格中列明。"
        "实际产量、历史产量、产能、目标和规划增量分别标注；未披露数值不视为零。不同日期、商品和权益口径"
        "不得相加。来源为千桶/日的油品数值在界面统一换算为万桶/日；生产状态带证据时点，"
        "不等于实时遥测。"
    )


def prepare_monitoring_cards(available_ports, available_chokepoints, state,
                             port_history=None, choke_history=None,
                             refresh_revision=None):
    """Prepare the same summary independently of the optional print panel."""
    errors = []
    # The map should never initiate a 90-day download. Use only validated local
    # history here; explicit report preparation may fetch its own history.
    revision = refresh_revision or "initial"
    port_ids = tuple(sorted(str(p["portid"]) for p in available_ports
                            if PORTWATCH.has_independent_statistics(p)))
    choke_ids = tuple(sorted(str(p["portid"]) for p in available_chokepoints))
    histories = []
    for kind, ids, day, supplied in (
        ("ports", port_ids, state.selected_day, port_history),
        ("chokepoints", choke_ids, state.selected_chokepoint_day, choke_history),
    ):
        rows = supplied
        if rows is None:
            rows = []
            if ids and day:
                try:
                    rows = report_data.history_window(kind, ids, day.isoformat(), revision)
                except portwatch_downloads.CacheMiss:
                    pass
                except Exception as exc:
                    errors.append(f"{kind} 历史窗口：{type(exc).__name__}: {exc}")
        histories.append(rows)
    port_history, choke_history = histories
    comparison_ports, comparison_chokes = [], []
    for kind, ids, day, target in (
        ("ports", port_ids, state.selected_day, comparison_ports),
        ("chokepoints", choke_ids, state.selected_chokepoint_day, comparison_chokes),
    ):
        if ids and day:
            try:
                target.extend(report_data.comparison_history(kind, ids, day.isoformat(), revision))
            except portwatch_downloads.CacheMiss:
                pass
            except Exception as exc:
                errors.append(f"{kind} 同比记录：{type(exc).__name__}: {exc}")
    sea_history = []
    sea_observation_card = None
    try:
        sea_state = report_data.card_sea_history()
        sea_history = sea_state["rows"]
        sea_observation_card = sea_state.get("card")
        if sea_state.get("error"):
            errors.append(sea_state["error"])
    except Exception as exc:
        errors.append(f"海域历史记录：{type(exc).__name__}: {exc}")
    cards = monitoring_cards.build_cards(
        available_ports, available_chokepoints,
        port_history + comparison_ports, choke_history + comparison_chokes,
        state.live_positions, state.selected_day, state.selected_chokepoint_day,
        vessel_day=datetime.now(ZoneInfo("Asia/Shanghai")).date(), assets=ASSETS,
        sea_passage_history=sea_history,
        sea_observation_card=sea_observation_card,
    )
    return cards, errors


def render_print_report(
    available_ports: list[dict], available_chokepoints: list[dict], state: DashboardViewState
) -> None:
    selected_day = state.selected_day
    selected_chokepoint_day = state.selected_chokepoint_day
    live_positions = state.live_positions
    port_error = state.port_error
    chokepoint_error = state.chokepoint_error
    open_state = state.open_state
    report_port_catalog = list(available_ports)
    report_choke_catalog = list(available_chokepoints)
    report_assets = list(ASSETS)
    report_vessels = [
        {
            key: vessel.get(key)
            for key in (
                "mmsi", "name", "lat", "lon", "region", "category", "category_label", "moving"
            )
        }
        for vessel in live_positions
    ]

    report_port_ids = tuple(
        sorted(
            str(port["portid"])
            for port in report_port_catalog
            if PORTWATCH.has_independent_statistics(port)
        )
    )
    report_choke_ids = tuple(sorted(str(point["portid"]) for point in report_choke_catalog))
    report_errors = []
    report_revision = st.session_state.get("portwatch_report_revision", "initial")
    if port_error:
        report_errors.append(f"港口最新数据：{port_error}")
    if chokepoint_error:
        report_errors.append(f"咽喉点最新数据：{chokepoint_error}")
    if open_state.get("error"):
        report_errors.append(f"Open Waters：{open_state['error']}")

    report_port_history = []
    report_choke_history = []
    if selected_day is not None and report_port_ids:
        try:
            with st.spinner("准备打印报告：读取最近90天港口记录…"):
                report_port_history = report_data.history_window(
                    "ports", report_port_ids, selected_day.isoformat(), report_revision
                )
        except Exception as exc:
            report_errors.append(f"ports 历史窗口：{type(exc).__name__}: {exc}")
    if selected_chokepoint_day is not None and report_choke_ids:
        try:
            with st.spinner("准备打印报告：读取最近90天咽喉点记录…"):
                report_choke_history = report_data.history_window(
                    "chokepoints",
                    report_choke_ids,
                    selected_chokepoint_day.isoformat(),
                    report_revision,
                )
        except Exception as exc:
            report_errors.append(f"chokepoints 历史窗口：{type(exc).__name__}: {exc}")

    cards, card_errors = prepare_monitoring_cards(
        report_port_catalog, report_choke_catalog, state, report_port_history, report_choke_history
    )
    report_errors.extend(card_errors)

    report_latest_ports = report_data.merge_latest_rows(report_port_catalog, report_port_history)

    report_asset_table = [dashboard_rows.print_asset_record(asset) for asset in report_assets]
    report_ais_state = state.ais_status
    report_ais_status = str(report_ais_state.get("status") or "等待数据")
    report_ais_note = (
        f"Open Waters 快照 {len(open_state.get('vessels') or [])} 艘；"
        f"AISStream 状态：{report_ais_status}"
    )
    report_html = report_data.cached_print_report({
        "scope_label": "全部监测对象",
        "monitoring_summary_cards": cards,
        "generated_at": None,
        "port_catalog": report_port_catalog,
        "choke_catalog": report_choke_catalog,
        "latest_ports": report_latest_ports,
        "port_history": report_port_history,
        "choke_history": report_choke_history,
        "assets": report_assets,
        "asset_table": report_asset_table,
        "vessels": report_vessels,
        "regions": PORTWATCH.REGIONS,
        "port_day": selected_day,
        "choke_day": selected_chokepoint_day,
        "ais_status": report_ais_status,
        "ais_source_note": report_ais_note,
        "errors": report_errors,
    })
    st.html(print_report.PRINT_CSS + report_html)
