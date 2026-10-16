"""Build versioned map evidence from a locally downloaded, pinned GEM export.

Operator-only utility; never runs in Streamlit or on a schedule.
Usage: python build_pipeline_data.py /path/to/goit_map_latest.geojson
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from shapely.geometry import mapping, shape
from pipeline_capacity import review_digest

SOURCE_COMMIT = "1f9ebdec2a863b7e0b6e9f4aa1edd666ec258667"
SOURCE_SHA256 = "5a8ec96c3e7a622d628fbe87afef9d9361eda7f42cd225fb79cc3ffa1740e4a1"
SOURCE_URL = ("https://raw.githubusercontent.com/GlobalEnergyMonitor/goit-ggit-data-ops/"
              + SOURCE_COMMIT + "/goit_map_latest.geojson")
COUNTRIES = {
    "Saudi Arabia", "Iraq", "Iran", "United Arab Emirates", "Egypt", "Oman",
    "Kuwait", "Qatar", "Yemen", "Syria", "Turkey", "Türkiye", "Israel",
    "Jordan", "Lebanon", "Bahrain",
}



def build(content):
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise ValueError("Input does not match the pinned GEM source SHA256")
    source = json.loads(content)
    review = json.loads((Path(__file__).parent / "data/pipeline_capacity_review.json").read_text())
    if review["geometry_source_sha256"] != SOURCE_SHA256:
        raise ValueError("Capacity audit belongs to a different source snapshot")
    reviewed = {row["project_id"]: row for row in review["records"]}
    names = json.loads((Path(__file__).parent / "data/bilingual_names.json").read_text())["pipelines"]
    features = []
    for feature in source["features"]:
        p = feature["properties"]
        countries = [value.strip() for value in p.get("CountriesOrAreas", "").split(";")]
        if p.get("Fuel") != "Oil" or not COUNTRIES.intersection(countries):
            continue
        geometry = feature.get("geometry")
        if not geometry or geometry["type"] not in {"LineString", "MultiLineString"}:
            continue
        # Preserve separate components: never join branches or missing sections.
        simplified = shape(geometry).simplify(0.003, preserve_topology=True)
        props = {
            "project_id": p["ProjectID"], "name": f"{names[p['PipelineName']]}（{p['PipelineName']}）",
            "name_cn": names[p["PipelineName"]],
            "name_en": p["PipelineName"], "segment": p.get("SegmentName"),
            "countries": countries, "fuel": "Oil", "status": p.get("Status"),
            "start": p.get("StartLocation"), "end": p.get("EndLocation"),
            "capacity": p.get("Capacity"), "capacity_unit": p.get("CapacityUnits"),
            "updated_at": p.get("LastUpdated"), "route_accuracy": p.get("RouteAccuracy"),
            "source_url": p.get("Wiki") or SOURCE_URL,
        }
        props["map_drawable"] = p["ProjectID"] != "P0640"
        if not props["map_drawable"]:
            props["geometry_review_note"] = "源坐标终点不在达斯岛，路线名称与坐标不符；保留原始证据，暂停地图绘制。"
        decision = reviewed[p["ProjectID"]]
        if (decision["original_capacity"], decision["original_unit"]) != (p.get("Capacity"), p.get("CapacityUnits")):
            raise ValueError("Capacity source changed after review: " + p["ProjectID"])
        props.update({key: value for key, value in decision.items() if key.startswith("capacity_")})
        features.append({"type": "Feature", "geometry": mapping(simplified), "properties": props})
    features.sort(key=lambda value: value["properties"]["project_id"])
    if {feature["properties"]["project_id"] for feature in features} != set(reviewed):
        raise ValueError("Capacity review does not cover every selected pipeline")
    return {
        "type": "FeatureCollection", "features": features,
        "metadata": {
            "source": "Global Energy Monitor — Global Oil Infrastructure Tracker",
            "source_url": SOURCE_URL, "source_commit": SOURCE_COMMIT,
            "source_sha256": SOURCE_SHA256,
            "source_commit_date_utc": "2026-10-15T12:49:58Z",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_statement": "https://globalenergymonitor.org/creative-commons-license",
            "modifications": "Regional Oil subset; translated labels; geometry simplified by 0.003 degrees.",
            "geometry_simplification_degrees": 0.003,
            "status_basis": "GEM research map export; LastUpdated is a record date, not live flow monitoring.",
            "bilingual_names_version": 1,
            "capacity_schema_version": 2, "capacity_display_unit": "百万桶/日",
            "capacity_reviewed_at_utc": review["reviewed_at_utc"],
            "capacity_review_source": "data/pipeline_capacity_review.json",
            "capacity_review_sha256": review_digest(review),
            "coverage": review["coverage"],
        },
    }


if __name__ == "__main__":
    result = build(Path(sys.argv[1]).read_bytes())
    destination = Path(__file__).parent / "data" / "oil_pipelines.geojson"
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(result['features'])} pipeline segments; {destination.stat().st_size} bytes")
