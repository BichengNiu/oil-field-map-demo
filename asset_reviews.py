"""Apply dated asset evidence in order, retaining each review's scope and dates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


def _key(row: dict) -> tuple[str, str]:
    return row["country"], row["name"]


@dataclass(frozen=True)
class AssetReview:
    date: str
    evidence: dict

    def additions(self, record) -> list[dict]:
        output = []
        for row in self.evidence["additions"]:
            item = record(
                row["country"],
                row["name"],
                row.get("name_cn", row["name"]),
                row["asset_type"],
                None,
                None,
                source=row["source"],
                source_url=row["source_url"],
                note=row["note"],
            )
            item["catalog_evidence_url"] = row["source_url"]
            output.append(item)
        return output

    def apply_measurements(self, assets: list[dict]) -> None:
        index = {_key(asset): asset for asset in assets}
        for row in self.evidence["measurements"]:
            item = index[_key(row)]
            item.setdefault("catalog_evidence_url", item["source_url"])
            item.update(
                {key: value for key, value in row.items() if key not in {"country", "name"}}
            )

    def levels(self) -> dict:
        return {_key(row): row["asset_level"] for row in self.evidence["additions"]}

    def parents(self) -> dict:
        return {_key(row): row["parent"] for row in self.evidence.get("parents", [])}

    def register_statuses(self, assign) -> None:
        self._apply_statuses(assign, self.evidence["additions"])

    def revise_statuses(self, revise) -> None:
        self._apply_statuses(revise, self.evidence["statuses"])

    @staticmethod
    def _apply_statuses(assign, rows: list[dict]) -> None:
        for row in rows:
            assign(
                row["country"],
                row["name"],
                row["state"],
                row["as_of"],
                row["confidence"],
                row["status_basis"],
                row["status_url"],
            )

    @property
    def status_keys(self) -> set:
        return {_key(row) for kind in ("additions", "statuses") for row in self.evidence[kind]}

    @property
    def reviewed_keys(self) -> set:
        return self.status_keys | {_key(row) for row in self.evidence["measurements"]}


def _load(date: str, filename: str) -> AssetReview:
    return AssetReview(date, json.loads(Path(__file__).with_name(filename).read_text()))


GULF = _load("2026-10-03", "GULF_REVIEW_2026-10-03.json")
FOLLOWUP = _load("2026-10-04", "FINAL_REVIEW_2026-10-04.json")
REVIEWS = (GULF, FOLLOWUP)

PUBLIC_METADATA = json.loads(
    (Path(__file__).parent / "data" / "asset_public_metadata.json").read_text(encoding="utf-8")
)


def public_reference_coordinates() -> dict:
    """Only reviewed missing points; mirror accuracy is unknown, so use proxies."""
    return {
        _key(row): {
            "lat": row["record"]["latitude"],
            "lon": row["record"]["longitude"],
            "precision": "GEM 2026-03目录参考点；原始精度未保留，非核验油田中心或井位",
            "source": "Global Energy Monitor（2026-03公开镜像；CC BY 4.0）",
            "url": PUBLIC_METADATA["source"]["mirror_url"],
            "proxy": True,
        }
        for row in PUBLIC_METADATA["records"]
        if row["use_reference_coordinates"]
    }


def apply_public_metadata(assets: list[dict]) -> None:
    """Keep directory facts separate from measurements and current status."""
    index = {_key(asset): asset for asset in assets}
    for row in PUBLIC_METADATA["records"]:
        index[_key(row)]["public_metadata"] = {
            **row["record"],
            "release": PUBLIC_METADATA["source"]["release"],
            "review_date": PUBLIC_METADATA["review_date"],
            "source_url": PUBLIC_METADATA["source"]["mirror_url"],
            "confidence": PUBLIC_METADATA["source"]["confidence"],
            "limitations": PUBLIC_METADATA["source"]["limitations"],
        }


def finish_reviews(assets: list[dict]) -> None:
    """Preserve the distinct country, freshness, and note rules of both reviews."""
    index = {_key(asset): asset for asset in assets}
    for asset in assets:
        asset["countries"] = [asset["country"]]
    for review in REVIEWS:
        for row in review.evidence["shared_countries"]:
            index[_key(row)].update(
                countries=row["countries"], shared_country_evidence_url=row["evidence_url"]
            )
    for row in GULF.evidence["measurements"]:
        if "ownership_basis" in row:
            index[_key(row)]["ownership_basis"] = row["ownership_basis"]
    rechecked = {
        (row["country"], name) for row in GULF.evidence["rechecked"] for name in row["names"]
    }
    gulf_status_keys = GULF.status_keys | rechecked
    for key in GULF.reviewed_keys | rechecked:
        item = index[key]
        item["data_audit_date"] = GULF.date
        item["freshness_note"] = "仅适用于标注的证据/观测期；复核日不是实绩日；缺失不等于零"
        if key in gulf_status_keys:
            item["status_audit_date"] = GULF.date
    for row in GULF.evidence["additional_measurements"]:
        item = index[_key(row)]
        item["data_audit_date"] = GULF.date
        item["additional_measurements"].append(
            {key: value for key, value in row.items() if key not in {"country", "name"}}
        )
    reviewed = FOLLOWUP.reviewed_keys
    followup_status_keys = FOLLOWUP.status_keys
    for row in FOLLOWUP.evidence["notes"]:
        reviewed.add(_key(row))
        item = index[_key(row)]
        item["note"] += " " + row["note"]
        item.setdefault("followup_evidence", []).append(row)
    index["科威特", "Homah"]["aliases"].append("Houma")
    for key in reviewed:
        item = index[key]
        item["data_audit_date"] = FOLLOWUP.date
        item["freshness_note"] = "仅适用于标注的证据期；复核日不是产量或停复产观测日"
        if key in followup_status_keys:
            item["status_audit_date"] = FOLLOWUP.date
