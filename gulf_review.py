"""Dated decisions from primary disclosures, not automatic source imports."""
import json
from pathlib import Path

REVIEW_DATE = "2026-10-03"
EVIDENCE = json.loads(Path(__file__).with_name("GULF_REVIEW_2026-10-03.json").read_text())
ADDED = {(r["country"], r["name"]) for r in EVIDENCE["additions"]}
MEASURED = {(r["country"], r["name"]) for r in EVIDENCE["measurements"]}
STATUS_REVIEWED = ADDED | {(r["country"], r["name"]) for r in EVIDENCE["statuses"]}
RECHECKED = {(r["country"], n) for r in EVIDENCE["rechecked"] for n in r["names"]}


def additions(record):
    output = []
    for row in EVIDENCE["additions"]:
        item = record(row["country"], row["name"], row.get("name_cn", row["name"]),
                      row["asset_type"], None, None, source="Iraq EITI 2023", note=row["note"])
        item.update(source=row["source"], source_url=row["source_url"],
                    catalog_evidence_url=row["source_url"])
        output.append(item)
    return output


def apply_measurements(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    for row in EVIDENCE["measurements"]:
        item = index[(row["country"], row["name"])]
        item.setdefault("catalog_evidence_url", item["source_url"])
        item.update({k: v for k, v in row.items() if k not in {"country", "name"}})


def levels():
    return {(r["country"], r["name"]): r["asset_level"] for r in EVIDENCE["additions"]}


def parents():
    return {(r["country"], r["name"]): r["parent"] for r in EVIDENCE["parents"]}


def register_statuses(assign):
    for row in EVIDENCE["additions"]:
        assign(row["country"], row["name"], row["state"], row["as_of"],
               row["confidence"], row["status_basis"], row["status_url"])


def revise_statuses(revise):
    for row in EVIDENCE["statuses"]:
        revise(row["country"], row["name"], row["state"], row["as_of"],
               row["confidence"], row["status_basis"], row["status_url"])


def finish_review(assets):
    index = {(a["country"], a["name"]): a for a in assets}
    for item in assets:
        item["countries"] = [item["country"]]
    for row in EVIDENCE["shared_countries"]:
        item = index[(row["country"], row["name"])]
        item["countries"] = row["countries"]
        item["shared_country_evidence_url"] = row["evidence_url"]
    for row in EVIDENCE["measurements"]:
        if "ownership_basis" in row:
            index[(row["country"], row["name"])]["ownership_basis"] = row["ownership_basis"]
    for key in ADDED | MEASURED | STATUS_REVIEWED | RECHECKED:
        item = index[key]
        item["data_audit_date"] = REVIEW_DATE
        item["freshness_note"] = "仅适用于标注的证据/观测期；复核日不是实绩日；缺失不等于零"
        if key in STATUS_REVIEWED | RECHECKED:
            item["status_audit_date"] = REVIEW_DATE
    for row in EVIDENCE["additional_measurements"]:
        index[(row["country"], row["name"])]["data_audit_date"] = REVIEW_DATE
        index[(row["country"], row["name"])]["additional_measurements"].append(
            {k: v for k, v in row.items() if k not in {"country", "name"}})
