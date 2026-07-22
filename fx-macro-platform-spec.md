# FX Macro Data Platform — Build Blueprint (v0.1)

## Purpose

A long-lived, incrementally-grown data platform that ingests macroeconomic and
FX data, stores it **point-in-time (as-reported vintages)**, transforms it with
dbt, and serves curated data via a FastAPI endpoint that returns dataframes.

This document defines **only the v1 vertical slice**. It is intentionally narrow.
The goal of v1 is to run one thread end-to-end: fetch → immutable raw → load →
dbt → API. Everything else is explicitly out of scope until the slice works.

---

## Non-negotiable design rules

These are the two decisions that are expensive to reverse. Honor them from the
first commit; refactor anything else freely.

1. **Raw layer is append-only and immutable.** Every API response is stored
   verbatim, keyed by fetch timestamp. Never overwrite. Re-fetching the same
   reference period on a later date produces a *new* raw record, not an update.
   This is what makes the point-in-time archive correct by construction.
2. **Vintage-aware from day one.** Macro series get revised. Storage and models
   must be able to answer "what value was known as of date X." Capture
   `reference_period`, `fetch_timestamp`, and `value` as distinct fields; never
   collapse them.

---

## Scope (v1)

### In scope
- **One pair:** EUR/USD.
- **One source:** FRED / ALFRED (single API, single parser, vintage history included).
- **~5 series:** EUR/USD daily spot, ECB policy rate, Fed funds rate, 2Y and 10Y
  Bund–Treasury yields (store each leg separately; compute differentials in dbt).
- Full flow: fetch → append-only raw JSON → loader → DuckDB → dbt
  (staging → intermediate → mart) → FastAPI reads mart → returns dataframe.

