"""Dashboard page renderers with explicit current-view inputs."""

from __future__ import annotations

from datetime import date

import streamlit as st

import ais as AIS
import csv_export
import dashboard_rows
import field_catalog as CATALOG
import map_renderer
import portwatch as PORTWATCH
import print_report
import report_data
from dashboard_state import DashboardViewState
from download_panel import open_download_tab
from map_popups import asset_popup, chokepoint_popup, port_popup, vessel_popup

ASSETS = CATALOG.ASSETS


def render_map_panel(state: DashboardViewState) -> None:
    all_positions = state.live_positions
    filtered_vessels = state.filtered_vessels
    map_vessels = filtered_vessels if "vessels" in state.visible_map_layers else []
    stream_state = state.ais_status
    if state.port_error:
        st.error(f"港口数据加载失败：{state.port_error}")
    elif "ports" in state.visible_map_layers and not state.map_ports:
        st.info(
            "港口图层已开启，但当前没有可绘制点位。请检查国家筛选和数据状态；"
            "港口筛选留空时显示所选国家的全部港口。"
        )
    if state.chokepoint_error:
        st.error(f"咽喉点数据加载失败：{state.chokepoint_error}")
    if state.archive_error:
        st.warning(state.archive_error)
    if not state.ais_enabled:
        st.info("船舶图层已关闭。")
    elif "vessels" in state.visible_map_layers:
        if stream_state.get("last_error") and not all_positions:
            st.warning(f"AISStream 暂无可用船位，后台将自动重连：{stream_state['last_error']}")
        if stream_state.get("archive_error"):
            st.warning(f"AISStream 船位归档失败：{stream_state['archive_error']}")
        if state.open_state.get("error"):
            st.warning(f"Open Waters 免费数据暂不可用：{state.open_state['error']}")
        if not all_positions and not state.open_state.get("error"):
            if (
                stream_state.get("status") == "订阅已确认"
                and stream_state.get("raw_event_count", 0) == 0
            ):
                st.warning(
                    "AISStream 已确认订阅但未送达事件；Open Waters 当前快照也没有船位。"
                    "这不代表监测水域内没有船舶。"
                )
            else:
                st.info("两处数据源尚未返回当前可用船位；不能据此判断水域内没有船舶。")
        elif all_positions and not map_vessels:
            st.info(
                f"已收到 {len(all_positions):,} 个船位，但船型、航行状态或搜索筛选没有匹配结果。"
                "清空这些筛选即可恢复显示。"
            )
        elif map_vessels:
            st.caption(
                f"地图正在显示 {len(map_vessels):,} 个 AIS 船位；低缩放级别会聚合密集船位，"
                "放大地图可查看单船图标。"
            )
    if state.unlocated_asset_count:
        st.info(
            f"当前筛选有 {state.unlocated_asset_count} 项仅列目录：既无可核验独立坐标，也无可用的"
            "上级资产代表点，因此不以猜测位置绘图。可在‘油气’表查看坐标证据。"
        )
    if state.unlocated_port_count:
        st.info(f"当前筛选有 {state.unlocated_port_count} 个港口尚无可靠坐标，仅列于‘港口’目录。")
    st.iframe(
        map_renderer.build_map_html(
            state.map_assets,
            state.map_ports,
            state.map_chokepoints,
            map_vessels,
            state.selected_day.isoformat() if state.selected_day else "无数据",
            state.selected_chokepoint_day.isoformat()
            if state.selected_chokepoint_day
            else "无数据",
            focus_assets=state.focus_assets,
            ais_configured=bool(state.ais_enabled),
            visible_layers=state.visible_map_layers,
            asset_popup=asset_popup,
            port_popup=port_popup,
            chokepoint_popup=chokepoint_popup,
            vessel_popup=vessel_popup,
        ),
        height=735,
    )


