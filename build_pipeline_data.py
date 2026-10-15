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

SOURCE_COMMIT = "1f9ebdec2a863b7e0b6e9f4aa1edd666ec258667"
SOURCE_SHA256 = "5a8ec96c3e7a622d628fbe87afef9d9361eda7f42cd225fb79cc3ffa1740e4a1"
SOURCE_URL = ("https://raw.githubusercontent.com/GlobalEnergyMonitor/goit-ggit-data-ops/"
              + SOURCE_COMMIT + "/goit_map_latest.geojson")
COUNTRIES = {
    "Saudi Arabia", "Iraq", "Iran", "United Arab Emirates", "Egypt", "Oman",
    "Kuwait", "Qatar", "Yemen", "Syria", "Turkey", "Türkiye", "Israel",
    "Jordan", "Lebanon", "Bahrain",
}
NAMES = {
    "East-West Crude Oil Pipeline": "沙特东西原油管线",
    "Bab-Habshan–Fujairah Oil Pipeline": "哈卜善—富查伊拉输油管线",
    "Sumed Oil Pipeline": "苏伊士—地中海输油管线（SUMED）",
    "Kirkuk-Ceyhan Oil Pipeline": "基尔库克—杰伊汉输油管线",
    "Baku-Tbilisi-Ceyhan Pipeline": "巴库—第比利斯—杰伊汉输油管线",
    "Goreh-Jask Crude Oil Pipeline": "戈雷—贾斯克原油管线",
    "Trans-Arabian Oil Pipeline": "泛阿拉伯输油管线",
    "Basra–Aqaba Oil Pipeline": "巴士拉—亚喀巴输油管线",
    "Kirkuk-Baniyas Oil Pipelines": "基尔库克—巴尼亚斯输油管线",
}


def build(content):
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise ValueError("Input does not match the pinned GEM source SHA256")
    source = json.loads(content)
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
            "project_id": p["ProjectID"], "name": NAMES.get(p["PipelineName"], p["PipelineName"]),
            "name_en": p["PipelineName"], "segment": p.get("SegmentName"),
            "countries": countries, "fuel": "Oil", "status": p.get("Status"),
            "start": p.get("StartLocation"), "end": p.get("EndLocation"),
            "capacity": p.get("Capacity"), "capacity_unit": p.get("CapacityUnits"),
            "updated_at": p.get("LastUpdated"), "route_accuracy": p.get("RouteAccuracy"),
            "source_url": p.get("Wiki") or SOURCE_URL,
        }
        features.append({"type": "Feature", "geometry": mapping(simplified), "properties": props})
    features.sort(key=lambda value: value["properties"]["project_id"])
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
        },
    }


if __name__ == "__main__":
    result = build(Path(sys.argv[1]).read_bytes())
    destination = Path(__file__).parent / "data" / "oil_pipelines.geojson"
    destination.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{len(result['features'])} pipeline segments; {destination.stat().st_size} bytes")
