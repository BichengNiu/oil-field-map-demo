"""Shared geographic definitions for the five monitored waters."""

MONITORED_REGIONS = {
    "霍尔木兹海峡": (25.7, 27.4, 55.9, 57.5),
    "阿曼湾": (22.0, 26.6, 56.0, 61.8),
    "波斯湾": (23.5, 30.9, 47.0, 56.8),
    "苏伊士运河": (29.4, 31.6, 31.7, 33.5),
    "曼德海峡": (11.0, 15.4, 42.0, 45.7),
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
