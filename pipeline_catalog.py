"""Read-only pipeline evidence and escaped popup content."""
from datetime import date
from html import escape
import math
from urllib.parse import urlsplit

import data_store

DOCUMENT = "data/oil_pipelines.geojson"
STATUSES = {
    "operating": "运行中", "construction": "建设中", "proposed": "规划中",
    "idle": "闲置", "mothballed": "封存", "retired": "退役",
    "cancelled": "取消", "shelved": "搁置",
}
COUNTRY_NAMES = {
    "Saudi Arabia": "沙特阿拉伯", "Iraq": "伊拉克", "Iran": "伊朗",
    "United Arab Emirates": "阿联酋", "Egypt": "埃及", "Oman": "阿曼",
    "Kuwait": "科威特", "Qatar": "卡塔尔", "Yemen": "也门", "Syria": "叙利亚",
    "Turkey": "土耳其", "Türkiye": "土耳其", "Israel": "以色列", "Jordan": "约旦",
    "Lebanon": "黎巴嫩", "Bahrain": "巴林", "Azerbaijan": "阿塞拜疆", "Georgia": "格鲁吉亚",
    "Libya": "利比亚", "Palestine": "巴勒斯坦",
}
ACCURACY = {
    "very high (within meters)": "源路线精度：米级",
    "high": "源路线精度：高", "medium": "源路线精度：中",
    "low": "源路线精度：低", "very low (straight line/schematic)": "源路线为直线或示意",
}


def validate(document):
    if document.get("type") != "FeatureCollection" or not document.get("features"):
        raise ValueError("输油管线快照为空或格式错误")
    metadata = document["metadata"]
    if metadata.get("license") != "CC BY 4.0" or len(metadata.get("source_sha256", "")) != 64:
        raise ValueError("输油管线快照缺少许可或来源校验信息")
    seen = set()
    for feature in document["features"]:
        p, geometry = feature["properties"], feature["geometry"]
        if p["project_id"] in seen or p.get("fuel") != "Oil" or p.get("status") not in STATUSES:
            raise ValueError("输油管线分段重复、类型或状态无效")
        seen.add(p["project_id"])
        if p.get("updated_at"):
            date.fromisoformat(p["updated_at"])
        url = urlsplit(p["source_url"])
        if url.scheme != "https" or not (url.hostname == "www.gem.wiki" or p["source_url"] == metadata["source_url"]):
            raise ValueError("输油管线来源链接无效")
        if geometry["type"] not in ("LineString", "MultiLineString"):
            raise ValueError("输油管线必须为线几何")
        lines = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
        if not lines:
            raise ValueError("输油管线路线为空")
        for line in lines:
            if len(line) < 2:
                raise ValueError("输油管线路线点不足")
            for lon, lat in line:
                if not all(math.isfinite(x) for x in (lon, lat)) or not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    raise ValueError("输油管线坐标超出范围")
    return document


def load():
    return validate(data_store.read_json(DOCUMENT))


def popup(p):
    def text(value):
        return escape(str(value if value not in (None, "", "--") else "未披露"))
    capacity = p.get("capacity")
    unit = {"bpd": "桶/日", "mtpa": "百万吨/年"}.get(p.get("capacity_unit"), p.get("capacity_unit") or "")
    capacity_text = f"{capacity} {unit}" if capacity not in (None, "", "--") else None
    rows = [
        ("GEM编号", p["project_id"]),
        ("分段", p.get("segment")),
        ("国家/地区", "、".join(COUNTRY_NAMES.get(x, x) for x in p["countries"])),
        ("起点", p.get("start")), ("终点", p.get("end")),
        ("资料记载状态", STATUSES[p["status"]] + "（非实时）"),
        ("公开运力", capacity_text), ("资料更新日", p.get("updated_at")),
        ("路线", (ACCURACY.get(p.get("route_accuracy"), p.get("route_accuracy")) or "源精度未披露") + "；地图已简化约0.003°"),
    ]
    return (
        f'<div class="field-name">{text(p["name"])}</div>'
        + (f'<div class="country">{text(p["name_en"])}</div>' if p["name"] != p["name_en"] else "")
        + "".join(f'<div class="row"><span>{label}</span><strong>{text(value)}</strong></div>' for label, value in rows)
        + f'<a class="source" href="{escape(p["source_url"], quote=True)}" target="_blank" rel="noopener">Global Energy Monitor · 管线资料</a>'
        + '<a class="source" href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0 · 路线经筛选及简化</a>'
    )
