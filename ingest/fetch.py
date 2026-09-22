"""Fetch clients. Each returns verbatim bytes plus request metadata (no disk I/O).

Three real clients (FRED JSON, Bundesbank CSV, ECB SDW CSV) plus a deterministic
synthetic generator so the pipeline runs without a FRED key. The orchestrator in
`ingest/load.py` writes the verbatim bytes to disk and lands rows in
`raw.source_fetch` (spec §5). Parsing to JSON happens at this boundary; the
byte-faithful original is always carried through.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests

from ingest.config import (
    BUNDESBANK_BASE_URL,
    ECB_SDW_BASE_URL,
    ECBWATCH_BASE_URL,
    FETCH_MODE,
    FRED_API_KEY,
    FRED_BASE_URL,
    HISTORY_START,
    SERIES,
    Series,
)

SYNTHETIC = FETCH_MODE == "synthetic"

#: The ECB Data Portal intermittently answers 5xx / drops the connection under
#: load (observed repeatedly while wiring the €STR + MMSR series). A bounded
#: retry keeps one flaky response from landing a null payload for the day.
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_S = 2.0


def _get_with_retry(url: str, params: dict, *, attempts: int = _RETRY_ATTEMPTS):
    """GET with bounded retries on 5xx/429 and transient connection errors."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code not in _RETRY_STATUS:
                return resp
            print(f"    retry {attempt}/{attempts}: HTTP {resp.status_code} from {url}")
        except requests.RequestException as exc:
            last_exc = exc
            print(f"    retry {attempt}/{attempts}: {type(exc).__name__} from {url}")
        if attempt < attempts:
            time.sleep(_RETRY_BACKOFF_S * attempt)
    if last_exc is not None:
        raise last_exc
    return resp


@dataclass(frozen=True)
class FetchResult:
    source: str
    resource: str          # series_id
    request_url: str
    request_params: dict   # api_key excluded (never persisted)
    http_status: int
    content_type: str | None
    body: bytes            # verbatim response bytes
    ext: str               # "json" | "csv"


# --- real sources -----------------------------------------------------------

def fetch_fred(series: Series) -> FetchResult:
    if not FRED_API_KEY:
        raise RuntimeError("live FRED fetch requires FRED_API_KEY in the environment / .env")
    params = {
        "series_id": series.key,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": HISTORY_START.isoformat(),
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url=FRED_BASE_URL,
        request_params={k: v for k, v in params.items() if k != "api_key"},
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type"),
        body=resp.content,
        ext="json",
    )


def fetch_bundesbank(series: Series) -> FetchResult:
    url = f"{BUNDESBANK_BASE_URL}/{series.key}"
    params = {"format": "csv", "lang": "en"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url=url,
        request_params=params,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type"),
        body=resp.content,
        ext="csv",
    )


def fetch_ecb(series: Series) -> FetchResult:
    # series.key includes the dataset, e.g. "FM/B.U2.EUR.4F.KR.MRR_FR.LEV".
    url = f"{ECB_SDW_BASE_URL}/{series.key}"
    params = {"startPeriod": HISTORY_START.isoformat(), "format": "csvdata"}
    resp = _get_with_retry(url, params)
    resp.raise_for_status()
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url=url,
        request_params=params,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type"),
        body=resp.content,
        ext="csv",
    )


def fetch_ecbwatch(series: Series) -> FetchResult:
    """ecb-watch.eu market-implied probabilities — one endpoint, one document.

    The whole feed is a single JSON object keyed by meeting date, so the series
    key is unused; the payload is landed verbatim and exploded in dbt.
    """
    params: dict = {}
    resp = _get_with_retry(ECBWATCH_BASE_URL, params)
    resp.raise_for_status()
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url=ECBWATCH_BASE_URL,
        request_params=params,
        http_status=resp.status_code,
        content_type=resp.headers.get("content-type"),
        body=resp.content,
        ext="json",
    )


REAL_CLIENTS = {
    "fred": fetch_fred,
    "bundesbank": fetch_bundesbank,
    "ecb": fetch_ecb,
    "ecbwatch": fetch_ecbwatch,
}


# --- synthetic (FRED-shaped JSON, any source) -----------------------------

def _business_days(start: date, end: date):
    d, one = start, timedelta(days=1)
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += one


def _month_ends(start: date, end: date):
    d = date(start.year, start.month, 1)
    while d <= end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        if start <= last <= end:
            yield last
        d = nxt


def _week_ends(start: date, end: date):
    # Weekly cadence anchored on Fridays, closest to provider convention.
    d = start - timedelta(days=start.weekday()) + timedelta(days=4)  # first Friday
    while d <= end:
        if d >= start:
            yield d
        d += timedelta(days=7)


