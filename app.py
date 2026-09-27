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
    {"country": "阿联酋", "name": "Upper Zakum（上扎库姆）", "daily": "约100万桶/日（≈13.7万吨/日）", "metric": "石油日产能", "date": "未提供（用户补充）", "lat": 25.93, "lon": 53.10},
    {"country": "阿联酋", "name": "SARB（Satah Al Razboot）/ Umm Lulu", "daily": "设计约10.5万桶/日（≈1.43万吨/日）；SARB/Umm Lulu/Nasr联合新增约27万桶/日", "metric": "石油设计产能/联合新增", "date": "未提供（用户补充）", "lat": 25.30, "lon": 54.18},
    {"country": "阿联酋", "name": "Bab（Murban Bab）", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 24.40, "lon": 54.70},
    {"country": "阿联酋", "name": "Bu Hasa", "daily": "65万桶/日（≈8.9万吨/日）", "metric": "石油日产量/产能", "date": "未提供（用户补充）", "lat": 23.00, "lon": 53.00},
    {"country": "阿联酋", "name": "South East Asset（Asab/Sahil/Shah/Qusahwira/Mender）", "daily": "Shah约7万桶/日（≈0.96万吨/日）；其余未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 23.20, "lon": 54.40},
    {"country": "阿联酋", "name": "North East Bab（NEB：Al Dabbiya / Rumaitha / Shanayel）", "daily": "NEB资产整体产能约11万桶/日（≈1.5万吨/日）", "metric": "石油整体产能", "date": "未提供（用户补充）", "lat": 24.20, "lon": 54.30},
    {"country": "阿联酋", "name": "Lower Zakum（下扎库姆）", "daily": "约42.5万桶/日（≈5.8万吨/日）", "metric": "石油日产能", "date": "未提供（用户补充）", "lat": 25.73, "lon": 53.20},
    {"country": "阿联酋", "name": "Umm Shaif（乌姆沙伊夫）", "daily": "约27.5万桶/日（≈3.75万吨/日）", "metric": "石油日产能", "date": "未提供（用户补充）", "lat": 25.50, "lon": 53.40},
    {"country": "阿联酋", "name": "Nasr（纳斯尔）", "daily": "约6.5万桶/日（≈0.89万吨/日）", "metric": "石油日产能", "date": "未提供（用户补充）", "lat": 25.60, "lon": 53.70},
    {"country": "阿联酋", "name": "Satah / Umm Al Dalkh", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 25.10, "lon": 53.50},
    {"country": "阿联酋", "name": "Abu Al Bukhoosh", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 25.00, "lon": 53.00},
    {"country": "阿联酋", "name": "Shah", "daily": "天然气处理约14.5–18.5亿立方英尺/日", "metric": "天然气处理量", "date": "未提供（用户补充）", "lat": 23.10, "lon": 53.90},
    {"country": "阿联酋", "name": "Bab Gas Cap", "daily": "目标15亿标准立方英尺/日", "metric": "天然气目标产能", "date": "未提供（用户补充）", "lat": 24.40, "lon": 54.70},
    {"country": "阿联酋", "name": "Ruwais Diyab非常规天然气区块", "daily": "未公开", "metric": "天然气产量/产能", "date": "未提供（用户补充）", "lat": 24.10, "lon": 52.60},
    {"country": "阿联酋", "name": "Hail / Ghasha / Dalma / Satah", "daily": "目标天然气15亿scf/d + 凝析油及原油超12万桶油当量/日", "metric": "油气综合目标", "date": "未提供（用户补充）", "lat": 25.30, "lon": 52.90},
    {"country": "阿联酋", "name": "Haliba", "daily": "早期生产阶段峰值约2.1万桶/日（≈0.29万吨/日）", "metric": "石油日产量峰值", "date": "未提供（用户补充）", "lat": 23.00, "lon": 53.80},
    {"country": "阿联酋", "name": "Bu Haseer（Offshore Concession）", "daily": "目标日产能1.5万桶/日（≈0.20万吨/日）", "metric": "石油目标产能", "date": "未提供（用户补充）", "lat": 24.80, "lon": 52.90},
    {"country": "阿联酋", "name": "Belbazem区块（Belbazem / Umm Al Salsal / Umm Al Dholou）", "daily": "达产约4.5万桶/日（≈0.61万吨/日）+2700万scf/d伴生气", "metric": "石油产能+伴生气", "date": "未提供（用户补充）", "lat": 24.40, "lon": 53.00},
    {"country": "阿联酋", "name": "Arzanah（Offshore Concession）", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 24.20, "lon": 53.30},
    {"country": "阿联酋", "name": "Nahaidiin / Bin Hadi / Gezira（Land Zone）", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 24.40, "lon": 54.30},
    {"country": "阿联酋", "name": "Muhaymat / Sila（Water Zone）", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 24.20, "lon": 52.90},
    {"country": "阿联酋", "name": "Mubarraz / Umm Al-Anbar / Neewat Al-Ghalan", "daily": "合计约2.4万桶/日（≈0.33万吨/日）", "metric": "石油合计日产量", "date": "未提供（用户补充）", "lat": 24.20, "lon": 53.40},
    {"country": "阿联酋", "name": "Hail（ADOC特许权）", "daily": "早期峰值约2.1万桶/日（≈0.29万吨/日）", "metric": "石油日产量峰值", "date": "未提供（用户补充）", "lat": 25.20, "lon": 53.10},
    {"country": "阿联酋", "name": "Bunduq", "daily": "未公开", "metric": "石油日产量", "date": "未提供（用户补充）", "lat": 24.70, "lon": 52.90},
    {"country": "阿联酋", "name": "Fateh / South West Fateh / Rashid / Falah / Jalilah", "daily": "Fateh历史峰值约30万桶/日，现已衰减", "metric": "石油历史峰值", "date": "未提供（用户补充）", "lat": 25.30, "lon": 55.10},
    {"country": "阿联酋", "name": "Margham", "daily": "凝析油约2.5万桶/日（2010年数据）", "metric": "凝析油日产量", "date": "2010（用户补充）", "lat": 25.00, "lon": 55.60},
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
            f"<b>{html.escape(row.get('metric', '日产量/产能'))}：</b>{html.escape(row['daily'])}<br>"
            f"<b>数据日期：</b>{html.escape(row['date'])}</div>"
        )
        points.append({"lat": row["lat"], "lon": row["lon"], "popup": popup})
    payload = json.dumps(points, ensure_ascii=False)
    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'>
