"""Pure HTML cards and asset labels used by the map, tables, and report."""

from __future__ import annotations

import html

import ais as AIS
import field_catalog as CATALOG
import portwatch as PORTWATCH
from asset_values import display_value
from portwatch_records import SHIP_TYPE_LABELS

METRIC_LABELS = {
    "estimated_daily_average": "估算期间日均（公布总量×份额）",
    "actual_output": "来源直报实际产量",
    "estimated_output": "来源转述估计产量",
    "production_acceptance_test": "开发生产验收测试（非持续日产量）",
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

OUTPUT_METRIC_TYPES = CATALOG.OUTPUT_METRIC_TYPES
ASSET_INDEX = {(a["country"], a["name"]): a for a in CATALOG.ASSETS}


def _esc(value: object) -> str:
    return html.escape(str(value))


def extra_measurements(asset: dict) -> str:
    return (
        "；".join(
            f"{CATALOG.COMMODITY_LABELS[m['commodity']]} {m['value']} {m['unit']}"
            f"（{METRIC_LABELS[m['metric_type']]}，{m['data_date']}；{m['basis']}）"
            for m in asset.get("additional_measurements", [])
        )
        or "未披露"
    )


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
    return " → ".join(f"{node['asset_level_label']}：{node['name']}" for node in chain)


def _hierarchy_panel(asset: dict[str, object]) -> str:
    cards: list[str] = []
    for node in hierarchy_chain(asset):
        output = daily_output_value(node)
        metric_type = str(node["metric_type"])
        output_detail = (
            f"{METRIC_LABELS[metric_type]} · {display_date(node)}"
            if output != "未披露"
            else "本层级实际／历史日均未披露"
        )
        other = other_daily_metric(node)
        other_html = (
            f'<div class="other-metric">{_esc(other)} · {_esc(display_date(node))}</div>'
            if other != "—"
            else ""
        )
        cards.append(
            '<div class="level-metric">'
            f'<div class="level-head"><span>{_esc(node["asset_level_label"])}</span>'
            f"<b>{_esc(node['name'])}</b></div>"
            f'<div class="output-line"><span>日产量</span><strong>{_esc(output)}</strong></div>'
            f'<div class="metric-detail">{_esc(output_detail)}</div>'
            f"{other_html}"
            "</div>"
        )
    return "".join(cards)


def _public_metadata_panel(asset: dict) -> str:
    reference = asset.get("public_metadata")
    if not reference:
        return ""
    rows = "".join(
        f'<div class="row"><span>{label}</span><strong>{_esc(reference[key])}</strong></div>'
        for key, label in (
            ("operator", "运营商（目录参考）"),
            ("owners", "权益持有人（目录参考）"),
            ("discoveryYear", "发现年（目录参考）"),
            ("productionStartYear", "商业投产年（目录参考）"),
        )
        if reference.get(key) is not None
    )
    return (
        f'<div class="hierarchy-title">公开目录背景（{_esc(reference["release"])}）</div>'
        + rows
        + '<div class="basis">二手目录参考；投产年不证明当前在产，运营商与权益可能后续变更。'
        '参考点精度未保留，不代表核验油田中心或井位。</div>'
        + f'<a class="source" href="{_esc(reference["source_url"])}" target="_blank" rel="noopener">'
        f'Global Energy Monitor · CC BY 4.0 · {_esc(reference["unitId"])}</a>'
    )


def _historical_production_panel(asset: dict) -> str:
    records = asset.get("gem_historical_production", [])
    if not records:
        return ""
    lines = []
    for row in records:
        refs = "、".join(
            f'<a href="{_esc(url)}" target="_blank" rel="noopener">来源</a>'
            for url in dict.fromkeys(row["source_urls"])
        ) or "未提供行级来源链接"
        lines.append(
            f'<div class="basis">{row["year"]}年：'
            f'{row["quantity_million_barrels_year"]:g} 百万桶，'
            f'换算 {row["derived_daily_thousand_barrels"]:g} 千桶/日；{refs}</div>'
        )
    latest = max(records, key=lambda row: row["year"])
    return (
        '<div class="hierarchy-title">历史原油年产量（不是当前产量）</div>'
        + "".join(lines)
        + '<div class="basis">日均换算 = 百万桶/年 × 1,000 ÷ 当年日数；'
        f'逐田原表版本：<a href="{_esc(latest["revision_url"])}" target="_blank" rel="noopener">'
        'GEM Wiki</a> · <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/" '
        'target="_blank" rel="noopener">CC BY-NC-SA 4.0</a> · 归属 Global Energy Monitor。'
        '底层引文链接按每条记录列示。</div>'
    )


def asset_popup(asset: dict[str, object]) -> str:
    """生成分层中文信息卡；逐层列示当前资产及其上级的日产量。"""

    source_url = _esc(asset["source_url"])
    status_source_url = _esc(asset["operating_status_evidence_url"])
    coordinate_source_url = asset.get("coordinate_source_url")
    coordinate_source_html = (
        f'<a class="source" href="{_esc(coordinate_source_url)}" target="_blank" rel="noopener">'
        f"坐标来源：{_esc(asset['coordinate_source'])}</a>"
        if coordinate_source_url
        else f'<div class="basis">坐标来源：{_esc(asset["coordinate_source"])}</div>'
    )
    parent = asset.get("parent_asset") or "无已登记上级"
    constituents = "、".join(asset.get("constituent_assets") or []) or "—"
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{_esc(asset["name"])}（{_esc(asset["name_cn"])}）</div>'
        f'<div class="country">{_esc("、".join(asset["countries"]))} · {_esc(asset["asset_type"])}</div>'
        '<div class="row"><span>资产层级</span>'
        f"<strong>{_esc(asset['asset_level_label'])}</strong></div>"
        '<div class="row"><span>地图角色</span>'
        f"<strong>{_esc(asset['map_role_label'])}</strong></div>"
        '<div class="row"><span>上级资产</span>'
        f"<strong>{_esc(parent)}</strong></div>"
        '<div class="row"><span>组成资产</span>'
        f"<strong>{_esc(constituents)}</strong></div>"
        '<div class="row"><span>汇总规则</span>'
        f"<strong>{_esc(asset['rollup_policy'])}</strong></div>"
        '<div class="row"><span>统计范围</span>'
        f"<strong>{_esc(asset['aggregation_scope'])}</strong></div>"
        '<div class="row"><span>商品</span>'
        f"<strong>{_esc(asset['commodity_label'])}</strong></div>"
        '<div class="row"><span>生产状态</span>'
        f"<strong>{_esc(asset['operating_status_label'])}</strong></div>"
        '<div class="row"><span>状态截至</span>'
        f"<strong>{_esc(asset['operating_status_as_of'])}</strong></div>"
        '<div class="row"><span>状态置信度</span>'
        f"<strong>{_esc(asset['operating_status_confidence'])}</strong></div>"
        f'<div class="hierarchy-title">分层日产量（当前资产 → 上级）</div>'
        f"{_hierarchy_panel(asset)}"
        '<div class="row"><span>坐标精度</span>'
        f"<strong>{_esc(asset['map_coordinate_precision'])}</strong></div>"
        '<div class="row"><span>定位属性</span>'
        f"<strong>{'区域/设施代理点' if asset.get('map_is_proxy') else '资产点位'}</strong></div>"
        f"{coordinate_source_html}"
        f'<div class="status">原始状态说明：{_esc(asset["status"])}</div>'
        f'<div class="basis">状态依据：{_esc(asset["operating_status_basis"])}</div>'
        f'<div class="basis">权益口径：{_esc(asset["ownership_basis"])}</div>'
        f'<div class="basis">其他商品指标：{_esc(extra_measurements(asset))}</div>'
        f'<div class="basis">数据时效：{_esc(asset["freshness_note"])}</div>'
        f'<div class="basis">数值复核：{_esc(asset["numeric_audit"])}</div>'
        f"{_historical_production_panel(asset)}"
        f"{_public_metadata_panel(asset)}"
        f'<div class="basis">说明：{_esc(asset["note"] or "公开命名资产；本层级数值未公开。")}</div>'
        f'<a class="source" href="{status_source_url}" target="_blank" rel="noopener">生产状态证据</a>'
        f'<a class="source" href="{source_url}" target="_blank" rel="noopener">目录来源：{_esc(asset["source"])}</a>'
        "</div>"
    )


