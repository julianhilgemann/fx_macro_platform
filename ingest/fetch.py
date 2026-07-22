"""Fetch each series and write the verbatim response to the append-only raw store.

Multi-source: FRED (JSON) and Bundesbank (CSV) are fetched by their own clients;
each response body is stored verbatim, keyed by fetch timestamp, with the format's
extension. Re-runs never overwrite; they produce a *new* vintage snapshot.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from ingest.config import (
    BUNDESBANK_BASE_URL,
    ECB_SDW_BASE_URL,
    FETCH_MODE,
    FRED_API_KEY,
    FRED_BASE_URL,
    HISTORY_START,
    RAW_DIR,
    SERIES,
    Series,
)

SYNTHETIC = FETCH_MODE == "synthetic"


def _fetch_ts_str(ts: datetime) -> str:
    # ISO-8601 UTC with microseconds, 'Z' suffix — used as the raw file key.
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _raw_path(series: Series, fetch_ts: datetime, ext: str) -> Path:
    return RAW_DIR / series.source / series.series_id / f"{_fetch_ts_str(fetch_ts)}.{ext}"


# --- real sources: each returns (verbatim_body, file_extension) -----------

def fetch_fred(series: Series) -> tuple[str, str]:
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
    return resp.text, "json"


def fetch_bundesbank(series: Series) -> tuple[str, str]:
    url = f"{BUNDESBANK_BASE_URL}/{series.key}"
    resp = requests.get(url, params={"format": "csv", "lang": "en"}, timeout=30)
    resp.raise_for_status()
    return resp.text, "csv"


def fetch_ecb(series: Series) -> tuple[str, str]:
    # series.key includes the dataset, e.g. "FM/B.U2.EUR.4F.KR.MRR_FR.LEV".
    url = f"{ECB_SDW_BASE_URL}/{series.key}"
    resp = requests.get(
        url,
        params={"startPeriod": HISTORY_START.isoformat(), "format": "csvdata"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text, "csv"


REAL_CLIENTS = {"fred": fetch_fred, "bundesbank": fetch_bundesbank, "ecb": fetch_ecb}


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


# role -> (level, daily vol) for mean-reverting random walks
_SYNTH_LEVELS = {
    "eurusd_spot":     (1.08, 0.004),
    "usd_broad_index": (120.0, 0.3),
    "vix":             (18.0, 1.0),
    "us_2y":           (4.30, 0.03),
    "us_10y":          (4.20, 0.03),
    "de_2y":           (2.70, 0.03),
    "de_10y":          (2.40, 0.03),
}
# role -> starting policy rate (step functions)
_SYNTH_RATES = {
    "ecb_policy_rate":  3.75,   # DFR (floor)
    "ecb_mro_rate":     4.00,   # MRO (mid)
    "ecb_mlf_rate":     4.25,   # MLF (ceiling)
    "fed_funds_rate":   4.33,
    "fed_target_lower": 4.25,
    "fed_target_upper": 4.50,
}


def synth_observations(series: Series, as_of: date) -> list[dict]:
    """Deterministic-ish synthetic history shaped like FRED observations.

    The base path is seeded by series_id (stable across runs); the trailing
    points get a small revision seeded by the fetch date, so re-fetching yields
    a genuinely new vintage — exercising the point-in-time archive.
    """
    dates = (
        list(_month_ends(HISTORY_START, as_of))
        if series.frequency == "monthly"
        else list(_business_days(HISTORY_START, as_of))
    )

    rng = random.Random(series.series_id)
    values: list[float] = []
    if series.role in _SYNTH_LEVELS:
        level, vol = _SYNTH_LEVELS[series.role]
        x = level
        for _ in dates:
            x += rng.gauss(0, vol) - 0.02 * (x - level)  # mean-reverting
            values.append(x)
    else:
        rate = _SYNTH_RATES.get(series.role, 2.0)
        for i in range(len(dates)):
            if i > 0 and rng.random() < 0.01:          # occasional 25bp move
                rate += rng.choice([-0.25, 0.25])
            values.append(rate)

    # Vintage revision: nudge the last few points by a fetch-date-seeded amount.
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


def synth_payload(series: Series, as_of: date) -> tuple[str, str]:
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
    return json.dumps(payload, indent=2), "json"


# --- driver ----------------------------------------------------------------

def fetch_series(series: Series, as_of: date) -> tuple[str, str]:
    if SYNTHETIC:
        return synth_payload(series, as_of)
    client = REAL_CLIENTS.get(series.source)
    if client is None:
        raise ValueError(f"no fetch client for source '{series.source}'")
    return client(series)


def run() -> list[Path]:
    fetch_ts = datetime.now(timezone.utc)
    as_of = fetch_ts.date()
    written: list[Path] = []
    for series in SERIES:
        body, ext = fetch_series(series, as_of)
        path = _raw_path(series, fetch_ts, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        written.append(path)
        rel = path.relative_to(RAW_DIR.parent)
        print(f"  {series.series_id:9s} [{series.source:10s}] -> {rel}  ({len(body)} bytes)")
    return written


def main() -> None:
    mode = "synthetic" if SYNTHETIC else "live"
    print(f"[fetch] mode={mode}  series={len(SERIES)}  sources={sorted({s.source for s in SERIES})}")
    paths = run()
    print(f"[fetch] wrote {len(paths)} immutable raw files")


if __name__ == "__main__":
    main()
