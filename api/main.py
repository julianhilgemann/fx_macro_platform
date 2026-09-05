"""Read-only FastAPI over the Postgres marts (spec §10).

Connects as `platform_reader` (SELECT on marts/meta only). Serves observations
from the bitemporal fact with an optional `as_of` parameter. All endpoints return
the `{data, meta}` envelope; query bounds are enforced here (not in SQL).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ingest.config import PG_DB, PG_HOST, PG_PORT, READER_PASSWORD, READER_USER

app = FastAPI(title="FX Macro Data Platform", version="0.2.0")

MAX_PAGE_SIZE = 1000
MAX_SERIES_IDS = 20
MAX_RANGE_DAYS = 50 * 365  # spec §10: max 50 years per request


# --- response models -------------------------------------------------------

class Meta(BaseModel):
    series_ids: list[str] = []
    as_of: str | None = None
    row_count: int = 0
    generated_at: str = ""
    warehouse_build: str | None = None


class SeriesRow(BaseModel):
    series_id: str
    source: str
    source_key: str
    title: str
    description: str
    unit: str
    frequency: str
    seasonal_adj: bool | None = None
    country: str | None = None
    category: str | None = None
    active: bool | None = None


class SeriesEnvelope(BaseModel):
    data: list[SeriesRow]
    meta: Meta


class ObservationRow(BaseModel):
    series_id: str
    obs_date: date
    value: float
    known_at: date | None = None


class ObservationEnvelope(BaseModel):
    data: list[ObservationRow]
    meta: Meta


class FreshnessRow(BaseModel):
    series_id: str
    last_obs_date: date | None = None
    last_known_at: date | None = None


class FreshnessEnvelope(BaseModel):
    data: list[FreshnessRow]
    meta: Meta


# --- helpers ---------------------------------------------------------------

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


def _warehouse_build(conn: psycopg.Connection) -> str | None:
    """Newest vintage present in the warehouse (proxy for the dbt build time)."""
    r = conn.execute(
        "SELECT max(known_at)::text FROM marts.fct_macro_observation_latest"
    ).fetchone()
    return r[0] if r else None


def _meta(conn, series_ids: list[str], as_of: str | None, row_count: int) -> Meta:
    wb = _warehouse_build(conn)
    return Meta(
        series_ids=series_ids,
        as_of=as_of or wb,
        row_count=row_count,
        generated_at=datetime.now(timezone.utc).isoformat(),
        warehouse_build=wb,
    )


def _range_check(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="from must be <= to")
    if start and end and (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"date range exceeds {MAX_RANGE_DAYS} days")


def _observations(conn, series_ids: list[str], start, end, as_of) -> list[dict]:
    """Latest-known observations per (series_id, obs_date), optionally as-of a date."""
    if as_of is not None:
        sql = """
            SELECT DISTINCT ON (series_id, obs_date)
                   series_id, obs_date, known_at, value
            FROM marts.fct_macro_observation
            WHERE series_id = ANY(%s)
              AND (%s::date IS NULL OR obs_date >= %s)
              AND (%s::date IS NULL OR obs_date <= %s)
              AND known_at <= %s::date
            ORDER BY series_id, obs_date, known_at DESC
        """
        params = [series_ids, start, start, end, end, as_of]
    else:
        sql = """
            SELECT series_id, obs_date, known_at, value
            FROM marts.fct_macro_observation_latest
            WHERE series_id = ANY(%s)
              AND (%s::date IS NULL OR obs_date >= %s)
              AND (%s::date IS NULL OR obs_date <= %s)
            ORDER BY series_id, obs_date
        """
        params = [series_ids, start, start, end, end]
    return _rows(conn, sql, params)


# --- routes ----------------------------------------------------------------

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


@app.get("/v1/series", response_model=SeriesEnvelope)
def list_series(
    country: str | None = Query(None),
    category: str | None = Query(None),
    frequency: str | None = Query(None),
    limit: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    clauses, params = [], []
    if country:
        clauses.append("country = %s"); params.append(country)
    if category:
        clauses.append("category = %s"); params.append(category)
    if frequency:
        clauses.append("frequency = %s"); params.append(frequency)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM marts.dim_series{where} ORDER BY series_id LIMIT %s OFFSET %s"
    params += [limit, offset]
    with _connect() as conn:
        data = _rows(conn, sql, params)
        meta = _meta(conn, [r["series_id"] for r in data], None, len(data))
    return SeriesEnvelope(data=data, meta=meta)


@app.get("/v1/series/{series_id}", response_model=SeriesEnvelope)
def get_series(series_id: str):
    with _connect() as conn:
        data = _rows(conn, "SELECT * FROM marts.dim_series WHERE series_id = %s", [series_id])
        if not data:
            raise HTTPException(status_code=404, detail=f"unknown series_id '{series_id}'")
        meta = _meta(conn, [series_id], None, 1)
    return SeriesEnvelope(data=data, meta=meta)


@app.get("/v1/series/{series_id}/observations", response_model=ObservationEnvelope)
def series_observations(
    series_id: str,
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    as_of: date | None = Query(None),
):
    _range_check(start, end)
    with _connect() as conn:
        if not _rows(conn, "SELECT 1 FROM marts.dim_series WHERE series_id = %s", [series_id]):
            raise HTTPException(status_code=404, detail=f"unknown series_id '{series_id}'")
        data = _observations(conn, [series_id], start, end, as_of)
        meta = _meta(conn, [series_id], as_of.isoformat() if as_of else None, len(data))
    return ObservationEnvelope(data=data, meta=meta)


@app.get("/v1/observations", response_model=ObservationEnvelope)
def observations(
    series_ids: str = Query(..., description=f"comma-separated series ids, max {MAX_SERIES_IDS}"),
    start: date | None = Query(None, alias="from"),
    end: date | None = Query(None, alias="to"),
    as_of: date | None = Query(None),
):
    ids = [s.strip() for s in series_ids.split(",") if s.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="series_ids is required")
    if len(ids) > MAX_SERIES_IDS:
        raise HTTPException(status_code=400, detail=f"max {MAX_SERIES_IDS} series_ids per request")
    _range_check(start, end)
    with _connect() as conn:
        data = _observations(conn, ids, start, end, as_of)
        meta = _meta(conn, ids, as_of.isoformat() if as_of else None, len(data))
    return ObservationEnvelope(data=data, meta=meta)


@app.get("/v1/meta/freshness", response_model=FreshnessEnvelope)
def freshness():
    sql = """
        SELECT series_id, max(obs_date) AS last_obs_date, max(known_at) AS last_known_at
        FROM marts.fct_macro_observation_latest
        GROUP BY series_id
        ORDER BY series_id
    """
    with _connect() as conn:
        data = _rows(conn, sql)
        meta = _meta(conn, [r["series_id"] for r in data], None, len(data))
    return FreshnessEnvelope(data=data, meta=meta)
