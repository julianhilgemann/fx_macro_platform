# FX Macro Data Platform

A long-lived data platform for macroeconomic and FX time series. Raw external
responses are immutable, series revisions are preserved as vintages, and the
whole thing is rebuildable from raw by re-running dbt.

**Single source of truth:** [`platform-spec.md`](platform-spec.md). It is the
architecture spec and the build contract; everything else defers to it.
The working delta list is [`docs/migration-plan.md`](docs/migration-plan.md),
and environment gotchas for agents live in [`agents/notes.md`](agents/notes.md).

## Status

| Stage | State |
|---|---|
| M0 — Postgres + Compose + schemas + roles | ✅ done |
| M1 — Dagster orchestration (ingest assets + dbt assets + schedule) | ✅ done |
| M2–M3 — dbt → marts, FastAPI (all Postgres) | ✅ done |
| M4+ — Astro chart, Metabase, Elementary, k3s/Tailscale | ⏳ pending |

The pipeline is now **Postgres + Dagster** end-to-end (the earlier DuckDB slice was retired).

## Quick start

```bash
make up                       # Postgres 16 via Docker Compose (host port 5433)
cp .env.example .env          # set FRED_API_KEY for live mode (else synthetic)
./scripts/run_pipeline.sh     # fetch -> raw.source_fetch -> dbt seed/run/test
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Interactive API docs at <http://127.0.0.1:8000/docs>.

## Orchestration (Dagster)

```bash
uv run dagster dev -m orchestration.definitions   # UI at http://127.0.0.1:3000
```

The asset graph (spec §8): `raw_fred` / `raw_ecb` / `raw_bundesbank` (ingest) →
`stg_*` → `int_macro__observations_unioned` → `fct_macro_observation` (+`_latest`)
and `dim_series`; the `series_catalog` seed feeds `dim_series`. A daily schedule
runs the whole thing at 06:00 Europe/Berlin. In the UI: **Assets** for the graph,
**Runs** for execution history, **Overview → Schedules** for the schedule.

## API (spec §10)

All endpoints return the `{data, meta}` envelope:

- `GET /health`, `GET /ready`
- `GET /v1/series` — catalog, filterable by `country`/`category`/`frequency`
- `GET /v1/series/{series_id}` — series metadata
- `GET /v1/series/{series_id}/observations?from=&to=&as_of=`
- `GET /v1/observations?series_ids=a,b,c&from=&to=&as_of=`
- `GET /v1/meta/freshness` — last observation and last known date per series

The API connects as `platform_reader` and reads `marts`/`meta` only.

## Data sources

- **FRED** (spot, US rates/yields, ECB deposit rate) — free key required; vintage
  (`known_at`) taken from each observation's `realtime_start`.
- **Bundesbank** (daily German 2Y/10Y Bund yields) — no key.
- **ECB SDW / Data Portal** (ECB policy corridor) — no key.

Upstream endpoints and response shapes are documented in
[`docs/api-calls.md`](docs/api-calls.md).

## Layout

```
ingest/     fetch clients -> Postgres raw.source_fetch (spec §5)
dbt/        staging -> intermediate -> marts (Postgres), series_catalog seed
api/        FastAPI read layer over marts (platform_reader)
sql/        001_init.sh — roles, databases, schemas, raw landing table
agents/     environment facts + gotchas for agentic builds
docs/       api-calls.md · migration-plan.md
```