def port_popup(port: dict, day: str) -> str:
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
    ship_labels = SHIP_TYPE_LABELS
    ship_colors = {
        "container": "#2563eb",
        "dry_bulk": "#b45309",
        "general_cargo": "#64748b",
        "roro": "#7c3aed",
        "tanker": "#0f766e",
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
            f"<b>{share_text} · {calls_text}艘次</b></div>"
        )
    risk_block = (
        '<div class="row"><span>风险运力（出港网络）</span>'
        f"<strong>{amount('risk_capacity', 10000)} 万吨/日</strong></div>"
        if port.get("risk_capacity") is not None
        else ""
    )
    return (
        '<div class="popup-card">'
        f'<div class="field-name">⚓ {_esc(port["name"])}</div>'
        f'<div class="country">{_esc(port["country"])} · {_esc(port["region"])} · {_esc(date_label)}</div>'
        '<div class="row"><span>当日有效进港</span>'
        f"<strong>{amount('portcalls', decimals=0)} 艘次</strong></div>"
        '<div class="row"><span>当日估算装卸</span>'
        f"<strong>{amount('handled', 10000)} 万吨</strong></div>"
        f'<div class="hierarchy-title">过去 {window} 天港口指标</div>'
        '<div class="row"><span>港口活动指数</span>'
        f"<strong>{activity_text}（前一窗口=100）</strong></div>"
        '<div class="row"><span>活跃天数率</span>'
        f"<strong>{amount('active_day_rate')}%</strong></div>"
        '<div class="row"><span>日均进港 / 日均装卸</span>'
        f"<strong>{amount('avg_calls')} 艘次 · {amount('avg_handled', 10000)} 万吨</strong></div>"
        '<div class="row"><span>单船平均货量</span>'
        f"<strong>{amount('average_cargo_per_call', 10000, 2)} 万吨/艘次</strong></div>"
        '<div class="row"><span>进出口平衡指数</span>'
        f"<strong>{balance_text}</strong></div>"
        f"{risk_block}"
        f'<div class="basis">停复运：{_esc(port["port_operating_status_label"])}；'
        f"{_esc(port['port_operating_status_as_of'])}。{_esc(port['port_status_basis'])}</div>"
        '<div class="hierarchy-title">船型结构</div>'
        f"{''.join(structure)}"
        '<div class="basis">活动指数比较相邻等长窗口；100表示持平。平衡指数范围−100至+100，'
        "负值偏进口、正值偏出口。风险运力来自2019—2024港口航线网络，是历史冲击暴露估算。"
        "“—”表示窗口不完整、基期为0或源数据不足，不按零处理。</div>"
        f'<div class="basis">统计覆盖：{_esc(port.get("coverage_note", ""))}</div>'
        f'<a class="source" href="{_esc(port.get("source_url", PORTWATCH.SOURCE))}" target="_blank" rel="noopener">港口目录/统计来源</a>'
        "</div>"
    )


