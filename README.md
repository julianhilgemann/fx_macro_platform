# FX Macro Data Platform

Point-in-time macro/FX data platform. Ingests FRED/ALFRED data, stores it
**append-only as as-reported vintages**, transforms with dbt, and serves curated
dataframes over FastAPI.

This is the **v1 vertical slice**: one pair (EUR/USD), two sources (FRED +
Bundesbank), 7 series, running one thread end to end — `fetch → immutable raw →
load → DuckDB → dbt → API`. See [`fx-macro-platform-spec.md`](fx-macro-platform-spec.md)
for the full blueprint and [`docs/architecture.md`](docs/architecture.md) for the data flow.

**Series** (each yield leg stored separately; dbt computes the differentials):

| Role | Series | Source | Freq |
|------|--------|--------|------|
| EUR/USD spot | `DEXUSEU` | FRED | daily |
| Fed funds rate | `FEDFUNDS` | FRED | monthly |
| ECB deposit rate | `ECBDFR` | FRED | daily |
| US 2Y / 10Y Treasury | `DGS2` / `DGS10` | FRED | daily |
| German 2Y / 10Y Bund | `DE2Y` / `DE10Y` | Bundesbank (BBSSY) | daily |

> **Two fetch modes.** With `FRED_API_KEY` set and `FX_FETCH_MODE=fred`, fetch
> hits the live APIs (FRED needs the key; Bundesbank needs none). With no key,
> `FX_FETCH_MODE=synthetic` generates deterministic FRED-shaped data so the whole
> pipeline still stands up end-to-end. Same raw → load → dbt → API path either way.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages the venv, a pinned Python 3.12, and deps)

## Setup

```bash
uv sync                 # creates .venv, installs pinned deps + the project
cp .env.example .env    # optional; defaults already run in synthetic mode
```

## Run the pipeline

```bash
./scripts/run_pipeline.sh
```

This fetches all series to immutable raw files (FRED → JSON, Bundesbank → CSV),
loads DuckDB, then runs `dbt run` + `dbt test`. Re-running creates **new** raw
records (new `fetch_timestamp`) without overwriting or duplicating prior grain.

## Serve the API

```bash
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

- `GET /health` — liveness
- `GET /series/{series_id}?start=&end=` — one series as records
- `GET /panel?start=&end=` — the daily EUR/USD + differentials panel

```bash
curl 'http://127.0.0.1:8000/health'
curl 'http://127.0.0.1:8000/series/DEXUSEU?start=2026-01-01'
curl 'http://127.0.0.1:8000/panel?start=2026-06-01' | head
```

Interactive docs at <http://127.0.0.1:8000/docs>.

## Tests

```bash
uv run pytest
```

## Data sources

- **FRED** (spot, US rates/yields, ECB rate) — free key required:
  <https://fred.stlouisfed.org/docs/api/api_key.html>. Put it in `.env` as
  `FRED_API_KEY` with `FX_FETCH_MODE=fred`.
- **Bundesbank** (daily German 2Y/10Y Bund yields, BBSSY flow) — no key. FRED has
  no clean daily German 2Y, so this is the second source and the multi-source proof.

Adding a series: append it to `SERIES` in [`ingest/config.py`](ingest/config.py)
(with a `provider_key` if the source's id differs) and add its `series_id` branch
to the panel pivot in `dbt/models/intermediate/int_daily_panel.sql`.

## Layout

```
ingest/     config (series registry) · fetch (FRED json / Bundesbank csv) · parse · load (DuckDB)
dbt/        staging → intermediate → mart, with tests
api/        FastAPI, reads mart only
raw/        append-only raw store (JSON + CSV)  (gitignored)
warehouse/  fx_macro.duckdb                      (gitignored)
scripts/    run_pipeline.sh — the cron target
```

## Local acceptance criteria

1. `scripts/run_pipeline.sh` runs clean; `dbt run` + `dbt test` pass. ✅
2. Re-running creates new raw records without overwriting/duplicating grain. ✅
3. `/panel` returns a sane EUR/USD + differentials dataframe. ✅
4. One passing pytest on the parser. ✅
5. *(deferred)* `docker-compose up` + volume persistence — containerization is last.
