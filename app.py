"""中东公开命名油气分层地图 DEMO。"""

from __future__ import annotations

import html
import importlib
import json
import csv
import io
import os
from datetime import date

import streamlit as st

import field_catalog
import ais
import portwatch
import audited_measurements
import supplemental_assets
import reconciled_assets
import port_inventory

# Streamlit 的热重载会重跑此文件；显式重新读取目录模块以同步仓库中的数据修订。
importlib.invalidate_caches()
importlib.reload(audited_measurements)
importlib.reload(supplemental_assets)
importlib.reload(reconciled_assets)
importlib.reload(port_inventory)
CATALOG = importlib.reload(field_catalog)
AIS = importlib.reload(ais)
PORTWATCH = importlib.reload(portwatch)
ASSETS = CATALOG.ASSETS

if (getattr(PORTWATCH, "MODULE_VERSION", 0) < 5
        or not hasattr(PORTWATCH, "chokepoint_activity")
        or not hasattr(PORTWATCH, "port_risk_capacity")):
    st.error("港口数据模块版本未同步。请在 Streamlit 管理页重启应用后重试。")
    st.stop()


def _ais_api_key() -> str:
    """Read the key server-side without requiring or exposing it in the UI."""

    try:
        secret = st.secrets.get("AISSTREAM_API_KEY")
    except Exception:
        secret = None
    return str(secret or os.environ.get("AISSTREAM_API_KEY") or "").strip()


@st.cache_resource(show_spinner=False)
def _ais_collector(api_key: str, collector_version: int) -> AIS.AISCollector:
    return AIS.AISCollector(api_key).start()


@st.cache_data(ttl=15, show_spinner=False)
def _openwaters_snapshot(max_age_minutes: int, collector_version: int) -> dict:
    return AIS.openwaters_snapshot(max_age_minutes=max_age_minutes)