### Explicitly OUT of scope for v1 (do not build yet)
- Airflow / any orchestrator (use cron). Wire seams, install nothing.
- Postgres (use DuckDB).
- Auth / API tokens / monetization / website.
- Additional currencies (GBP, JPY later; CNY later as managed-regime contrast case).
- Inflation, GDP, balance sheets, capital flows (tier 2/3, added post-slice).
- ECB SDMX source (added as source #2 to prove multi-source, after slice runs).
- Model calibration / backtesting / VaR (consumes the data layer later).

---

## Tech stack (v1)

| Concern             | Choice                          | Notes |
|---------------------|---------------------------------|-------|
| Language            | Python 3.12+                    | |
| Dependency mgmt     | `uv`                            | Pin everything. Lockfile committed. |
| Fetch               | `requests` (+ `fredapi` optional)| FRED/ALFRED REST. |
| Raw storage         | JSON files on local disk        | Append-only, timestamped keys. |
| Analytical DB       | DuckDB                          | Single file. Serving + curated tables. |
| Transformation      | dbt (`dbt-duckdb`)              | staging → intermediate → mart. |
| API                 | FastAPI + Uvicorn               | Reads mart only. Returns dataframe (JSON/Arrow). |
| Validation          | Pydantic                        | Parsed-record shapes + API response models. |
| DataFrames          | Polars (or pandas)              | Polars pairs well with DuckDB. |
| Tests               | pytest                          | At least one parser test in v1. |
| Scheduling          | cron                            | One line. No orchestrator. |
| Container           | Docker + docker-compose         | Build Linux-deployable from the start. |

**Deliberately deferred:** Airflow/Dagster/Prefect, Postgres, R2/object storage,
Cloudflare Tunnel, auth. Leave clean seams; install none.

---

## Data flow

```
FRED/ALFRED API
      │  (Python fetcher)
      ▼
Immutable raw JSON on disk        ← append-only, keyed by fetch_timestamp
      │  (dumb, re-runnable loader)
      ▼
DuckDB: raw table                 ← dbt source; one row per (series, ref_period, fetch_ts)
      │  dbt
      ├─ staging     (typed, renamed, 1:1 with source)
      ├─ intermediate(differentials, joins, vintage logic)
      ▼
      mart           (curated, stable — the API contract)
      │  FastAPI (read-only)
      ▼
Dataframe out (JSON / Arrow)
```

**Boundary note:** dbt does **not** fetch. Ingestion (fetch + raw + load) is plain
Python. dbt's `source` is the already-landed raw DuckDB table. Do not push
ingestion into dbt.

---

## Repository layout

```
fx-macro-platform/
├── README.md
├── pyproject.toml            # uv-managed, pinned
├── uv.lock
├── .env.example             # FRED_API_KEY, paths (no secrets committed)
├── docker-compose.yml
├── Dockerfile
├── docs/
│   └── architecture.md      # one-page data-flow diagram + seam notes
├── ingest/
│   ├── config.py            # series registry: {series_id, source, frequency}
│   ├── fetch.py             # calls API, writes immutable raw JSON
│   ├── parse.py             # raw JSON → validated records (Pydantic)
│   └── load.py              # records → DuckDB raw table (re-runnable)
├── raw/                     # append-only JSON store (gitignored if large)
├── warehouse/
│   └── fx_macro.duckdb      # gitignored
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml         # dbt-duckdb, points at warehouse/
│   └── models/
│       ├── staging/
│       ├── intermediate/
│       └── mart/
├── api/
│   └── main.py              # FastAPI, reads mart, returns dataframe
├── tests/
│   └── test_parse.py
└── scripts/
    └── run_pipeline.sh      # fetch → load → dbt run  (the cron target)
```

---

## Raw storage convention

Append-only. One decision to lock: the key includes fetch time so re-fetches
never collide.

```
raw/{source}/{series_id}/{fetch_timestamp_iso}.json
# e.g. raw/fred/DEXUSEU/2026-07-21T06:00:03Z.json
```

Each file = the verbatim API response body. Nothing is ever deleted or overwritten.

---

## Data model (raw table in DuckDB)

Minimum columns to preserve vintage correctness:

| Column            | Meaning |
|-------------------|---------|
| `source`          | e.g. `fred` |
| `series_id`       | e.g. `DEXUSEU` |
| `reference_period`| the date the value describes |
| `value`           | the observation |
| `fetch_timestamp` | when this record was pulled (vintage key) |
| `raw_file`        | pointer to the source JSON on disk |
| `loaded_at`       | load-run timestamp |

Primary grain: one row per `(source, series_id, reference_period, fetch_timestamp)`.

---

## dbt layer responsibilities

- **staging** — 1:1 with raw. Type-cast, rename to consistent conventions, no logic.
- **intermediate** — vintage resolution (latest-known-as-of logic), join legs,
  compute 2Y/10Y **differentials** and rate spreads, align to a daily panel with
  macro series carried forward as step functions from their known date.
- **mart** — the stable, curated tables the API serves. Treat column names/shapes
  here as a contract; upstream can be refactored freely, mart should stay stable.

Add at least one **dbt test** (e.g. uniqueness on the raw grain, not-null on `value`).

---

## API surface (v1)

Read-only. Serves from mart only.

- `GET /health` — liveness.
- `GET /series/{series_id}?start=&end=` — returns a series as a dataframe payload.
- `GET /panel?start=&end=` — returns the joined daily EUR/USD + differentials panel.

Response: JSON records (or Arrow) that deserialize cleanly to a Polars/pandas
dataframe client-side. Define response schemas with Pydantic.

**No auth in v1.** Bind to localhost during local dev.

---

## Containerization notes (Linux-deployable from the start)

- **dbt** runs as an ephemeral run-to-completion step (CLI invocation in
  `run_pipeline.sh`), **not** a long-lived service.
- **FastAPI** is the one long-running service in compose.
- **DuckDB** is a file on a mounted volume — the one stateful thing; its volume is
  where backup care goes later.
- Build images `linux/amd64` so the same compose runs locally and on the Hetzner
  CX23 unchanged.
- `raw/` and `warehouse/` on mounted volumes, never baked into images.

---

## Local acceptance criteria (must pass before pushing to Hetzner)

1. `scripts/run_pipeline.sh` runs clean: fetches all ~5 series, writes immutable
   raw JSON, loads DuckDB, `dbt run` + `dbt test` pass.
2. Re-running the pipeline a second time creates **new** raw records (new
   fetch_timestamp) and does **not** overwrite or duplicate prior grain.
3. `docker-compose up` serves the API locally; `/panel` returns a sane EUR/USD +
   differentials dataframe.
4. Killing and recreating containers preserves `raw/` and the DuckDB file (volumes
   work).
5. One passing pytest on the parser.

Only after all five pass: provision the Hetzner CX23 and deploy the same compose.

---

## Deferred roadmap (context only — do NOT build now)

- **Source #2:** ECB SDW via `sdmx1` (proves multi-source schema generalization).
- **Pairs:** GBP, JPY; then CNY as managed-regime contrast.
- **Macro tiers:** inflation (HICP/CPI) → balance sheets (Fed H.4.1 / ECB WFS) →
  capital flows / current account.
- **Orchestration:** cron → Dagster/Prefect (evaluate before defaulting to Airflow;
  Airflow needs ~2GB idle and won't fit the CX23 — resize first if adopted).
- **Serving DB:** DuckDB → Postgres when concurrent read/write contends.
- **Object storage:** raw JSON → Cloudflare R2.
- **Public exposure:** Cloudflare Tunnel.
- **Monetization:** API tokens + website. **Gate:** review loyos side-activity /
  IP / confidentiality clauses *before* anything goes public or takes money.
- **Research layer:** model-run store (params, forecasts, **data-vintage pointer**,
  code version) → regime models → backtests → VaR/portfolio tracking.
