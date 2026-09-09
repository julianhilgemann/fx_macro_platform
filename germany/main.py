"""German economy — macro snapshot dashboard API.

Read-only FastAPI over the Postgres marts, curated to the German / euro-area
economy, plus static serving of the D3 dashboard that visualises it.

The dashboard consumes a handful of bespoke endpoints so the browser never has
to reason about the underlying (bitemporal) warehouse schema:

  GET /health                      liveness
  GET /ready                       DB readiness
  GET /api/meta                    warehouse build + generated-at
  GET /api/indicators              curated series catalogue
  GET /api/observations/{id}       one series, optional resample (D/W/M/Q/Y)
  GET /api/snapshot                headline KPI cards (value + deltas + sparkline)
  GET /api/yield-curve             Bund curve surface (anchors interpolated
                                   across tenors, monthly grid) + snapshot curve

Yield-curve anchors are real market rates: ECB deposit facility (O/N), ECB MRO
(1W) and Bundesbank Bund yields at 2Y / 5Y / 10Y. Intermediate tenors are a
monotone (PCHIP) interpolation — standard curve practice, and labelled as such.
"""
from __future__ import annotations

import bisect
import os
from datetime import date, datetime, timedelta, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# --- connection (mirrors the platform `api` service env) ---------------------
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "warehouse")
READER_USER = os.getenv("PLATFORM_READER_USER", "platform_reader")
READER_PASSWORD = os.getenv("PLATFORM_READER_PASSWORD", "reader_dev")

MAX_RANGE_DAYS = 50 * 365

app = FastAPI(title="German Macro Dashboard", version="1.0.0")


# ---------------------------------------------------------------------------
# Curated catalogue
# ---------------------------------------------------------------------------

# Yield-curve anchors (real rates). maturity is in years.
CURVE_ANCHORS: list[dict] = [
    {"series_id": "ECBDFR", "label": "O/N", "maturity": 1 / 365, "kind": "anchor"},
    {"series_id": "ECB_MRO", "label": "1W", "maturity": 7 / 365, "kind": "anchor"},
    {"series_id": "DE2Y", "label": "2Y", "maturity": 2.0, "kind": "anchor"},
    {"series_id": "DE5Y", "label": "5Y", "maturity": 5.0, "kind": "anchor"},
    {"series_id": "DE10Y", "label": "10Y", "maturity": 10.0, "kind": "anchor"},
]

# Display tenors: a smooth grid interpolated between the anchors above.
CURVE_TENORS: list[dict] = [
    {"label": "1M", "maturity": 1 / 12},
    {"label": "3M", "maturity": 3 / 12},
    {"label": "6M", "maturity": 6 / 12},
    {"label": "1Y", "maturity": 1.0},
    {"label": "2Y", "maturity": 2.0},
    {"label": "3Y", "maturity": 3.0},
    {"label": "4Y", "maturity": 4.0},
    {"label": "5Y", "maturity": 5.0},
    {"label": "7Y", "maturity": 7.0},
    {"label": "10Y", "maturity": 10.0},
]

