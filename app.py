import html
import json
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="中东油田地图 DEMO", page_icon="🛢️", layout="wide")

FIELDS = [
    {"country": "沙特阿拉伯", "name": "Ghawar（加瓦尔）", "daily": "约 3,800 千桶/日", "date": "2019-12-31", "lat": 25.40, "lon": 49.60},
    {"country": "沙特阿拉伯", "name": "Marjan（马尔詹）", "daily": "+300 千桶/日（新增产能）", "date": "2025-12-31", "lat": 27.40, "lon": 49.80},
    {"country": "伊朗", "name": "South Azadegan（南阿扎德甘）", "daily": "150 千桶/日", "date": "2025-01-15", "lat": 30.06, "lon": 48.23},
    {"country": "伊拉克", "name": "Rumaila（鲁迈拉）", "daily": "1,500 千桶/日（产能）", "date": "2023-08-01", "lat": 30.08, "lon": 47.43},
    {"country": "伊拉克", "name": "West Qurna-2（西古尔纳2期）", "daily": "460 千桶/日", "date": "2025-12-08", "lat": 30.96, "lon": 47.31},
    {"country": "阿联酋", "name": "Upper Zakum（上扎库姆）", "daily": "1,000 千桶/日（产能）", "date": "2025-07-04", "lat": 25.93, "lon": 53.10},
    {"country": "阿联酋", "name": "Umm Lulu（乌姆卢卢）", "daily": "约 230 千桶/日", "date": "2026-02-28", "lat": 25.30, "lon": 54.18},
    {"country": "科威特", "name": "Greater Burgan（大布尔干）", "daily": "约 1,600 千桶/日", "date": "2022-08-02", "lat": 29.00, "lon": 47.93},
    {"country": "卡塔尔", "name": "Al Shaheen（阿尔沙欣）", "daily": "300 千桶/日（产能）", "date": "2026-09-01", "lat": 26.10, "lon": 51.22},
    {"country": "阿曼", "name": "Mukhaizna（穆凯兹奈）", "daily": "约 120 千桶/日", "date": "2025-05-19", "lat": 19.34, "lon": 56.47},
    {"country": "叙利亚", "name": "Al-Omar（奥马尔）", "daily": "约 5 千桶/日", "date": "2026-05-01", "lat": 35.02, "lon": 40.25},
    {"country": "以色列", "name": "Heletz（赫莱兹）", "daily": "<0.1 千桶/日 / 已停产", "date": "2025-12-31", "lat": 31.60, "lon": 34.63},
]


def map_html(rows):
    points = []
    for row in rows:
        popup = (
            "<div style='min-width:210px;font-family:sans-serif'>"
            f"<b style='font-size:15px'>{html.escape(row['name'])}</b><br>"
            f"<span style='color:#64748b'>{html.escape(row['country'])}</span><hr>"
            f"<b>日产量：</b>{html.escape(row['daily'])}<br>"
            f"<b>数据日期：</b>{html.escape(row['date'])}</div>"
        )
        points.append({"lat": row["lat"], "lon": row["lon"], "popup": popup})
    payload = json.dumps(points, ensure_ascii=False)
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>
<style>html,body,#map{height:100%;margin:0}#map{background:#e8eef4;font-family:sans-serif}.map-title{background:white;padding:9px 11px;border-radius:8px;box-shadow:0 2px 10px #999;font-size:12px;line-height:1.45}.map-title b{font-size:14px}</style>
</head><body><div id='map'></div><script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script><script>
const map=L.map('map').setView([26,51.5],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{attribution:'© OpenStreetMap © CARTO',maxZoom:18}).addTo(map);
const title=L.control({position:'topleft'});title.onAdd=()=>{const e=L.DomUtil.create('div','map-title');e.innerHTML='<b>中东主要油田</b><br>点击红点查看日产量与日期';return e};title.addTo(map);
const points=__DATA__;
points.forEach(p=>L.circleMarker([p.lat,p.lon],{radius:6,color:'#991b1b',weight:1.5,fillColor:'#ef4444',fillOpacity:.95}).bindPopup(p.popup,{maxWidth:290}).addTo(map));
</script></body></html>""".replace("__DATA__", payload)

st.title("中东主要油田地图 · DEMO")
st.caption("红点为油田或油田群近似中心点；点击红点查看油田名称、日产量、数据日期。")
countries = sorted({row["country"] for row in FIELDS})
selected = st.multiselect("国家筛选", countries, default=countries)
shown = [row for row in FIELDS if row["country"] in selected]
components.html(map_html(shown), height=620, scrolling=False)
st.info("DEMO 数据保留公开资料口径；部分数值是产能、代理值或估计值，不等同于统一口径的实际产量。")
st.dataframe([
    {"国家": row["country"], "油田": row["name"], "日产量": row["daily"], "数据日期": row["date"]}
    for row in shown
], width="stretch", hide_index=True)
