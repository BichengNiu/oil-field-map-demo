"""Every checkpoint clue receives a disposition; no silent loss of old work."""
import csv
import argparse
from datetime import date
from pathlib import Path

from field_catalog import ASSETS
from reconciled_assets import MERGES, GEM_ROWS, pending


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-date", type=date.fromisoformat, default=date(2026, 10, 1))
    review_date = parser.parse_args().review_date.isoformat()
    root = Path(__file__).parent
    with (root / "ASSET_DATA_AUDIT_CHECKPOINT_2026-09-30.csv").open(encoding="utf-8-sig") as stream:
        old = list(csv.DictReader(stream))
    current = {(a["country"], a["name"]): a for a in ASSETS}
    probes = {(r["country"], r["name"]): r for r in GEM_ROWS}
    output = []
    for row in old:
        key = (row["国家"], row["名称"])
        targets = MERGES.get(key, (row["名称"],))
        matched = [current[(key[0], name)] for name in targets if (key[0], name) in current]
        if key in MERGES:
            state = "同田别名/已列组合范围；不另增节点"
            reason = ("名称变体按公开资产名录/原文对应；不以距离匹配" if len(targets) == 1
                      else "组合名单已分别保留成员；组合位置/数值不拆给成员")
        elif matched:
            state = "纳入当前目录；现时产量/状态以新审计为准"
            reason = "已列资产或新增原文确认；新来源、资产层级与数据期见当前逐行审计；旧值不自动沿用"
        else:
            state = "待核线索；未纳入确认目录"
            reason = "原页及定向检索多次未取得确认内容；不据快照复制坐标/指标"
        output.append({"国家": key[0], "快照名称": key[1], "处理": state,
                       "当前对应": " | ".join(a["name"] for a in matched), "依据/限制": reason,
                       "快照来源": row["来源"], "本轮来源": " | ".join(a["source_url"] for a in matched),
                       "旧值仅供追溯": row["值"], "现值": " | ".join(str(a["value"]) for a in matched),
                       "现值口径": " | ".join(a["metric_type"] for a in matched),
                       "回查名录成功": probes.get(key, {}).get("catalog_name_confirmed", "不适用")})
    for filename, rows in ((f"ASSET_CHECKPOINT_RECONCILIATION_{review_date}.csv", output),
                           (f"PENDING_ASSET_CLUES_{review_date}.csv", pending())):
        with (root / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            fields = rows[0].keys() if rows else ("国家", "名称线索", "原页", "核验结果")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(filename, len(rows))


if __name__ == "__main__":
    main()