# Headline KPI tiles (2 rows × 5). `series_id` feeds value/deltas/sparkline and
# the hero history; `spread` of two series yields a computed difference. `step`
# is the default resample for the hero chart (weekly for daily series).
KPIS: list[dict] = [
    {"id": "de10y", "label": "10Y Bund Yield", "series_id": "DE10Y",
     "unit": "%", "decimals": 2, "tone": "yield", "color": "#f6b94b", "step": "W",
     "subtitle": "German 10-year Bund — the benchmark euro-area safe rate"},
    {"id": "curve", "label": "Bund 2s10s Spread", "spread": ["DE10Y", "DE2Y"],
     "unit": "bp", "decimals": 0, "tone": "curve", "factor": 100, "color": "#9d8cff", "step": "W",
     "subtitle": "10Y minus 2Y — curve shape and recession signal"},
    {"id": "de2y", "label": "2Y Bund Yield", "series_id": "DE2Y",
     "unit": "%", "decimals": 2, "tone": "yield", "color": "#5b8cff", "step": "W",
     "subtitle": "German 2-year Bund — the policy-sensitive short end"},
    {"id": "de5y", "label": "5Y Bund Yield", "series_id": "DE5Y",
     "unit": "%", "decimals": 2, "tone": "yield", "color": "#4dd6c1", "step": "W",
     "subtitle": "German 5-year Bund — the middle of the curve"},
    {"id": "ecb", "label": "ECB Deposit Rate", "series_id": "ECBDFR",
     "unit": "%", "decimals": 2, "tone": "rate", "color": "#ff7aa2", "step": "W",
     "subtitle": "ECB deposit facility — the policy floor"},
    {"id": "hicp", "label": "EA Inflation (HICP)", "series_id": "ECB_HICP",
     "unit": "% YoY", "decimals": 1, "tone": "inflation", "color": "#f0a63a",
     "subtitle": "Euro-area headline inflation, year-over-year"},
    {"id": "hicp_core", "label": "EA Core Inflation", "series_id": "ECB_HICP_CORE",
     "unit": "% YoY", "decimals": 1, "tone": "inflation", "color": "#5b8cff",
     "subtitle": "Euro-area core inflation (excl. energy & food)"},
    {"id": "unrate", "label": "EA Unemployment", "series_id": "ECB_UNRATE",
     "unit": "%", "decimals": 1, "tone": "labor", "invert": True, "color": "#3ddc84",
     "subtitle": "Euro-area unemployment rate, seasonally adjusted"},
    {"id": "eurusd", "label": "EUR / USD", "series_id": "DEXUSEU",
     "unit": "", "decimals": 4, "tone": "fx", "color": "#67d7ff", "step": "W",
     "subtitle": "Euro vs US dollar spot exchange rate"},
    {"id": "gas", "label": "EU Natural Gas", "series_id": "PNGASEUUSDM",
     "unit": "USD", "decimals": 1, "tone": "energy", "color": "#ff9d6b",
     "subtitle": "EU natural gas (TTF proxy) — a key German industrial input"},
]

# Reference lines shown on the hero chart for the relevant indicators.
REF_LINES: dict[str, list[dict]] = {
    "hicp": [{"value": 2.0, "label": "2% target"}],
    "hicp_core": [{"value": 2.0, "label": "2% target"}],
    "curve": [{"value": 0.0, "label": "inversion line"}],
}

INDICATORS: list[dict] = [
    {"series_id": "DE10Y", "title": "German 10Y Bund Yield", "unit": "percent",
     "frequency": "D", "country": "DE", "category": "yield"},
    {"series_id": "DE5Y", "title": "German 5Y Bund Yield", "unit": "percent",
     "frequency": "D", "country": "DE", "category": "yield"},
    {"series_id": "DE2Y", "title": "German 2Y Bund Yield", "unit": "percent",
     "frequency": "D", "country": "DE", "category": "yield"},
    {"series_id": "ECBDFR", "title": "ECB Deposit Facility Rate", "unit": "percent",
     "frequency": "D", "country": "EA", "category": "policy_rate"},
    {"series_id": "ECB_MRO", "title": "ECB Main Refinancing Rate", "unit": "percent",
     "frequency": "D", "country": "EA", "category": "policy_rate"},
    {"series_id": "ECB_MLF", "title": "ECB Marginal Lending Rate", "unit": "percent",
     "frequency": "D", "country": "EA", "category": "policy_rate"},
    {"series_id": "ECB_HICP", "title": "EA HICP YoY", "unit": "percent",
     "frequency": "M", "country": "EA", "category": "inflation"},
    {"series_id": "ECB_HICP_CORE", "title": "EA Core HICP YoY", "unit": "percent",
     "frequency": "M", "country": "EA", "category": "inflation"},
    {"series_id": "ECB_UNRATE", "title": "EA Unemployment Rate", "unit": "percent",
     "frequency": "M", "country": "EA", "category": "labor"},
    {"series_id": "DEXUSEU", "title": "EUR/USD Spot", "unit": "USD per EUR",
     "frequency": "D", "country": "US", "category": "fx"},
    {"series_id": "PNGASEUUSDM", "title": "EU Natural Gas (TTF proxy)", "unit": "USD/mmBtu",
     "frequency": "M", "country": "US", "category": "commodity"},
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _connect() -> psycopg.Connection:
    return psycopg.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=READER_USER, password=READER_PASSWORD,
    )


