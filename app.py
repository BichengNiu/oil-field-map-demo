"""中东公开命名油气资产分层地图 DEMO。"""

from __future__ import annotations

import html
import importlib
import json
import csv
import io
from datetime import date

import streamlit as st
import streamlit.components.v1 as components

import field_catalog
import portwatch

# Streamlit 的热重载会重跑此文件；显式重新读取目录模块以同步仓库中的数据修订。
CATALOG = importlib.reload(field_catalog)
ASSETS = CATALOG.ASSETS


st.set_page_config(page_title="中东油气田地图 DEMO", page_icon="🛢️", layout="wide")

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
        f'<a class="source" href="{esc(portwatch.SOURCE)}" target="_blank" rel="noopener">IMF PortWatch 数据与方法</a>'
        '</div>'
    )


def _map_html(assets: list[dict[str, object]], ports: list[dict],
              day: str, barrels_per_tonne: float) -> str:
    markers = [
        {
            "lat": asset["lat"],
            "lon": asset["lon"],
            "level": asset["asset_level"],
            "popup": _popup(asset),
        }
        for asset in assets
        if asset["lat"] is not None and asset["lon"] is not None
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    port_json = json.dumps([
        {"lat": port["lat"], "lon": port["lon"], "popup": _port_popup(port, day, barrels_per_tonne),
         "has_data": port["has_data"]} for port in ports
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
      .leaflet-control-layers {{ font-size: 12px; }}
    </style></head><body><div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([25.5, 48.5], 4);
      L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', maxZoom: 18
      }}).addTo(map);
      const title = L.control({{position: 'topleft'}});
      title.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-title');
        el.innerHTML = '<b>中东油气资产与港口活动</b><br>圆点为油气资产，方块为港口；右上角可切换图层。';
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
      const assetLayer = L.layerGroup().addTo(map);
      const portLayer = L.layerGroup().addTo(map);
      assets.forEach((asset) => {{
        const color = levelColors[asset.level] || '#64748b';
        L.circleMarker([asset.lat, asset.lon], {{
          radius: asset.level === 'field' ? 5.5 : 7,
          color: color,
          weight: 1.4,
          fillColor: color,
          fillOpacity: 0.88
        }}).bindPopup(asset.popup, {{maxWidth: 390}}).addTo(assetLayer);
      }});
      ports.forEach((port) => {{
        L.circleMarker([port.lat, port.lon], {{
          radius: 7, color: port.has_data ? '#0f766e' : '#64748b', weight: 2,
          fillColor: port.has_data ? '#14b8a6' : '#cbd5e1', fillOpacity: .95
        }}).bindPopup(port.popup, {{maxWidth: 410}}).addTo(portLayer);
      }});
      L.control.layers(null, {{'油气资产': assetLayer, '港口（青色有数据；灰色缺报）': portLayer}},
                       {{collapsed: false}}).addTo(map);
    </script></body></html>
    """


st.title("中东公开命名油气资产地图 · 分层审计版")
st.caption(
    "资产分为单一油气田、油田群／综合体、区块、特许区、开发项目和开发区。"
    "popup按层级展示当前资产与已登记上级的日产量；产能、目标和项目增量单独显示。"
    "生产状态带截至日期、置信度与证据链接，不能视为实时遥测。"
)

country_options = sorted({str(asset["country"]) for asset in ASSETS})
level_options = list(LEVEL_LABELS)
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})
status_options = list(STATUS_LABELS)

with st.sidebar:
    st.header("筛选")
    selected_countries = st.multiselect("国家", country_options, default=country_options)
    selected_levels = st.multiselect(
        "资产层级",
        level_options,
        default=level_options,
        format_func=lambda key: LEVEL_LABELS[key],
    )
    selected_types = st.multiselect("资产类型", type_options, default=type_options)
    selected_statuses = st.multiselect(
        "生产状态",
        status_options,
        default=status_options,
        format_func=lambda key: STATUS_LABELS[key],
    )
    selected_metrics = st.multiselect(
        "指标口径",
        metric_options,
        default=metric_options,
        format_func=lambda key: METRIC_LABELS[key],
    )
    values_only = st.checkbox("仅显示有公开资产级数值的资产", value=False)
    output_only = st.checkbox("仅显示有日产量的资产", value=False)
    st.divider()
    st.caption(
        "popup中的上级数据不受筛选器隐藏：即使只筛选单田，仍会展示其所属区块／"
        "油田群／特许区的已披露日量。无坐标资产保留在下方数据表。"
    )
    st.divider()
    st.header("港口活动 · IMF PortWatch")
    selected_regions = st.multiselect("附近水域", list(portwatch.REGIONS),
                                      default=list(portwatch.REGIONS))
    try:
        newest_day = portwatch.latest_date()
        if st.button("刷新港口数据缓存"):
            portwatch.latest_date.clear()
            portwatch.port_catalog.clear()
            portwatch.daily_activity.clear()
            portwatch.rolling_activity.clear()
            st.rerun()
        selected_day = st.date_input("统计日期（UTC）", value=newest_day,
                                     min_value=date(2019, 1, 1), max_value=newest_day)
        st.caption(f"源站最新可用日期：{newest_day.isoformat()}")
    except Exception as exc:
        newest_day = selected_day = None
        st.warning(f"PortWatch 暂时不可用：{exc}")
    barrels_per_tonne = st.number_input("原油当量换算：桶/吨", min_value=5.0,
                                        max_value=9.0, value=7.33, step=0.01,
                                        help="仅供对比的假设系数；油轮货物并非全部原油。")
    rolling_days = st.selectbox("滚动日均窗口", [7, 30], index=0,
                                help="保留原始单日值，另列过去 7 或 30 个自然日的日均。")

ports = []
if selected_day is not None and selected_regions:
    try:
        catalog = [p for p in portwatch.port_catalog() if p["region"] in selected_regions]
        ids = tuple(p["portid"] for p in catalog)
        activity = portwatch.daily_activity(selected_day, ids)
        rolling = portwatch.rolling_activity(selected_day, ids, rolling_days)
        ports = portwatch.decorate(catalog, activity, rolling)
    except Exception as exc:
        st.warning(f"港口数据加载失败，油气资产图仍可使用：{exc}")

filtered = [
    asset
    for asset in ASSETS
    if asset["country"] in selected_countries
    and asset["asset_level"] in selected_levels
    and asset["asset_type"] in selected_types
    and asset["operating_status"] in selected_statuses
    and asset["metric_type"] in selected_metrics
    and (not values_only or asset["value"] is not None)
    and (not output_only or asset["is_daily_output"])
]

daily_output_count = sum(bool(asset["is_daily_output"]) for asset in filtered)
aggregate_output_count = sum(
    bool(asset["is_daily_output"]) and asset["asset_level"] != "field"
    for asset in filtered
)
other_daily_count = sum(
    asset["value"] is not None and not asset["is_daily_output"] for asset in filtered
)
unknown_count = sum(asset["value"] is None for asset in filtered)
producing_count = sum(asset["operating_status"] == "producing" for asset in filtered)
status_pending_count = sum(
    asset["operating_status"] in {"unknown", "historical_unverified"} for asset in filtered
)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("已显示资产", f"{len(filtered)}")
col2.metric("在产（带时点）", f"{producing_count}")
col3.metric("状态待核", f"{status_pending_count}")
col4.metric("有日产量记录", f"{daily_output_count}")
col5.metric("产能／目标等日量", f"{other_daily_count}")

unlocated_count = sum(
    asset["lat"] is None or asset["lon"] is None for asset in filtered
)
parented_count = sum(bool(asset["parent_asset"]) for asset in filtered)
st.caption(
    f"已建立父子关系：{parented_count} 条；日产量未披露：{unknown_count} 条；"
    f"待核验坐标、仅列数据表：{unlocated_count} 条。"
)

components.html(_map_html(filtered, ports, selected_day.isoformat() if selected_day else "无数据",
                          barrels_per_tonne), height=690, scrolling=False)

st.subheader("港口日活动")
st.caption(
    "覆盖上述五个自定义地理框内的全部 PortWatch 港口，范围以港口点位判定；"
    "不包括 PortWatch 未收录的码头。油轮与其他货轮分别列示，装卸合计为双向货量。"
    "单日的 0 表示该日源站未观测到对应挂靠或估算货量为 0，不代表港口长期停运。"
    "滚动日均只有在窗口每一天都有源记录时才计算。"
)
if ports:
    port_rows = []
    for port in ports:
        def ten_thousand(key):
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
            "油轮载货原油当量估算 万桶/日": (
                round(tanker_tonnes * barrels_per_tonne / 10000, 6)
                if tanker_tonnes is not None else None),
            f"过去{rolling_days}天油轮日均艘次": (
                round(port["avg_calls_tanker"], 3)
                if port.get("avg_calls_tanker") is not None else None),
            f"过去{rolling_days}天油轮日均装卸 万吨/日": ten_thousand("avg_handled_tanker"),
            f"过去{rolling_days}天油轮原油当量日均 万桶/日": (
                round(port["avg_handled_tanker"] * barrels_per_tonne / 10000, 6)
                if port.get("avg_handled_tanker") is not None else None),
            f"过去{rolling_days}天油轮有挂靠天数": port.get("tanker_positive_days"),
            "其他货轮艘次/日": port.get("portcalls_cargo"),
            "其他货轮卸货 万吨/日": ten_thousand("import_cargo"),
            "其他货轮装货 万吨/日": ten_thousand("export_cargo"),
            "其他货轮装卸 万吨/日": ten_thousand("handled_cargo"),
            f"过去{rolling_days}天其他货轮日均艘次": (
                round(port["avg_calls_cargo"], 3)
                if port.get("avg_calls_cargo") is not None else None),
            f"过去{rolling_days}天其他货轮日均装卸 万吨/日": ten_thousand("avg_handled_cargo"),
            f"过去{rolling_days}天其他货轮有挂靠天数": port.get("cargo_positive_days"),
            f"过去{rolling_days}天有效日期": port.get("observed_days"),
            "数据状态": "有记录" if port["has_data"] else "当日缺报",
            "油轮数据提示": (
                "有挂靠但估算货量为0，待核" if port.get("portcalls_tanker", 0) and tanker_tonnes == 0
                else "窗口有油轮挂靠但日均估算货量为0，待核"
                if (port.get("avg_calls_tanker") or 0) > 0 and port.get("avg_handled_tanker") == 0
                else "当日无挂靠，窗口内有挂靠" if port.get("portcalls_tanker") == 0
                and (port.get("tanker_positive_days") or 0) > 0
                else ""),
            "纬度": port["lat"], "经度": port["lon"],
            "来源": portwatch.SOURCE,
        })
    c1, c2, c3 = st.columns(3)
    c1.metric("PortWatch 港口", len(ports))
    c2.metric("当日油轮挂靠为零", sum(p.get("portcalls_tanker") == 0 for p in ports))
    c3.metric(f"过去{rolling_days}天有油轮挂靠", sum((p.get("tanker_positive_days") or 0) > 0 for p in ports))
    st.dataframe(port_rows, width="stretch", hide_index=True, height=430)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=port_rows[0].keys())
    writer.writeheader()
    writer.writerows(port_rows)
    st.download_button("下载所选港口 CSV", buffer.getvalue().encode("utf-8-sig"),
                       file_name=f"portwatch_ports_{selected_day.isoformat()}.csv",
                       mime="text/csv")
else:
    st.info("所选范围暂无可显示的港口，或 PortWatch 服务暂时不可用。")
with st.expander("港口覆盖范围与数据口径"):
    st.write("“附近”按港口中心坐标落入以下经纬度框判定；交叠位置按表中顺序归属。")
    st.dataframe([
        {"水域": name, "南界": bounds[0], "北界": bounds[1],
         "西界": bounds[2], "东界": bounds[3]}
        for name, bounds in portwatch.REGIONS.items()
    ], hide_index=True, width="stretch")
    st.markdown(
        f"[IMF PortWatch 方法说明]({portwatch.SOURCE}) · "
        "[港口点位 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports/FeatureServer/1) · "
        "[每日活动 API](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0)"
    )
    st.write("PortWatch 以 AIS 和船舶吃水变化估算公吨货量；其 tanker 为船型分类，无法仅凭该列识别原油。"
             "“原油当量万桶”按用户可调系数换算，属于情景估算。真实分油种的港口日桶数需另接港口或商业 AIS 数据。"
             "货轮 cargo 为集装箱、干散、杂货及滚装等船型合计，不含 tanker。")

st.info(
    "防重复规则：单田与上级区块／油田群／特许区的数值不能同时求和。"
    "日产量仅包括来源直报实际产量、来源年产量换算日均及明确标注的历史产量；"
    "产能、目标产能、增量产能和天然气项目能力在popup中另列，不计作日产量。"
    "“在产”表示截至所列证据日期可核实，不代表此刻连续运行。"
)

rows = [
    {
        "国家": asset["country"],
        "资产层级": asset["asset_level_label"],
        "层级路径": hierarchy_path(asset),
        "上级资产": asset["parent_asset"] or "—",
        "英文名称": asset["name"],
        "中文名称": asset["name_cn"],
        "资产类型": asset["asset_type"],
        "商品": asset["commodity_label"],
        "统计范围": asset["aggregation_scope"],
        "权益口径": asset["ownership_basis"],
        "本层级日产量": daily_output_value(asset),
        "其他日量指标": other_daily_metric(asset),
        "指标口径": METRIC_LABELS[asset["metric_type"]],
        "数据日期": display_date(asset),
        "生产状态": asset["operating_status_label"],
        "状态截至": asset["operating_status_as_of"],
        "状态置信度": asset["operating_status_confidence"],
        "状态审计结果": asset["status_audit_result"],
        "状态依据": asset["operating_status_basis"],
        "状态证据链接": asset["operating_status_evidence_url"],
        "原始状态说明": asset["status"],
        "坐标精度": asset["coordinate_precision"],
        "来源": asset["source"],
        "来源链接": asset["source_url"],
        "说明": asset["note"],
    }
    for asset in filtered
]
st.subheader("分层资产数据表")
st.dataframe(rows, width="stretch", hide_index=True, height=520)

st.caption(
    "目录范围：公开命名的主要生产、开发或保留油气资产；不宣称覆盖全部历史探井或未商业化发现。"
    "任何合计分析都应先在层级路径中选择一个互斥层级，避免父子资产重复。"
)