def chokepoint_popup(point: dict, day: str) -> str:
    def value(key: str, divisor: float = 1, decimals: int = 0) -> str:
        raw = point.get(key)
        return "—" if raw is None else f"{raw / divisor:,.{decimals}f}"

    categories = SHIP_TYPE_LABELS.items()
    rows = "".join(
        '<div class="row"><span>' + label + "</span>"
        f"<strong>{value(f'n_{kind}')} 艘 · {value(f'capacity_{kind}', 10000, 1)} 万吨</strong></div>"
        for kind, label in categories
    )
    return (
        '<div class="popup-card">'
        f'<div class="field-name">◆ {_esc(point.get("name_cn", point["portname"]))}</div>'
        f'<div class="country">{_esc(point.get("fullname") or point["portname"])} · {_esc(day)} UTC</div>'
        '<div class="row"><span>当日通过船舶</span>'
        f"<strong>{value('n_total')} 艘</strong></div>"
        '<div class="row"><span>估算承载货量</span>'
        f"<strong>{value('capacity', 10000, 1)} 万吨</strong></div>"
        '<div class="hierarchy-title">船型分解 · 艘数 / 估算货量</div>'
        f"{rows}"
        '<div class="basis">PortWatch按船舶穿越咽喉点边界计数；跨越多日的同一次通行只计一次，'
        "48小时内同船再次出现不重复计数。货量由AIS、吃水与载重能力估算。</div>"
        f'<a class="source" href="{_esc(PORTWATCH.SOURCE)}" target="_blank" rel="noopener">IMF PortWatch 数据与方法</a>'
        "</div>"
    )


