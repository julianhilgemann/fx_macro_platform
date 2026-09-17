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
  GET /api/yield-curve             Bund curve, real tenors 0.5y..30y (Bundesbank
                                   BBSIS term structure) + snapshot curve

The Bund curve is real data at every tenor: the Bundesbank BBSIS Svensson term
structure, one series per residual maturity (0.5y, then 1..30y), daily from
2000. Nothing on that card is interpolated. The observed yields of the actual
on-the-run bonds (Bundesbank BBSSY: 2y/5y/10y) ride along as dots, so the fitted
curve and the traded bonds can be compared rather than blended.
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

# The Bund curve is real data at every tenor: the Bundesbank BBSIS Svensson term
# structure, one series per residual maturity — a 0.5y bucket then 1..30y. The
# series ids mirror `ingest.config.BUND_TERM_STRUCTURE`, which mints the same
# labels; nothing here is interpolated any more.
CURVE_TENORS: list[dict] = (
    [{"label": "6M", "maturity": 0.5, "series_id": "DE_TS_6M"}]
    + [{"label": f"{m}Y", "maturity": float(m), "series_id": f"DE_TS_{m}Y"}
       for m in range(1, 31)]
)

# Observed yields of the actual on-the-run bonds (Bundesbank BBSSY) — a
# different measure from the fitted curve above, drawn as dots so the two can be
# compared rather than blended.
CURVE_ANCHORS: list[dict] = [
    {"series_id": "DE2Y", "label": "2Y", "maturity": 2.0, "kind": "observed"},
    {"series_id": "DE5Y", "label": "5Y", "maturity": 5.0, "kind": "observed"},
    {"series_id": "DE10Y", "label": "10Y", "maturity": 10.0, "kind": "observed"},
]