def _rows(conn: psycopg.Connection, sql: str, params=None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _iso(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _warehouse_build(conn: psycopg.Connection) -> str | None:
    r = conn.execute(
        "SELECT max(known_at)::text FROM marts.fct_macro_observation_latest"
    ).fetchone()
    return r[0] if r else None


def _fetch_observations(conn, series_id: str, start: date | None, end: date | None) -> list[tuple[date, float]]:
    sql = """
        SELECT obs_date, value
        FROM marts.fct_macro_observation_latest
        WHERE series_id = %s
          AND (%s::date IS NULL OR obs_date >= %s)
          AND (%s::date IS NULL OR obs_date <= %s)
        ORDER BY obs_date
    """
    rows = _rows(conn, sql, [series_id, start, start, end, end])
    return [(r["obs_date"], float(r["value"])) for r in rows]


def _resample(points: list[tuple[date, float]], step: str | None) -> list[tuple[date, float]]:
    """Downsample to period-end (last observation in each bucket)."""
    if not step or step.upper() == "D":
        return points
    step = step.upper()
    buckets: dict[date, tuple[date, float]] = {}
    for d, v in points:
        if step == "W":
            # ISO week start (Monday)
            key = d - timedelta(days=d.weekday())
        elif step == "M":
            key = date(d.year, d.month, 1)
        elif step == "Q":
            key = date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)
        elif step == "Y":
            key = date(d.year, 1, 1)
        else:
            raise HTTPException(status_code=400, detail=f"unknown step '{step}'")
        buckets[key] = (d, v)
    return sorted(buckets.values())


# --- PCHIP (monotone cubic Hermite) interpolation ---------------------------
def _pchip_slopes(xs: list[float], ys: list[float]) -> list[float]:
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n

    def endpoint(h0, h1, d0, d1):
        mm = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if mm * d0 < 0:
            mm = 0.0
        elif d0 * d1 < 0 and abs(mm) > 3 * abs(d0):
            mm = 3 * d0
        return mm

    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1 = 2 * h[i] + h[i - 1]
            w2 = h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    m[0] = endpoint(h[0], h[1], d[0], d[1])
    m[-1] = endpoint(h[-1], h[-2], d[-1], d[-2])
    return m


def _pchip_eval(xs: list[float], ys: list[float], m: list[float], xq: float) -> float:
    i = bisect.bisect_right(xs, xq) - 1
    if i < 0:
        i = 0
    if i >= len(xs) - 1:
        i = len(xs) - 2
    h = xs[i + 1] - xs[i]
    t = (xq - xs[i]) / h
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def _interp_tenors(anchor_vals: list[float]) -> list[float]:
    ax = [a["maturity"] for a in CURVE_ANCHORS]
    m = _pchip_slopes(ax, anchor_vals)
    return [round(_pchip_eval(ax, anchor_vals, m, t["maturity"]), 4) for t in CURVE_TENORS]


def _month_ends(start: date, end: date) -> list[date]:
    out: list[date] = []
    y, mth = start.year, start.month
    while True:
        d = date(y, mth, 1)
        d = date(d.year, d.month, 1) + timedelta(days=32)
        d = date(d.year, d.month, 1) - timedelta(days=1)
        if d > end:
            break
        if d >= start:
            out.append(d)
        y, mth = (y + 1, 1) if mth == 12 else (y, mth + 1)
    return out


def _nearest_index(dates: list[date], target: date) -> int:
    i = bisect.bisect_right(dates, target) - 1
    return max(0, min(len(dates) - 1, i))


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> dict:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready"}
    except Exception as exc:  # noqa: BLE001 — readiness reports, doesn't crash
        raise HTTPException(status_code=503, detail=f"not ready: {exc}") from exc


@app.get("/api/meta")
def meta() -> dict:
    with _connect() as conn:
        return {
            "warehouse_build": _warehouse_build(conn),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "series_count": _rows(conn, "SELECT count(*) AS n FROM marts.dim_series")[0]["n"],
        }


@app.get("/api/indicators")
def indicators() -> dict:
    return {"data": INDICATORS, "meta": {"row_count": len(INDICATORS)}}


@app.get("/api/observations/{series_id}")
def observations(
    series_id: str,
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    step: str | None = Query(None),
) -> dict:
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="from must be <= to")
    if start and end and (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"date range exceeds {MAX_RANGE_DAYS} days")

    with _connect() as conn:
        series = _rows(conn, "SELECT * FROM marts.dim_series WHERE series_id = %s", [series_id])
        if not series:
            raise HTTPException(status_code=404, detail=f"unknown series_id '{series_id}'")
        pts = _fetch_observations(conn, series_id, start, end)
        wb = _warehouse_build(conn)
    data = [{"date": _iso(d), "value": v} for d, v in _resample(pts, step)]
    return {
        "series": series[0],
        "data": data,
        "meta": {"row_count": len(data), "warehouse_build": wb},
    }


