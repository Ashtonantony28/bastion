"""Filesystem layout. Data lives outside git (ADR 0004); fixtures are committed."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = REPO_ROOT / "fixtures"
FIXTURE_RAW = FIXTURES_ROOT / "raw"
TRANSFORM_DIR = REPO_ROOT / "transform"
PINS_FILE = Path(__file__).resolve().parent / "ingest" / "pins.json"


def data_root() -> Path:
    """Root for downloaded data and the lakehouse. Override with BASTION_DATA."""
    return Path(os.environ.get("BASTION_DATA", REPO_ROOT / "data")).resolve()


def raw_root() -> Path:
    return data_root() / "raw"


def warehouse_path(target: str) -> Path:
    if target == "ci":
        return data_root() / "ci" / "bastion_ci.duckdb"
    return data_root() / "warehouse" / "bastion.duckdb"
