"""Pure record-to-table transformations; missing values stay missing."""

from __future__ import annotations

import json
from datetime import date

import ais as AIS
import portwatch as PORTWATCH
from map_popups import (
    METRIC_LABELS,
    daily_output_value,
    display_date,
    extra_measurements,
    hierarchy_path,
    other_daily_metric,
    production_display_value,
    production_display_date,
    aggregate_production_note,
)


def _rounded(value, digits: int = 1, divisor: int = 1):
    if value is None:
        return None
    return round(value / divisor if divisor != 1 else value, digits)


def port_rows(ports: list[dict], selected_day: date | None, rolling_days: int) -> list[dict]:
    rows = []
    for port in ports:
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
        rows.append(
            {
                "水域": port["region"],
                "国家": port["country"],
                "港口": port["name"],
                "PortWatch ID": port["portid"],
                "日期 UTC": selected_day.isoformat(),
                "当日有效进港 艘次": port.get("portcalls"),
                "港口活动指数": _rounded(port.get("activity_index"), 1),
                f"{rolling_days}天活跃天数率 %": _rounded(port.get("active_day_rate"), 1),
                f"{rolling_days}天日均进港 艘次": _rounded(port.get("avg_calls"), 3),
                f"{rolling_days}天日均装卸 万吨": _rounded(port.get("avg_handled"), 6, 10000),
                "单船平均货量 万吨/艘次": _rounded(port.get("average_cargo_per_call"), 6, 10000),
                "进出口平衡指数": _rounded(port.get("trade_balance_index"), 1),
                "风险运力 万吨/日": _rounded(port.get("risk_capacity"), 6, 10000),
                "集装箱船占比 %": _rounded(port.get("share_container"), 1),
                "干散货船占比 %": _rounded(port.get("share_dry_bulk"), 1),
                "普通货船占比 %": _rounded(port.get("share_general_cargo"), 1),
                "滚装船占比 %": _rounded(port.get("share_roro"), 1),
                "油轮/液货船占比 %": _rounded(port.get("share_tanker"), 1),
                f"{rolling_days}天有效日期": port.get("observed_days"),
                "数据提示": "；".join(notes),
                "纬度": port["lat"],
                "经度": port["lon"],
                "来源": port.get("source_url", PORTWATCH.SOURCE),
                "统计覆盖": port.get("activity_source"),
                "NGA WPI编号": str(port.get("wpi_ids", [])),
                "停复运状态": port["port_operating_status_label"],
                "状态截至": port["port_operating_status_as_of"],
                "状态依据": port["port_status_basis"],
                "状态证据": port["port_status_evidence_url"],
            }
        )

    return rows


def asset_rows(assets: list[dict]) -> list[dict]:
    return [
        {
            "国家": asset["country"],
            "资产层级": asset["asset_level_label"],
            "共享国家": "、".join(asset["countries"]),
            "权益口径": asset["ownership_basis"],
            "地图角色": asset["map_role_label"],
            "层级路径": hierarchy_path(asset),
            "上级资产": asset["parent_asset"] or "—",
            "组成资产": "、".join(asset["constituent_assets"]) or "—",
            "汇总规则": asset["rollup_policy"],
            "英文名称": asset["name"],
            "中文名称": asset["name_cn"],
            "别名": "、".join(asset["aliases"]),
            "运营商（2026-03目录参考）": asset.get("public_metadata", {}).get("operator"),
            "权益持有人（2026-03目录参考）": asset.get("public_metadata", {}).get("owners"),
            "发现年（目录参考）": asset.get("public_metadata", {}).get("discoveryYear"),
            "商业投产年（目录参考）": asset.get("public_metadata", {}).get("productionStartYear"),
            "海陆位置（目录原文）": asset.get("public_metadata", {}).get("onshoreOffshore"),
            "GEM Unit ID": asset.get("public_metadata", {}).get("unitId"),
            "参考资料版本": asset.get("public_metadata", {}).get("release"),
            "参考资料复核日": asset.get("public_metadata", {}).get("review_date"),
            "参考资料置信度": asset.get("public_metadata", {}).get("confidence"),
            "参考资料限制": asset.get("public_metadata", {}).get("limitations"),
            "参考资料链接": asset.get("public_metadata", {}).get("source_url"),
            "参考资产页面": asset.get("public_metadata", {}).get("wikiUrl"),
            "数据时效提示": asset["freshness_note"],
            "数值复核": asset["numeric_audit"],
            "数据复核日": asset["data_audit_date"],
            "其他商品指标": extra_measurements(asset),
            "待核验GEM产量线索": json.dumps(
                asset.get("gem_production_candidates", []), ensure_ascii=False, separators=(",", ":")
            ),
            "产量显示": production_display_value(asset),
            "产量显示日期": production_display_date(asset),
            "合计口径说明": aggregate_production_note(asset),
            "合计参考日期": "；".join(row["data_date"] for row in asset.get("aggregate_references", [])),
            "合计参考证据链接": "；".join(row["source_url"] for row in asset.get("aggregate_references", [])),
            "产量检索复核": asset.get("production_review", {}).get("conclusion"),
            "资产类型": asset["asset_type"],
            "商品": asset["commodity_label"],
            "生产状态": asset["operating_status_label"],
            "状态截至": asset["operating_status_as_of"],
            "本层级日产量": daily_output_value(asset),
            "本层级指标原值": str(asset["value"]) if asset["value"] is not None else None,
            "本层级指标原单位": asset["unit"],
            "其他日量指标": other_daily_metric(asset),
            "指标口径": METRIC_LABELS[asset["metric_type"]],
            "数据日期": display_date(asset),
            "统计范围": asset["aggregation_scope"],
            "状态置信度": asset["operating_status_confidence"],
            "状态依据": asset["operating_status_basis"],
            "状态证据链接": asset["operating_status_evidence_url"],
            "地图坐标精度": asset["map_coordinate_precision"],
            "地图参考纬度": asset["map_lat"],
            "地图参考经度": asset["map_lon"],
            "定位属性": "区域/设施代理点" if asset.get("map_is_proxy") else "资产点位",
            "坐标来源": asset["coordinate_source"],
            "坐标来源链接": asset["coordinate_source_url"],
            "默认战略节点": "是" if asset["strategic_default"] else "否",
            "来源": asset["source"],
            "来源链接": asset["source_url"],
            "说明": asset["note"],
        }
        for asset in assets
    ]


