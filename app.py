"""中东公开命名油气资产分层地图 DEMO。"""

from __future__ import annotations

import html
import importlib
import json

import streamlit as st
import streamlit.components.v1 as components

import field_catalog

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
        f'<div class="hierarchy-title">分层日产量（当前资产 → 上级）</div>'
        f'{_hierarchy_panel(asset)}'
        '<div class="row"><span>坐标精度</span>'
        f'<strong>{esc(asset["coordinate_precision"])}</strong></div>'
        f'<div class="status">状态：{esc(asset["status"])}</div>'
        f'<div class="basis">权益口径：{esc(asset["ownership_basis"])}</div>'
        f'<div class="basis">说明：{esc(asset["note"] or "公开命名资产；本层级数值未公开。")}</div>'
        f'<a class="source" href="{source_url}" target="_blank" rel="noopener">来源：{esc(asset["source"])}</a>'
        '</div>'
    )


def _map_html(assets: list[dict[str, object]]) -> str:
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
        el.innerHTML = '<b>中东公开命名油气资产</b><br>颜色区分资产层级；点击点位查看本层级及上级日产量。';
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
      const levelColors = {color_json};
      assets.forEach((asset) => {{
        const color = levelColors[asset.level] || '#64748b';
        L.circleMarker([asset.lat, asset.lon], {{
          radius: asset.level === 'field' ? 5.5 : 7,
          color: color,
          weight: 1.4,
          fillColor: color,
          fillOpacity: 0.88
        }}).bindPopup(asset.popup, {{maxWidth: 390}}).addTo(map);
      }});
    </script></body></html>
    """


st.title("中东公开命名油气资产地图 · 分层审计版")
st.caption(
    "资产分为单一油气田、油田群／综合体、区块、特许区、开发项目和开发区。"
    "popup按层级展示当前资产与已登记上级的日产量；产能、目标和项目增量单独显示。"
)

country_options = sorted({str(asset["country"]) for asset in ASSETS})
level_options = list(LEVEL_LABELS)
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})

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

filtered = [
    asset
    for asset in ASSETS
    if asset["country"] in selected_countries
    and asset["asset_level"] in selected_levels
    and asset["asset_type"] in selected_types
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
col1, col2, col3, col4 = st.columns(4)
col1.metric("已显示资产", f"{len(filtered)}")
col2.metric("有日产量记录", f"{daily_output_count}")
col3.metric("上级合计日产量", f"{aggregate_output_count}")
col4.metric("产能／目标等日量", f"{other_daily_count}")

unlocated_count = sum(
    asset["lat"] is None or asset["lon"] is None for asset in filtered
)
parented_count = sum(bool(asset["parent_asset"]) for asset in filtered)
st.caption(
    f"已建立父子关系：{parented_count} 条；日产量未披露：{unknown_count} 条；"
    f"待核验坐标、仅列数据表：{unlocated_count} 条。"
)

components.html(_map_html(filtered), height=690, scrolling=False)

st.info(
    "防重复规则：单田与上级区块／油田群／特许区的数值不能同时求和。"
    "日产量仅包括来源直报实际产量、来源年产量换算日均及明确标注的历史产量；"
    "产能、目标产能、增量产能和天然气项目能力在popup中另列，不计作日产量。"
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
        "状态": asset["status"],
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
