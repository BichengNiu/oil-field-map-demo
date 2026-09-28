"""中东公开命名油气资产分层地图 DEMO。"""

from __future__ import annotations

import html
import importlib
import json
import csv
import io
from datetime import date

import streamlit as st

import field_catalog
import portwatch

# Streamlit 的热重载会重跑此文件；显式重新读取目录模块以同步仓库中的数据修订。
importlib.invalidate_caches()
CATALOG = importlib.reload(field_catalog)
PORTWATCH = importlib.reload(portwatch)
ASSETS = CATALOG.ASSETS

if getattr(PORTWATCH, "MODULE_VERSION", 0) < 3 or not hasattr(PORTWATCH, "rolling_activity"):
    st.error("港口数据模块版本未同步。请在 Streamlit 管理页重启应用后重试。")
    st.stop()


st.set_page_config(page_title="中东能源保供监测", page_icon="◉", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  .stApp { background: #f5f7fb; }
  .block-container { padding-top: 1.35rem; padding-bottom: 2.5rem; max-width: 1680px; }
  [data-testid="stSidebar"] { background: #0b1f33; }
  [data-testid="stSidebar"] * { color: #eef6ff; }
  [data-testid="stSidebar"] div[data-baseweb="select"] > div,
  [data-testid="stSidebar"] input { background: #142d46; border-color: #31516e; }
  [data-testid="stSidebar"] .stCaption { color: #a9bfd2 !important; }
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
    "actual_output": "来源直报实际产量",
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
LEVEL_COLORS = {
    "field": "#dc2626",
    "field_group": "#ea580c",
    "block": "#2563eb",
    "concession": "#7c3aed",
    "project": "#475569",
    "development_area": "#059669",
}
ASSET_INDEX = {(asset["country"], asset["name"]): asset for asset in ASSETS}


def display_value(asset: dict[str, object]) -> str:
    value = asset.get("value")
    unit = asset.get("unit")
    if value is None:
        return "未披露"
    return f"{value} {unit}" if unit else str(value)


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
    parent = asset.get("parent_asset") or "无已登记上级"
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{esc(asset["name"])}（{esc(asset["name_cn"])}）</div>'
        f'<div class="country">{esc(asset["country"])} · {esc(asset["asset_type"])}</div>'
        '<div class="row"><span>资产层级</span>'
        f'<strong>{esc(asset["asset_level_label"])}</strong></div>'
        '<div class="row"><span>上级资产</span>'
        f'<strong>{esc(parent)}</strong></div>'
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
        f'<strong>{esc(asset["coordinate_precision"])}</strong></div>'
        f'<div class="status">原始状态说明：{esc(asset["status"])}</div>'
        f'<div class="basis">状态依据：{esc(asset["operating_status_basis"])}</div>'
        f'<div class="basis">权益口径：{esc(asset["ownership_basis"])}</div>'
        f'<div class="basis">说明：{esc(asset["note"] or "公开命名资产；本层级数值未公开。")}</div>'
        f'<a class="source" href="{status_source_url}" target="_blank" rel="noopener">生产状态证据</a>'
        f'<a class="source" href="{source_url}" target="_blank" rel="noopener">目录来源：{esc(asset["source"])}</a>'
        '</div>'
    )


def _port_popup(port: dict, day: str, barrels_per_tonne: float) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value))

    def amount(key: str, divisor: float = 1) -> str:
        value = port.get(key)
        if value is None:
            return "无数据"
        if divisor != 1 and 0 < value / divisor < 0.005:
            return "<0.01"
        decimals = 2 if key.startswith("avg_") or divisor != 1 else 0
        return f"{value / divisor:,.{decimals}f}"

    oil_equivalent = port.get("handled_tanker")
    barrels = (f"{oil_equivalent * barrels_per_tonne / 10000:,.2f}"
               if oil_equivalent is not None else "无数据")
    window = port.get("window_days", 7)
    avg_tanker = port.get("avg_handled_tanker")
    avg_barrels = (f"{avg_tanker * barrels_per_tonne / 10000:,.2f}"
                   if avg_tanker is not None else "不完整")
    warning = ""
    if port.get("portcalls_tanker", 0) and port.get("handled_tanker") == 0:
        warning = '<div class="basis">⚠ 当日有油轮挂靠，但源站估算装卸量为 0；不能解读为实际没有装卸。</div>'
    elif (port.get("avg_calls_tanker") or 0) > 0 and port.get("avg_handled_tanker") == 0:
        warning = '<div class="basis">⚠ 滚动窗口内有油轮挂靠，但估算货量持续为 0；需核对源站吃水记录。</div>'
    elif port.get("portcalls_tanker") == 0 and (port.get("tanker_positive_days") or 0) > 0:
        warning = '<div class="basis">当日未观测到油轮挂靠；所选滚动窗口内有挂靠记录。</div>'
    return (
        '<div class="popup-card">'
        f'<div class="field-name">⚓ {esc(port["name"])}</div>'
        f'<div class="country">{esc(port["country"])} · {esc(port["region"])} · {esc(day)}</div>'
        '<div class="row"><span>油轮到港</span>'
        f'<strong>{amount("portcalls_tanker")} 艘次/日</strong></div>'
        '<div class="row"><span>油轮卸货 / 装货</span>'
        f'<strong>{amount("import_tanker", 10000)} / {amount("export_tanker", 10000)} 万吨/日</strong></div>'
        '<div class="row"><span>油轮装卸合计</span>'
        f'<strong>{amount("handled_tanker", 10000)} 万吨/日</strong></div>'
        '<div class="row"><span>油轮载货原油当量估算</span>'
        f'<strong>{barrels} 万桶/日</strong></div>'
        '<div class="row"><span>其他货轮到港</span>'
        f'<strong>{amount("portcalls_cargo")} 艘次/日</strong></div>'
        '<div class="row"><span>其他货轮卸货 / 装货</span>'
        f'<strong>{amount("import_cargo", 10000)} / {amount("export_cargo", 10000)} 万吨/日</strong></div>'
        '<div class="row"><span>其他货轮装卸合计</span>'
        f'<strong>{amount("handled_cargo", 10000)} 万吨/日</strong></div>'
        f'<div class="hierarchy-title">过去 {window} 天日均（含所选日）</div>'
        '<div class="row"><span>有效日期</span>'
        f'<strong>{port.get("observed_days", 0)}/{window} 天</strong></div>'
        '<div class="row"><span>油轮挂靠 / 日均货量</span>'
        f'<strong>{amount("avg_calls_tanker")} 艘次/日 · {amount("avg_handled_tanker", 10000)} 万吨/日</strong></div>'
        '<div class="row"><span>油轮载货原油当量日均</span>'
        f'<strong>{avg_barrels} 万桶/日</strong></div>'
        '<div class="row"><span>其他货轮挂靠 / 日均货量</span>'
        f'<strong>{amount("avg_calls_cargo")} 艘次/日 · {amount("avg_handled_cargo", 10000)} 万吨/日</strong></div>'
        f'{warning}'
        '<div class="basis">油轮类别可能含原油、成品油和其他液体货物。桶数仅将油轮估算吨数按'
        f'{barrels_per_tonne:g} 桶/吨换算，不是实测原油吞吐量；装卸合计不等于净贸易量。'
        '未匹配日期的港口显示“无数据”，不记为零。</div>'
        f'<a class="source" href="{esc(PORTWATCH.SOURCE)}" target="_blank" rel="noopener">IMF PortWatch 数据与方法</a>'
        '</div>'
    )


def _map_html(assets: list[dict[str, object]], ports: list[dict],
              day: str, barrels_per_tonne: float) -> str:
    markers = [
        {
            "lat": asset["lat"],
            "lon": asset["lon"],
            "level": asset["asset_level"],
            "name": f'{asset["name_cn"]} · {asset["name"]}',
            "popup": _popup(asset),
        }
        for asset in assets
        if asset["lat"] is not None and asset["lon"] is not None
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    port_json = json.dumps([
        {"lat": port["lat"], "lon": port["lon"], "name": port["name"],
         "popup": _port_popup(port, day, barrels_per_tonne), "has_data": port["has_data"],
         "activity": (port.get("avg_calls_tanker") or 0) + (port.get("avg_calls_cargo") or 0)}
        for port in ports
    ], ensure_ascii=False).replace("</", "<\\/")
    color_json = json.dumps(LEVEL_COLORS, ensure_ascii=False)
    legend_items = "".join(
        f'<span><i style="background:{LEVEL_COLORS[level]}"></i>{label}</span>'
        for level, label in LEVEL_LABELS.items()
    )
    legend_json = json.dumps(
        "<b>资产层级</b>" + legend_items, ensure_ascii=False
    ).replace("</", "<\\/")
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
      .status, .basis {{ font-size: 11px; margin-top: 8px; line-height: 1.4; }}
      .source {{ display: block; color: #2563eb; font-size: 11px; margin-top: 8px; text-decoration: none; }}
      .map-title, .map-legend {{ background: rgba(255,255,255,.95); padding: 9px 11px; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.15); color: #0f172a; font-size: 11px; line-height: 1.45; }}
      .map-title {{ max-width: 290px; }}
      .map-title b, .map-legend b {{ font-size: 13px; }}
      .map-legend span {{ display: block; margin-top: 4px; }}
      .map-legend i {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 6px; }}
      .leaflet-control-layers {{ font-size: 12px; border: 0; border-radius: 10px; box-shadow: 0 4px 18px rgba(15,23,42,.18); }}
      .leaflet-control-layers-expanded {{ padding: 9px 12px; }}
      .leaflet-tooltip {{ border: 0; border-radius: 7px; padding: 5px 8px; box-shadow: 0 3px 12px rgba(15,23,42,.18); font-size: 11px; }}
      .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large {{ background: rgba(32, 106, 137, .22); }}
      .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {{ background: #176b87; color: white; font-weight: 700; }}
    </style></head><body><div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([25.5, 48.5], 4);
      const streets = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Tiles &copy; Esri', maxZoom: 18
      }}).addTo(map);
      const light = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Tiles &copy; Esri', maxZoom: 16
      }});
      const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Tiles &copy; Esri', maxZoom: 18
      }});
      const title = L.control({{position: 'topleft'}});
      title.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-title');
        el.innerHTML = '<b>中东能源资产与港口活动</b><br>点击点位查看详情；悬停显示名称。';
        return el;
      }};
      title.addTo(map);
      const legend = L.control({{position: 'bottomright'}});
      legend.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-legend');
        el.innerHTML = {legend_json};
        return el;
      }};
      legend.addTo(map);
      const assets = {marker_json};
      const ports = {port_json};
      const levelColors = {color_json};
      const assetLayer = L.markerClusterGroup({{showCoverageOnHover: false, maxClusterRadius: 34,
          disableClusteringAtZoom: 8, spiderfyOnMaxZoom: true}}).addTo(map);
      const portLayer = L.layerGroup().addTo(map);
      assets.forEach((asset) => {{
        const color = levelColors[asset.level] || '#64748b';
        L.circleMarker([asset.lat, asset.lon], {{
          radius: asset.level === 'field' ? 5.5 : 7,
          color: color,
          weight: 1.4,
          fillColor: color,
          fillOpacity: 0.88
        }}).bindTooltip(asset.name, {{direction: 'top', opacity: .95}})
          .bindPopup(asset.popup, {{maxWidth: 390}}).addTo(assetLayer);
      }});
      ports.forEach((port) => {{
        const radius = Math.min(12, 6 + Math.sqrt(Math.max(0, port.activity)) * 1.5);
        L.circleMarker([port.lat, port.lon], {{
          radius: radius, color: port.has_data ? '#064e5f' : '#64748b', weight: 2,
          fillColor: port.has_data ? '#20b8a5' : '#cbd5e1', fillOpacity: .9
        }}).bindTooltip(port.name, {{direction: 'top', opacity: .95}})
          .bindPopup(port.popup, {{maxWidth: 410}}).addTo(portLayer);
      }});
      const allPoints = ports.map((p) => [p.lat, p.lon]).concat(assets.map((a) => [a.lat, a.lon]));
      if (allPoints.length) map.fitBounds(L.latLngBounds(allPoints), {{padding: [36, 36], maxZoom: 5}});
      L.control.layers({{'英文街道图': streets, '浅色底图': light, '卫星影像': satellite}},
        {{'油气资产': assetLayer, '港口活动（点越大越活跃）': portLayer}}, {{collapsed: false}}).addTo(map);
    </script></body></html>
    """


st.markdown("""
<div class="hero">
  <h1>中东能源保供监测</h1>
  <p>油气资产、关键港口与每日航运活动｜资产来源审计 + IMF PortWatch 日度数据</p>