def render_ais_panel(state: DashboardViewState) -> None:
    st.subheader("船舶")
    if not state.ais_enabled:
        st.info("船舶位置已关闭，可在左侧‘船舶’中启用。")
        return
    all_positions = state.live_positions
    vessels = state.filtered_vessels
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
        st.warning(state.archive_error)
    vessel_metric = len(vessels) if has_position_data else "—"
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("筛选后船舶", vessel_metric)
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
    if state.open_state.get("truncated"):
        st.warning("Open Waters 返回结果达到该区域查询上限，较早船位可能未包含。")
    if state.open_state.get("error"):
        st.warning(f"Open Waters 快照错误：{state.open_state['error']}")
    if ais_status.get("compression_enabled") is False:
        st.warning("AISStream 未确认 WebSocket 压缩协商；未压缩连接可能受带宽限制。")
    if ais_status.get("last_error"):
        st.warning(f"最近连接错误：{ais_status['last_error']}；采集器会自动指数退避重连。")
    st.markdown("**各监测水域当前船位**")
    st.dataframe(
        [
            {
                "水域": region,
                "Open Waters": counts["open_waters"],
                "AISStream": counts["aisstream"],
                "合计": counts["open_waters"] + counts["aisstream"],
            }
            for region, counts in region_counts.items()
        ],
        width="stretch",
        hide_index=True,
    )
    st.caption("这里统计当前快照中按 MMSI 合并后的船位；0 条表示当前数据源没有返回报文，不代表该水域没有船舶。")
    if ais_status.get("status") == "未配置（可选）":
        st.info(
            "AISStream 尚未配置。Open Waters 的公开接收站覆盖并非全球连续覆盖；"
            "若苏伊士运河或曼德海峡没有报文，可在部署环境配置 AISSTREAM_API_KEY 接入该区域广播。"
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
    elif not all_positions:
        if (
            ais_status.get("status") == "订阅已确认"
            and ais_status.get("raw_event_count", 0) == 0
            and not state.open_state.get("error")
        ):
            st.warning(
                "AISStream 已确认订阅但尚未送达事件，Open Waters 当前快照也没有返回船位。"
                "当前船位不可用，不能据此判断监测水域内没有船舶。"
            )
        elif state.open_state.get("error"):
            st.warning("免费公共快照暂时不可用；可稍后刷新。没有报文不等于水域内没有船舶。")
        else:
            st.info("正在等待监测水域内的新 AIS 报文；当前船位尚不可用。")
    else:
        st.info("当前船型、水域、搜索和数据年龄筛选没有匹配船舶。")


def render_ports_panel(
    ports: list[dict],
    selected_day: date | None,
    rolling_days: int,
    port_error: str | None,
    port_risk_error: str | None,
) -> None:
    port_rows = dashboard_rows.port_rows(ports, selected_day, rolling_days)
    st.subheader("港口日活动")
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    elif port_rows:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("筛选后港口", len(port_rows))
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
            st.caption(f"历史风险运力暂不可用：{port_risk_error}")
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
            "下载当前筛选结果 CSV",
            csv_export.csv_bytes(port_rows, list(port_rows[0])),
            file_name=f"portwatch_ports_{selected_day.isoformat()}.csv",
            mime="text/csv",
            type="primary",
        )
        st.button(
            "下载当前筛选港口历史",
            key="download_port_history",
            on_click=open_download_tab,
            args=("ports", tuple(p["portid"] for p in ports)),
        )
    else:
        st.info("当前筛选没有匹配港口。选择“全选”可恢复全部港口。")


