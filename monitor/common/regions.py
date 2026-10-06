"""Geographic definitions for PortWatch and the broader AIS corridor."""

MONITORED_REGIONS = {
    "霍尔木兹海峡": (25.7, 27.4, 55.9, 57.5),
    "阿曼湾": (22.0, 26.6, 56.0, 61.8),
    "波斯湾": (23.5, 30.9, 47.0, 56.8),
    "苏伊士运河": (29.4, 31.6, 31.7, 33.5),
    "曼德海峡": (11.0, 15.4, 42.0, 45.7),
}

# AIS also follows the Red Sea corridor between Suez and Bab el-Mandeb.
# Keep these after the five named waters so their positions retain those names.
AIS_REGIONS = {
    **MONITORED_REGIONS,
    "红海北段": (21.0, 30.0, 32.0, 40.0),
    "红海南段": (12.0, 21.0, 36.0, 44.0),
}


def region_for(lat: float, lon: float, regions: dict = MONITORED_REGIONS) -> str | None:
    """Use definition order to assign a point in overlapping region boxes once."""
    return next(
        (
            name
            for name, (south, north, west, east) in regions.items()
            if south <= lat <= north and west <= lon <= east
        ),
        None,
    )
