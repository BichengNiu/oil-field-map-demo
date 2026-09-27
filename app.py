"""中东公开命名油气资产地图 DEMO。"""

from __future__ import annotations

import html
import json

import streamlit as st
import streamlit.components.v1 as components

from field_catalog import ASSETS


st.set_page_config(page_title="中东油气田地图 DEMO", page_icon="🛢️", layout="wide")

METRIC_LABELS = {
    "actual_output": "实际产量",
    "capacity": "产能",
    "oil_capacity": "原油产能",
    "target_capacity": "目标产能",
    "maximum_sustainable_capacity": "最大可持续产能",
    "historical_capacity": "历史产能",
    "historical_design_capacity": "历史设计产能",
    "historical_peak": "历史峰值",
    "historical_condensate_output": "历史凝析油产量",
    "incremental_capacity": "新增产能",
    "undisclosed": "未披露",
}


def display_value(asset: dict[str, object]) -> str:
    value = asset.get("value")
    unit = asset.get("unit")
    if value is None:
        return "未披露"
    return f"{value} {unit}" if unit else str(value)


def display_date(asset: dict[str, object]) -> str:
    return str(asset.get("data_date") or "未提供")


def _popup(asset: dict[str, object]) -> str:
    """生成点击红点后展示的中文信息卡。"""

    def esc(value: object) -> str:
        return html.escape(str(value))

    source_url = esc(asset["source_url"])
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{esc(asset["name"])}（{esc(asset["name_cn"])}）</div>'
        f'<div class="country">{esc(asset["country"])} · {esc(asset["asset_type"])} </div>'
        '<div class="row"><span>指标口径</span>'
        f'<strong>{esc(METRIC_LABELS[str(asset["metric_type"])])}</strong></div>'
        '<div class="row"><span>数值</span>'
        f'<strong>{esc(display_value(asset))}</strong></div>'
        '<div class="row"><span>数据日期</span>'
        f'<strong>{esc(display_date(asset))}</strong></div>'
        '<div class="row"><span>坐标精度</span>'
        f'<strong>{esc(asset["coordinate_precision"])}</strong></div>'
        f'<div class="status">状态：{esc(asset["status"])}</div>'
        f'<div class="basis">说明：{esc(asset["note"] or "公开命名资产；逐田数值未公开。")}</div>'
        f'<a class="source" href="{source_url}" target="_blank" rel="noopener">来源：{esc(asset["source"])}</a>'
        '</div>'
    )


def _map_html(assets: list[dict[str, object]]) -> str:
    markers = [
        {"lat": asset["lat"], "lon": asset["lon"], "popup": _popup(asset)}
        for asset in assets
    ]
    marker_json = json.dumps(markers, ensure_ascii=False).replace("</", "<\\/")
    return f"""
    <!doctype html><html lang="zh-CN"><head>
    <meta charset="utf-8" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
      html, body, #map {{ height: 100%; margin: 0; }}
      #map {{ background: #e8eef4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
      .leaflet-popup-content-wrapper {{ border-radius: 10px; box-shadow: 0 8px 24px rgba(15, 23, 42, .25); }}
      .leaflet-popup-content {{ margin: 13px 15px; min-width: 258px; }}
      .field-name {{ font-weight: 750; color: #0f172a; font-size: 14px; line-height: 1.35; margin-bottom: 3px; }}
      .country {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
      .row {{ display: flex; justify-content: space-between; gap: 14px; padding: 5px 0; border-top: 1px solid #e2e8f0; font-size: 12px; }}
      .row span, .basis, .status {{ color: #64748b; }}
      .row strong {{ color: #991b1b; text-align: right; }}
      .status, .basis {{ font-size: 11px; margin-top: 8px; line-height: 1.4; }}
      .source {{ display: block; color: #2563eb; font-size: 11px; margin-top: 8px; text-decoration: none; }}
      .map-title {{ background: rgba(255,255,255,.95); padding: 10px 12px; border-radius: 8px; box-shadow: 0 2px 10px rgba(15,23,42,.15); color: #0f172a; font-size: 12px; line-height: 1.5; max-width: 280px; }}
      .map-title b {{ font-size: 14px; }}
    </style></head><body><div id="map"></div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const map = L.map('map', {{zoomControl: true}}).setView([26.0, 51.5], 4);
      L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO', maxZoom: 18
      }}).addTo(map);
      const title = L.control({{position: 'topleft'}});
      title.onAdd = () => {{
        const el = L.DomUtil.create('div', 'map-title');
        el.innerHTML = '<b>中东公开命名油气资产</b><br>红点：单一油气田、项目或区块。点击查看口径、日期和来源。';
        return el;
      }};
      title.addTo(map);
      const assets = {marker_json};
      assets.forEach((asset) => {{
        L.circleMarker([asset.lat, asset.lon], {{
          radius: 5.5, color: '#991b1b', weight: 1.3, fillColor: '#ef4444', fillOpacity: 0.92
        }}).bindPopup(asset.popup, {{maxWidth: 340}}).addTo(map);
      }});
    </script></body></html>
    """