</div>
""", unsafe_allow_html=True)

country_options = sorted({str(asset["country"]) for asset in ASSETS})
level_options = list(LEVEL_LABELS)
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})
status_options = list(STATUS_LABELS)

with st.sidebar:
    st.markdown("### 监测视图")
    map_mode = st.radio("地图内容", ["港口与油气资产", "仅港口", "仅油气资产"],
                        horizontal=False, label_visibility="collapsed", key="map_mode")

    with st.expander("⚓ 港口筛选", expanded=True):
        selected_regions = st.multiselect(
            "水域（空选＝全部）", list(PORTWATCH.REGIONS), default=[],
            placeholder="全部五个水域", key="port_regions")
        port_search = st.text_input("搜索港口或国家", placeholder="例如 Fujairah / UAE",
                                    key="port_search").strip().lower()
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
        barrels_per_tonne = st.number_input(
            "原油当量（桶/吨）", min_value=5.0, max_value=9.0, value=7.33,
            step=0.01, help="只用于将油轮货物吨数换算为情景原油当量。",
            key="barrels_per_tonne")

    with st.expander("◉ 油气资产筛选", expanded=True):
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

    with st.expander("高级资产口径", expanded=False):
        selected_types = st.multiselect("资产类型（空选＝全部）", type_options, default=[],
                                        placeholder="全部类型", key="asset_types")
        selected_metrics = st.multiselect(
            "指标口径（空选＝全部）", metric_options, default=[],
            format_func=lambda key: METRIC_LABELS[key], placeholder="全部口径",
            key="asset_metrics")

    if st.button("刷新 PortWatch 缓存", width="stretch"):
        PORTWATCH.latest_date.clear()
        PORTWATCH.port_catalog.clear()
        PORTWATCH.daily_activity.clear()
        PORTWATCH.rolling_activity.clear()
        st.rerun()
    st.caption("筛选框留空表示全部。地图右上角可切换底图和数据图层。")

selected_region_set = set(selected_regions or PORTWATCH.REGIONS)
ports: list[dict] = []
port_error = None
if selected_day is not None and map_mode != "仅油气资产":
    try:
        catalog = [
            p for p in PORTWATCH.port_catalog()
            if p["region"] in selected_region_set
            and (not port_search or port_search in p["name"].lower()
                 or port_search in p["country"].lower())
        ]
        ids = tuple(p["portid"] for p in catalog)
        if ids:
            activity = PORTWATCH.daily_activity(selected_day, ids)
            rolling = PORTWATCH.rolling_activity(selected_day, ids, rolling_days)
            ports = PORTWATCH.decorate(catalog, activity, rolling)
    except Exception as exc:
        port_error = str(exc)

filtered = [
    asset for asset in ASSETS
    if (not selected_countries or asset["country"] in selected_countries)
    and (not selected_levels or asset["asset_level"] in selected_levels)
    and (not selected_types or asset["asset_type"] in selected_types)
    and (not selected_statuses or asset["operating_status"] in selected_statuses)
    and (not selected_metrics or asset["metric_type"] in selected_metrics)
    and (not values_only or asset["value"] is not None)
    and (not output_only or asset["is_daily_output"])
    and (not asset_search or asset_search in str(asset["name"]).lower()
         or asset_search in str(asset["name_cn"]).lower())
]
if map_mode == "仅港口":
    map_assets = []
else:
    map_assets = filtered
map_ports = [] if map_mode == "仅油气资产" else ports

port_rows = []
for port in ports:
    def ten_thousand(key: str):
        value = port.get(key)
        return None if value is None else round(value / 10000, 6)

    tanker_tonnes = port.get("handled_tanker")
    port_rows.append({
        "水域": port["region"], "国家": port["country"], "港口": port["name"],
        "PortWatch ID": port["portid"], "日期 UTC": selected_day.isoformat(),
        "油轮艘次/日": port.get("portcalls_tanker"),
        "油轮卸货 万吨/日": ten_thousand("import_tanker"),
        "油轮装货 万吨/日": ten_thousand("export_tanker"),
        "油轮装卸 万吨/日": ten_thousand("handled_tanker"),
        "油轮原油当量 万桶/日": (
            round(tanker_tonnes * barrels_per_tonne / 10000, 6)
            if tanker_tonnes is not None else None),
        f"{rolling_days}天油轮日均艘次": (
            round(port["avg_calls_tanker"], 3)
            if port.get("avg_calls_tanker") is not None else None),
        f"{rolling_days}天油轮日均装卸 万吨/日": ten_thousand("avg_handled_tanker"),
        f"{rolling_days}天油轮原油当量日均 万桶/日": (
            round(port["avg_handled_tanker"] * barrels_per_tonne / 10000, 6)
            if port.get("avg_handled_tanker") is not None else None),
        f"{rolling_days}天油轮有挂靠天数": port.get("tanker_positive_days"),
        "其他货轮艘次/日": port.get("portcalls_cargo"),
        "其他货轮装卸 万吨/日": ten_thousand("handled_cargo"),
        f"{rolling_days}天其他货轮日均艘次": (
            round(port["avg_calls_cargo"], 3)
            if port.get("avg_calls_cargo") is not None else None),
        f"{rolling_days}天其他货轮日均装卸 万吨/日": ten_thousand("avg_handled_cargo"),
        f"{rolling_days}天有效日期": port.get("observed_days"),
        "数据提示": (
            "有挂靠但估算货量为0，待核"
            if port.get("portcalls_tanker", 0) and tanker_tonnes == 0
            else "窗口有油轮挂靠但日均估算货量为0，待核"
            if (port.get("avg_calls_tanker") or 0) > 0 and port.get("avg_handled_tanker") == 0
            else "当日无挂靠，窗口内有挂靠"
            if port.get("portcalls_tanker") == 0 and (port.get("tanker_positive_days") or 0) > 0
            else ""),
        "纬度": port["lat"], "经度": port["lon"], "来源": PORTWATCH.SOURCE,
    })

asset_rows = [
    {
        "国家": asset["country"], "资产层级": asset["asset_level_label"],
        "层级路径": hierarchy_path(asset), "上级资产": asset["parent_asset"] or "—",
        "英文名称": asset["name"], "中文名称": asset["name_cn"],
        "资产类型": asset["asset_type"], "商品": asset["commodity_label"],
        "生产状态": asset["operating_status_label"], "状态截至": asset["operating_status_as_of"],
        "本层级日产量": daily_output_value(asset), "其他日量指标": other_daily_metric(asset),
        "指标口径": METRIC_LABELS[asset["metric_type"]], "数据日期": display_date(asset),
        "统计范围": asset["aggregation_scope"], "状态置信度": asset["operating_status_confidence"],
        "状态依据": asset["operating_status_basis"], "状态证据链接": asset["operating_status_evidence_url"],
        "坐标精度": asset["coordinate_precision"], "来源": asset["source"],
        "来源链接": asset["source_url"], "说明": asset["note"],
    }
    for asset in filtered
]

tab_map, tab_ports, tab_assets, tab_method = st.tabs(
    ["地图总览", "港口活动", "油气资产", "数据与方法"])

with tab_map:
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("地图油气资产", len(map_assets))
    m2.metric("地图港口", len(map_ports))
    m3.metric("当日有油轮挂靠", sum((p.get("portcalls_tanker") or 0) > 0 for p in map_ports))
    m4.metric(f"{rolling_days}天有油轮挂靠", sum((p.get("tanker_positive_days") or 0) > 0 for p in map_ports))
    st.caption("港口点大小按滚动窗口内油轮与其他货轮的日均挂靠数缩放；油气资产在低缩放级别自动聚合。")
    st.iframe(
        _map_html(map_assets, map_ports,
                  selected_day.isoformat() if selected_day else "无数据",
                  barrels_per_tonne),
        height=735,
    )

with tab_ports:
    st.subheader("港口日活动")
    if port_error:
        st.error(f"港口数据加载失败：{port_error}")
    elif port_rows:
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("筛选后港口", len(port_rows))
        p2.metric("当日油轮挂靠", sum((p.get("portcalls_tanker") or 0) > 0 for p in ports))
        p3.metric("当日其他货轮挂靠", sum((p.get("portcalls_cargo") or 0) > 0 for p in ports))
        p4.metric("需关注记录", sum(bool(row["数据提示"]) for row in port_rows))
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

with tab_assets:
    st.subheader("油气资产目录")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("筛选后资产", len(filtered))
    a2.metric("在产", sum(a["operating_status"] == "producing" for a in filtered))
    a3.metric("有日产量", sum(bool(a["is_daily_output"]) for a in filtered))
    a4.metric("状态待核", sum(a["operating_status"] in {"unknown", "historical_unverified"} for a in filtered))
    st.info("同一资产链上的单田与上级区块、油田群或特许区不能同时求和。")
    st.dataframe(asset_rows, width="stretch", hide_index=True, height=620,
                 column_config={
                     "状态证据链接": st.column_config.LinkColumn("状态证据"),
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
        "[每日活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0)"
    )
    st.warning(
        "PortWatch 以 AIS、船舶载重和吃水变化估算公吨货量。tanker 是船型分类，可能包含原油、"
        "成品油及其他液体货物。页面的万桶数是情景原油当量，不是分油种的实测港口吞吐量。"
        "单日零值只表示源表当日为零；有挂靠而估算货量为零的记录会单独标注。"
    )
    st.markdown(
        "**资产覆盖。** 目录收录公开命名的主要生产、开发或保留油气资产；生产状态带证据时点，"
        "不等于实时遥测。地图 popup 会显示当前资产及已登记上级的分层数值。"
    )
