# FX Macro Data Platform

A long-lived data platform for macroeconomic and FX time series. Raw external
responses are immutable, series revisions are preserved as vintages, and the
whole thing is rebuildable from raw by re-running dbt.

**Single source of truth:** [`platform-spec.md`](platform-spec.md). It is the
architecture spec, the build contract, and the ground truth for implementation.
Everything else in this repo defers to it.

## Status

- **Target (v2):** Postgres warehouse · Dagster orchestration · dbt + Elementary ·
  FastAPI read layer · Metabase → single-node k3s + Tailscale on Hetzner.
  See [`platform-spec.md`](platform-spec.md).
- **Currently running (v1 slice):** a working DuckDB + cron vertical slice —
  fetch → immutable raw → DuckDB → dbt → FastAPI — covering one EUR/USD panel
  across three sources (FRED, Bundesbank, ECB SDW), 13 series.
- **The bridge:** [`docs/migration-plan.md`](docs/migration-plan.md) maps the
  current files onto the v2 target and sequences the M0–M8 milestones.

## Quick start (current v1 slice — superseded by v2)

```bash
uv sync                 # creates .venv, installs pinned deps + the project
cp .env.example .env    # optional; defaults run in synthetic mode
./scripts/run_pipeline.sh   # fetch -> load -> dbt run -> dbt test
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health` — liveness
- `GET /series/{series_id}?start=&end=` — one series as records
- `GET /panel?start=&end=` — the daily EUR/USD + differentials panel

Interactive docs at <http://127.0.0.1:8000/docs>. Tests: `uv run pytest`.

## Data sources

- **FRED** (spot, US rates/yields, ECB deposit rate) — free key required.
- **Bundesbank** (daily German 2Y/10Y Bund yields) — no key.
- **ECB SDW / Data Portal** (ECB policy corridor) — no key.

Upstream endpoints, key structures, and response shapes are documented in
[`docs/api-calls.md`](docs/api-calls.md).

## Layout (current, being reorganized per the migration plan)

```
ingest/     config (series registry) · fetch (FRED json / Bundesbank csv / ECB csv) · parse · load (DuckDB)
dbt/        staging → intermediate → mart, with tests
api/        FastAPI, reads mart only
raw/        append-only raw store (JSON + CSV)  (gitignored)
warehouse/  fx_macro.duckdb                      (gitignored)
docs/       api-calls.md · migration-plan.md
scripts/    run_pipeline.sh — the v1 cron target
```