# The ECB policy corridor: deposit facility (floor) · main refinancing (mid) ·
# marginal lending (ceiling). Every leg is a change-point series — a rate holds
# until the governing council moves it — which is what makes the ribbon between
# floor and ceiling mean something: the corridor is as wide as the current stance
# and nothing wider. `/api/snapshot` and `/api/indicator/{id}` ship these legs so
# the tile sparkline and the big chart can both draw the corridor itself.
CORRIDOR_LEGS: list[dict] = [
    {"role": "floor", "series_id": "ECBDFR"},
    {"role": "mid", "series_id": "ECB_MRO"},
    {"role": "ceiling", "series_id": "ECB_MLF"},
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
    {"id": "ecb", "label": "ECB Policy Corridor", "series_id": "ECBDFR",
     "unit": "%", "decimals": 2, "tone": "rate", "color": "#ff7aa2", "step": "W",
     "corridor": True,
     "subtitle": "Deposit facility (floor) · MRO (main rate) · marginal lending (ceiling)"},
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
] + [
    # the curve family the snapshot card reads — generated from CURVE_TENORS so
    # the catalogue can never drift from the chart
    {"series_id": t["series_id"], "title": f"German Bund Term Structure {t['label']}",
     "unit": "percent", "frequency": "D", "country": "DE", "category": "yield"}
    for t in CURVE_TENORS
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


def _corridor(conn, step: str | None = None, start: date | None = None) -> list[dict]:
    """The three corridor legs as one payload.

    Each leg keeps its own change-point observations — the client forward-fills
    them onto a shared grid to draw the ribbon, so no synthetic rows are minted
    here. `start` trims the tile sparkline window; the last observation *before*
    the window is kept so the level is defined at its left edge.
    """
    legs: list[dict] = []
    for leg in CORRIDOR_LEGS:
        pts = _fetch_observations(conn, leg["series_id"], start, None)
        if start:
            prior = _rows(
                conn,
                """SELECT obs_date, value FROM marts.fct_macro_observation_latest
                   WHERE series_id = %s AND obs_date < %s
                   ORDER BY obs_date DESC LIMIT 1""",
                [leg["series_id"], start],
            )
            if prior:
                pts = [(prior[0]["obs_date"], float(prior[0]["value"]))] + pts
        legs.append({
            "role": leg["role"],
            "series_id": leg["series_id"],
            "values": [[_iso(d), round(v, 6)] for d, v in _resample(pts, step)],
        })
    return legs


# --- calendar helpers --------------------------------------------------------
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
            card = {
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
            }
            if k.get("corridor"):
                # same window as the sparkline, so the ribbon sits under it exactly
                card["corridor"] = _corridor(conn, None, start=pts[-260][0])
            kpis.append(card)

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
    """The Bund curve, read straight off the BBSIS term structure.

    Every tenor is a real observation, so there is no interpolation anywhere in
    this route: `latest` is the curve as of the newest date any tenor carries,
    and the one-year-ago curve is the same 31 tenors a year earlier. The monthly
    `surface` is the same data on month-ends (forward-filled), kept for the API
    contract. `latest_anchors` are the observed BBSSY bond yields — a different
    measure from the fitted curve, shipped for comparison.
    """
    with _connect() as conn:
        tenor_series: dict[str, list[tuple[date, float]]] = {
            t["series_id"]: _fetch_observations(conn, t["series_id"], None, None)
            for t in CURVE_TENORS
        }
        anchor_series: dict[str, list[tuple[date, float]]] = {
            a["series_id"]: _fetch_observations(conn, a["series_id"], None, None)
            for a in CURVE_ANCHORS
        }

    common_last = max((s[-1][0] for s in tenor_series.values() if s), default=None)
    if common_last is None:
        raise HTTPException(status_code=503, detail="no term-structure observations in the warehouse")
    first_common = max((s[0][0] for s in tenor_series.values() if s), default=None)

    # last value at or before `d` (policy/curve series hold between prints)
    def value_at(sid: str, d: date) -> float | None:
        pts = tenor_series.get(sid) or []
        i = bisect.bisect_right([p[0] for p in pts], d) - 1
        return pts[i][1] if i >= 0 else None

    def observed_at(sid: str, d: date) -> float | None:
        pts = anchor_series.get(sid) or []
        i = bisect.bisect_right([p[0] for p in pts], d) - 1
        return pts[i][1] if i >= 0 else None

    def curve_at(d: date) -> list[dict]:
        return [{"label": t["label"], "maturity": t["maturity"],
                 "series_id": t["series_id"], "value": value_at(t["series_id"], d)}
                for t in CURVE_TENORS]

    latest_curve = curve_at(common_last)
    one_year_ago_date = common_last - timedelta(days=365)
    one_year_ago_curve = curve_at(one_year_ago_date)

    # --- monthly surface grid (real tenors, forward-filled) ------------------
    grid_start = start or first_common or one_year_ago_date
    grid_end = end or common_last
    grid_dates = [d for d in _month_ends(grid_start, grid_end) if d >= (first_common or grid_start)]
    if not grid_dates or common_last > grid_dates[-1]:
        grid_dates.append(common_last)

    surface: list[list[float | None]] = [
        [value_at(t["series_id"], d) for t in CURVE_TENORS] for d in grid_dates
    ]

    latest_anchors = [
        {"label": a["label"], "maturity": a["maturity"],
         "value": observed_at(a["series_id"], common_last)}
        for a in CURVE_ANCHORS
    ]

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
        "source": "Bundesbank BBSIS (Svensson term structure, daily)",
        "meta": {"tenor_count": len(CURVE_TENORS), "date_count": len(grid_dates),
                 "interpolated_tenors": 0},
    }


@app.get("/api/indicator/{kpi_id}")
def indicator_history(kpi_id: str, step: str | None = Query(None)) -> dict:
    """Full history for one KPI tile — drives the big hero chart."""
    k = next((x for x in KPIS if x["id"] == kpi_id), None)
    if not k:
        raise HTTPException(status_code=404, detail=f"unknown indicator '{kpi_id}'")

    start = date.today() - timedelta(days=MAX_RANGE_DAYS)
    eff_step = step if step is not None else k.get("step")
    with _connect() as conn:
        if k.get("spread"):
            a = _fetch_observations(conn, k["spread"][0], start, None)
            b = _fetch_observations(conn, k["spread"][1], start, None)
            pts = _align_diff(a, b)
            pts = [(d, v * k.get("factor", 1)) for d, v in pts]
        else:
            pts = _fetch_observations(conn, k["series_id"], start, None)
        corridor = _corridor(conn, eff_step, start=start) if k.get("corridor") else []
        wb = _warehouse_build(conn)

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
        "corridor": corridor,
        "meta": {"row_count": len(data), "warehouse_build": wb},
    }


# --- static dashboard (mounted last so /api/* wins) --------------------------
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
