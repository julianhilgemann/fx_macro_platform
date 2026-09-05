"""Central configuration: paths, Postgres connection, fetch mode, series registry.

Single source of truth for *what* the platform ingests. The series registry below
is configuration-as-code for now; it moves to a dbt seed (`meta.series_catalog`)
as part of M2 (spec §7). Nothing downstream hardcodes a series except the dbt
pivot, which maps series_id -> panel column.
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


# Append-only verbatim archive on disk (belt-and-suspenders alongside raw.source_fetch).
RAW_DIR: Path = _path_env("RAW_DIR", REPO_ROOT / "raw")

FRED_API_KEY: str | None = os.getenv("FRED_API_KEY") or None
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Source #2: Bundesbank statistics REST API (BBSSY flow). No key required.
BUNDESBANK_BASE_URL = "https://api.statistiken.bundesbank.de/rest/data/BBSSY"

# Source #3: ECB Data Portal (SDW) SDMX REST API. No key required.
ECB_SDW_BASE_URL = "https://data-api.ecb.europa.eu/service/data"

# "synthetic" needs no key and generates deterministic FRED-shaped data so the
# whole pipeline runs end-to-end. "fred" hits the real API.
FETCH_MODE: str = os.getenv("FX_FETCH_MODE") or ("fred" if FRED_API_KEY else "synthetic")

# How far back history goes (real FRED pulls use it as observation_start).
HISTORY_START: date = date.fromisoformat(os.getenv("FX_HISTORY_START", "2024-01-01"))

# --- Postgres (spec §13). Ingest + dbt connect as platform_writer ----------
PG_HOST: str = os.getenv("POSTGRES_HOST", "127.0.0.1")
PG_PORT: int = int(os.getenv("POSTGRES_PORT", "5433"))
PG_DB: str = os.getenv("POSTGRES_DB", "warehouse")
WRITER_USER: str = os.getenv("PLATFORM_WRITER_USER", "platform_writer")
WRITER_PASSWORD: str = os.getenv("PLATFORM_WRITER_PASSWORD", "writer_dev")
READER_USER: str = os.getenv("PLATFORM_READER_USER", "platform_reader")
READER_PASSWORD: str = os.getenv("PLATFORM_READER_PASSWORD", "reader_dev")

# Fetch-level landing table (spec §5). One row per fetch event.
RAW_TABLE = "raw.source_fetch"


@dataclass(frozen=True)
class Series:
    series_id: str            # stable, readable id (used in raw path + dbt pivot)
    source: str               # "fred" | "ecb" | "bundesbank"
    frequency: str            # "daily" (business days) | "monthly"
    role: str                 # stable panel column name (dbt pivots on this)
    provider_key: str = ""    # provider's own key if it differs from series_id
    verify_id: bool = False   # True => confirm the exact id before real fetch

    @property
    def key(self) -> str:
        """The identifier the provider's API expects."""
        return self.provider_key or self.series_id


# v1 payload: one EUR/USD slice across FRED (spot, US rates/yields, ECB floor),
# ECB SDW (MRO/MLF corridor), Bundesbank (daily German Bund yields).
SERIES: list[Series] = [
    # --- spot + FX context (FRED) ---
    Series("DEXUSEU",  "fred", "daily",   "eurusd_spot"),      # EUR/USD spot
    Series("DTWEXBGS", "fred", "daily",   "usd_broad_index"),  # nominal broad USD index (2006+)
    Series("VIXCLS",   "fred", "daily",   "vix"),              # CBOE VIX (risk sentiment)

    # --- US policy corridor (FRED): target range mirrors the ECB corridor ---
    Series("FEDFUNDS", "fred", "monthly", "fed_funds_rate"),   # effective fed funds (monthly)
    Series("DFEDTARU", "fred", "daily",   "fed_target_upper"), # fed funds target range upper
    Series("DFEDTARL", "fred", "daily",   "fed_target_lower"), # fed funds target range lower

    # --- ECB policy corridor: DFR floor (FRED) + MRO mid + MLF ceiling (ECB SDW) ---
    Series("ECBDFR",   "fred", "daily",   "ecb_policy_rate"),  # deposit facility rate (floor)
    Series("ECB_MRO",  "ecb",  "daily",   "ecb_mro_rate",
           provider_key="FM/B.U2.EUR.4F.KR.MRR_FR.LEV"),       # main refinancing, fixed rate (mid)
    Series("ECB_MLF",  "ecb",  "daily",   "ecb_mlf_rate",
           provider_key="FM/B.U2.EUR.4F.KR.MLFR.LEV"),         # marginal lending facility (ceiling)

    # --- US Treasury yields (FRED) ---
    Series("DGS2",     "fred", "daily",   "us_2y"),            # US 2Y Treasury (daily)
    Series("DGS10",    "fred", "daily",   "us_10y"),           # US 10Y Treasury (daily)

    # --- German Bund yields (Bundesbank BBSSY, daily) ---
    Series("DE2Y",  "bundesbank", "daily", "de_2y",
           provider_key="D.REN.EUR.A610.000000WT0202.A"),      # German 2Y Bund (daily, from 2014)
    Series("DE10Y", "bundesbank", "daily", "de_10y",
           provider_key="D.REN.EUR.A630.000000WT1010.A"),      # German 10Y Bund (daily)
]

PENDING_SERIES: list[Series] = []


def series_by_id(series_id: str) -> Series | None:
    return next((s for s in SERIES if s.series_id == series_id), None)
