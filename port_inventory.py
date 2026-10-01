"""Supplement PortWatch coverage without inventing PortWatch observations."""
import json
from pathlib import Path

WPI_SOURCE = "https://msi.nga.mil/api/publications/download?key=16694622%2FSFH00000%2FUpdatedPub150.csv"
WPI_ROWS = json.loads(Path(__file__).with_name("port_inventory_wpi_2026-09-30.json").read_text())
NGA_SAILING = "https://msi.nga.mil/api/publications/download?key=16694491%2FSFH00000%2FPub172bk.pdf"


def enrich(ports: list[dict]) -> list[dict]:
    output = [dict(p, activity_source="IMF PortWatch", source_url="https://portwatch.imf.org/pages/data-and-methodology",
                   coverage_note="AIS识别进港及模型估算货量；不是港务局实测吞吐量", wpi_ids=[], wpi_names=[])
              for p in ports]
    index = {p["portid"]: p for p in output}
    for row in WPI_ROWS:
        pid = row["portwatch_id"]
        if pid:
            if pid not in index:
                raise ValueError(f"WPI对应PortWatch点位已缺失/改变：{pid}，需重审跨库映射")
            if index[pid]["country"] != row["country"]:
                raise ValueError(f"WPI与PortWatch映射国家不符：{pid}")
            index[pid]["wpi_ids"].append(row["wpi"])
            index[pid]["wpi_names"].append(row["name"])
            index[pid]["inventory_source_url"] = WPI_SOURCE
            continue
        output.append(dict(portid=f"wpi{row['wpi']}", name=row["name"], country=row["country"],
                           lat=row["lat"], lon=row["lon"], region=row["region"],
                           wpi_ids=[row["wpi"]], source_url=WPI_SOURCE,
                           activity_source="无独立PortWatch统计", inventory_source_url=WPI_SOURCE,
                           coordinate_precision="NGA港口代表点；非泊位边界",
                           coverage_note="NGA名录补充，观察量未知；邻近综合港可能范围重叠，不借用邻港统计；名录日期未注明"))
    # Nautical positions represent the named coastal locality, not a surveyed berth.
    for pid, name, lat, lon, section in (
        ("facility_shinas", "Shinas", 24 + 46 / 60, 56 + 29 / 60, "11.22"),
        ("facility_suwaiq", "Suwaiq", 23 + 51 / 60, 57 + 27 / 60, "11.18"),
    ):
        output.append(dict(portid=pid, name=name, country="Oman", lat=lat, lon=lon, region="阿曼湾",
                           wpi_ids=[], source_url="https://www.asyad.com/ports",
                           inventory_source_url=NGA_SAILING, activity_source="无独立PortWatch统计",
                           coordinate_precision=f"NGA Pub172 §{section}港口所在地代表点；分钟精度",
                           coverage_note="Asyad港口名录补充；坐标是所在地近似点，进港与货量未知"))
    if len({p["portid"] for p in output}) != len(output):
        raise ValueError("合并港口目录出现重复编号")
    for port in output:
        if len(port["wpi_ids"]) > 1:
            port["coverage_note"] += "；跨库对应多个名录条目，PortWatch统计保持一个节点，不拆分：" + " / ".join(port["wpi_names"])
    return sorted(output, key=lambda p: (p["region"], p["country"], p["name"]))


SUPPLEMENTAL_IDS = {f"wpi{r['wpi']}" for r in WPI_ROWS if not r["portwatch_id"]} | {
    "facility_shinas", "facility_suwaiq"}
