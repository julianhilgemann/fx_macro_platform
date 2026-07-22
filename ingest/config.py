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

# Source #2: Bundesbank statistics REST API (BBSSY flow = daily yields of the
# most recently issued German federal securities). No key required.
BUNDESBANK_BASE_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSSY"

# "synthetic" needs no key and generates deterministic FRED-shaped data so the
# whole pipeline runs end-to-end. "fred" hits the real API.
FETCH_MODE: str = os.getenv("FX_FETCH_MODE") or ("fred" if FRED_API_KEY else "synthetic")

# How far back synthetic history goes (real FRED pulls use it as observation_start).
HISTORY_START: date = date.fromisoformat(os.getenv("FX_HISTORY_START", "2024-01-01"))

# Name of the raw landing table in DuckDB (dbt source points here).
RAW_TABLE = "raw_observations"


@dataclass(frozen=True)
class Series:
    series_id: str            # stable, readable id (used in raw path + dbt pivot)
    source: str               # "fred" | "bundesbank"
    frequency: str            # "daily" (business days) | "monthly"
    role: str                 # stable panel column name (dbt pivots on this)
    provider_key: str = ""    # provider's own key if it differs from series_id
    verify_id: bool = False   # True => confirm the exact id before real fetch

    @property
    def key(self) -> str:
        """The identifier the provider's API expects."""
        return self.provider_key or self.series_id


# v1 EUR/USD slice. Two sources: FRED (spot, US rates/yields, ECB rate) and the
# Bundesbank (true daily German Bund yields — FRED has no clean daily German 2Y).
# Each yield leg is stored separately; dbt computes the differentials.
SERIES: list[Series] = [
    Series("DEXUSEU",  "fred", "daily",   "eurusd_spot"),      # EUR/USD spot
    Series("FEDFUNDS", "fred", "monthly", "fed_funds_rate"),   # effective fed funds (monthly)
    Series("ECBDFR",   "fred", "daily",   "ecb_policy_rate"),  # ECB deposit facility rate (daily)
    Series("DGS2",     "fred", "daily",   "us_2y"),            # US 2Y Treasury (daily)
    Series("DGS10",    "fred", "daily",   "us_10y"),           # US 10Y Treasury (daily)
    Series("DE2Y",  "bundesbank", "daily", "de_2y",
           provider_key="D.REN.EUR.A610.000000WT0202.A"),      # German 2Y Bund (daily, from 2014)
    Series("DE10Y", "bundesbank", "daily", "de_10y",
           provider_key="D.REN.EUR.A630.000000WT1010.A"),      # German 10Y Bund (daily)
]

# Nothing parked right now. Add future series (e.g. ECB SDW as source #3) here,
# then wire the matching series_id branch in
# dbt/models/intermediate/int_daily_panel.sql.
PENDING_SERIES: list[Series] = []


def series_by_id(series_id: str) -> Series | None:
    return next((s for s in SERIES if s.series_id == series_id), None)
