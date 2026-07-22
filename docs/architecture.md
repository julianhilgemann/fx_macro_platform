# Architecture — v1 vertical slice

One thread, end to end: **fetch → immutable raw → load → DuckDB → dbt → FastAPI**.

```
FRED (json) + Bundesbank (csv) + ECB SDW (csv)   (or synthetic generator when no key)
      │  ingest/fetch.py     (per-source client, verbatim body stored)
      ▼
Immutable raw on disk        raw/{source}/{series_id}/{fetch_ts}.{json|csv}
      │  ingest/load.py  (dumb, re-runnable, idempotent on grain; parses by extension)
      ▼
DuckDB: raw_observations             one row per (source, series_id, ref_period, fetch_ts)
      │  dbt  (dbt/models)
      ├─ staging       stg_fred__observations   typed, renamed, 1:1, +surrogate key
      ├─ intermediate  int_series_latest_vintage latest-known-as-of resolution
      │                int_daily_panel           pivot + daily spine + forward-fill + differentials
      ▼
      mart             mart_series               long, latest-vintage  (API contract)
                       mart_eurusd_panel         daily EUR/USD + differentials (API contract)
      │  api/main.py  (FastAPI, read-only)
      ▼
Dataframe out (JSON records)
```

## Two non-negotiable invariants

1. **Raw is append-only and immutable.** Every response is stored verbatim, keyed
   by `fetch_timestamp`. Re-fetching a reference period later writes a *new* raw
   record, never an update. The loader's `INSERT OR IGNORE` on the grain
   `(source, series_id, reference_period, fetch_timestamp)` enforces this — old
   grains are never touched, new fetch timestamps append.
2. **Vintage-aware from day one.** `reference_period`, `fetch_timestamp`, and
   `value` are distinct columns and never collapsed. "What was known as of date X"
   is answerable by filtering on `fetch_timestamp`; `int_series_latest_vintage`
   resolves the current best value as the row with the max `fetch_timestamp` per
   `(series_id, reference_period)`.

## Boundary note

dbt does **not** fetch. Ingestion (fetch + raw + load) is plain Python. dbt's
`source` is the already-landed `raw_observations` DuckDB table. Do not push
ingestion into dbt.

## Seams left deliberately open (installed: nothing)

| Seam                | v1 choice        | Later                                   |
|---------------------|------------------|-----------------------------------------|
| Fetch sources       | FRED + Bundesbank + ECB SDW (3 parsers) | more series / pairs |
| Fetch mode          | synthetic / live | more series; ALFRED realtime windows    |
| Orchestration       | `run_pipeline.sh` + cron | Dagster/Prefect                 |
| Analytical DB       | DuckDB (file)    | Postgres when read/write contends       |
| Raw storage         | local disk       | Cloudflare R2                           |
| Serving             | FastAPI, localhost | auth + Cloudflare Tunnel              |
| Packaging           | local uv venv    | Docker + compose (Linux amd64)          |

## The synthetic seam

`FX_FETCH_MODE` selects the fetch path in `ingest/fetch.py`. `synthetic` emits
FRED-shaped payloads (same JSON the parser consumes for real data), so raw →
load → dbt → API is identical whether data is synthetic or real. Trailing points
carry a fetch-date-seeded revision, so re-running produces a genuinely new
vintage — the point-in-time archive is exercised without a key. Swap to `fred`
by putting `FRED_API_KEY` in `.env`; no downstream code changes.