def _quarter_ends(start: date, end: date):
    d = date(start.year, ((start.month - 1) // 3) * 3 + 1, 1)
    while d <= end:
        if d >= start:
            yield d
        d = (d.replace(day=28) + timedelta(days=100)).replace(day=1)
        d = date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


_SYNTH_LEVELS = {
    "eurusd_spot":     (1.08, 0.004),
    "usd_broad_index": (120.0, 0.3),
    "vix":             (18.0, 1.0),
    "us_2y":           (4.30, 0.03),
    "us_10y":          (4.20, 0.03),
    "de_2y":           (2.70, 0.03),
    "de_10y":          (2.40, 0.03),
}
_SYNTH_RATES = {
    "ecb_policy_rate":  3.75,
    "ecb_mro_rate":     4.00,
    "ecb_mlf_rate":     4.25,
    "fed_funds_rate":   4.33,
    "fed_target_lower": 4.25,
    "fed_target_upper": 4.50,
}


def synth_observations(series: Series, as_of: date) -> list[dict]:
    """Deterministic-ish synthetic history shaped like FRED observations."""
    gen = {
        "daily": _business_days,
        "weekly": _week_ends,
        "monthly": _month_ends,
        "quarterly": _quarter_ends,
    }.get(series.frequency, _business_days)
    dates = list(gen(HISTORY_START, as_of))

    rng = random.Random(series.series_id)
    values: list[float] = []
    if series.role in _SYNTH_LEVELS:
        level, vol = _SYNTH_LEVELS[series.role]
        x = level
        for _ in dates:
            x += rng.gauss(0, vol) - 0.02 * (x - level)
            values.append(x)
    else:
        rate = _SYNTH_RATES.get(series.role, 2.0)
        for i in range(len(dates)):
            if i > 0 and rng.random() < 0.01:
                rate += rng.choice([-0.25, 0.25])
            values.append(rate)

    rev = random.Random(f"{series.series_id}:{as_of.isoformat()}")
    for i in range(max(0, len(values) - 5), len(values)):
        values[i] += rev.gauss(0, 0.0005)

    digits = 4 if series.role == "eurusd_spot" else 2
    today = as_of.isoformat()
    return [
        {"realtime_start": today, "realtime_end": today,
         "date": d.isoformat(), "value": f"{v:.{digits}f}"}
        for d, v in zip(dates, values)
    ]


def synth_payload(series: Series, as_of: date) -> FetchResult:
    obs = synth_observations(series, as_of)
    payload = {
        "realtime_start": as_of.isoformat(),
        "realtime_end": as_of.isoformat(),
        "observation_start": HISTORY_START.isoformat(),
        "observation_end": as_of.isoformat(),
        "units": "lin", "output_type": 1, "file_type": "json",
        "order_by": "observation_date", "sort_order": "asc",
        "count": len(obs), "offset": 0, "limit": 100000,
        "observations": obs,
    }
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url="synthetic",
        request_params={"mode": "synthetic"},
        http_status=200,
        content_type="application/json",
        body=json.dumps(payload, indent=2).encode("utf-8"),
        ext="json",
    )


def synth_ecbwatch_payload(series: Series, as_of: date) -> FetchResult:
    """Shape-correct stand-in for the ecb-watch feed in synthetic mode.

    Faking a FRED-shaped body here would make the staging model silently read
    nothing, so the synthetic payload mirrors the real contract
    (`abs_data` keyed by meeting date) with a trivially flat distribution.
    """
    meetings = [as_of + timedelta(days=45 * (i + 1)) for i in range(2)]
    abs_data = {
        d.isoformat(): {"2.50%": 1.0, "2.75%": 0.0}
        for d in meetings
    }
    payload = {
        "abs_data": abs_data,
        "current_rate": 2.50,
        "metadata": {"last_updated": as_of.isoformat(), "version": "synthetic",
                     "status": "synthetic", "data_sources": "synthetic"},
    }
    return FetchResult(
        source=series.source,
        resource=series.series_id,
        request_url="synthetic",
        request_params={"mode": "synthetic"},
        http_status=200,
        content_type="application/json",
        body=json.dumps(payload, indent=2).encode("utf-8"),
        ext="json",
    )


# --- driver ----------------------------------------------------------------

def fetch_series(series: Series, as_of: date) -> FetchResult:
    if SYNTHETIC:
        if series.source == "ecbwatch":
            return synth_ecbwatch_payload(series, as_of)
        return synth_payload(series, as_of)
    client = REAL_CLIENTS.get(series.source)
    if client is None:
        raise ValueError(f"no fetch client for source '{series.source}'")
    return client(series)