st.title("中东公开命名油气资产地图 · DEMO")
st.caption(
    "字段级目录：红点尽量对应单一油田/气田；“未披露”不以国家或油田群数据替代。"
    "数值严格标明实际产量、产能、目标或历史口径。"
)

country_options = sorted({str(asset["country"]) for asset in ASSETS})
type_options = sorted({str(asset["asset_type"]) for asset in ASSETS})
metric_options = sorted({str(asset["metric_type"]) for asset in ASSETS})

with st.sidebar:
    st.header("筛选")
    selected_countries = st.multiselect("国家", country_options, default=country_options)
    selected_types = st.multiselect("资产类型", type_options, default=type_options)
    selected_metrics = st.multiselect(
        "指标口径",
        metric_options,
        default=metric_options,
        format_func=lambda key: METRIC_LABELS[key],
    )
    values_only = st.checkbox("仅显示有公开字段级数值的资产", value=False)
    st.divider()
    st.caption("坐标为公开资料交叉核对后的近似中心点；弹窗明确标注该精度。")

filtered = [
    asset
    for asset in ASSETS
    if asset["country"] in selected_countries
    and asset["asset_type"] in selected_types
    and asset["metric_type"] in selected_metrics
    and (not values_only or asset["value"] is not None)
]

actual_count = sum(asset["metric_type"] == "actual_output" for asset in filtered)
numeric_count = sum(asset["value"] is not None for asset in filtered)
unknown_count = sum(asset["value"] is None for asset in filtered)
col1, col2, col3, col4 = st.columns(4)
col1.metric("已显示资产", f"{len(filtered)}")
col2.metric("有字段级公开数值", f"{numeric_count}")
col3.metric("实际产量口径", f"{actual_count}")
col4.metric("逐田值未公开", f"{unknown_count}")

components.html(_map_html(filtered), height=690, scrolling=False)

st.info(
    "使用说明：不同口径不可直接相加。`实际产量`为特定日期公开快照；`产能`、`目标产能`、"
    "`新增产能`和`历史峰值`仅用于资产能力监测，不等同于当前日产量。"
)

rows = [
    {
        "国家": asset["country"],
        "英文名称": asset["name"],
        "中文名称": asset["name_cn"],
        "资产类型": asset["asset_type"],
        "指标口径": METRIC_LABELS[asset["metric_type"]],
        "数值": display_value(asset),
        "数据日期": display_date(asset),
        "状态": asset["status"],
        "坐标精度": asset["coordinate_precision"],
        "来源": asset["source"],
        "说明": asset["note"],
    }
    for asset in filtered
]
st.subheader("字段级目录")
st.dataframe(rows, width="stretch", hide_index=True, height=480)

st.caption(
    "目录范围：公开命名的主要生产、开发或保留油气资产；不宣称覆盖所有历史探井或未商业化发现。"
    "来源链接见各点弹窗。"
)
