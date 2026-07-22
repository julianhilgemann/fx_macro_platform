"""Central configuration: paths, fetch mode, and the series registry.

Single source of truth for *what* the platform ingests. When the real FRED key
is wired in, only the series IDs below (and FX_FETCH_MODE) need attention —
nothing downstream hardcodes them except the dbt panel pivot, which maps
series_id -> panel column and is documented in int_daily_panel.sql.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

# Repo root = parent of this package. Load .env from there if present.
REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")


def _path_env(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser().resolve() if raw else default


RAW_DIR: Path = _path_env("RAW_DIR", REPO_ROOT / "raw")
DUCKDB_PATH: Path = _path_env("DUCKDB_PATH", REPO_ROOT / "warehouse" / "fx_macro.duckdb")

FRED_API_KEY: str | None = os.getenv("FRED_API_KEY") or None
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# "synthetic" needs no key and generates deterministic FRED-shaped data so the
# whole pipeline runs end-to-end. "fred" hits the real API.
FETCH_MODE: str = os.getenv("FX_FETCH_MODE") or ("fred" if FRED_API_KEY else "synthetic")

# How far back synthetic history goes (real FRED pulls use it as observation_start).
HISTORY_START: date = date.fromisoformat(os.getenv("FX_HISTORY_START", "2024-01-01"))

# Name of the raw landing table in DuckDB (dbt source points here).
RAW_TABLE = "raw_observations"


@dataclass(frozen=True)
class Series:
    series_id: str            # FRED/ALFRED series id
    source: str               # e.g. "fred"
    frequency: str            # "daily" (business days) | "monthly"
    role: str                 # stable panel column name (dbt pivots on this)
    verify_id: bool = False   # True => confirm the exact FRED id before real fetch


# v1 EUR/USD slice. Only series confirmed against FRED are fetched, so a real
# run never 400s on an unverified id. Each yield leg is stored separately; dbt
# computes the Bund-Treasury differentials once the legs are ingested.
SERIES: list[Series] = [
    Series("DEXUSEU",  "fred", "daily",   "eurusd_spot"),     # EUR/USD spot
    Series("FEDFUNDS", "fred", "monthly", "fed_funds_rate"),  # effective fed funds (monthly)
]

# Spec'd but awaiting the user's confirmed FRED calls. To light up the ecb-rate /
# yield-differential columns: move a series into SERIES above and add the matching
# series_id branch in dbt/models/intermediate/int_daily_panel.sql.
PENDING_SERIES: list[Series] = [
    Series("ECBDFR",          "fred", "daily",   "ecb_policy_rate", verify_id=True),
    Series("DGS2",            "fred", "daily",   "us_2y"),
    Series("DGS10",           "fred", "daily",   "us_10y"),
    Series("IRLTLT01DEM156N", "fred", "monthly", "de_10y",          verify_id=True),
    # German 2Y (de_2y): no clean daily FRED series identified yet.
]


def series_by_id(series_id: str) -> Series | None:
    return next((s for s in SERIES if s.series_id == series_id), None)
