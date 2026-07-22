# FX Macro Data Platform

Point-in-time macro/FX data platform. Ingests FRED/ALFRED data, stores it
**append-only as as-reported vintages**, transforms with dbt, and serves curated
dataframes over FastAPI.

This is the **v1 vertical slice**: one pair (EUR/USD), one source (FRED), ~5–7
series, running one thread end to end — `fetch → immutable raw → load → DuckDB →
dbt → API`. See [`fx-macro-platform-spec.md`](fx-macro-platform-spec.md) for the
full blueprint and [`docs/architecture.md`](docs/architecture.md) for the data flow.

> **Runs with no API key today.** `FX_FETCH_MODE=synthetic` (the default when no
> `FRED_API_KEY` is set) generates deterministic FRED-shaped data so the whole
> pipeline stands up end-to-end. Swap in a real key to switch to live FRED — no
> downstream code changes.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (manages the venv, a pinned Python 3.12, and deps)

## Setup

```bash
uv sync                 # creates .venv, installs pinned deps + the project
cp .env.example .env    # optional; defaults already run in synthetic mode
```

## Run the pipeline (synthetic data)

```bash
./scripts/run_pipeline.sh
```

This fetches all series to immutable raw JSON, loads DuckDB, then runs `dbt run`
+ `dbt test`. Re-running creates **new** raw records (new `fetch_timestamp`)
without overwriting or duplicating prior grain.

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

## Switching to real FRED

1. Get a free key: <https://fred.stlouisfed.org/docs/api/api_key.html>
2. In `.env`: set `FRED_API_KEY=...` and `FX_FETCH_MODE=fred`.
3. Confirm the series IDs flagged `verify_id=True` in
   [`ingest/config.py`](ingest/config.py) (ECB rate, German 2Y/10Y — the German
   2Y is a placeholder pending the exact FRED id).
4. `./scripts/run_pipeline.sh`

## Layout

```
ingest/     config (series registry) · fetch (raw JSON) · parse (Pydantic) · load (DuckDB)
dbt/        staging → intermediate → mart, with tests
api/        FastAPI, reads mart only
raw/        append-only JSON store        (gitignored)
warehouse/  fx_macro.duckdb               (gitignored)
scripts/    run_pipeline.sh — the cron target
```

## Local acceptance criteria

1. `scripts/run_pipeline.sh` runs clean; `dbt run` + `dbt test` pass. ✅
2. Re-running creates new raw records without overwriting/duplicating grain. ✅
3. `/panel` returns a sane EUR/USD + differentials dataframe. ✅
4. One passing pytest on the parser. ✅
5. *(deferred)* `docker-compose up` + volume persistence — containerization is last.
