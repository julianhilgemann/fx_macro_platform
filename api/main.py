"""Read-only FastAPI over the dbt mart. Serves dataframes as JSON records.

Reads mart tables only — never raw, never writes. Opens DuckDB read-only.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from ingest.config import DUCKDB_PATH

app = FastAPI(title="FX Macro Data Platform", version="0.1.0")


# --- response models (dataframe row shapes) -------------------------------

class SeriesPoint(BaseModel):
    series_id: str
    reference_period: date
    value: float


class PanelRow(BaseModel):
    reference_period: date
    eurusd_spot: float | None = None
    usd_broad_index: float | None = None
    vix: float | None = None
    # ECB corridor (ceiling / mid / floor)
    ecb_mlf_rate: float | None = None
    ecb_mro_rate: float | None = None
    ecb_policy_rate: float | None = None
    # Fed corridor (range + effective)
    fed_target_upper: float | None = None
    fed_target_lower: float | None = None
    fed_funds_rate: float | None = None
    # yield legs
    us_2y: float | None = None
    us_10y: float | None = None
    de_2y: float | None = None
    de_10y: float | None = None
    # differentials & curve slopes
    diff_2y: float | None = None
    diff_10y: float | None = None
    us_2s10s: float | None = None
    de_2s10s: float | None = None
    policy_rate_spread: float | None = None


# --- helpers ---------------------------------------------------------------

def _connect() -> duckdb.DuckDBPyConnection:
    if not Path(DUCKDB_PATH).exists():
        raise HTTPException(
            status_code=503,
            detail="warehouse not built yet — run scripts/run_pipeline.sh",
        )
    try:
        return duckdb.connect(str(DUCKDB_PATH), read_only=True)
    except duckdb.Error as exc:  # e.g. file locked by a concurrent writer
        raise HTTPException(status_code=503, detail=f"warehouse unavailable: {exc}") from exc


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> list[dict]:
    cur = con.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# --- routes ----------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "warehouse_exists": Path(DUCKDB_PATH).exists()}


@app.get("/series/{series_id}", response_model=list[SeriesPoint])
def get_series(
    series_id: str,
    start: date | None = Query(None, description="inclusive lower bound"),
    end: date | None = Query(None, description="inclusive upper bound"),
) -> list[SeriesPoint]:
    con = _connect()
    try:
        if con.execute(
            "select 1 from mart_series where series_id = ? limit 1", [series_id]
        ).fetchone() is None:
            raise HTTPException(status_code=404, detail=f"unknown series_id '{series_id}'")

        clauses, params = ["series_id = ?"], [series_id]
        if start is not None:
            clauses.append("reference_period >= ?"); params.append(start)
        if end is not None:
            clauses.append("reference_period <= ?"); params.append(end)

        rows = _rows(
            con,
            f"""select series_id, reference_period, value
                from mart_series
                where {' and '.join(clauses)}
                order by reference_period""",
            params,
        )
    finally:
        con.close()
    return [SeriesPoint(**r) for r in rows]


@app.get("/panel", response_model=list[PanelRow])
def get_panel(
    start: date | None = Query(None, description="inclusive lower bound"),
    end: date | None = Query(None, description="inclusive upper bound"),
) -> list[PanelRow]:
    con = _connect()
    try:
        clauses, params = [], []
        if start is not None:
            clauses.append("reference_period >= ?"); params.append(start)
        if end is not None:
            clauses.append("reference_period <= ?"); params.append(end)
        where = (" where " + " and ".join(clauses)) if clauses else ""
        rows = _rows(
            con,
            f"select * from mart_eurusd_panel{where} order by reference_period",
            params,
        )
    finally:
        con.close()
    return [PanelRow(**r) for r in rows]