<style>html,body,#map{height:100%;margin:0}#map{background:#e8eef4;font-family:sans-serif}.map-title{background:white;padding:9px 11px;border-radius:8px;box-shadow:0 2px 10px #999;font-size:12px;line-height:1.45}.map-title b{font-size:14px}</style>
</head><body><div id='map'></div><script src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'></script><script>
const map=L.map('map').setView([26,51.5],4);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap',maxZoom:18}).addTo(map);
const title=L.control({position:'topleft'});title.onAdd=()=>{const e=L.DomUtil.create('div','map-title');e.innerHTML='<b>中东油气资产</b><br>点击红点查看指标与日期';return e};title.addTo(map);
const points=__DATA__;
points.forEach(p=>L.circleMarker([p.lat,p.lon],{radius:6,color:'#991b1b',weight:1.5,fillColor:'#ef4444',fillOpacity:.95}).bindPopup(p.popup,{maxWidth:290}).addTo(map));
</script></body></html>""".replace("__DATA__", payload)

st.title("中东主要油气田地图 · DEMO")
st.caption("红点为油田、油田群或天然气资产近似中心点；点击红点查看名称、指标和数据日期。")
countries = sorted({row["country"] for row in FIELDS})
selected = st.multiselect("国家筛选", countries, default=countries)
shown = [row for row in FIELDS if row["country"] in selected]
components.html(map_html(shown), height=620, scrolling=False)
st.info("DEMO 数据保留公开资料口径；阿联酋新增资产的日期由用户补充表未提供，已标注“未提供（用户补充）”；天然气指标单独标注，不与石油日产量混用。")
st.dataframe([
    {"国家": row["country"], "油田": row["name"], "指标": row.get("metric", "日产量/产能"), "数值": row["daily"], "数据日期": row["date"]}
    for row in shown
], width="stretch", hide_index=True)