@app.get("/api/snapshot")
def snapshot() -> dict:
    """Headline KPI cards: latest value, 1M / 1Y deltas, sparkline."""
    today = date.today()
    window_start = today - timedelta(days=MAX_RANGE_DAYS)

    with _connect() as conn:
        # Preload every series referenced by a KPI (raw, no resample).
        needed: set[str] = set()
        for k in KPIS:
            if k.get("series_id"):
                needed.add(k["series_id"])
            for s in k.get("spread", []):
                needed.add(s)
        series_map: dict[str, list[tuple[date, float]]] = {}
        for sid in needed:
            series_map[sid] = _fetch_observations(conn, sid, window_start, None)

        kpis: list[dict] = []
        for k in KPIS:
            sid = k.get("series_id")
            spread = k.get("spread")
            factor = k.get("factor", 1)
            if spread:
                a = series_map.get(spread[0], [])
                b = series_map.get(spread[1], [])
                pts = _align_diff(a, b)
            else:
                pts = series_map.get(sid, [])
            pts = [(d, v * factor) for d, v in pts]

            if not pts:
                kpis.append({**k, "value": None, "spark": [], "last_date": None})
                continue

            last_date, last_value = pts[-1]
            spark = [(d.isoformat(), v) for d, v in pts[-260:]]

            d1m = _value_at(pts, last_date - timedelta(days=31))
            d1y = _value_at(pts, last_date - timedelta(days=365))
            kpis.append({
                "id": k["id"],
                "label": k["label"],
                "unit": k.get("unit", ""),
                "decimals": k.get("decimals", 2),
                "tone": k.get("tone"),
                "invert": k.get("invert", False),
                "color": k["color"],
                "subtitle": k["subtitle"],
                "value": round(last_value, k.get("decimals", 2)),
                "last_date": last_date.isoformat(),
                "delta_1m": _delta(last_value, d1m),
                "delta_1y": _delta(last_value, d1y),
                "spark": spark,
            })

        wb = _warehouse_build(conn)
    return {"as_of": max((k["last_date"] for k in kpis if k["last_date"]), default=None),
            "warehouse_build": wb, "kpis": kpis}


def _align_diff(a: list[tuple[date, float]], b: list[tuple[date, float]]) -> list[tuple[date, float]]:
    """Difference a - b, forward-filled onto the union of dates."""
    def ffill_map(pts):
        out, last = {}, None
        for d, v in pts:
            last = v
            out[d] = v
        return out, last

    ma, _ = ffill_map(a)
    mb, _ = ffill_map(b)
    dates = sorted(set(ma) | set(mb))
    last_a = last_b = None
    res = []
    for d in dates:
        if d in ma:
            last_a = ma[d]
        if d in mb:
            last_b = mb[d]
        if last_a is not None and last_b is not None:
            res.append((d, last_a - last_b))
    return res


def _value_at(pts: list[tuple[date, float]], target: date) -> float | None:
    idx = bisect.bisect_right([p[0] for p in pts], target) - 1
    if idx < 0:
        return None
    return pts[idx][1]


def _delta(latest: float, prior: float | None) -> float | None:
    if prior is None:
        return None
    return round(latest - prior, 4)