st.set_page_config(page_title="中东能源保供监测", page_icon="◉", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  .stApp { background: #f5f7fb; }
  .block-container { padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1680px; }
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
  .hero { background: linear-gradient(115deg,#0b2742,#0e5570); border-radius: 18px; padding: 20px 24px;
      color: white; margin-bottom: 14px; box-shadow: 0 12px 30px rgba(10,42,68,.16); }
  .hero h1 { margin: 0 0 5px; font-size: 1.65rem; color: white; }
  .hero p { margin: 0; color: #cfe5ef; font-size: .94rem; }
  div[data-testid="stTabs"] button { font-weight: 650; }
  div[data-testid="stDataFrame"] { border: 1px solid #dfe7ef; border-radius: 12px; overflow: hidden; }
  .stAlert { border-radius: 12px; }
</style>
""", unsafe_allow_html=True)

METRIC_LABELS = {
    "estimated_daily_average": "估算期间日均（公布总量×份额）",
    "actual_output": "来源直报实际产量",
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
MAP_LAYER_LABELS = {
    "vessels": "船舶",
    "ports": "港口",
    "assets": "油气",
    "chokepoints": "咽喉点",
}
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
    return (
        '<div class="popup-card">'
        f'<div class="field-name">⚓ {esc(port["name"])}</div>'
        f'<div class="country">{esc(port["country"])} · {esc(port["region"])} · {esc(day)}</div>'
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
        '<div class="row"><span>风险运力（出港网络）</span>'
        f'<strong>{amount("risk_capacity", 10000)} 万吨/日</strong></div>'
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


def _map_html(assets: list[dict[str, object]], ports: list[dict],
              chokepoints: list[dict], vessels: list[dict], day: str, chokepoint_day: str,
              focus_assets: bool = False, ais_configured: bool = True,
              visible_layers: set[str] | None = None,
              region_bounds: list[tuple[float, float, float, float]] | None = None) -> str:
    visible_layers = set(MAP_LAYER_LABELS) if visible_layers is None else visible_layers
    show_assets = "assets" in visible_layers
    show_ports = "ports" in visible_layers
    show_chokepoints = "chokepoints" in visible_layers
    show_vessels = "vessels" in visible_layers and ais_configured
    markers = [
        {
            "lat": asset["map_lat"],
            "lon": asset["map_lon"],
            "is_proxy": asset.get("map_is_proxy", False),
            "name": f'{asset["name_cn"]} · {asset["name"]}',
            "popup": _popup(asset),
        }
        for asset in assets
        if asset["map_drawable"]
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    port_json = json.dumps([
        {"lat": port["lat"], "lon": port["lon"], "name": port["name"],
         "popup": _port_popup(port, day)}
        for port in ports
    ], ensure_ascii=False).replace("</", "<\\/")
    chokepoint_json = json.dumps([
        {"lat": point["lat"], "lon": point["lon"], "name": point.get("name_cn", point["portname"]),
         "popup": _chokepoint_popup(point, chokepoint_day)}
        for point in chokepoints
    ], ensure_ascii=False).replace("</", "<\\/")
    vessel_json = json.dumps([
        {
            "lat": vessel["lat"], "lon": vessel["lon"],
            "name": html.escape(str(vessel.get("name") or f'MMSI {vessel["mmsi"]}')),
            "category": vessel.get("category", "unknown"),
            "course": vessel.get("course") or 0,
            "popup": _vessel_popup(vessel),
        }
        for vessel in vessels
    ], ensure_ascii=False).replace("</", "<\\/")
    legend_lines = ["<b>地图符号</b>"]
    if show_assets:
        legend_lines.append('<span><i class="shape-asset"></i>油气：菱形</span>')
    if show_ports:
        legend_lines.append('<span><i class="shape-port"></i>港口：方形</span>')
    if show_chokepoints:
        legend_lines.append('<span><i class="shape-choke"></i>咽喉点：六边形</span>')
    if show_vessels:
        legend_lines.append('<span><i class="shape-vessel"></i>船舶：三角形</span>')
    if show_assets:
        legend_lines.append('<span><i class="legend-proxy"></i>油气虚线边：近似坐标</span>')
    if show_vessels:
        legend_lines.extend([
            '<span><i class="shape-vessel vessel-tanker"></i>油轮/液货船　<i class="shape-vessel vessel-cargo"></i>货船</span>',
            '<span><i class="shape-vessel"></i>其他船舶/船型未知</span>',
        ])
    legend_json = json.dumps("".join(legend_lines), ensure_ascii=False).replace("</", "<\\/")
    focus_json = json.dumps(focus_assets)
    region_bounds_json = json.dumps(region_bounds or [])
    return f"""
    <!doctype html><html lang="zh-CN"><head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
      html, body, #map {{ height: 100%; margin: 0; }}
      #map {{ background: #e8eef4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .leaflet-popup-content-wrapper {{ border-radius: 10px; box-shadow: 0 8px 24px rgba(15, 23, 42, .25); }}
      .leaflet-popup-content {{ margin: 13px 15px; min-width: 300px; max-width: 360px; }}
      .field-name {{ font-weight: 750; color: #0f172a; font-size: 14px; line-height: 1.35; margin-bottom: 3px; }}
      .country {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
      .row {{ display: flex; justify-content: space-between; gap: 14px; padding: 5px 0; border-top: 1px solid #e2e8f0; font-size: 12px; }}
      .row span, .basis, .status {{ color: #64748b; }}
      .row strong {{ color: #0f172a; text-align: right; }}
      .hierarchy-title {{ margin-top: 10px; padding-top: 8px; border-top: 2px solid #cbd5e1; color: #334155; font-size: 12px; font-weight: 700; }}
      .level-metric {{ padding: 7px 8px; margin-top: 6px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 7px; }}
      .level-head, .output-line {{ display: flex; justify-content: space-between; gap: 10px; font-size: 11px; }}
      .level-head span, .output-line span, .metric-detail {{ color: #64748b; }}
      .level-head b {{ color: #334155; text-align: right; }}
      .output-line {{ margin-top: 4px; align-items: baseline; }}
      .output-line strong {{ color: #991b1b; font-size: 13px; }}
      .metric-detail, .other-metric {{ font-size: 10px; margin-top: 2px; line-height: 1.35; }}
      .other-metric {{ color: #92400e; }}
      .mix-row {{ display: grid; grid-template-columns: 72px 1fr 92px; gap: 7px; align-items: center; margin-top: 6px; font-size: 10px; }}
      .mix-row span {{ color: #475569; }}
      .mix-row b {{ color: #334155; text-align: right; font-weight: 600; }}
      .mix-track {{ height: 6px; border-radius: 999px; background: #e2e8f0; overflow: hidden; }}
      .mix-track i {{ display: block; height: 100%; border-radius: 999px; }}
      .status, .basis {{ font-size: 11px; margin-top: 8px; line-height: 1.4; }}
      .source {{ display: block; color: #2563eb; font-size: 11px; margin-top: 8px; text-decoration: none; }}
      .map-legend {{ background: rgba(255,255,255,.95); padding: 9px 11px; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.15); color: #0f172a; font-size: 11px; line-height: 1.45; }}
      .map-legend b {{ font-size: 13px; }}
      .map-legend span {{ display: block; margin-top: 4px; white-space: nowrap; }}
      .map-legend i {{ display: inline-block; width: 10px; height: 10px; margin-right: 6px; box-sizing: border-box; vertical-align: -1px; }}
      .map-legend .shape-asset {{ background: #ea580c; transform: rotate(45deg) scale(.78); }}
      .map-legend .shape-port {{ background: #2563eb; border-radius: 2px; }}
      .map-legend .shape-choke {{ background: #7c3aed; clip-path: polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%); }}
      .map-legend .shape-vessel {{ background: #64748b; clip-path: polygon(50% 0,100% 100%,50% 78%,0 100%); }}
      .map-legend .vessel-tanker {{ background: #ef4444; }}
      .map-legend .vessel-cargo {{ background: #2563eb; }}
      .map-legend .legend-proxy {{ background: #ea580c; border: 2px dashed #7c2d12; transform: rotate(45deg) scale(.78); }}
      .asset-icon, .port-icon, .chokepoint-icon, .vessel-icon, .vessel-cluster {{ background: transparent; border: 0; }}
      .asset-icon svg, .port-icon svg, .chokepoint-icon svg, .vessel-icon svg, .vessel-cluster svg {{ display: block; filter: drop-shadow(0 1px 1px rgba(15,23,42,.45)); }}
      .leaflet-tooltip {{ border: 0; border-radius: 7px; padding: 5px 8px; box-shadow: 0 3px 12px rgba(15,23,42,.18); font-size: 11px; }}
      .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {{ background: transparent; }}
      .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {{ background: #ea580c; color: white; font-weight: 700; border-radius: 7px; transform: rotate(45deg); box-shadow: 0 0 0 5px rgba(234,88,12,.22); }}
      .marker-cluster-small span, .marker-cluster-medium span, .marker-cluster-large span {{ display: block; transform: rotate(-45deg); }}
    </style></head><body><div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([25.5, 48.5], 4);
      L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Tiles &copy; Esri', maxZoom: 18
      }}).addTo(map);
      const legend = L.control({{position: 'bottomright'}});
      legend.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-legend');
        el.innerHTML = {legend_json};
        return el;
      }};
      legend.addTo(map);
      const assets = {marker_json};
      const ports = {port_json};
      const chokepoints = {chokepoint_json};
      const vessels = {vessel_json};
      const regionBounds = {region_bounds_json};
      const assetLayer = L.markerClusterGroup({{showCoverageOnHover: false, maxClusterRadius: 34,
          disableClusteringAtZoom: 8, spiderfyOnMaxZoom: true}}).addTo(map);
      const portLayer = L.layerGroup().addTo(map);
      const chokepointLayer = L.layerGroup().addTo(map);
      const vesselLayer = L.markerClusterGroup({{
        showCoverageOnHover: false, maxClusterRadius: 24, disableClusteringAtZoom: 7,
        spiderfyOnMaxZoom: true,
        iconCreateFunction: (cluster) => {{
          const count = cluster.getChildCount();
          const label = count > 999 ? `${{Math.round(count / 100) / 10}}k` : String(count);
          return L.divIcon({{
            className: 'vessel-cluster', iconSize: [38, 34], iconAnchor: [19, 17],
            html: `<svg width="38" height="34" viewBox="0 0 38 34">
              <path d="M19 1 L37 32 L19 26 L1 32 Z" fill="#334155" stroke="#ffffff" stroke-width="1.4"/>
              <text x="19" y="22" text-anchor="middle" fill="#ffffff" font-size="10" font-weight="700">${{label}}</text>
            </svg>`
          }});
        }}
      }}).addTo(map);
      assets.forEach((asset) => {{
        const size = 18;
        const dash = asset.is_proxy ? '3 2' : 'none';
        const icon = L.divIcon({{
          className: 'asset-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <polygon points="${{size/2}},1 ${{size-1}},${{size/2}} ${{size/2}},${{size-1}} 1,${{size/2}}"
              fill="#ea580c" fill-opacity=".94" stroke="#7c2d12"
              stroke-width="1.5" stroke-dasharray="${{dash}}"/>
          </svg>`
        }});
        L.marker([asset.lat, asset.lon], {{icon}}).bindTooltip(asset.name, {{direction: 'top', opacity: .95}})
          .bindPopup(asset.popup, {{maxWidth: 390}}).addTo(assetLayer);
      }});
      ports.forEach((port) => {{
        const size = 16;
        const icon = L.divIcon({{
          className: 'port-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 ${{size}} ${{size}}">
            <rect x="1.5" y="1.5" width="${{size-3}}" height="${{size-3}}" rx="2.5"
              fill="#2563eb" fill-opacity=".9" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        L.marker([port.lat, port.lon], {{icon}}).bindTooltip(port.name, {{direction: 'top', opacity: .95}})
          .bindPopup(port.popup, {{maxWidth: 410}}).addTo(portLayer);
      }});
      chokepoints.forEach((point) => {{
        const size = 22;
        const icon = L.divIcon({{
          className: 'chokepoint-icon', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
          html: `<svg width="${{size}}" height="${{size}}" viewBox="0 0 24 24">
            <polygon points="6,2 18,2 23,12 18,22 6,22 1,12"
              fill="#7c3aed" fill-opacity=".94" stroke="#ffffff" stroke-width="1.5"/>
          </svg>`
        }});
        L.marker([point.lat, point.lon], {{icon}}).bindTooltip(point.name, {{direction: 'top', opacity: .95}})
          .bindPopup(point.popup, {{maxWidth: 410}}).addTo(chokepointLayer);
      }});
      const vesselColors = {{
        tanker: '#ef4444', cargo: '#2563eb', other: '#64748b'
      }};
      vessels.forEach((vessel) => {{
        const color = vesselColors[vessel.category] || vesselColors.other;
        const angle = Number.isFinite(Number(vessel.course)) ? Number(vessel.course) : 0;
        const icon = L.divIcon({{
          className: 'vessel-icon', iconSize: [18, 18], iconAnchor: [9, 9],
          html: `<svg width="18" height="18" viewBox="0 0 18 18" style="transform:rotate(${{angle}}deg)">
            <path d="M9 1 L16 16 L9 12.8 L2 16 Z" fill="${{color}}" stroke="#ffffff" stroke-width="1.15"/>
          </svg>`
        }});
        const marker = L.marker([vessel.lat, vessel.lon], {{icon}});
        marker.bindTooltip(vessel.name, {{direction: 'top', opacity: .95}})
          .bindPopup(vessel.popup, {{maxWidth: 410}}).addTo(vesselLayer);
      }});
      const allPoints = ports.map((p) => [p.lat, p.lon])
        .concat(chokepoints.map((p) => [p.lat, p.lon]))
        .concat(assets.map((a) => [a.lat, a.lon]))
        .concat(vessels.map((v) => [v.lat, v.lon]));
      const focusAssets = {focus_json};
      if (focusAssets && assets.length === 1) {{
        map.setView([assets[0].lat, assets[0].lon], 8);
      }} else if (focusAssets && assets.length > 1) {{
        map.fitBounds(L.latLngBounds(assets.map((a) => [a.lat, a.lon])),
          {{padding: [42, 42], maxZoom: 7}});
      }} else if (regionBounds.length) {{
        const selectedBounds = regionBounds.reduce((bounds, region) =>
          bounds.extend([[region[0], region[2]], [region[1], region[3]]]),
          L.latLngBounds([]));
        map.fitBounds(selectedBounds, {{padding: [42, 42], maxZoom: 8}});
      }} else if (allPoints.length) {{
        map.fitBounds(L.latLngBounds(allPoints), {{padding: [36, 36], maxZoom: 5}});
      }}
    </script></body></html>
    """


st.markdown("""
<div class="hero">
  <h1>中东能源保供监测</h1>
  <p>战略生产节点、港口活动、关键咽喉点与船舶位置｜来源分层、口径不重复</p>
</div>
""", unsafe_allow_html=True)

country_options = sorted({str(asset["country"]) for asset in ASSETS})
level_options = list(LEVEL_LABELS)
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})
status_options = list(STATUS_LABELS)
ais_api_key = _ais_api_key()
ais_collector_instance: AIS.AISCollector | None = None

with st.sidebar:
    st.markdown("### 监测视图")
    selected_map_layers = st.multiselect(
        "地图内容", list(MAP_LAYER_LABELS), default=["ports"],
        format_func=lambda value: MAP_LAYER_LABELS[value], key="map_layers",
        placeholder="全部图层",
        help="默认显示港口；可选择一个或多个图层。",
        select_all=False)
    selected_regions = st.multiselect(
        "航运水域", list(PORTWATCH.REGIONS), default=["霍尔木兹海峡"],
        placeholder="全部五个水域", key="monitor_regions",
        help="同时筛选港口、咽喉点和船舶，并自动调整地图视野。")
    active_regions = tuple(selected_regions or PORTWATCH.REGIONS)
    selected_region_set = set(active_regions)
    selected_region_bounds = [PORTWATCH.REGIONS[region] for region in active_regions]
    try:
        region_port_catalog = [
            port for port in PORTWATCH.port_catalog()
            if port["region"] in selected_region_set
        ]
        port_catalog_error = None
    except Exception as exc:
        region_port_catalog = []
        port_catalog_error = str(exc)

    with st.expander("港口与咽喉点", expanded=False):
        port_country_options = sorted({port["country"] for port in region_port_catalog})
        if "port_countries" in st.session_state:
            st.session_state["port_countries"] = [
                country for country in st.session_state["port_countries"]
                if country in port_country_options
            ]
        selected_port_countries = st.multiselect(
            "国家（可多选）", port_country_options, default=[],
            placeholder="全部国家", key="port_countries",
            help="国家列表随航运水域联动；空选表示当前水域内全部国家。",
            select_all=False)
        country_port_catalog = [
            port for port in region_port_catalog
            if port["country"] in selected_port_countries
        ]
        port_labels = {
            port["portid"]: f'{port["name"]} · {port["country"]}'
            for port in country_port_catalog
        }
        port_id_options = [
            port["portid"] for port in sorted(
                country_port_catalog, key=lambda port: (port["country"], port["name"]))
        ]
        if "port_ids" in st.session_state:
            st.session_state["port_ids"] = [
                port_id for port_id in st.session_state["port_ids"]
                if port_id in port_labels
            ]
        selected_port_ids = st.multiselect(
            "港口（可多选）", port_id_options, default=[],
            format_func=lambda port_id: port_labels.get(port_id, port_id),
            placeholder=("请先选择国家" if not selected_port_countries else "所选国家的全部港口"),
            key="port_ids", disabled=not selected_port_countries,
            help="先选择一个或多个国家；港口空选时显示所选国家的全部港口。",
            select_all=False)
        if port_catalog_error:
            st.warning(f"港口目录暂时不可用：{port_catalog_error}")
        try:
            newest_day = PORTWATCH.latest_date()
            selected_day = st.date_input("统计日期（UTC）", value=newest_day,
                                         min_value=date(2019, 1, 1), max_value=newest_day,
                                         key="port_day")
            st.caption(f"源站最新：{newest_day.isoformat()}")
        except Exception as exc:
            newest_day = selected_day = None
            st.warning(f"PortWatch 暂时不可用：{exc}")
        rolling_label = st.radio("日均窗口", ["过去 7 天", "过去 30 天"],
                                 horizontal=True, key="rolling_window")
        rolling_days = 7 if rolling_label == "过去 7 天" else 30
        try:
            newest_chokepoint_day = PORTWATCH.latest_chokepoint_date()
            st.caption(f"咽喉点最新：{newest_chokepoint_day.isoformat()} UTC")
        except Exception as exc:
            newest_chokepoint_day = None
            st.warning(f"咽喉点数据暂时不可用：{exc}")
        if st.button("刷新 PortWatch 数据", width="stretch"):
            PORTWATCH.latest_date.clear()
            PORTWATCH.port_catalog.clear()
            PORTWATCH.daily_activity.clear()
            PORTWATCH.rolling_activity.clear()
            PORTWATCH.port_risk_capacity.clear()
            PORTWATCH.latest_chokepoint_date.clear()
            PORTWATCH.chokepoint_catalog.clear()
            PORTWATCH.chokepoint_activity.clear()
            st.rerun()

    with st.expander("船舶", expanded=True):
        ais_enabled = st.toggle(
            "启用实时船位", value=True,
            key="ais_enabled")
        selected_ais_categories = st.multiselect(
            "船型（空选＝全部）", list(AIS.VESSEL_TYPE_LABELS), default=[],
            format_func=lambda key: AIS.VESSEL_TYPE_LABELS[key],
            placeholder="全部船型", key="ais_categories")
        ais_search = st.text_input(
            "搜索船名、MMSI或IMO", placeholder="例如 EVER GIVEN / 636…",
            key="ais_search").strip().lower()
        ais_moving_only = st.toggle("仅航行中（≥0.5节）", value=False,
                                    key="ais_moving_only")
        ais_max_age = st.select_slider(
            "最大数据年龄", options=[10, 30, 60, 120], value=30,
            format_func=lambda value: f"{value}分钟", key="ais_max_age")
        if ais_enabled:
            stream_status = "未配置（可选）"
            if ais_api_key:
                ais_collector_instance = _ais_collector(ais_api_key, AIS.MODULE_VERSION)
                ais_state = ais_collector_instance.status()
                stream_status = ais_state["status"]
                if ais_state.get("last_error"):
                    st.caption(f'最近 AISStream 错误：{ais_state["last_error"]}')
            open_state = _openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
            stream_rows = (
                ais_collector_instance.snapshot(max_age_minutes=ais_max_age)
                if ais_collector_instance is not None else []
            )
            merged_count = len(AIS.merge_vessel_snapshots(
                stream_rows, open_state.get("vessels", [])))
            st.caption(
                f'数据状态：合并后 {merged_count:,} 艘'
                f'（公开快照 {len(open_state["vessels"]):,}）· '
                f'AISStream {stream_status}')
            if open_state.get("error"):
                st.caption(f'Open Waters 错误：{open_state["error"]}')
        if st.button("刷新船舶数据", width="stretch", disabled=not ais_enabled):
            if ais_collector_instance:
                ais_collector_instance.stop()
            if ais_api_key:
                _ais_collector.clear()
            _openwaters_snapshot.clear()
            st.rerun()

    with st.expander("油气", expanded=False):
        asset_view = st.radio(
            "资产视图", ["战略生产节点", "完整资产目录"],
            horizontal=True, key="asset_view")
        st.caption("战略视图按油田群／区块优先，避免组成资产与上级重复展示。")
        asset_search = st.text_input("搜索资产", placeholder="输入中英文名称",
                                     key="asset_search").strip().lower()
        selected_countries = st.multiselect("国家（空选＝全部）", country_options, default=[],
                                            placeholder="全部国家", key="asset_countries")
        selected_levels = st.multiselect(
            "资产层级（空选＝全部）", level_options, default=[],
            format_func=lambda key: LEVEL_LABELS[key], placeholder="全部层级",
            key="asset_levels")
        selected_statuses = st.multiselect(
            "生产状态（空选＝全部）", status_options, default=[],
            format_func=lambda key: STATUS_LABELS[key], placeholder="全部状态",
            key="asset_statuses")
        values_only = st.toggle("只看有公开数值", value=False, key="values_only")
        output_only = st.toggle("只看有日产量", value=False, key="output_only")
        st.markdown("**高级筛选**")
        selected_types = st.multiselect("资产类型（空选＝全部）", type_options, default=[],
                                        placeholder="全部类型", key="asset_types")
        selected_metrics = st.multiselect(
            "指标口径（空选＝全部）", metric_options, default=[],
            format_func=lambda key: METRIC_LABELS[key], placeholder="全部口径",
            key="asset_metrics")

    st.caption("航运水域同时作用于港口、咽喉点和船舶；其他筛选留空表示全部。")

ports: list[dict] = []
port_error = port_catalog_error
if selected_day is not None and not port_error:
    try:
        catalog = [
            port for port in region_port_catalog
            if (not selected_port_countries
                or port["country"] in selected_port_countries)
            and (not selected_port_ids or port["portid"] in selected_port_ids)
        ]
        ids = tuple(p["portid"] for p in catalog)
        if ids:
            activity = PORTWATCH.daily_activity(selected_day, ids)
            rolling = PORTWATCH.rolling_activity(selected_day, ids, rolling_days)
            risk_capacity = PORTWATCH.port_risk_capacity(ids)
            ports = PORTWATCH.decorate(catalog, activity, rolling, risk_capacity)
    except Exception as exc:
        port_error = str(exc)

chokepoints: list[dict] = []
chokepoint_error = None
if newest_chokepoint_day is not None:
    try:
        chokepoint_catalog = PORTWATCH.chokepoint_catalog()
        chokepoint_catalog = [
            point for point in chokepoint_catalog
            if point.get("name_cn") in selected_region_set
        ]
        chokepoint_ids = tuple(point["portid"] for point in chokepoint_catalog)
        if chokepoint_ids:
            chokepoint_values = PORTWATCH.chokepoint_activity(
                newest_chokepoint_day, chokepoint_ids)
            chokepoints = PORTWATCH.decorate_chokepoints(
                chokepoint_catalog, chokepoint_values)
    except Exception as exc:
        chokepoint_error = str(exc)


def current_ais_positions() -> list[dict]:
    """Merge the direct AISStream feed and the public Open Waters snapshot."""

    if not ais_enabled:
        return []
    stream_rows = []
    if ais_collector_instance is not None:
        stream_rows = ais_collector_instance.snapshot(max_age_minutes=ais_max_age)
    open_state = _openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
    return AIS.merge_vessel_snapshots(stream_rows, open_state.get("vessels", []))


def current_vessels(rows: list[dict] | None = None) -> list[dict]:
    """Return one consistent, filtered snapshot; missing AIS is unavailable, not zero."""

    snapshot = current_ais_positions() if rows is None else rows
    return AIS.filter_vessels(
        snapshot,
        regions=selected_region_set,
        categories=set(selected_ais_categories),
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
    if (not selected_countries or asset["country"] in selected_countries)
    and (not selected_levels or asset["asset_level"] in selected_levels)
    and (not selected_types or asset["asset_type"] in selected_types)
    and (not selected_statuses or asset["operating_status"] in selected_statuses)
    and (not selected_metrics or asset["metric_type"] in selected_metrics)
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
visible_map_layers = set(selected_map_layers) or set(MAP_LAYER_LABELS)
map_asset_candidates = filtered if "assets" in visible_map_layers else []
map_assets = [asset for asset in map_asset_candidates if asset["map_drawable"]]
unlocated_map_assets = [asset for asset in map_asset_candidates if not asset["map_drawable"]]
map_ports = ports if "ports" in visible_map_layers else []
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
        "数据年龄 分钟": round(vessel.get("age_minutes", 0), 1),
        "纬度": vessel.get("lat"), "经度": vessel.get("lon"),
        "数据源": vessel.get("data_source"),
        "来源": vessel.get("source_url") or AIS.SOURCE,
    } for vessel in vessels]


def render_map_panel() -> None:
    all_positions = current_ais_positions()
    filtered_vessels = current_vessels(all_positions)
    map_vessels = (
        filtered_vessels
        if "vessels" in visible_map_layers
        else []
    )
    stream_state = current_ais_status()
    open_state = _openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    if chokepoint_error:
        st.error(f"咽喉点数据加载失败：{chokepoint_error}")
    if not ais_enabled:
        st.info("船舶图层已关闭。")
    else:
        if stream_state.get("last_error") and not all_positions:
            st.warning(f'AISStream 暂无可用船位，后台将自动重连：{stream_state["last_error"]}')
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
        _map_html(
            map_assets, map_ports, map_chokepoints, map_vessels,
            selected_day.isoformat() if selected_day else "无数据",
            newest_chokepoint_day.isoformat() if newest_chokepoint_day else "无数据",
            focus_assets=bool(asset_search), ais_configured=bool(ais_enabled),
            visible_layers=visible_map_layers,
            region_bounds=selected_region_bounds),
        height=735,
    )


def render_ais_panel() -> None:
    st.subheader("船舶")
    if not ais_enabled:
        st.info("船舶位置已关闭，可在左侧‘船舶’中启用。")
        return
    all_positions = current_ais_positions()
    vessels = current_vessels(all_positions)
    rows = vessel_rows(vessels)
    state = current_ais_status()
    open_state = _openwaters_snapshot(ais_max_age, AIS.MODULE_VERSION)
    has_position_data = bool(all_positions)
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
            "下载当前船位快照 CSV", buffer.getvalue().encode("utf-8-sig"),
            file_name="ais_vessel_snapshot.csv", mime="text/csv", type="primary")
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


tab_map, tab_ports, tab_vessels, tab_assets, tab_method = st.tabs(
    ["地图总览", "港口活动", "船舶", "油气", "数据与方法"])

with tab_map:
    render_map_panel()

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
        p4.metric("风险运力合计",
                  f'{sum(p.get("risk_capacity") or 0 for p in ports) / 10000:,.1f} 万吨/日')
        st.dataframe(port_rows, width="stretch", hide_index=True, height=560,
                     column_config={"来源": st.column_config.LinkColumn("来源")})
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=port_rows[0].keys())
        writer.writeheader(); writer.writerows(port_rows)
        st.download_button("下载当前筛选结果 CSV", buffer.getvalue().encode("utf-8-sig"),
                           file_name=f"portwatch_ports_{selected_day.isoformat()}.csv",
                           mime="text/csv", type="primary")
    else:
        st.info("当前筛选没有匹配港口。清空水域和搜索框可恢复全部港口。")

with tab_vessels:
    render_ais_panel()

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

with tab_method:
    st.subheader("范围、口径与数据限制")
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
    st.markdown("**港口派生指标。** 所有窗口指标使用同一7日或30日完整日历窗口；缺报不补零。")
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
        "页面不会定时刷新；点击侧栏“刷新船舶数据”时读取最新船位快照。"
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
        "**咽喉点。** 地图紫色六边形显示所选水域内咽喉点的最新可用日数据。"
        "popup列示总通过船数、估算承载货量及五类船型分解；咽喉点日期与港口日期分别读取，"
        "避免把更新节奏不同的两张表强行对齐。"
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

pending_clues = reconciled_assets.pending()
with st.expander(f"待核资产线索（{len(pending_clues)}条；未纳入确认目录）"):
    st.caption("以下线索来自保存的历史名录。原页及定向检索未取得充分确认内容，保留供继续核验；不填产量或坐标。")
    st.dataframe(pending_clues, hide_index=True, width="stretch")
    pending_buffer = io.StringIO()
    pending_writer = csv.DictWriter(pending_buffer, fieldnames=pending_clues[0].keys())
    pending_writer.writeheader()
    pending_writer.writerows(pending_clues)
    st.download_button("下载待核线索 CSV", pending_buffer.getvalue().encode("utf-8-sig"),
                       "pending_asset_clues.csv", "text/csv", key="pending_asset_clues")
