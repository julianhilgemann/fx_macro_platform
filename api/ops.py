"""Owner-only ops router — the only write/trigger surface (spec §10).

Spec §10: *"Owner-only endpoints (anything that triggers work rather than reads
data) live on a separate router behind a single API key header, compared with
secrets.compare_digest. At single-operator scale this is sufficient. Never mount
such a router under /v1."*

So this router sits at ``/ops`` and every route requires ``X-Ops-Key``:

    GET  /ops/health                    → API↔Dagster connectivity
    GET  /ops/series                    → catalog + freshness for the refresh UI
    GET  /ops/jobs                      → the triggerable jobs
    POST /ops/refresh/{series_id}       → queue a single-series refresh
    POST /ops/refresh-all               → queue the full ingest + dbt pipeline
    GET  /ops/runs/{run_id}             → run status + event log (poll target)
    POST /ops/runs/{run_id}/terminate   → cancel a run

The API stays read-only over the warehouse: it never writes data and never runs
ingest/dbt itself. It asks Dagster for a run and reports the outcome — Dagster
remains the single orchestrator (spec §8).
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from api import dagster_client as dg
from ingest.config import SERIES, PG_DB, PG_HOST, PG_PORT, READER_PASSWORD, READER_USER

#: Shared secret for the owner-only router. Fails closed: if unset, every request
#: is rejected rather than silently open. The dev default lives in
#: docker-compose.yml / .env.example, never in committed real values.
OPS_API_KEY: str | None = os.getenv("OPS_API_KEY") or None

# --- auth ------------------------------------------------------------------

def require_key(x_ops_key: str | None = Header(default=None, alias="X-Ops-Key")) -> None:
    """Constant-time check of the owner key (spec §10)."""
    if not OPS_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OPS_API_KEY is not configured on the API service; "
                   "trigger endpoints are disabled",
        )
    if not x_ops_key or not secrets.compare_digest(x_ops_key, OPS_API_KEY):
        raise HTTPException(status_code=401, detail="invalid or missing X-Ops-Key")


#: Job names as registered in orchestration/definitions.py.
SERIES_JOB = "refresh_series_job"
FULL_JOB = "full_refresh"

router = APIRouter(prefix="/ops", tags=["ops"], dependencies=[Depends(require_key)])

#: How long a blocking (?wait=true) call will poll before giving up.
WAIT_TIMEOUT_S = float(os.getenv("OPS_WAIT_TIMEOUT", "900"))
WAIT_POLL_S = 2.0


# --- warehouse reads (catalog + freshness) ---------------------------------

def _connect():
    import psycopg

    return psycopg.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                           user=READER_USER, password=READER_PASSWORD)


def catalog_with_freshness() -> list[dict]:
    """Every configured series with its warehouse freshness (one round trip).

    Reads only ``marts`` as ``platform_reader``, same as the rest of the API.
    """
    sql = """
        SELECT s.series_id,
               s.title,
               s.frequency,
               s.category,
               s.country,
               f.last_obs_date,
               f.last_known_at,
               f.n_obs
        FROM marts.dim_series s
        LEFT JOIN (
            SELECT series_id,
                   max(obs_date)  AS last_obs_date,
                   max(known_at)  AS last_known_at,
                   count(*)       AS n_obs
            FROM marts.fct_macro_observation_latest
            GROUP BY series_id
        ) f USING (series_id)
        ORDER BY s.series_id
    """
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:  # noqa: BLE001 — the freshness join is a nicety, not required
        rows = []

    known = {r["series_id"]: r for r in rows}
    out: list[dict] = []
    for s in SERIES:
        r = known.get(s.series_id, {})
        out.append(
            {
                "series_id": s.series_id,
                "source": s.source,
                "frequency": s.frequency,
                "title": r.get("title") or "",
                "unit": "",
                "category": r.get("category") or "",
                "country": r.get("country") or "",
                "last_obs_date": _as_date(r.get("last_obs_date")),
                "last_known_at": _as_date(r.get("last_known_at")),
                "n_obs": r.get("n_obs"),
                "in_warehouse": bool(r),
                "triggerable": True,
            }
        )
    return out


def _as_date(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


# --- models ----------------------------------------------------------------

class SubmitResponse(BaseModel):
    run_id: str
    job_name: str
    status: str
    series_id: str | None = None
    message: str = "queued"
    dagster_url: str = ""


class RunStatusResponse(BaseModel):
    run_id: str
    job_name: str | None = None
    status: str
    is_running: bool
    ok: bool
    start_time: str | None = None
    end_time: str | None = None
    steps_succeeded: int | None = None
    steps_failed: int | None = None
    dagster_url: str = ""
    events: list[dict] = []


# --- trigger endpoints ------------------------------------------------------

@router.get("/health")
def ops_health() -> dict:
    """API → Dagster reachability, for the UI's 'can I refresh?' badge.

    Requires the owner key (this is an ops route, not a public one), so a 200
    means both the key and the Dagster connection are good.
    """
    return {
        "dagster": dg.health(),
        "jobs": {"series": SERIES_JOB, "full": FULL_JOB},
    }


@router.get("/series")
def ops_series() -> dict:
    return {
        "data": catalog_with_freshness(),
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_series": len(SERIES),
            "sources": sorted({s.source for s in SERIES}),
        },
    }


@router.post("/refresh/{series_id}", response_model=SubmitResponse)
def refresh_series(
    series_id: str,
    wait: bool = Query(default=False, description="block until the run finishes"),
) -> SubmitResponse:
    """Queue a single-series refresh: ingest that series, then the dbt transform."""
    series = next((s for s in SERIES if s.series_id == series_id), None)
    if series is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown series_id '{series_id}' — not in ingest.config.SERIES",
        )
    run_config = {"ops": {"ingest_one_series": {"config": {"series_id": series_id}}}}
    try:
        run = dg.launch_run(
            SERIES_JOB,
            run_config=run_config,
            tags={"trigger": "ops-api", "series_id": series_id, "source": series.source},
        )
    except dg.DagsterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _submit(run, series_id=series_id, wait=wait)


@router.post("/refresh-all", response_model=SubmitResponse)
def refresh_all(
    wait: bool = Query(default=False, description="block until the run finishes"),
) -> SubmitResponse:
    """Queue the full pipeline: every ingest source, then the full dbt build."""
    try:
        run = dg.launch_run(FULL_JOB, tags={"trigger": "ops-api", "scope": "all"})
    except dg.DagsterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _submit(run, series_id=None, wait=wait)


def _submit(run: dict, series_id: str | None, wait: bool) -> SubmitResponse:
    run_id = run.get("run_id")
    if not run_id:
        raise HTTPException(status_code=502, detail="Dagster returned no run id")
    message = "queued"
    if wait:
        final = _wait_for(run_id)
        message = f"finished with status {final['status']}"
    return SubmitResponse(
        run_id=run_id,
        job_name=run.get("job_name", ""),
        status=run.get("status", "QUEUED"),
        series_id=series_id,
        message=message,
        dagster_url=f"{dg.DAGSTER_URL}/runs/{run_id}",
    )


def _wait_for(run_id: str) -> dict:
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    while True:
        st = dg.run_status(run_id, include_events=False)
        if not st["is_running"]:
            return st
        if time.monotonic() > deadline:
            raise HTTPException(
                status_code=504,
                detail=f"run {run_id} still running after {WAIT_TIMEOUT_S:.0f}s; "
                       "poll GET /ops/runs/{run_id} instead",
            )
        time.sleep(WAIT_POLL_S)


@router.get("/runs", response_model=list[dict])
def runs(
    limit: int = Query(default=15, ge=1, le=100),
) -> list[dict]:
    """Recent triggerable runs — the UI's run history."""
    try:
        return dg.list_runs(limit=limit, job_names=[SERIES_JOB, FULL_JOB])
    except dg.DagsterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def run_detail(
    run_id: str,
    events: bool = Query(default=True, description="include the step event log"),
) -> RunStatusResponse:
    try:
        return RunStatusResponse(**dg.run_status(run_id, include_events=events))
    except dg.DagsterError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/terminate")
def terminate(run_id: str) -> dict:
    try:
        return dg.terminate_run(run_id)
    except dg.DagsterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