@app.get("/api/yield-curve")
def yield_curve(
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> dict:
    with _connect() as conn:
        anchor_series: dict[str, list[tuple[date, float]]] = {}
        for a in CURVE_ANCHORS:
            anchor_series[a["series_id"]] = _fetch_observations(conn, a["series_id"], None, None)

        # latest date across anchors — step series (MRO/MLF) are forward-filled
        # past their last change, so take the max (Bund yields / DFR are daily).
        common_last = max((s[-1][0] for s in anchor_series.values() if s), default=None)

    # --- monthly surface grid ------------------------------------------------
    first_common = max((s[0][0] for s in anchor_series.values() if s), default=None)
    grid_start = start or first_common
    grid_end = end or (common_last or date.today())
    grid_dates = _month_ends(grid_start, grid_end)
    # only keep grid dates where every anchor already has an observation
    grid_dates = [d for d in grid_dates if all(s and s[0][0] <= d for s in anchor_series.values())]
    # close the surface at the latest observation so the last column == as_of
    if common_last and (not grid_dates or common_last > grid_dates[-1]):
        grid_dates.append(common_last)

    # per-anchor: sorted (date,value) with last-value lookup (ffill semantics)
    def anchor_value(sid: str, d: date) -> float:
        pts = anchor_series[sid]
        i = bisect.bisect_right([p[0] for p in pts], d) - 1
        return pts[i][1]

    surface: list[list[float]] = []
    for d in grid_dates:
        vals = [anchor_value(a["series_id"], d) for a in CURVE_ANCHORS]
        surface.append(_interp_tenors(vals))

    # --- snapshot curves: latest vs one year ago -----------------------------
    def curve_at(d: date) -> list[dict]:
        vals = [anchor_value(a["series_id"], d) for a in CURVE_ANCHORS]
        ys = _interp_tenors(vals)
        return [{"label": t["label"], "maturity": t["maturity"], "value": ys[i]}
                for i, t in enumerate(CURVE_TENORS)]

    latest_curve = curve_at(common_last)
    one_year_ago_date = grid_dates[_nearest_index(grid_dates, common_last - timedelta(days=365))]
    one_year_ago_curve = curve_at(one_year_ago_date)

    # anchor points on the snapshot curve (real rates, not interpolated)
    latest_anchors = [{"label": a["label"], "maturity": a["maturity"],
                       "value": anchor_value(a["series_id"], common_last)}
                      for a in CURVE_ANCHORS]

    return {
        "as_of": common_last.isoformat(),
        "one_year_ago": one_year_ago_date.isoformat(),
        "anchors": CURVE_ANCHORS,
        "tenors": CURVE_TENORS,
        "dates": [d.isoformat() for d in grid_dates],
        "surface": surface,
        "latest": latest_curve,
        "latest_anchors": latest_anchors,
        "one_year_ago_curve": one_year_ago_curve,
        "meta": {"tenor_count": len(CURVE_TENORS), "date_count": len(grid_dates)},
    }


@app.get("/api/indicator/{kpi_id}")
def indicator_history(kpi_id: str, step: str | None = Query(None)) -> dict:
    """Full history for one KPI tile — drives the big hero chart."""
    k = next((x for x in KPIS if x["id"] == kpi_id), None)
    if not k:
        raise HTTPException(status_code=404, detail=f"unknown indicator '{kpi_id}'")

    start = date.today() - timedelta(days=MAX_RANGE_DAYS)
    with _connect() as conn:
        if k.get("spread"):
            a = _fetch_observations(conn, k["spread"][0], start, None)
            b = _fetch_observations(conn, k["spread"][1], start, None)
            pts = _align_diff(a, b)
            pts = [(d, v * k.get("factor", 1)) for d, v in pts]
        else:
            pts = _fetch_observations(conn, k["series_id"], start, None)
        wb = _warehouse_build(conn)

    eff_step = step if step is not None else k.get("step")
    data = [{"date": _iso(d), "value": round(v, 6)} for d, v in _resample(pts, eff_step)]
    return {
        "id": k["id"],
        "label": k["label"],
        "subtitle": k["subtitle"],
        "unit": k.get("unit", ""),
        "decimals": k.get("decimals", 2),
        "tone": k.get("tone"),
        "color": k["color"],
        "as_of": data[-1]["date"] if data else None,
        "ref": REF_LINES.get(k["id"], []),
        "data": data,
        "meta": {"row_count": len(data), "warehouse_build": wb},
    }


# --- static dashboard (mounted last so /api/* wins) --------------------------
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
