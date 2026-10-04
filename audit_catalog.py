"""Export every asset's evidence gaps; never label HTTP success as fact verification.

Run: python audit_catalog.py
Source access results are a dated optional snapshot, not a live availability promise.
"""
import csv
import json
import argparse
from datetime import date
from pathlib import Path

from field_catalog import ASSETS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-date", type=date.fromisoformat, default=date(2026, 10, 1))
    review_date = parser.parse_args().review_date.isoformat()
    health_file = Path(__file__).with_name("SOURCE_ACCESS_2026-09-30.csv")
    health = {}
    if health_file.exists():
        with health_file.open(encoding="utf-8-sig") as stream:
            health = {r["url"]: dict(r, access_date="2026-09-30") for r in csv.DictReader(stream)}
    followup_file = Path(__file__).with_name("GULF_SOURCE_MANIFEST_2026-10-04.json")
    if followup_file.exists():
        for entry in json.loads(followup_file.read_text())["files"]:
            health[entry["url"]] = dict(http_status=str(entry.get("status", "访问失败")),
                                        access_date=entry["access_date"])
    rows = []
    for asset in ASSETS:
        source = health.get(asset["source_url"], {})
        issues = []
        if asset["value"] is None:
            issues.append("未取得可展示的本层级产量/产能；不填0")
        else:
            issues.append("非实时数值；只能用于所标日期和口径")
        if source.get("http_status") != "200":
            issues.append("所引URL自动访问失败或未探测；不代表资产不存在")
        if not asset["map_drawable"]:
            issues.append("没有独立核验坐标；仅列目录")
        elif asset["map_is_proxy"]:
            issues.append("代理点；不能当田边界或独立子田坐标")
        elif not asset["coordinate_source_url"]:
            issues.append("继承近似点的独立坐标出处待核")
        rows.append({
            "国家": asset["country"], "名称": asset["name"], "中文/原文名": asset["name_cn"],
            "共享国家": " | ".join(asset["countries"]), "权益口径": asset["ownership_basis"],
            "别名": " | ".join(asset["aliases"]), "层级": asset["asset_level"],
            "上级": asset["parent_asset"], "商品": asset["commodity_label"],
            "数值": asset["value"], "单位": asset["unit"], "指标类型": asset["metric_type"],
            "观测/规划日期": asset["data_date"], "年产桶": asset.get("annual_barrels"),
            "日均分母": asset.get("calendar_days"), "报送口径": asset.get("measurement_basis"),
            "估计总桶量": asset.get("estimate_total_barrels"),
            "估计总气量_百万m3": asset.get("estimate_total_million_m3"),
            "估计公布份额": asset.get("estimate_share"),
            "其他商品指标JSON": json.dumps(asset["additional_measurements"], ensure_ascii=False),
            "本轮补充证据JSON": json.dumps(asset.get("followup_evidence", []), ensure_ascii=False),
            "冲突年报送JSON": json.dumps(asset.get("conflicting_annual_returns", []), ensure_ascii=False),
            "数值核验结论": asset["numeric_audit"], "时效结论": asset["freshness_note"],
            "状态": asset["operating_status_label"], "状态证据时点": asset["operating_status_as_of"],
            "状态置信度": asset["operating_status_confidence"],
            "状态证据": asset["operating_status_evidence_url"],
            "可绘制": asset["map_drawable"], "代理坐标": asset["map_is_proxy"],
            "地图纬度": asset["map_lat"], "地图经度": asset["map_lon"],
            "坐标证据": asset["coordinate_source_url"], "目录/指标来源": asset["source_url"],
            "来源HTTP探测日期": source.get("access_date", "未探测"),
            "状态复核日": asset["status_audit_date"],
            "状态依据": asset["operating_status_basis"],
            "来源HTTP自动探测": source.get("http_status", "未探测"),
            "复核日": asset["data_audit_date"], "未解决事项": "；".join(issues), "说明": asset["note"],
        })
    output = Path(f"ASSET_DATA_AUDIT_{review_date}.csv")
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(output, "rows", len(rows), "numeric", sum(a["value"] is not None for a in ASSETS),
          "without coordinate", sum(not a["map_drawable"] for a in ASSETS))


if __name__ == "__main__":
    main()
