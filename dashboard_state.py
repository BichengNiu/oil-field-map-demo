"""Typed inputs passed from dashboard data preparation to its page views."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class DashboardViewState:
    live_positions: list[dict[str, Any]]
    filtered_vessels: list[dict[str, Any]]
    ais_status: dict[str, Any]
    open_state: dict[str, Any]
    ais_enabled: bool
    archive_error: str | None
    port_error: str | None
    chokepoint_error: str | None
    map_assets: list[dict[str, Any]]
    map_ports: list[dict[str, Any]]
    map_chokepoints: list[dict[str, Any]]
    visible_map_layers: set[str]
    selected_day: date | None
    selected_chokepoint_day: date | None
    focus_assets: bool
    unlocated_asset_count: int
    unlocated_port_count: int