def render_assets_panel(filtered: list[dict], asset_view: str) -> None:
    asset_rows = dashboard_rows.asset_rows(filtered)
    st.subheader(f"油气目录 · {asset_view}")
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("当前视图", len(filtered))
    a2.metric("可绘制", sum(bool(a["map_drawable"]) for a in filtered))
    a3.metric("有产量记录", sum(bool(a["is_daily_output"]) for a in filtered))
    a4.metric(
        "产能／目标", sum(a["value"] is not None and not a["is_daily_output"] for a in filtered)
    )
    a5.metric("底层目录", len(ASSETS))
    st.info(
        "上级节点有直接披露值时优先采用该值，组成资产不重复计入；"
        "逐田产量缺失时，“产量显示”可列注明所属范围的合计参考；参考值不分配到单田、不重复计入。"
        "不同日期、商品或口径的子项不会自动相加。搜索可临时显示完整目录中的匹配资产。"
    )
    aggregate_count = sum(
        not asset["is_daily_output"] and bool(asset.get("aggregate_references"))
        for asset in filtered
    )
    st.caption(f"其中 {aggregate_count} 项逐田产量未确认，显示注明范围的合计参考；产量记录包含历史期间。")
    reference_count = sum(bool(asset.get("public_metadata")) for asset in filtered)
    if reference_count:
        st.caption(
            f"本视图 {reference_count} 项补有 Global Energy Monitor 2026-03公开目录参考（CC BY 4.0）；"
            "运营商、权益和投产年有版本限制，不证明当前在产。未披露日产量继续留空。"
        )
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
        "**更新方式。** 动态数据和目录使用进程级短期缓存；切换筛选时复用已读取数据。点击侧栏“刷新 PortWatch 数据”可清除 PortWatch 实时缓存并重读；源站未发布新记录时，观测日期不会改变；请求失败明确显示不可用。"
    )
    st.dataframe(
        [
            {
                "数据": "港口 / 咽喉点日度记录",
                "当前更新": "使用短期缓存；可手动刷新",
                "进一步自动化": "已接入；源站发布时间决定最新观测日",
            },
            {
                "数据": "实时船位",
                "当前更新": "显示船舶图层、打开船舶页或打印时读取 Open Waters；可选 AISStream 后台持续接收",
                "进一步自动化": "AISStream 需配置服务端密钥；页面另有手动刷新",
            },
            {
                "数据": "港口 / 咽喉点官方目录",
                "当前更新": "使用24小时缓存；失败后60秒重试，手动刷新可提前重读",
                "进一步自动化": "已接入；补充 WPI / 运营商名录仍需版本核验",
            },
            {
                "数据": "港口风险运力",
                "当前更新": "使用24小时缓存；打开港口页时按需读取",
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
                "进一步自动化": "设置持久AIS_ARCHIVE_PATH以跨重启保存；五水域完整历史需有授权的数据源",
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.markdown(
        "**地图与截图。** 港口和咽喉点分别使用源站最新观测日，船舶图层显示当前AIS快照；油气保留披露日期。地图右上角保存 PNG，包含当前视野、图例、日期、弹窗及底图署名。"
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
    st.markdown("**港口派生指标。** 所有窗口指标固定使用所选观测日及此前6个日历日；缺报不补零。")
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
    st.warning(
        "PortWatch 的portcalls是进入港界并通过贸易挂靠筛选的有效进港艘次，不是在港船舶存量。"
        "货量根据AIS、载重和吃水估算。单日0只表示源表当日为0；窗口不完整或比较基期为0时，"
        "派生指标保持为空，不以0替代。tanker可能包含原油、成品油及其他液体货物。"
    )
    st.markdown(
        f"**船舶数据。** 免费快照来自[Open Waters开放AIS网络]({AIS.OPENWATERS_SOURCE})，"
        f"可选[AISStream WebSocket API]({AIS.SOURCE})在服务器端接收五个监测水域的船级广播；"
        "船位快照用于地图、船舶页和后台打印报告；停留期间可点击侧栏“刷新船舶数据”。"
        "浏览器只接收标准化的每船最新位置，不接收API Key。"
        "多源位置按MMSI合并，航行阈值为0.5节，超过所选最大数据年龄的船位只从当前显示中排除；"
        "上游来源署名随船舶表及弹窗显示。"
    )
    st.warning(
        "AIS基础船型只能可靠区分油轮／液货船、货船、客船等大类，不能直接识别集装箱船、"
        "干散货船、原油油轮或成品油轮。AIS是事件驱动广播，覆盖中断、设备关闭、错误MMSI、"
        "延迟或位置欺骗都会造成缺失；未收到报文不等于水域内船舶数为0。实时船位不能替代"
        "PortWatch经港界和贸易规则处理后的日度挂靠指标。"
    )
    st.markdown(
        "**咽喉点。** 地图紫色六边形显示所选水域内咽喉点的日度记录。"
        "popup列示总通过船数、估算承载货量及五类船型分解；港口和咽喉点分别使用源站最新观测日，缺报不补零。"
    )
    st.markdown(
        f"**资产覆盖与战略层级（公开目录，非全量保证）。** 底层目录保留全部{len(ASSETS)}项公开命名的生产、开发、发现或历史资产；"
        f"默认地图仅显示{sum(a['strategic_default'] for a in ASSETS)}个战略生产节点，其中"
        f"{sum(a['strategic_default'] and a['map_drawable'] for a in ASSETS)}个具备可绘制坐标。"
        "上级油田群、区块或特许区有"
        "直接披露值时，地图使用上级值并隐藏组成资产，避免双重计算；上级缺坐标时可使用已定位组成"
        "资产的几何中心，并在popup中明确标注。没有可靠数值的小型单田仍可在“完整资产目录”中查询。"
    )
    st.markdown(
        "**坐标质量。** 地图优先使用资产级公开WGS84点位；区块缺少直接点位时，可使用组成油田"
        "或公开设施的代表点／几何中心；组成单田仍缺点位时，可使用最近上级资产代表点。此类坐标"
        "明确标为“近似”，只用于地图定位，不代表区块边界、储层范围或精确井位。坐标证据链接可在"
        "popup和资产表中追溯。"
    )
    st.markdown(
        "**产量与产能。** 油气统一使用橙色实心菱形；指标性质、数据日期和披露情况在弹窗及表格中列明。"
        "实际产量、历史产量、产能、目标和规划增量分别标注；未披露数值不视为零。不同日期、商品和权益口径"
        "不得相加。来源为千桶/日的油品数值在界面统一换算为万桶/日；生产状态带证据时点，"
        "不等于实时遥测。"
    )


def render_print_report(
    available_ports: list[dict], available_chokepoints: list[dict], state: DashboardViewState
) -> None:
    selected_day = state.selected_day
    selected_chokepoint_day = state.selected_chokepoint_day
    live_positions = state.live_positions
    ais_enabled = state.ais_enabled
    port_error = state.port_error
    chokepoint_error = state.chokepoint_error
    open_state = state.open_state
    report_port_catalog = list(available_ports)
    report_choke_catalog = list(available_chokepoints)
    report_assets = [asset for asset in ASSETS if asset.get("strategic_default")]
    report_vessels = list(live_positions)

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

    report_latest_ports = report_data.merge_latest_rows(report_port_catalog, report_port_history)

    report_asset_table = [dashboard_rows.print_asset_record(asset) for asset in report_assets]
    report_ais_state = state.ais_status
    report_ais_status = (
        "已关闭" if not ais_enabled else str(report_ais_state.get("status") or "等待数据")
    )
    report_ais_note = (
        f"Open Waters 快照 {len(open_state.get('vessels') or [])} 艘；"
        f"AISStream 状态：{report_ais_status}"
    )
    report_html = print_report.build_report_html(
        scope_label="全项目",
        generated_at=None,
        port_catalog=report_port_catalog,
        choke_catalog=report_choke_catalog,
        latest_ports=report_latest_ports,
        port_history=report_port_history,
        choke_history=report_choke_history,
        assets=report_assets,
        asset_table=report_asset_table,
        vessels=report_vessels,
        regions=PORTWATCH.REGIONS,
        port_day=selected_day,
        choke_day=selected_chokepoint_day,
        ais_status=report_ais_status,
        ais_source_note=report_ais_note,
        errors=report_errors,
    )
    st.html(print_report.PRINT_CSS + report_html)