def vessel_rows(vessels: list[dict]) -> list[dict]:
    return [
        {
            "水域": vessel.get("region"),
            "船名": vessel.get("name") or "—",
            "船型": vessel.get("category_label"),
            "MMSI": vessel.get("mmsi"),
            "IMO": vessel.get("imo"),
            "航行状态": vessel.get("navigation_status"),
            "航速 节": (round(vessel["sog"], 1) if vessel.get("sog") is not None else None),
            "航向 °": (round(vessel["course"], 1) if vessel.get("course") is not None else None),
            "目的地": vessel.get("destination"),
            "吃水 米": vessel.get("draught"),
            "AIS报告时间 UTC": vessel.get("observed_at"),
            "本机接收时间 UTC": vessel.get("received_at"),
            "上游接收时间 UTC": vessel.get("provider_received_at"),
            "数据年龄 分钟": (
                round(vessel["age_minutes"], 1) if vessel.get("age_minutes") is not None else None
            ),
            "数据年龄依据": vessel.get("age_basis"),
            "来源署名": vessel.get("source_attribution"),
            "纬度": vessel.get("lat"),
            "经度": vessel.get("lon"),
            "数据源": vessel.get("data_source"),
            "来源": vessel.get("source_url") or AIS.SOURCE,
        }
        for vessel in vessels
    ]


def print_asset_record(asset: dict) -> dict:
    metric_type = str(asset.get("metric_type") or "")
    if daily_output_value(asset) == "未披露" and asset.get("aggregate_references"):
        metric_type = asset["aggregate_references"][0]["metric_type"]
    return {
        "中文名称": asset.get("name_cn") or asset.get("name"),
        "英文名称": asset.get("name"),
        "国家": asset.get("country"),
        "资产层级": asset.get("asset_level_label"),
        "生产状态": asset.get("operating_status_label"),
        "本层级日产量": daily_output_value(asset),
        "产量显示": production_display_value(asset),
        "合计口径说明": aggregate_production_note(asset),
        "产量口径说明": (
            f'{asset["ownership_basis"]}；{asset["note"]}' if asset["is_daily_output"] else ""
        ),
        "其他日量指标": other_daily_metric(asset),
        "指标口径": METRIC_LABELS.get(metric_type, metric_type or "未披露"),
        "数据日期": production_display_date(asset),
        "来源链接": asset.get("source_url"),
        "合计参考证据链接": "；".join(
            row["source_url"] for row in asset.get("aggregate_references", [])
        ),
        "产量检索复核": asset.get("production_review", {}).get("conclusion"),
        "运营商（2026-03目录参考）": asset.get("public_metadata", {}).get("operator"),
        "发现年（目录参考）": asset.get("public_metadata", {}).get("discoveryYear"),
        "商业投产年（目录参考）": asset.get("public_metadata", {}).get("productionStartYear"),
        "GEM Unit ID": asset.get("public_metadata", {}).get("unitId"),
        "参考资料链接": asset.get("public_metadata", {}).get("source_url"),
        "地图坐标精度": asset.get("map_coordinate_precision") or "未核验",
    }