def vessel_popup(vessel: dict[str, object]) -> str:
    def shown(key: str, suffix: str = "") -> str:
        value = vessel.get(key)
        return "—" if value in (None, "") else f"{_esc(value)}{suffix}"

    name = vessel.get("name") or f"MMSI {vessel['mmsi']}"
    age = vessel.get("age_minutes")
    age_text = "—" if age is None else f"{float(age):.1f} 分钟"
    speed = vessel.get("sog")
    speed_text = "—" if speed is None else f"{float(speed):.1f} 节"
    course = vessel.get("course")
    course_text = "—" if course is None else f"{float(course):.1f}°"
    return (
        '<div class="popup-card">'
        f'<div class="field-name">{_esc(name)}</div>'
        f'<div class="country">船舶 · {_esc(vessel.get("region") or "监测水域")}</div>'
        '<div class="row"><span>船型</span>'
        f"<strong>{shown('category_label')}</strong></div>"
        '<div class="row"><span>MMSI / IMO</span>'
        f"<strong>{shown('mmsi')} / {shown('imo')}</strong></div>"
        '<div class="row"><span>航速 / 航向</span>'
        f"<strong>{speed_text} / {course_text}</strong></div>"
        '<div class="row"><span>航行状态</span>'
        f"<strong>{shown('navigation_status')}</strong></div>"
        '<div class="row"><span>呼号 / 目的地</span>'
        f"<strong>{shown('call_sign')} / {shown('destination')}</strong></div>"
        '<div class="row"><span>AIS报告时间 UTC</span>'
        f"<strong>{shown('observed_at')}</strong></div>"
        '<div class="row"><span>本机接收时间 UTC</span>'
        f"<strong>{shown('received_at')}</strong></div>"
        '<div class="row"><span>数据年龄</span>'
        f"<strong>{age_text} · {shown('age_basis')}</strong></div>"
        '<div class="row"><span>数据源</span>'
        f"<strong>{shown('data_source')}</strong></div>"
        '<div class="basis">AIS船型为船载设备广播的基础分类；货船不能据此可靠细分为集装箱船或散货船。'
        "点位可能因岸基/卫星覆盖、设备关闭、延迟或错误广播而缺失。</div>"
        f'<a class="source" href="{_esc(vessel.get("source_url") or AIS.SOURCE)}" target="_blank" rel="noopener">'
        f"{_esc(vessel.get('source_attribution') or vessel.get('data_source') or 'AIS数据来源')}</a>"
        "</div>"
    )
