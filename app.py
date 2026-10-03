"""中东公开命名油气分层地图 DEMO。"""

from __future__ import annotations

import html
import json
import csv
import io
import os
import time
from datetime import date, datetime, timedelta, timezone

import streamlit as st

import field_catalog as CATALOG
import ais as AIS
import ais_history
import portwatch as PORTWATCH
import port_inventory
import portwatch_downloads
import report_data
import map_renderer
import print_report

ASSETS = CATALOG.ASSETS

if (getattr(PORTWATCH, "MODULE_VERSION", 0) < 5
        or not hasattr(PORTWATCH, "has_independent_statistics")
        or not hasattr(PORTWATCH, "chokepoint_activity")
        or not hasattr(PORTWATCH, "port_risk_capacity")):
    st.error("港口数据模块版本未同步。请在 Streamlit 管理页重启应用后重试。")
    st.stop()


ALL_SELECTION = "全选"


def _exclusive_multiselect_changed(key: str) -> None:
    """Keep 全选 exclusive while allowing an empty selection to mean none."""
    previous_key = f"_selection_previous_{key}"
    selected = list(st.session_state.get(key, []))
    previous = list(st.session_state.get(previous_key, []))
    newly_added = [value for value in selected if value not in previous]
    if ALL_SELECTION in newly_added:
        selected = [ALL_SELECTION]
    elif ALL_SELECTION in selected:
        selected = [value for value in selected if value != ALL_SELECTION]
    st.session_state[key] = selected
    st.session_state[previous_key] = list(selected)


def _multiselect_with_all(label: str, options: list, *, key: str,
                          default_all: bool = True, default: list | None = None,
                          format_func=None, **kwargs) -> list:
    """Add an exclusive 全选 option; an empty selection stays empty."""
    options = list(options)
    valid_options = set(options)
    previous_key = f"_selection_previous_{key}"
    if key not in st.session_state:
        selected = [ALL_SELECTION] if default_all else list(default or [])
    else:
        current = st.session_state.get(key, [])
        selected = list(current) if isinstance(current, (list, tuple)) else [current]
        # Migrate an old empty selection once; new empty selections remain empty.
        if not selected and default_all and previous_key not in st.session_state:
            selected = [ALL_SELECTION]
        selected = [value for value in selected
                    if value == ALL_SELECTION or value in valid_options]
        if ALL_SELECTION in selected and len(selected) > 1:
            previous = list(st.session_state.get(previous_key, []))
            newly_added = [value for value in selected if value not in previous]
            if ALL_SELECTION in newly_added:
                selected = [ALL_SELECTION]
            else:
                selected = [value for value in selected if value != ALL_SELECTION]
    st.session_state[key] = selected
    st.session_state[previous_key] = list(selected)

    def display(value):
        if value == ALL_SELECTION:
            return ALL_SELECTION
        return format_func(value) if format_func else str(value)

    return st.multiselect(
        label, [ALL_SELECTION, *options], key=key, format_func=display,
        on_change=_exclusive_multiselect_changed, args=(key,), **kwargs)


def _selected_values(selection: list, options: list) -> list:
    """Expand explicit 全选; keep [] as an empty filter."""
    return list(options) if ALL_SELECTION in selection else list(selection)


def _ais_api_key() -> str:
    """Read the key server-side without requiring or exposing it in the UI."""

    try:
        secret = st.secrets.get("AISSTREAM_API_KEY")
    except Exception:
        secret = None
    return str(secret or os.environ.get("AISSTREAM_API_KEY") or "").strip()


def _refresh_portwatch_data() -> None:
    """Invalidate PortWatch data before Streamlit reruns the page."""
    PORTWATCH.clear_live_cache()
    st.session_state["portwatch_report_revision"] = (
        int(st.session_state.get("portwatch_report_revision", 0)) + 1)


def _refresh_vessel_data() -> None:
    """Refresh the public snapshot without restarting the shared AISStream feed."""
    _openwaters_snapshot.clear()


@st.cache_resource(show_spinner=False)
def _ais_collector(api_key: str, collector_version: int) -> AIS.AISCollector:
    return AIS.AISCollector(api_key).start()


@st.cache_data(ttl=15, show_spinner=False)
def _openwaters_snapshot(max_age_minutes: int, collector_version: int) -> dict:
    return AIS.openwaters_snapshot(max_age_minutes=max_age_minutes)


@st.cache_data(ttl=300, max_entries=12, show_spinner=False)
def _archive_public_snapshot(rows: list[dict]) -> int:
    """Archive each identical polled snapshot at most once per five minutes."""
    return ais_history.archive_reports(rows)


def _open_download_tab(kind: str | None = None, node_ids: tuple[str, ...] = ()) -> None:
    """Open the downloader with either the map scope or a chosen node."""
    st.session_state["main_tabs"] = "数据下载"
    st.session_state["pw_download_mode"] = "全部可用历史"
    if node_ids:
        st.session_state["pw_download_scope"] = "按条件筛选"
        st.session_state["pw_download_regions"] = [ALL_SELECTION]
        st.session_state["pw_download_countries"] = [ALL_SELECTION]
        st.session_state["pw_download_nodes"] = [(kind, pid) for pid in node_ids]
    else:
        st.session_state["pw_download_scope"] = "沿用地图筛选"
        st.session_state.pop("pw_download_nodes", None)
    st.session_state["pw_download_kinds"] = [kind] if kind else [ALL_SELECTION]


