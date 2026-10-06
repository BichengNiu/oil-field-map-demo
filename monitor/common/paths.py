"""Canonical paths for source data, browser assets, and generated runtime files."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def data_path(*parts: str) -> Path:
    return PROJECT_ROOT / "data" / Path(*parts)


def asset_path(*parts: str) -> Path:
    return PROJECT_ROOT / "assets" / Path(*parts)


def runtime_path(*parts: str) -> Path:
    return PROJECT_ROOT / "runtime" / Path(*parts)
