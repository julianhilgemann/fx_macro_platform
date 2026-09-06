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
    frequency: str            # "daily" | "weekly" | "monthly" | "quarterly"
    role: str                 # stable panel column name (dbt pivots on this)
    provider_key: str = ""    # provider's own key if it differs from series_id
    verify_id: bool = False   # True => confirm the exact id before real fetch

    @property
    def key(self) -> str:
        """The identifier the provider's API expects."""
        return self.provider_key or self.series_id


# v1 payload: one EUR/USD slice across FRED (spot, US rates/yields, ECB floor),
# ECB SDW (MRO/MLF corridor), Bundesbank (daily German Bund yields).
# v2 adds the macro regime layer: inflation & expectations, full yield curve +
# term premium, credit, labor, growth, money/liquidity, commodities, equity, vol,
# uncertainty, and EA inflation/labor (ECB) + 5Y Bund (Bundesbank).
SERIES: list[Series] = [
    # --- spot + FX context (FRED) ---
    Series("DEXUSEU",  "fred", "daily",   "eurusd_spot"),      # EUR/USD spot
    Series("DTWEXBGS", "fred", "daily",   "usd_broad_index"),  # nominal broad USD index (2006+)
    Series("DTWEXAFEGS","fred","daily",   "usd_adv_fx_index"), # nominal advanced FX economies USD index
    Series("RTWEXBGS", "fred", "monthly", "usd_real_broad_index"),  # real broad USD index
    Series("VIXCLS",   "fred", "daily",   "vix"),              # CBOE VIX (risk sentiment)

    # --- US policy corridor (FRED): target range mirrors the ECB corridor ---
    Series("FEDFUNDS", "fred", "monthly", "fed_funds_rate"),   # effective fed funds (monthly)
    Series("DFEDTARU", "fred", "daily",   "fed_target_upper"), # fed funds target range upper
    Series("DFEDTARL", "fred", "daily",   "fed_target_lower"), # fed funds target range lower
    Series("DFF",      "fred", "daily",   "fed_funds_effective_daily"),  # effective fed funds (daily)
    Series("SOFR",     "fred", "daily",   "sofr"),             # secured overnight financing rate

    # --- ECB policy corridor: DFR floor (FRED) + MRO mid + MLF ceiling (ECB SDW) ---
    Series("ECBDFR",   "fred", "daily",   "ecb_policy_rate"),  # deposit facility rate (floor)
    Series("ECB_MRO",  "ecb",  "daily",   "ecb_mro_rate",
           provider_key="FM/B.U2.EUR.4F.KR.MRR_FR.LEV"),       # main refinancing, fixed rate (mid)
    Series("ECB_MLF",  "ecb",  "daily",   "ecb_mlf_rate",
           provider_key="FM/B.U2.EUR.4F.KR.MLFR.LEV"),         # marginal lending facility (ceiling)

    # --- US Treasury yields + curve + term premium (FRED) ---
    Series("DGS1MO",   "fred", "daily",   "us_1mo"),           # US 1M Treasury
    Series("DGS1",     "fred", "daily",   "us_1y"),            # US 1Y Treasury
    Series("DGS2",     "fred", "daily",   "us_2y"),            # US 2Y Treasury (daily)
    Series("DGS5",     "fred", "daily",   "us_5y"),            # US 5Y Treasury
    Series("DGS10",    "fred", "daily",   "us_10y"),           # US 10Y Treasury (daily)
    Series("DGS30",    "fred", "daily",   "us_30y"),           # US 30Y Treasury
    Series("T10Y2Y",   "fred", "daily",   "us_10y2y_spread"),  # 10Y-2Y spread
    Series("T10Y3M",   "fred", "daily",   "us_10y3m_spread"),  # 10Y-3M spread
    Series("THREEFYTP10","fred","daily",  "us_term_premium_10y"),  # ACM 10Y term premium
    Series("THREEFYTP5", "fred","daily",  "us_term_premium_5y"),   # ACM 5Y term premium

    # --- Inflation expectations / breakevens (FRED) ---
    Series("T5YIE",    "fred", "daily",   "us_5y_breakeven"),   # 5Y breakeven
    Series("T10YIE",   "fred", "daily",   "us_10y_breakeven"),  # 10Y breakeven
    Series("T5YIFR",   "fred", "daily",   "us_5y5y_breakeven"), # 5Y5Y forward breakeven

    # --- Credit & financial conditions (FRED) ---
    Series("BAA10Y",   "fred", "daily",   "us_baa10y_spread"),  # Moody's Baa - 10Y spread
    Series("AAA10Y",   "fred", "daily",   "us_aaa10y_spread"),  # Moody's Aaa - 10Y spread
    Series("BAMLH0A0HYM2","fred","daily", "us_hy_oas"),         # ICE BofA US HY OAS (2023+)
    Series("BAMLC0A0CM","fred","daily",   "us_ig_oas"),         # ICE BofA US IG OAS (2023+)
    Series("STLFSI4",  "fred", "weekly",  "stl_financial_stress"),  # St. Louis Fed stress
    Series("KCFSI",    "fred", "monthly", "kc_financial_stress"),   # Kansas City stress
    Series("USEPUINDXD","fred","daily",    "us_epu"),           # US economic policy uncertainty

    # --- US inflation (FRED) ---
    Series("CPIAUCSL", "fred", "monthly", "us_cpi"),            # CPI all items
    Series("CPILFESL", "fred", "monthly", "us_core_cpi"),       # core CPI
    Series("PCEPI",    "fred", "monthly", "us_pce"),            # PCE price index
    Series("PCEPILFE", "fred", "monthly", "us_core_pce"),       # core PCE
    Series("PCETRIM12M159SFRBDAL","fred","monthly","us_trimmed_mean_pce"),  # trimmed-mean PCE YoY

    # --- US labor (FRED) ---
    Series("UNRATE",   "fred", "monthly", "us_unemployment"),   # unemployment rate
    Series("PAYEMS",   "fred", "monthly", "us_nonfarm_payrolls"),   # nonfarm payrolls
    Series("JTSJOL",   "fred", "monthly", "us_job_openings"),   # JOLTS job openings
    Series("CES0500000003","fred","monthly","us_avg_hourly_earnings"),  # avg hourly earnings
    Series("ICSA",     "fred", "weekly",  "initial_claims"),    # initial claims
    Series("CCSA",     "fred", "weekly",  "continued_claims"),  # continued claims

    # --- US growth (FRED) ---
    Series("GDPC1",    "fred", "quarterly","us_real_gdp"),      # real GDP
    Series("INDPRO",   "fred", "monthly", "us_industrial_production"),  # industrial production
    Series("RSXFS",    "fred", "monthly", "us_retail_sales"),   # retail sales
    Series("HOUST",    "fred", "monthly", "us_housing_starts"), # housing starts
    Series("CSUSHPISA","fred", "monthly", "us_case_shiller"),   # Case-Shiller home price
    Series("UMCSENT",  "fred", "monthly", "us_consumer_sentiment"),  # Michigan sentiment

    # --- US money / liquidity (FRED) ---
    Series("M2SL",     "fred", "monthly", "us_m2"),             # M2 money stock
    Series("WALCL",    "fred", "weekly",  "fed_balance_sheet"), # Fed total assets
    Series("RRPONTSYD","fred", "daily",   "us_on_rrp"),         # Fed ON RRP usage

    # --- Commodities (FRED): oil, gas, metals, softs, broad indices ---
    Series("DCOILWTICO","fred","daily",    "wti_spot"),         # WTI crude spot
    Series("DCOILBRENTEU","fred","daily",  "brent_spot"),       # Brent crude spot
    Series("DHHNGSP",  "fred", "daily",    "henry_hub_spot"),   # Henry Hub natural gas
    Series("PCOPPUSDM","fred", "monthly",  "copper"),           # global copper
    Series("PALUMUSDM","fred", "monthly",  "aluminum"),         # global aluminum
    Series("PZINCUSDM","fred", "monthly",  "zinc"),             # global zinc
    Series("PCOCOUSDM","fred", "monthly",  "cocoa"),            # global cocoa
    Series("PWHEAMTUSDM","fred","monthly", "wheat"),            # global wheat
    Series("PIORECRUSDM","fred","monthly", "iron_ore"),         # global iron ore
    Series("PNGASEUUSDM","fred","monthly", "eu_gas"),           # EU natural gas (TTF proxy)
    Series("PNGASJPUSDM","fred","monthly", "lng_asia"),         # LNG Asia
    Series("PALLFNFINDEXM","fred","monthly","all_commodities_index"),  # all commodities index
    Series("PNRGINDEXM","fred","monthly",  "energy_index"),     # energy index
    Series("PPIACO",   "fred", "monthly",  "us_ppi"),           # PPI all commodities

    # --- Equity & vol (FRED) ---
    Series("SP500",    "fred", "daily",    "sp500"),            # S&P 500
    Series("NASDAQCOM","fred", "daily",    "nasdaq_composite"), # NASDAQ Composite
    Series("NASDAQ100","fred", "daily",    "nasdaq100"),        # NASDAQ-100
    Series("DJIA",     "fred", "daily",    "djia"),             # Dow Jones Industrial Avg
    Series("GVZCLS",   "fred", "daily",    "gold_etf_vol"),     # CBOE Gold ETF Volatility
    Series("RVXCLS",   "fred", "daily",    "russell_2000_vol"), # CBOE Russell 2000 Volatility

    # --- German Bund yields (Bundesbank BBSSY, daily) ---
    Series("DE2Y",  "bundesbank", "daily", "de_2y",
           provider_key="D.REN.EUR.A610.000000WT0202.A"),      # German 2Y Bund (daily, from 2014)
    Series("DE5Y",  "bundesbank", "daily", "de_5y",
           provider_key="D.REN.EUR.A620.000000WT0505.A"),      # German 5Y Bund (Bundesobligation)
    Series("DE10Y", "bundesbank", "daily", "de_10y",
           provider_key="D.REN.EUR.A630.000000WT1010.A"),      # German 10Y Bund (daily)

    # --- Euro area macro (ECB SDW, monthly) ---
    Series("ECB_HICP",      "ecb", "monthly", "ea_hicp_yoy",
           provider_key="ICP/M.U2.N.000000.4.ANR"),            # EA HICP overall YoY
    Series("ECB_HICP_CORE", "ecb", "monthly", "ea_hicp_core_yoy",
           provider_key="ICP/M.U2.N.XEF000.4.ANR"),            # EA HICP excl energy+food YoY
    Series("ECB_UNRATE",    "ecb", "monthly", "ea_unemployment",
           provider_key="LFSI/M.U2.S.UNEHRT.TOTAL0.15_74.T"),  # EA unemployment rate (15-74, SA)
]

PENDING_SERIES: list[Series] = []


def series_by_id(series_id: str) -> Series | None:
    return next((s for s in SERIES if s.series_id == series_id), None)