def _render_portwatch_download_panel(selected_port_countries: list[str],
                                     selected_port_ids: list[str],
                                     selected_chokepoint_ids: list[str],
                                     newest_port_day: date | None,
                                     newest_choke_day: date | None) -> None:
    st.subheader("港口与咽喉要道数据")
    st.caption("来源：IMF PortWatch。下载的是AIS推算的港口／要道日度汇总，不含逐船AIS航迹；日度数据从2019-01-01起，缺报不补零。")
    latest = [day for day in (newest_port_day, newest_choke_day) if day]
    default_last = max(latest) if latest else datetime.now(timezone.utc).date()
    last_downloadable = datetime.now(timezone.utc).date()

    try:
        all_ports = [portwatch_downloads.node("ports", row) for row in PORTWATCH.port_catalog()]
        all_chokes = [portwatch_downloads.node("chokepoints", row)
                      for row in PORTWATCH.chokepoint_catalog()]
    except Exception as exc:
        st.error(f"无法读取下载节点目录：{exc}")
        return

    kind_options = list(portwatch_downloads.KINDS)
    kinds_selection = _multiselect_with_all(
        "数据类型", kind_options, key="pw_download_kinds",
        format_func=lambda value: portwatch_downloads.KINDS[value],
        placeholder="全选或选择数据类型")
    selected_kinds = set(_selected_values(kinds_selection, kind_options))
    scope_options = ["全部项目节点", "按条件筛选", "沿用地图筛选"]
    scope = st.radio("节点范围", scope_options, horizontal=True, key="pw_download_scope")
    selected_nodes = []
    if scope == "全部项目节点":
        selected_nodes = [*all_ports, *all_chokes]
    elif scope == "沿用地图筛选":
        selected_nodes = [n for n in all_ports
                          if n["country"] in selected_port_countries
                          and n["portid"] in selected_port_ids]
        choke_ids = set(selected_chokepoint_ids)
        selected_nodes += [n for n in all_chokes if n["portid"] in choke_ids]
    else:
        region_options = list(PORTWATCH.REGIONS)
        regions_selection = _multiselect_with_all(
            "水域", region_options, key="pw_download_regions",
            placeholder="全选或选择水域")
        regions = set(_selected_values(regions_selection, region_options))
        region_ports = [n for n in all_ports if n["region"] in regions]
        country_options = sorted(
            {n["country"] for n in region_ports if n["country"]},
            key=port_inventory.country_label)
        countries_selection = _multiselect_with_all(
            "国家", country_options, key="pw_download_countries",
            format_func=port_inventory.country_label,
            placeholder="全选或选择国家")
        countries = set(_selected_values(countries_selection, country_options))
        candidate_ports = [n for n in region_ports if n["country"] in countries]
        choke_options = [n for n in all_chokes if n["region"] in regions]
        node_options = [("ports", n["portid"]) for n in candidate_ports] + [
            ("chokepoints", n["portid"]) for n in choke_options]
        labels = {
            ("ports", n["portid"]):
                port_inventory.port_label(n)
            for n in candidate_ports
        }
        labels.update({("chokepoints", n["portid"]): n["node_name"] for n in choke_options})
        nodes_selection = _multiselect_with_all(
            "节点", node_options, key="pw_download_nodes",
            format_func=lambda key: labels.get(key, key[1]),
            placeholder="全选或选择节点")
        chosen_nodes = set(_selected_values(nodes_selection, node_options))
        selected_nodes = [n for n in candidate_ports if ("ports", n["portid"]) in chosen_nodes]
        selected_nodes += [n for n in choke_options
                           if ("chokepoints", n["portid"]) in chosen_nodes]

    selected_nodes = [n for n in selected_nodes if n["node_kind"] in selected_kinds]
    st.caption(f"当前范围：{len(selected_nodes):,} 个节点，其中有独立活动统计的节点 "
               f"{sum(n['statistics_available'] for n in selected_nodes):,} 个。")

    mode = st.radio("时间范围", ["最新数据", "历史区间", "全部可用历史"], horizontal=True,
                    key="pw_download_mode")
    first = last = None
    if mode == "历史区间":
        preset = st.radio("日期快捷选项", ["近30天", "近90天", "今年以来", "自定义日期"],
                          horizontal=True, key="pw_download_preset")
        if preset == "自定义日期":
            current = st.session_state.get("pw_download_dates")
            default_start, default_end = (current if isinstance(current, (tuple, list))
                and len(current) == 2 else
                (max(portwatch_downloads.FIRST_DAY, default_last - timedelta(days=29)), default_last))
            dates = st.date_input("UTC日期范围", value=(default_start, default_end),
                min_value=portwatch_downloads.FIRST_DAY, max_value=last_downloadable,
                key="pw_download_dates")
            if isinstance(dates, (tuple, list)) and len(dates) == 2:
                first, last = dates
        else:
            last = default_last
            days = {"近30天": 30, "近90天": 90}.get(preset)
            first = date(last.year, 1, 1) if preset == "今年以来" else max(
                portwatch_downloads.FIRST_DAY, last - timedelta(days=days - 1))
    derived = st.checkbox("附加连续7日和30日均值", value=False, key="pw_download_derived")
    force = st.checkbox("重新读取源站（忽略24小时历史缓存）", value=False,
                        key="pw_download_force")
    st.caption("港口进口／出口为AIS推算货量；咽喉要道capacity为通行运力。两者口径不同。")
    if not selected_nodes:
        st.info("按条件选择至少一个数据类型与节点。")
        return

    def selection_signature():
        import hashlib
        payload = {"nodes": sorted((n["node_kind"], n["portid"]) for n in selected_nodes),
                   "mode": mode, "start": first.isoformat() if first else None,
                   "end": last.isoformat() if last else None, "derived": derived, "force": force}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    signature = selection_signature()
    if st.button("生成下载数据", type="primary", key="pw_download_generate"):
        try:
            status = st.status("正在查询PortWatch历史…", expanded=True)
            last_notice = [0.0]
            def progress(message: str):
                now = time.monotonic()
                if now - last_notice[0] >= 1.0:
                    status.update(label=message, state="running", expanded=True)
                    last_notice[0] = now
            mode_key = {"最新数据": "latest", "历史区间": "history", "全部可用历史": "all"}[mode]
            result = portwatch_downloads.collect(selected_nodes, mode_key,
                first=first, last=last, derived=derived, force=force, progress=progress)
            exports = {
                f"csv_{kind}": portwatch_downloads.csv_bytes(
                    rows, portwatch_downloads.columns(kind, result["manifest"]["derived"]))
                for kind, rows in result["datasets"].items()
            }
            exports["zip"] = portwatch_downloads.zip_bytes(result)
            if sum(map(len, result["datasets"].values())) <= portwatch_downloads.XLSX_ROW_LIMIT:
                exports["xlsx"] = portwatch_downloads.xlsx_bytes(result)
            st.session_state["pw_download_result"] = {
                "signature": signature, "value": result, "exports": exports}
            status.update(label="数据已生成并完成记录数校验", state="complete", expanded=False)
        except Exception as exc:
            st.session_state.pop("pw_download_result", None)
            st.error(f"数据下载准备失败：{exc}")
    saved = st.session_state.get("pw_download_result")
    if not saved:
        return
    if saved.get("signature") != signature:
        st.info("下载条件已更改。点击“生成下载数据”以刷新导出。")
        return
    result = saved["value"]
    exports = saved["exports"]
    st.success("已完成来源记录数与分页校验。")
    summary = result["manifest"]["row_counts"]
    st.write(f"港口记录 {summary.get('ports', 0):,} 行；咽喉要道记录 "
             f"{summary.get('chokepoints', 0):,} 行；覆盖状态详见ZIP中的coverage.csv。")
    slug = "latest" if mode == "最新数据" else "all-history" if mode == "全部可用历史" else f"{first}_{last}"
    for kind, rows in result["datasets"].items():
        data = exports[f"csv_{kind}"]
        st.download_button(f"下载{portwatch_downloads.KINDS[kind]} CSV",
            data, file_name=f"portwatch_{kind}_{slug}.csv", mime="text/csv",
            key=f"pw_download_csv_{kind}_{signature[:12]}")
    st.download_button("下载完整 ZIP（CSV、节点目录、覆盖、字典、来源查询）",
        exports["zip"], file_name=f"portwatch_{slug}.zip",
        mime="application/zip", key=f"pw_download_zip_{signature[:12]}")
    records = sum(map(len, result["datasets"].values()))
    if records <= portwatch_downloads.XLSX_ROW_LIMIT:
        st.download_button("下载 Excel 工作簿", exports["xlsx"],
            file_name=f"portwatch_{slug}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"pw_download_xlsx_{signature[:12]}")
    else:
        st.info(f"当前结果超过{portwatch_downloads.XLSX_ROW_LIMIT:,}行，已提供完整CSV与ZIP下载；缩短日期范围即可下载Excel。")
    left, right = st.columns(2)
    with left:
        st.dataframe(result["coverage"], width="stretch", hide_index=True, height=300)
    with right:
        st.dataframe(result["dictionary"], width="stretch", hide_index=True, height=300)


st.set_page_config(page_title="中东能源与战略通道运输监测", page_icon="◉", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  .stApp { background: #f5f7fb; }
  .block-container { padding-top: 4rem; padding-bottom: 2.5rem; max-width: 1680px; }
  [data-testid="stSidebar"] {
      background: #f1f5f9;
      border-right: 1px solid #dbe4ee;
  }
  [data-testid="stSidebar"] * { color: #172b4d; }
  [data-testid="stSidebar"] div[data-baseweb="select"] > div,
  [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] textarea,
  [data-testid="stSidebar"] [data-testid="stDateInput"] button {
      background: #ffffff;
      color: #172b4d;
      border-color: #cbd5e1;
  }
  [data-testid="stSidebar"] input::placeholder,
  [data-testid="stSidebar"] textarea::placeholder {
      color: #64748b;
      opacity: 1;
  }
  [data-testid="stSidebar"] [data-baseweb="select"] span,
  [data-testid="stSidebar"] [data-baseweb="select"] svg {
      color: #172b4d;
      fill: #475569;
  }
  [data-testid="stSidebar"] [data-baseweb="tag"] {
      background: #dbeafe;
      border-color: #bfdbfe;
  }
  [data-testid="stSidebar"] .stCaption,
  [data-testid="stSidebar"] [data-testid="stCaption"] {
      color: #52667d !important;
  }
  [data-testid="stSidebar"] hr { border-color: #dbe4ee; }
  [data-testid="stMetric"] { background: white; border: 1px solid #dfe7ef; border-radius: 14px;
      padding: 13px 16px; box-shadow: 0 3px 12px rgba(25, 49, 74, .05); }
  [data-testid="stMetricLabel"] { color: #557085; }
  [data-testid="stMetricValue"] { color: #102a43; }
  div[data-testid="stTabs"] button { font-weight: 650; }
  div[data-testid="stDataFrame"] { border: 1px solid #dfe7ef; border-radius: 12px; overflow: hidden; }
  .stAlert { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

METRIC_LABELS = {
    "estimated_daily_average": "估算期间日均（公布总量×份额）",
    "actual_output": "来源直报实际产量",
    "sales_volume": "期间销售量（非产量）",
    "actual_output_boe": "来源实绩（油当量；非原油桶）",
    "derived_daily_average": "历史推算日均产量",
    "capacity": "产能",
    "oil_capacity": "原油产能",
    "target_capacity": "目标产能",
    "maximum_sustainable_capacity": "最大可持续产能",
    "historical_capacity": "历史产能",
    "historical_design_capacity": "历史设计产能",
    "historical_peak": "历史峰值",
    "historical_condensate_output": "历史凝析油产量",
    "incremental_capacity": "新增产能",
    "planned_incremental_capacity": "规划新增产能",
    "undisclosed": "未披露",
}

LEVEL_LABELS = CATALOG.ASSET_LEVEL_LABELS
STATUS_LABELS = CATALOG.OPERATING_STATUS_LABELS
OUTPUT_METRIC_TYPES = CATALOG.OUTPUT_METRIC_TYPES
MAP_LAYER_LABELS = map_renderer.MAP_LAYER_LABELS
ASSET_INDEX = {(asset["country"], asset["name"]): asset for asset in ASSETS}


def display_value(asset: dict[str, object]) -> str:
    value = asset.get("value")
    unit = asset.get("unit")
    if value is None:
        return "未披露"
    if unit and str(unit).startswith("千桶/日"):
        try:
            ten_thousand_barrels = float(str(value).replace(",", "")) / 10
            formatted = f"{ten_thousand_barrels:,.2f}".rstrip("0").rstrip(".")
            suffix = str(unit)[len("千桶/日"):]
            return f"{formatted} 万桶/日{suffix}"
        except ValueError:
            pass
    return f"{value} {unit}" if unit else str(value)


def extra_measurements(asset: dict) -> str:
    return "；".join(
        f"{CATALOG.COMMODITY_LABELS[m['commodity']]} {m['value']} {m['unit']}"
        f"（{METRIC_LABELS[m['metric_type']]}，{m['data_date']}）"
        for m in asset.get("additional_measurements", [])) or "未披露"


def display_date(asset: dict[str, object]) -> str:
    return str(asset.get("data_date") or "未提供")


def daily_output_value(asset: dict[str, object]) -> str:
    if asset.get("value") is None or asset.get("metric_type") not in OUTPUT_METRIC_TYPES:
        return "未披露"
    return display_value(asset)


def other_daily_metric(asset: dict[str, object]) -> str:
    if asset.get("value") is None or asset.get("metric_type") in OUTPUT_METRIC_TYPES:
        return "—"
    metric_label = METRIC_LABELS[str(asset["metric_type"])]
    return f"{metric_label}：{display_value(asset)}"


def hierarchy_chain(asset: dict[str, object]) -> list[dict[str, object]]:
    """返回当前资产到最高已登记上级的链条；防止异常循环。"""

    chain = [asset]
    seen = {(asset["country"], asset["name"])}
    current = asset
    while current.get("parent_asset"):
        parent_key = (current["country"], current["parent_asset"])
        if parent_key in seen:
            break
        parent = ASSET_INDEX.get(parent_key)
        if parent is None:
            break
        chain.append(parent)
        seen.add(parent_key)
        current = parent
    return chain


def hierarchy_path(asset: dict[str, object]) -> str:
    chain = list(reversed(hierarchy_chain(asset)))
    return " → ".join(
        f'{node["asset_level_label"]}：{node["name"]}' for node in chain
    )


def _hierarchy_panel(asset: dict[str, object]) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    cards: list[str] = []
    for node in hierarchy_chain(asset):
        output = daily_output_value(node)
        metric_type = str(node["metric_type"])
        output_detail = (
            f'{METRIC_LABELS[metric_type]} · {display_date(node)}'
            if output != "未披露"
            else "本层级实际／历史日均未披露"
        )
        other = other_daily_metric(node)
        other_html = (
            f'<div class="other-metric">{esc(other)} · {esc(display_date(node))}</div>'
            if other != "—"
            else ""
        )
        cards.append(
            '<div class="level-metric">'
            f'<div class="level-head"><span>{esc(node["asset_level_label"])}</span>'
            f'<b>{esc(node["name"])}</b></div>'
            f'<div class="output-line"><span>日产量</span><strong>{esc(output)}</strong></div>'
            f'<div class="metric-detail">{esc(output_detail)}</div>'
            f'{other_html}'
            '</div>'
        )
    return "".join(cards)


def _popup(asset: dict[str, object]) -> str:
    """生成分层中文信息卡；逐层列示当前资产及其上级的日产量。"""

    def esc(value: object) -> str:
        return html.escape(str(value))

    source_url = esc(asset["source_url"])
    status_source_url = esc(asset["operating_status_evidence_url"])
    coordinate_source_url = asset.get("coordinate_source_url")
    coordinate_source_html = (
        f'<a class="source" href="{esc(coordinate_source_url)}" target="_blank" rel="noopener">'
        f'坐标来源：{esc(asset["coordinate_source"])}</a>'
        if coordinate_source_url
        else f'<div class="basis">坐标来源：{esc(asset["coordinate_source"])}</div>'
    )
    parent = asset.get("parent_asset") or "无已登记上级"
    constituents = "、".join(asset.get("constituent_assets") or []) or "—"
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{esc(asset["name"])}（{esc(asset["name_cn"])}）</div>'
        f'<div class="country">{esc(asset["country"])} · {esc(asset["asset_type"])}</div>'
        '<div class="row"><span>资产层级</span>'
        f'<strong>{esc(asset["asset_level_label"])}</strong></div>'
        '<div class="row"><span>地图角色</span>'
        f'<strong>{esc(asset["map_role_label"])}</strong></div>'
        '<div class="row"><span>上级资产</span>'
        f'<strong>{esc(parent)}</strong></div>'
        '<div class="row"><span>组成资产</span>'
        f'<strong>{esc(constituents)}</strong></div>'
        '<div class="row"><span>汇总规则</span>'
        f'<strong>{esc(asset["rollup_policy"])}</strong></div>'
        '<div class="row"><span>统计范围</span>'
        f'<strong>{esc(asset["aggregation_scope"])}</strong></div>'
        '<div class="row"><span>商品</span>'
        f'<strong>{esc(asset["commodity_label"])}</strong></div>'
        '<div class="row"><span>生产状态</span>'
        f'<strong>{esc(asset["operating_status_label"])}</strong></div>'
        '<div class="row"><span>状态截至</span>'
        f'<strong>{esc(asset["operating_status_as_of"])}</strong></div>'
        '<div class="row"><span>状态置信度</span>'
        f'<strong>{esc(asset["operating_status_confidence"])}</strong></div>'
        f'<div class="hierarchy-title">分层日产量（当前资产 → 上级）</div>'
        f'{_hierarchy_panel(asset)}'
        '<div class="row"><span>坐标精度</span>'
        f'<strong>{esc(asset["map_coordinate_precision"])}</strong></div>'
        '<div class="row"><span>定位属性</span>'
        f'<strong>{"区域/设施代理点" if asset.get("map_is_proxy") else "资产点位"}</strong></div>'
        f'{coordinate_source_html}'
        f'<div class="status">原始状态说明：{esc(asset["status"])}</div>'
        f'<div class="basis">状态依据：{esc(asset["operating_status_basis"])}</div>'
        f'<div class="basis">权益口径：{esc(asset["ownership_basis"])}</div>'
        f'<div class="basis">其他商品指标：{esc(extra_measurements(asset))}</div>'
        f'<div class="basis">数据时效：{esc(asset["freshness_note"])}</div>'
        f'<div class="basis">数值复核：{esc(asset["numeric_audit"])}</div>'
        f'<div class="basis">说明：{esc(asset["note"] or "公开命名资产；本层级数值未公开。")}</div>'
        f'<a class="source" href="{status_source_url}" target="_blank" rel="noopener">生产状态证据</a>'
        f'<a class="source" href="{source_url}" target="_blank" rel="noopener">目录来源：{esc(asset["source"])}</a>'
        '</div>'
    )


def _port_popup(port: dict, day: str) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    def amount(key: str, divisor: float = 1, decimals: int = 1) -> str:
        value = port.get(key)
        if value is None:
            return "—"
        if divisor != 1 and 0 < abs(value / divisor) < 0.05:
            return "<0.1"
        return f"{value / divisor:,.{decimals}f}"

    if port.get("activity_source") == "无独立PortWatch统计":
        date_label = "无独立统计"
    elif port.get("has_data"):
        date_label = f"观测日 UTC：{day}"
    else:
        date_label = "该日无源记录"

    window = port.get("window_days", 7)
    activity = port.get("activity_index")
    activity_text = f"{activity:,.0f}" if activity is not None else "—"
    balance = port.get("trade_balance_index")
    if balance is None:
        balance_text = "—"
    elif balance > 5:
        balance_text = f"{balance:+.1f} · 出口偏向"
    elif balance < -5:
        balance_text = f"{balance:+.1f} · 进口偏向"
    else:
        balance_text = f"{balance:+.1f} · 大致平衡"
    ship_labels = {
        "container": "集装箱船", "dry_bulk": "干散货船",
        "general_cargo": "普通货船", "roro": "滚装船", "tanker": "油轮/液货船",
    }
    ship_colors = {
        "container": "#2563eb", "dry_bulk": "#b45309", "general_cargo": "#64748b",
        "roro": "#7c3aed", "tanker": "#0f766e",
    }
    structure = []
    for kind, label in ship_labels.items():
        share = port.get(f"share_{kind}")
        calls = port.get(f"window_calls_{kind}")
        width = max(0, min(100, share or 0))
        share_text = f"{share:.1f}%" if share is not None else "—"
        calls_text = f"{calls:,.0f}" if calls is not None else "—"
        structure.append(
            '<div class="mix-row">'
            f'<span>{label}</span><div class="mix-track"><i style="width:{width:.1f}%;background:{ship_colors[kind]}"></i></div>'
            f'<b>{share_text} · {calls_text}艘次</b></div>'
        )
    risk_block = (
        '<div class="row"><span>风险运力（出港网络）</span>'
        f'<strong>{amount("risk_capacity", 10000)} 万吨/日</strong></div>'
        if port.get("risk_capacity") is not None else ""
    )
    return (
        '<div class="popup-card">'
        f'<div class="field-name">⚓ {esc(port["name"])}</div>'
        f'<div class="country">{esc(port["country"])} · {esc(port["region"])} · {esc(date_label)}</div>'
        '<div class="row"><span>当日有效进港</span>'
        f'<strong>{amount("portcalls", decimals=0)} 艘次</strong></div>'
        '<div class="row"><span>当日估算装卸</span>'
        f'<strong>{amount("handled", 10000)} 万吨</strong></div>'
        f'<div class="hierarchy-title">过去 {window} 天港口指标</div>'
        '<div class="row"><span>港口活动指数</span>'
        f'<strong>{activity_text}（前一窗口=100）</strong></div>'
        '<div class="row"><span>活跃天数率</span>'
        f'<strong>{amount("active_day_rate")}%</strong></div>'
        '<div class="row"><span>日均进港 / 日均装卸</span>'
        f'<strong>{amount("avg_calls")} 艘次 · {amount("avg_handled", 10000)} 万吨</strong></div>'
        '<div class="row"><span>单船平均货量</span>'
        f'<strong>{amount("average_cargo_per_call", 10000, 2)} 万吨/艘次</strong></div>'
        '<div class="row"><span>进出口平衡指数</span>'
        f'<strong>{balance_text}</strong></div>'
        f'{risk_block}'
        '<div class="hierarchy-title">船型结构</div>'
        f'{"".join(structure)}'
        '<div class="basis">活动指数比较相邻等长窗口；100表示持平。平衡指数范围−100至+100，'
        '负值偏进口、正值偏出口。风险运力来自2019—2024港口航线网络，是历史冲击暴露估算。'
        '“—”表示窗口不完整、基期为0或源数据不足，不按零处理。</div>'
        f'<div class="basis">统计覆盖：{esc(port.get("coverage_note", ""))}</div>'
        f'<a class="source" href="{esc(port.get("source_url", PORTWATCH.SOURCE))}" target="_blank" rel="noopener">港口目录/统计来源</a>'
        '</div>'
    )


def _chokepoint_popup(point: dict, day: str) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    def value(key: str, divisor: float = 1, decimals: int = 0) -> str:
        raw = point.get(key)
        return "—" if raw is None else f"{raw / divisor:,.{decimals}f}"

    categories = (
        ("container", "集装箱船"), ("dry_bulk", "干散货船"),
        ("general_cargo", "普通货船"), ("roro", "滚装船"), ("tanker", "油轮/液货船"),
    )
    rows = "".join(
        '<div class="row"><span>' + label + '</span>'
        f'<strong>{value(f"n_{kind}")} 艘 · {value(f"capacity_{kind}", 10000, 1)} 万吨</strong></div>'
        for kind, label in categories
    )
    return (
        '<div class="popup-card">'
        f'<div class="field-name">◆ {esc(point.get("name_cn", point["portname"]))}</div>'
        f'<div class="country">{esc(point.get("fullname") or point["portname"])} · {esc(day)} UTC</div>'
        '<div class="row"><span>当日通过船舶</span>'
        f'<strong>{value("n_total")} 艘</strong></div>'
        '<div class="row"><span>估算承载货量</span>'
        f'<strong>{value("capacity", 10000, 1)} 万吨</strong></div>'
        '<div class="hierarchy-title">船型分解 · 艘数 / 估算货量</div>'
        f'{rows}'
        '<div class="basis">PortWatch按船舶穿越咽喉点边界计数；跨越多日的同一次通行只计一次，'
        '48小时内同船再次出现不重复计数。货量由AIS、吃水与载重能力估算。</div>'
        f'<a class="source" href="{esc(PORTWATCH.SOURCE)}" target="_blank" rel="noopener">IMF PortWatch 数据与方法</a>'
        '</div>'
    )


def _vessel_popup(vessel: dict[str, object]) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    def shown(key: str, suffix: str = "") -> str:
        value = vessel.get(key)
        return "—" if value in (None, "") else f"{esc(value)}{suffix}"

    name = vessel.get("name") or f'MMSI {vessel["mmsi"]}'
    age = vessel.get("age_minutes")
    age_text = "—" if age is None else f"{float(age):.1f} 分钟"
    speed = vessel.get("sog")
    speed_text = "—" if speed is None else f"{float(speed):.1f} 节"
    course = vessel.get("course")
    course_text = "—" if course is None else f"{float(course):.1f}°"
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{esc(name)}</div>'
        f'<div class="country">船舶 · {esc(vessel.get("region") or "监测水域")}</div>'
        '<div class="row"><span>船型</span>'
        f'<strong>{shown("category_label")}</strong></div>'
        '<div class="row"><span>MMSI / IMO</span>'
        f'<strong>{shown("mmsi")} / {shown("imo")}</strong></div>'
        '<div class="row"><span>航速 / 航向</span>'
        f'<strong>{speed_text} / {course_text}</strong></div>'
        '<div class="row"><span>航行状态</span>'
        f'<strong>{shown("navigation_status")}</strong></div>'
        '<div class="row"><span>呼号 / 目的地</span>'
        f'<strong>{shown("call_sign")} / {shown("destination")}</strong></div>'
        '<div class="row"><span>AIS报告时间 UTC</span>'
        f'<strong>{shown("received_at")}</strong></div>'
        '<div class="row"><span>数据年龄</span>'
        f'<strong>{age_text}</strong></div>'
        '<div class="row"><span>数据源</span>'
        f'<strong>{shown("data_source")}</strong></div>'
        '<div class="basis">AIS船型为船载设备广播的基础分类；货船不能据此可靠细分为集装箱船或散货船。'
        '点位可能因岸基/卫星覆盖、设备关闭、延迟或错误广播而缺失。</div>'
        f'<a class="source" href="{esc(vessel.get("source_url") or AIS.SOURCE)}" target="_blank" rel="noopener">'
        f'{esc(vessel.get("source_attribution") or vessel.get("data_source") or "AIS数据来源")}</a>'
        '</div>'
    )



country_options = sorted({str(asset["country"]) for asset in ASSETS})
level_options = list(LEVEL_LABELS)
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})
status_options = list(STATUS_LABELS)
ais_api_key = _ais_api_key()
ais_collector_instance: AIS.AISCollector | None = None

with st.sidebar:
    st.session_state.pop("monitor_regions", None)
    st.markdown("### 中东能源与战略通道运输监测")
    print_mode = st.toggle(
        "打印模式", value=False, key="print_mode",
        help="开启后读取港口和咽喉点最近90天数据并生成全项目报告。可下载独立HTML报告，再打印或保存为PDF。")
    map_layers_selection = _multiselect_with_all(
        "地图内容", list(MAP_LAYER_LABELS), key="map_layers",
        default_all=False, default=["ports"],
        format_func=lambda value: MAP_LAYER_LABELS[value],
        placeholder="全选或选择图层",
        help="“全选”显示所有图层；清空选择时地图不显示任何图层。")
    selected_map_layers = _selected_values(map_layers_selection, list(MAP_LAYER_LABELS))

    try:
        available_ports = PORTWATCH.port_catalog()
        port_catalog_error = None
    except Exception as exc:
        available_ports = []
        port_catalog_error = str(exc)
    try:
        available_chokepoints = PORTWATCH.chokepoint_catalog()
        chokepoint_catalog_error = None
    except Exception as exc:
        available_chokepoints = []
        chokepoint_catalog_error = str(exc)

    with st.expander("港口筛选", expanded=False):
        port_country_options = sorted(
            {port["country"] for port in available_ports},
            key=port_inventory.country_label)
        port_countries_selection = _multiselect_with_all(
            "国家", port_country_options, key="port_countries",
            format_func=port_inventory.country_label,
            placeholder="全选或选择国家",
            help="“全选”表示所有国家；清空选择时不显示港口。")
        selected_port_countries = _selected_values(
            port_countries_selection, port_country_options)
        country_port_catalog = [
            port for port in available_ports if port["country"] in selected_port_countries
        ]
        port_labels = {
            port["portid"]:
                port_inventory.port_label(port)
            for port in country_port_catalog
        }
        port_id_options = [
            port["portid"] for port in sorted(
                country_port_catalog,
                key=lambda port: (port_inventory.country_label(port["country"]),
                                  port_inventory.port_label(port)))
        ]
        port_ids_selection = _multiselect_with_all(
            "港口", port_id_options, key="port_ids",
            format_func=lambda port_id: port_labels.get(port_id, port_id),
            placeholder="全选或选择港口",
            disabled=not bool(selected_port_countries),
            help="“全选”表示所选国家中的所有港口；清空选择时不显示港口。")
        selected_port_ids = _selected_values(port_ids_selection, port_id_options)
        show_only_ports_with_data = st.checkbox(
            "仅在地图上显示有最新数据的港口", value=False,
            key="ports_latest_data_only",
            help="只显示在 PortWatch 最新观测日有日度记录的港口；不影响港口列表和统计。")
        if port_catalog_error:
            st.warning(f"港口目录暂时不可用：{port_catalog_error}")
        try:
            newest_day = PORTWATCH.latest_date()
            selected_day = newest_day
        except Exception as exc:
            newest_day = selected_day = None
            st.warning(f"PortWatch 暂时不可用：{exc}")
        rolling_days = 7

    with st.expander("咽喉点筛选", expanded=False):
        if chokepoint_catalog_error:
            st.warning(f"咽喉点目录暂时不可用：{chokepoint_catalog_error}")
        chokepoint_id_options = [str(point["portid"]) for point in available_chokepoints]
        chokepoint_labels = {
            str(point["portid"]): point.get("name_cn", point.get("portname", str(point["portid"])))
            for point in available_chokepoints
        }
        chokepoints_selection = _multiselect_with_all(
            "咽喉点", chokepoint_id_options, key="chokepoint_ids",
            format_func=lambda point_id: chokepoint_labels.get(point_id, point_id),
            placeholder="全选或选择咽喉点",
            help="此筛选独立于港口国家与港口筛选；清空选择时不显示咽喉点。")
        selected_chokepoint_ids = _selected_values(
            chokepoints_selection, chokepoint_id_options)
        try:
            newest_chokepoint_day = PORTWATCH.latest_chokepoint_date()
        except Exception as exc:
            newest_chokepoint_day = None
            st.warning(f"咽喉点数据暂时不可用：{exc}")

    st.button("刷新 PortWatch 数据", type="primary", width="stretch",
              on_click=_refresh_portwatch_data)

    with st.expander("船舶", expanded=True):
        ais_enabled = st.toggle(
            "显示 AIS 实时船位", value=True, key="ais_enabled",
            help="开启后读取 Open Waters 当前船位快照，并合并已配置的 AISStream 数据；地图还需在“地图内容”中选中“船舶”图层。")
        ais_categories_selection = _multiselect_with_all(
            "船型", list(AIS.VESSEL_TYPE_LABELS), key="ais_categories",
            format_func=lambda key: AIS.VESSEL_TYPE_LABELS[key],
            placeholder="全选或选择船型")
        selected_ais_categories = set(_selected_values(
            ais_categories_selection, list(AIS.VESSEL_TYPE_LABELS)))
        ais_search = st.text_input(
            "搜索船名、MMSI或IMO", placeholder="例如 EVER GIVEN / 636…",
            key="ais_search").strip().lower()
        ais_moving_only = st.toggle("仅航行中（≥0.5节）", value=False,
                                    key="ais_moving_only")
        ais_max_age = st.select_slider(
            "最大数据年龄", options=[10, 30, 60, 120], value=30,
            format_func=lambda value: f"{value}分钟", key="ais_max_age")
        open_state = {"vessels": [], "error": None}
        stream_status = "未配置（可选）"
        vessel_status_panel = st.empty()
        st.button("刷新船舶数据", type="primary", width="stretch",
                  disabled=not ais_enabled, on_click=_refresh_vessel_data)

    with st.expander("油气", expanded=False):
        asset_view = st.radio(
            "资产视图", ["战略生产节点", "完整资产目录"],
            horizontal=True, key="asset_view")
        st.caption("战略视图按油田群／区块优先，避免组成资产与上级重复展示。")
        asset_search = st.text_input("搜索资产", placeholder="输入中英文名称",
                                     key="asset_search").strip().lower()
        selected_countries = _selected_values(
            _multiselect_with_all("国家", country_options, key="asset_countries",
                                  format_func=port_inventory.country_label,
                                  placeholder="全选或选择国家"),
            country_options)
        selected_levels = _selected_values(
            _multiselect_with_all("资产层级", level_options, key="asset_levels",
                                  format_func=lambda key: LEVEL_LABELS[key],
                                  placeholder="全选或选择层级"),
            level_options)
        selected_statuses = _selected_values(
            _multiselect_with_all("生产状态", status_options, key="asset_statuses",
                                  format_func=lambda key: STATUS_LABELS[key],
                                  placeholder="全选或选择状态"),
            status_options)
        values_only = st.toggle("只看有公开数值", value=False, key="values_only")
        output_only = st.toggle("只看有日产量", value=False, key="output_only")
        st.markdown("**高级筛选**")
        selected_types = _selected_values(
            _multiselect_with_all("资产类型", type_options, key="asset_types",
                                  placeholder="全选或选择资产类型"),
            type_options)
        selected_metrics = _selected_values(
            _multiselect_with_all("指标口径", metric_options, key="asset_metrics",
                                  format_func=lambda key: METRIC_LABELS[key],
                                  placeholder="全选或选择口径"),
            metric_options)

    st.caption("港口和咽喉点在独立筛选区选择；多选器中的“全选”与单项互斥，清空选择表示无匹配结果。")



tab_map, tab_ports, tab_vessels, tab_assets, tab_download, tab_method = st.tabs(
    ["地图", "港口", "船舶", "油气", "数据下载", "数据与方法"],
    key="main_tabs", on_change="rerun")
selected_chokepoint_day = newest_chokepoint_day

need_port_data = ((tab_map.open and "ports" in selected_map_layers)
                  or tab_ports.open)
need_chokepoint_data = tab_map.open and "chokepoints" in selected_map_layers
need_ais_data = ais_enabled and (
    (tab_map.open and "vessels" in selected_map_layers) or tab_vessels.open or print_mode)
if need_ais_data:
    if ais_api_key:
        ais_collector_instance = _ais_collector(ais_api_key, AIS.MODULE_VERSION)
        ais_state = ais_collector_instance.status()
        stream_status = ais_state["status"]
        if ais_state.get("last_error"):
            with vessel_status_panel:
                st.caption(f'最近 AISStream 错误：{ais_state["last_error"]}')
    open_state = _openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
    stream_rows = (
        ais_collector_instance.snapshot(max_age_minutes=ais_max_age)
        if ais_collector_instance is not None else []
    )
    merged_count = len(AIS.merge_vessel_snapshots(
        stream_rows, open_state.get("vessels", [])))
    with vessel_status_panel:
        st.caption(
            f'数据状态：合并后 {merged_count:,} 艘'
            f'（公开快照 {len(open_state["vessels"]):,}）· '
            f'AISStream {stream_status}')
        if open_state.get("error"):
            st.caption(f'Open Waters 错误：{open_state["error"]}')
elif ais_enabled:
    with vessel_status_panel:
        st.caption("船位在地图显示船舶图层、打开船舶页或进入打印模式时读取。")

ports: list[dict] = []
port_error = port_catalog_error
port_risk_error = None
if need_port_data and selected_day is not None and not port_error:
    try:
        catalog = [
            port for port in available_ports
            if port["country"] in selected_port_countries
            and port["portid"] in selected_port_ids
        ]
        ids = tuple(p["portid"] for p in catalog)
        statistical_ids = tuple(sorted(
            str(port["portid"]) for port in available_ports
            if PORTWATCH.has_independent_statistics(port)))
        if ids:
            activity_all = (PORTWATCH.daily_activity(selected_day, statistical_ids)
                            if statistical_ids else {})
            rolling_all = (PORTWATCH.rolling_activity(selected_day, statistical_ids, rolling_days)
                           if statistical_ids else {})
            # The historical route-risk model is slower and is only used in
            # the detailed port table; do not block the default map on it.
            risk_all = {}
            if tab_ports.open and statistical_ids:
                try:
                    risk_all = PORTWATCH.port_risk_capacity(statistical_ids)
                except Exception as exc:
                    port_risk_error = str(exc)
            activity = {port_id: activity_all[port_id] for port_id in ids
                        if port_id in activity_all}
            rolling = {port_id: rolling_all[port_id] for port_id in ids
                       if port_id in rolling_all}
            risk_capacity = {port_id: risk_all.get(port_id) for port_id in ids} if tab_ports.open else None
            ports = PORTWATCH.decorate(catalog, activity, rolling, risk_capacity)
    except Exception as exc:
        port_error = str(exc)

chokepoints: list[dict] = []
chokepoint_error = chokepoint_catalog_error
if need_chokepoint_data and selected_chokepoint_day is not None and not chokepoint_error:
    try:
        chosen_chokepoint_ids = set(selected_chokepoint_ids)
        chokepoint_catalog = [
            point for point in available_chokepoints
            if str(point["portid"]) in chosen_chokepoint_ids
        ]
        chokepoint_ids = tuple(str(point["portid"]) for point in available_chokepoints)
        if chokepoint_ids:
            chokepoint_values_all = PORTWATCH.chokepoint_activity(selected_chokepoint_day, chokepoint_ids)
            chokepoints = PORTWATCH.decorate_chokepoints(
                chokepoint_catalog, chokepoint_values_all)
    except Exception as exc:
        chokepoint_error = str(exc)


def current_ais_positions() -> list[dict]:
    """Merge the direct AISStream feed and the public Open Waters snapshot."""

    if not ais_enabled:
        return []
    stream_rows = []
    if ais_collector_instance is not None:
        stream_rows = ais_collector_instance.snapshot(max_age_minutes=ais_max_age)
    return AIS.merge_vessel_snapshots(stream_rows, open_state.get("vessels", []))


live_positions = current_ais_positions() if need_ais_data else []
archive_error = None
if open_state.get("vessels"):
    try:
        # AISStream positions are archived by its collector; only persist the
        # polled public snapshot here to avoid rewriting the same feed twice.
        _archive_public_snapshot(open_state["vessels"])
    except Exception as exc:
        archive_error = f"船位归档失败：{exc}"
def current_vessels() -> list[dict]:
    """Return one consistent, filtered snapshot; missing AIS is unavailable, not zero."""

    if not selected_ais_categories:
        return []
    return AIS.filter_vessels(
        live_positions,
        regions=set(PORTWATCH.REGIONS),
        categories=selected_ais_categories,
        moving_only=ais_moving_only,
        query=ais_search,
    )


def current_ais_status() -> dict:
    """Return the collector status with one stable shape when it is optional."""

    if ais_collector_instance is not None:
        return ais_collector_instance.status()
    return {
        "status": "未配置（可选）", "last_error": None,
        "last_message_at": None, "last_position_message_at": None,
        "raw_event_count": 0, "rejected_event_count": 0,
        "message_count": 0, "position_message_count": 0,
        "static_message_count": 0, "tracked_vessels": 0,
        "compression_enabled": None,
    }

filtered_all = [
    asset for asset in ASSETS
    if asset["country"] in selected_countries
    and asset["asset_level"] in selected_levels
    and asset["asset_type"] in selected_types
    and asset["operating_status"] in selected_statuses
    and asset["metric_type"] in selected_metrics
    and (not values_only or asset["value"] is not None)
    and (not output_only or asset["is_daily_output"])
    and (not asset_search or asset_search in str(asset["name"]).lower()
         or asset_search in str(asset["name_cn"]).lower()
         or any(asset_search in alias.lower() for alias in asset["aliases"]))
]
filtered = [
    asset for asset in filtered_all
    if asset_view == "完整资产目录" or asset["strategic_default"] or bool(asset_search)
]
visible_map_layers = set(selected_map_layers)
map_asset_candidates = filtered if "assets" in visible_map_layers else []
map_assets = [asset for asset in map_asset_candidates if asset["map_drawable"]]
unlocated_map_assets = [asset for asset in map_asset_candidates if not asset["map_drawable"]]
map_ports = ports if "ports" in visible_map_layers else []
if show_only_ports_with_data:
    map_ports = [port for port in map_ports if port.get("has_data")]
map_chokepoints = (
    chokepoints
    if "chokepoints" in visible_map_layers
    else []
)

port_rows = []
for port in ports:
    def ten_thousand(key: str):
        value = port.get(key)
        return None if value is None else round(value / 10000, 6)

    notes = [port.get("coverage_note", "")]
    if not port.get("has_data"):
        notes.append("所选日缺少源记录")
    if port.get("observed_days") != rolling_days:
        notes.append("当前窗口不完整")
    if port.get("previous_observed_days") != rolling_days:
        notes.append("比较窗口不完整")
    if port.get("activity_index") is None:
        notes.append("活动指数不可算（基期为0或数据不完整）")
    if port.get("portcalls") == 0 and (port.get("active_days") or 0) > 0:
        notes.append("当日为0但窗口内有进港")
    port_rows.append({
        "水域": port["region"], "国家": port["country"], "港口": port["name"],
        "PortWatch ID": port["portid"], "日期 UTC": selected_day.isoformat(),
        "当日有效进港 艘次": port.get("portcalls"),
        "港口活动指数": (round(port["activity_index"], 1)
                         if port.get("activity_index") is not None else None),
        f"{rolling_days}天活跃天数率 %": (
            round(port["active_day_rate"], 1)
            if port.get("active_day_rate") is not None else None),
        f"{rolling_days}天日均进港 艘次": (
            round(port["avg_calls"], 3) if port.get("avg_calls") is not None else None),
        f"{rolling_days}天日均装卸 万吨": ten_thousand("avg_handled"),
        "单船平均货量 万吨/艘次": ten_thousand("average_cargo_per_call"),
        "进出口平衡指数": (round(port["trade_balance_index"], 1)
                          if port.get("trade_balance_index") is not None else None),
        "风险运力 万吨/日": ten_thousand("risk_capacity"),
        "集装箱船占比 %": (round(port["share_container"], 1)
                          if port.get("share_container") is not None else None),
        "干散货船占比 %": (round(port["share_dry_bulk"], 1)
                          if port.get("share_dry_bulk") is not None else None),
        "普通货船占比 %": (round(port["share_general_cargo"], 1)
                          if port.get("share_general_cargo") is not None else None),
        "滚装船占比 %": (round(port["share_roro"], 1)
                        if port.get("share_roro") is not None else None),
        "油轮/液货船占比 %": (round(port["share_tanker"], 1)
                            if port.get("share_tanker") is not None else None),
        f"{rolling_days}天有效日期": port.get("observed_days"),
        "数据提示": "；".join(notes),
        "纬度": port["lat"], "经度": port["lon"], "来源": port.get("source_url", PORTWATCH.SOURCE),
        "统计覆盖": port.get("activity_source"), "NGA WPI编号": str(port.get("wpi_ids", [])),
    })

asset_rows = [
    {
        "国家": asset["country"], "资产层级": asset["asset_level_label"],
        "地图角色": asset["map_role_label"],
        "层级路径": hierarchy_path(asset), "上级资产": asset["parent_asset"] or "—",
        "组成资产": "、".join(asset["constituent_assets"]) or "—",
        "汇总规则": asset["rollup_policy"],
        "英文名称": asset["name"], "中文名称": asset["name_cn"],
        "别名": "、".join(asset["aliases"]), "数据时效提示": asset["freshness_note"],
        "数值复核": asset["numeric_audit"], "数据复核日": asset["data_audit_date"],
        "其他商品指标": extra_measurements(asset),
        "资产类型": asset["asset_type"], "商品": asset["commodity_label"],
        "生产状态": asset["operating_status_label"], "状态截至": asset["operating_status_as_of"],
        "本层级日产量": daily_output_value(asset), "其他日量指标": other_daily_metric(asset),
        "指标口径": METRIC_LABELS[asset["metric_type"]], "数据日期": display_date(asset),
        "统计范围": asset["aggregation_scope"], "状态置信度": asset["operating_status_confidence"],
        "状态依据": asset["operating_status_basis"], "状态证据链接": asset["operating_status_evidence_url"],
        "地图坐标精度": asset["map_coordinate_precision"],
        "定位属性": "区域/设施代理点" if asset.get("map_is_proxy") else "资产点位",
        "坐标来源": asset["coordinate_source"],
        "坐标来源链接": asset["coordinate_source_url"],
        "默认战略节点": "是" if asset["strategic_default"] else "否",
        "来源": asset["source"],
        "来源链接": asset["source_url"], "说明": asset["note"],
    }
    for asset in filtered
]


def vessel_rows(vessels: list[dict]) -> list[dict]:
    return [{
        "水域": vessel.get("region"),
        "船名": vessel.get("name") or "—",
        "船型": vessel.get("category_label"),
        "MMSI": vessel.get("mmsi"),
        "IMO": vessel.get("imo"),
        "航行状态": vessel.get("navigation_status"),
        "航速 节": (round(vessel["sog"], 1) if vessel.get("sog") is not None else None),
        "航向 °": (round(vessel["course"], 1)
                   if vessel.get("course") is not None else None),
        "目的地": vessel.get("destination"),
        "吃水 米": vessel.get("draught"),
        "AIS报告时间 UTC": vessel.get("received_at"),
        "采集器接收时间 UTC": vessel.get("provider_received_at"),
        "数据年龄 分钟": (round(vessel["age_minutes"], 1)
                         if vessel.get("age_minutes") is not None else None),
        "来源署名": vessel.get("source_attribution"),
        "纬度": vessel.get("lat"), "经度": vessel.get("lon"),
        "数据源": vessel.get("data_source"),
        "来源": vessel.get("source_url") or AIS.SOURCE,
    } for vessel in vessels]


def render_map_panel() -> None:
    all_positions = live_positions
    filtered_vessels = current_vessels()
    map_vessels = (
        filtered_vessels
        if "vessels" in visible_map_layers
        else []
    )
    stream_state = current_ais_status()
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    if chokepoint_error:
        st.error(f"咽喉点数据加载失败：{chokepoint_error}")
    if archive_error:
        st.warning(archive_error)
    if not ais_enabled:
        st.info("船舶图层已关闭。")
    elif "vessels" in visible_map_layers:
        if stream_state.get("last_error") and not all_positions:
            st.warning(f'AISStream 暂无可用船位，后台将自动重连：{stream_state["last_error"]}')
        if stream_state.get("archive_error"):
            st.warning(f'AISStream 船位归档失败：{stream_state["archive_error"]}')
        if open_state.get("error"):
            st.warning(f'Open Waters 免费数据暂不可用：{open_state["error"]}')
        if not all_positions and not open_state.get("error"):
            if stream_state.get("status") == "订阅已确认" and stream_state.get("raw_event_count", 0) == 0:
                st.warning(
                    "AISStream 已确认订阅但未送达事件；Open Waters 当前快照也没有船位。"
                    "这不代表监测水域内没有船舶。"
                )
            else:
                st.info("两处数据源尚未返回当前可用船位；不能据此判断水域内没有船舶。")
    if unlocated_map_assets:
        st.info(
            f"当前筛选有 {len(unlocated_map_assets)} 项仅列目录：既无可核验独立坐标，也无可用的"
            "上级资产代表点，因此不以猜测位置绘图。可在‘油气’表查看坐标证据。"
        )
    st.iframe(
        map_renderer.build_map_html(
            map_assets, map_ports, map_chokepoints, map_vessels,
            selected_day.isoformat() if selected_day else "无数据",
            selected_chokepoint_day.isoformat() if selected_chokepoint_day else "无数据",
            focus_assets=bool(asset_search), ais_configured=bool(ais_enabled),
            visible_layers=visible_map_layers,
            asset_popup=_popup, port_popup=_port_popup,
            chokepoint_popup=_chokepoint_popup, vessel_popup=_vessel_popup),
        height=735,
    )


def render_ais_panel() -> None:
    st.subheader("船舶")
    if not ais_enabled:
        st.info("船舶位置已关闭，可在左侧‘船舶’中启用。")
        return
    all_positions = live_positions
    vessels = current_vessels()
    rows = vessel_rows(vessels)
    state = current_ais_status()
    has_position_data = bool(all_positions)
    if archive_error:
        st.warning(archive_error)
    vessel_metric = len(vessels) if has_position_data else "—"
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("筛选后船舶", vessel_metric)
    v2.metric("航行中", sum(bool(v.get("moving")) for v in vessels) if has_position_data else "—")
    v3.metric("油轮/液货船", sum(v.get("category") == "tanker" for v in vessels)
              if has_position_data else "—")
    v4.metric("货船", sum(v.get("category") == "cargo" for v in vessels)
              if has_position_data else "—")
    v5.metric("船型待识别", sum(v.get("category") == "unknown" for v in vessels)
              if has_position_data else "—")
    if open_state.get("truncated"):
        st.warning("Open Waters 返回结果达到该区域查询上限，较早船位可能未包含。")
    if open_state.get("error"):
        st.warning(f'Open Waters 快照错误：{open_state["error"]}')
    if state.get("compression_enabled") is False:
        st.warning("AISStream 未确认 WebSocket 压缩协商；未压缩连接可能受带宽限制。")
    if state.get("last_error"):
        st.warning(f'最近连接错误：{state["last_error"]}；采集器会自动指数退避重连。')
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True, height=570,
                     column_config={"来源": st.column_config.LinkColumn("来源")})
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
        st.download_button(
            "下载当前船位快照 CSV",
            buffer.getvalue().encode("utf-8-sig"),
            file_name="ais_vessel_snapshot.csv",
            mime="text/csv", type="primary")
    elif not all_positions:
        if (state.get("status") == "订阅已确认"
                and state.get("raw_event_count", 0) == 0
                and not open_state.get("error")):
            st.warning(
                "AISStream 已确认订阅但尚未送达事件，Open Waters 当前快照也没有返回船位。"
                "当前船位不可用，不能据此判断监测水域内没有船舶。"
            )
        elif open_state.get("error"):
            st.warning("免费公共快照暂时不可用；可稍后刷新。没有报文不等于水域内没有船舶。")
        else:
            st.info("正在等待监测水域内的新 AIS 报文；当前船位尚不可用。")
    elif has_position_data:
        st.info("当前船型、水域、搜索和数据年龄筛选没有匹配船舶。")
    elif state.get("position_message_count", 0) == 0:
        st.info("已收到AIS事件，但尚未收到可绘制的位置报告。")
    elif state.get("tracked_vessels", 0) == 0:
        st.info("已收到位置报告，但当前数据年龄范围内没有可用的新鲜船位。")
    else:
        st.info("当前船型、水域、搜索和数据年龄筛选没有匹配船舶。")


if tab_map.open:
    with tab_map:
        render_map_panel()

if tab_ports.open:
    with tab_ports:
        st.subheader("港口日活动")
        if port_error:
            st.error(f"港口数据加载失败：{port_error}")
        elif port_rows:
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("筛选后港口", len(port_rows))
            p2.metric("当日有进港", sum((p.get("portcalls") or 0) > 0 for p in ports))
            p3.metric(f"{rolling_days}天持续活跃",
                      sum((p.get("active_day_rate") or 0) >= 50 for p in ports))
            risk_values = [p["risk_capacity"] for p in ports
                           if p.get("risk_capacity") is not None]
            p4.metric("风险运力合计",
                      "—" if port_risk_error or not risk_values else
                      f'{sum(risk_values) / 10000:,.1f} 万吨/日')
            if port_risk_error:
                st.caption(f"历史风险运力暂不可用：{port_risk_error}")
            st.dataframe(port_rows, width="stretch", hide_index=True, height=560,
                         column_config={"来源": st.column_config.LinkColumn("来源")})
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=port_rows[0].keys())
            writer.writeheader(); writer.writerows(port_rows)
            st.download_button("下载当前筛选结果 CSV", buffer.getvalue().encode("utf-8-sig"),
                               file_name=f"portwatch_ports_{selected_day.isoformat()}.csv",
                               mime="text/csv", type="primary")
            st.button("下载当前筛选港口历史", key="download_port_history",
                      on_click=_open_download_tab, args=("ports", tuple(p["portid"] for p in ports)))
        else:
            st.info("当前筛选没有匹配港口。选择“全选”可恢复全部港口。")

if tab_download.open:
    with tab_download:
        _render_portwatch_download_panel(
            selected_port_countries, selected_port_ids, selected_chokepoint_ids,
            newest_day, newest_chokepoint_day)

if tab_vessels.open:
    with tab_vessels:
        render_ais_panel()

if tab_assets.open:
    with tab_assets:
        st.subheader(f"油气目录 · {asset_view}")
        a1, a2, a3, a4, a5 = st.columns(5)
        a1.metric("当前视图", len(filtered))
        a2.metric("可绘制", sum(bool(a["map_drawable"]) for a in filtered))
        a3.metric("有日产量", sum(bool(a["is_daily_output"]) for a in filtered))
        a4.metric("产能／目标", sum(a["value"] is not None and not a["is_daily_output"] for a in filtered))
        a5.metric("底层目录", len(ASSETS))
        st.info(
            "上级节点有直接披露值时优先采用该值，组成资产不重复计入；"
            "不同日期、商品或口径的子项不会自动相加。搜索可临时显示完整目录中的匹配资产。")
        st.dataframe(asset_rows, width="stretch", hide_index=True, height=620,
                     column_config={
                         "状态证据链接": st.column_config.LinkColumn("状态证据"),
                         "坐标来源链接": st.column_config.LinkColumn("坐标来源"),
                         "来源链接": st.column_config.LinkColumn("目录来源"),
                     })

if tab_method.open:
    with tab_method:
        st.subheader("范围、口径与数据限制")
        st.markdown("**更新方式。** 动态数据和目录使用进程级短期缓存；切换筛选时复用已读取数据。点击侧栏“刷新 PortWatch 数据”可清除 PortWatch 实时缓存并重读；源站未发布新记录时，观测日期不会改变；请求失败明确显示不可用。")
        st.dataframe([
            {"数据": "港口 / 咽喉点日度记录", "当前更新": "使用短期缓存；可手动刷新", "进一步自动化": "已接入；源站发布时间决定最新观测日"},
            {"数据": "实时船位", "当前更新": "显示船舶图层、打开船舶页或打印时读取 Open Waters；可选 AISStream 后台持续接收", "进一步自动化": "AISStream 需配置服务端密钥；页面另有手动刷新"},
            {"数据": "港口 / 咽喉点官方目录", "当前更新": "打开页面重读 PortWatch API", "进一步自动化": "已接入；补充 WPI / 运营商名录仍需版本核验"},
            {"数据": "港口风险运力", "当前更新": "打开页面重读源 API", "进一步自动化": "源为历史航线模型；重新抓取不代表实时风险"},
            {"数据": "油气产量、产能、状态和坐标", "当前更新": "经核验的静态公开披露记录", "进一步自动化": "接运营商 / 监管机构 API 或公告抓取，校验资产、日期、单位、产量 / 产能后更新"},
            {"数据": "船位归档", "当前更新": "运行期间自动归档当前快照及AISStream事件；地图与船舶页只展示当前船位", "进一步自动化": "设置持久AIS_ARCHIVE_PATH以跨重启保存；五水域完整历史需有授权的数据源"},
        ], hide_index=True, width="stretch")
        st.markdown("**地图与截图。** 港口和咽喉点分别使用源站最新观测日，船舶图层显示当前AIS快照；油气保留披露日期。地图右上角保存 PNG，包含当前视野、图例、日期、弹窗及底图署名。")
        st.markdown(
            "**港口覆盖。** 地图读取 IMF 当前维护的 PortWatch 港口点位数据库，"
            "并按下表五个经纬度框选取港口。交叠区域按表中顺序唯一归属。"
        )
        st.dataframe([
            {"水域": name, "南界": b[0], "北界": b[1], "西界": b[2], "东界": b[3]}
            for name, b in PORTWATCH.REGIONS.items()
        ], hide_index=True, width="stretch")
        st.markdown(
            f"[IMF PortWatch 方法说明]({PORTWATCH.SOURCE}) · "
            "[当前港口点位 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) · "
            "[每日港口活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0) · "
            "[每日咽喉点 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0) · "
            "[风险运力网络 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/spillovers_port_level_impact/FeatureServer/0)"
        )
        st.markdown("**港口派生指标。** 所有窗口指标固定使用所选观测日及此前6个日历日；缺报不补零。")
        st.dataframe([
            {"指标": "港口活动指数", "计算": "当前窗口日均有效进港艘次 ÷ 前一等长窗口日均值 × 100",
             "解释": "100持平；高于100表示进港活动增加"},
            {"指标": "船型结构", "计算": "窗口内各船型进港艘次 ÷ 全部进港艘次",
             "解释": "集装箱、干散货、普通货物、滚装、油轮/液货船"},
            {"指标": "活跃天数率", "计算": "窗口内有效进港艘次大于0的天数 ÷ 窗口天数",
             "解释": "反映港口活动连续性"},
            {"指标": "单船平均货量", "计算": "窗口内估算进口量与出口量之和 ÷ 有效进港艘次",
             "解释": "单位万吨/艘次；属于AIS载荷估算"},
            {"指标": "进出口平衡指数", "计算": "(出口量−进口量) ÷ (出口量+进口量) × 100",
             "解释": "−100进口导向；+100出口导向"},
            {"指标": "风险运力", "计算": "该港所有出港航线 daily_capacity_at_risk 之和",
             "解释": "2019—2024历史航线网络冲击暴露，非实时值"},
        ], hide_index=True, width="stretch")
        st.warning(
            "PortWatch 的portcalls是进入港界并通过贸易挂靠筛选的有效进港艘次，不是在港船舶存量。"
            "货量根据AIS、载重和吃水估算。单日0只表示源表当日为0；窗口不完整或比较基期为0时，"
            "派生指标保持为空，不以0替代。tanker可能包含原油、成品油及其他液体货物。"
        )
        st.markdown(
            f"**船舶数据。** 免费快照来自[Open Waters开放AIS网络]({AIS.OPENWATERS_SOURCE})，"
            f"可选[AISStream WebSocket API]({AIS.SOURCE})在服务器端接收五个监测水域的船级广播；"
            "显示船舶图层、打开船舶页或打印报告时读取最新船位快照；停留期间可点击侧栏“刷新船舶数据”。"
            "浏览器只接收标准化的每船最新位置，不接收API Key。"
            "多源位置按MMSI合并，航行阈值为0.5节，超过所选最大数据年龄的船位会被删除；"
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

# Build the full-project report only when the user enables print mode.
if print_mode:
    report_port_catalog = list(available_ports)
    report_choke_catalog = list(available_chokepoints)
    report_assets = [asset for asset in ASSETS if asset.get("strategic_default")]
    report_vessels = list(live_positions)

    report_port_ids = tuple(sorted(
        str(port["portid"]) for port in report_port_catalog
        if PORTWATCH.has_independent_statistics(port)
    ))
    report_choke_ids = tuple(sorted(
        str(point["portid"]) for point in report_choke_catalog
    ))
    report_errors = []
    report_revision = int(st.session_state.get("portwatch_report_revision", 0))
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
                    "ports", report_port_ids, selected_day.isoformat(), report_revision)
        except Exception as exc:
            report_errors.append(f"ports 历史窗口：{type(exc).__name__}: {exc}")
    if selected_chokepoint_day is not None and report_choke_ids:
        try:
            with st.spinner("准备打印报告：读取最近90天咽喉点记录…"):
                report_choke_history = report_data.history_window(
                    "chokepoints", report_choke_ids, selected_chokepoint_day.isoformat(),
                    report_revision)
        except Exception as exc:
            report_errors.append(f"chokepoints 历史窗口：{type(exc).__name__}: {exc}")

    report_latest_ports = report_data.merge_latest_rows(report_port_catalog, report_port_history)
    report_latest_chokes = report_data.merge_latest_rows(report_choke_catalog, report_choke_history)

    def _print_asset_record(asset: dict) -> dict:
        metric_type = str(asset.get("metric_type") or "")
        return {
            "中文名称": asset.get("name_cn") or asset.get("name"),
            "英文名称": asset.get("name"),
            "国家": asset.get("country"),
            "资产层级": asset.get("asset_level_label"),
            "生产状态": asset.get("operating_status_label"),
            "本层级日产量": daily_output_value(asset),
            "其他日量指标": other_daily_metric(asset),
            "指标口径": METRIC_LABELS.get(metric_type, metric_type or "未披露"),
            "数据日期": display_date(asset),
            "地图坐标精度": asset.get("map_coordinate_precision") or "未核验",
        }

    report_asset_table = [_print_asset_record(asset) for asset in report_assets]
    report_ais_state = current_ais_status()
    report_ais_status = (
        "已关闭" if not ais_enabled
        else str(report_ais_state.get("status") or "等待数据")
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
        latest_chokes=report_latest_chokes,
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
    st.caption(
        "此开关负责准备全项目报告数据。右上角 Streamlit Print 打印的是当前应用页面；"
        "要打印独立报告，请下载下方 HTML，打开后点击报告顶部的按钮。"
    )
    st.download_button(
        "下载可打印报告（HTML）",
        data=print_report.build_standalone_document(report_html),
        file_name="中东能源与战略通道运输监测.html",
        mime="text/html",
        type="primary",
        width="stretch",
    )
    st.html(print_report.PRINT_CSS + report_html)
