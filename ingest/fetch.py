"""Fetch each series and write the verbatim response to the append-only raw store.

Immutable + append-only: one file per (series, fetch run), keyed by fetch
timestamp. Re-runs never overwrite; they produce a *new* vintage snapshot.
"""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from ingest.config import (
    FETCH_MODE,
    FRED_API_KEY,
    FRED_BASE_URL,
    HISTORY_START,
    RAW_DIR,
    SERIES,
    Series,
)


def _fetch_ts_str(ts: datetime) -> str:
    # ISO-8601 UTC with microseconds, 'Z' suffix — used as the raw file key.
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _raw_path(series: Series, fetch_ts: datetime) -> Path:
    return RAW_DIR / series.source / series.series_id / f"{_fetch_ts_str(fetch_ts)}.json"


# --- real FRED -------------------------------------------------------------

def fetch_fred(series: Series) -> dict:
    if not FRED_API_KEY:
        raise RuntimeError(
            "FX_FETCH_MODE=fred requires FRED_API_KEY in the environment / .env"
        )
    params = {
        "series_id": series.series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": HISTORY_START.isoformat(),
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# --- synthetic (FRED-shaped) ----------------------------------------------

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
    "eurusd_spot": (1.08, 0.004),
    "us_2y":       (4.30, 0.03),
    "us_10y":      (4.20, 0.03),
    "de_2y":       (2.70, 0.03),
    "de_10y":      (2.40, 0.03),
}
# role -> starting policy rate (step functions)
_SYNTH_RATES = {
    "ecb_policy_rate": 3.75,
    "fed_funds_rate":  4.33,
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
        {
            "realtime_start": today,
            "realtime_end": today,
            "date": d.isoformat(),
            "value": f"{v:.{digits}f}",
        }
        for d, v in zip(dates, values)
    ]


def synth_payload(series: Series, as_of: date) -> dict:
    obs = synth_observations(series, as_of)
    return {
        "realtime_start": as_of.isoformat(),
        "realtime_end": as_of.isoformat(),
        "observation_start": HISTORY_START.isoformat(),
        "observation_end": as_of.isoformat(),
        "units": "lin",
        "output_type": 1,
        "file_type": "json",
        "order_by": "observation_date",
        "sort_order": "asc",
        "count": len(obs),
        "offset": 0,
        "limit": 100000,
        "observations": obs,
    }


# --- driver ----------------------------------------------------------------

def fetch_series(series: Series, as_of: date) -> dict:
    if FETCH_MODE == "fred":
        return fetch_fred(series)
    return synth_payload(series, as_of)


def run() -> list[Path]:
    fetch_ts = datetime.now(timezone.utc)
    as_of = fetch_ts.date()
    written: list[Path] = []
    for series in SERIES:
        payload = fetch_series(series, as_of)
        path = _raw_path(series, fetch_ts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2))
        written.append(path)
        rel = path.relative_to(RAW_DIR.parent)
        print(f"  {series.series_id:20s} -> {rel}  ({payload.get('count', '?')} obs)")
    return written


def main() -> None:
    print(f"[fetch] mode={FETCH_MODE}  series={len(SERIES)}")
    paths = run()
    print(f"[fetch] wrote {len(paths)} immutable raw files")


if __name__ == "__main__":
    main()
