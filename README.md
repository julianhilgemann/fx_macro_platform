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
| M2 — dbt → marts + **Elementary** (data quality) | ✅ done |
| M3 — FastAPI read layer (Postgres) | ✅ done |
| M4 — **Metabase** (BI) | ✅ done |
| Containerization — all services in Docker Compose | ✅ done |
| M5+ — unattended schedule week, k3s/Tailscale | ⏳ pending |

The pipeline is **Postgres + Dagster + dbt/Elementary + FastAPI + Metabase +
Streamlit**, fully containerized (the earlier DuckDB slice was retired).

## Quick start (containerized)

```bash
cp .env.example .env          # set FRED_API_KEY for live mode (else synthetic)
make up                       # builds the image and starts all 5 services
```

| Service | URL | Notes |
|---|---|---|
| Launchpad | <http://127.0.0.1:8080> | dev navigation hub → all services below |
| Dagster UI | <http://127.0.0.1:3000> | asset graph, runs, schedule |
| API (OpenAPI) | <http://127.0.0.1:8000/docs> | `/v1/*` endpoints |
| Dashboard | <http://127.0.0.1:8501> | Streamlit forecasting studio (auto-ARIMA / ETS, walk-forward CV, diagnostics) |
| Metabase | <http://127.0.0.1:3001> | add warehouse: host `postgres`, db `warehouse`, user `platform_reader` |
| Elementary | <http://127.0.0.1:8081> | data-quality report (regenerates every 30 min) |
| dbt deps | <http://127.0.0.1:8082> | `dbt deps` install report (regenerates every 5 min) |
| dbt docs | <http://127.0.0.1:8083> | native dbt lineage DAG + catalog (refreshed after every build) |

`make up` brings up `postgres`, `dagster-webserver`, `dagster-daemon`, `api`,
`metabase`, `dashboard` (Streamlit), `elementary-report`, and the `launchpad`. Dagster metadata lives in
the `dagster` DB; the warehouse is `warehouse`.
The daily schedule (`macro_pipeline_schedule`, 06:00 Europe/Berlin) ingests all
sources and runs the full dbt build.

### Local dev (no containers, for iteration)

```bash
make up                       # Postgres only (host port 5433)
./scripts/run_pipeline.sh     # fetch -> raw.source_fetch -> dbt build (local)
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
uv run dagster dev -m orchestration.definitions   # local Dagster UI
```

## Orchestration (Dagster)

The asset graph (spec §8): `raw_fred` / `raw_ecb` / `raw_bundesbank` (ingest) →
`stg_*` → `int_macro__observations_unioned` → `fct_macro_observation` (+`_latest`)
and `dim_series`; the `series_catalog` seed feeds `dim_series`, and Elementary's
models materialize into the `elementary` schema. In the UI: **Assets** for the
graph, **Runs** for execution history, **Overview → Schedules** for the schedule.

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
dashboard/  Streamlit forecasting studio + Signal Lab (separate image, reads marts as platform_reader)
sql/        001_init.sh — roles, databases, schemas, raw landing table
agents/     environment facts + gotchas for agentic builds
docs/       api-calls.md · migration-plan.md
```

### dbt marts for grains & transforms

Beyond the observation facts, dbt precomputes the Signal Lab analytics in the
warehouse (tables, rebuilt by the daily schedule):

- `marts.fct_macro_series_grains` — every series resampled to each applicable
  calendar grain (`day` calendar-filled for daily series, `week` ISO-Monday
  buckets, `month`, `quarter`, `year`), never finer than the native frequency
  (singular test asserts this). Unique index + ANALYZE via post-hooks.
- `marts.fct_macro_series_transforms` — long format
  (series, grain, period_date, transform): `level`, `diff`, `pct_change`,
  `log_level` (positives only), `log_return` (positives only), `index_100`
  (base = series inception), `zscore`. STL components stay runtime (Loess has
  no SQL equivalent).
- `marts.fct_macro_series_period_metrics` — per (series, grain, period_date):
  `mom_pct`, `qoq_pct`, `yoy_pct` (calendar-date joins — robust to gaps in the
  native data, unlike lag-k), `mtd_pct`, `ytd_pct`.

Signal Lab's sidebar **Data grain** selector reads these marts (platform_reader
has SELECT via default privileges); STL transforms and the `native` grain fall
back to runtime computation.

## Dashboard (Streamlit)

A separate container (`dashboard/`) with the scientific stack (statsmodels,
scikit-learn, scipy, Plotly). It reads `marts.dim_series` and
`marts.fct_macro_observation_latest` directly as `platform_reader`, the same as
Metabase. Pick a series, hit **Run model**, and it will:

- calendar-align the series (business-day / month-start, forward-fill gaps);
- fit a model — AIC-selected auto-ARIMA (SARIMAX), Holt-Winters ETS, or a
  naive-drift baseline;
- evaluate it with **walk-forward (rolling-origin) cross-validation**
  (expanding or sliding window, always out-of-sample);
- report pooled error metrics (MSE, RMSE, MAE, MAPE, sMAPE, MASE, R²) and a
  diagnostic battery (ADF/KPSS, Ljung-Box, Jarque-Bera, Engle ARCH,
  Durbin-Watson, residual ACF/PACF);
- plot the multi-period forecast with prediction intervals over the history.

### Signal Lab (multipage)

A second page (`pages/1_📊_Signal_Lab.py`, analytics in `lab.py`) dissects any
series in the time *and* frequency domains:

- transforms — level, first difference, % change, log-return, index (base
  date), z-score, STL components and seasonally-adjusted series;
- calendar metrics — MoM/QoQ/YoY/MTD/YTD, annual performance, recent-history
  tables with YoY columns;
- decomposition — STL / classical additive / multiplicative with Hyndman
  strength-of-trend & seasonality, component volatility, single-cycle zoom;
- cyclicality — ACF/PACF, Ljung-Box p-values per lag, lag-scatter plots,
  seasonal subseries overlays, cycle profiles, year × position heatmaps
  (levels and YoY);
- frequency domain — periodogram + Welch PSD (log-log) with dominant-period
  peaks and spectral band shares, and a Morlet wavelet scalogram;
- time filtering — HP, Baxter-King, Christiano-Fitzgerald, Butterworth
  low/high/band-pass, centred MA and EMA, each with frequency response and a
  variance split; the filtered slice can feed every other tab;
- distribution & risk — KDE vs normal fit, Q-Q plots, rolling moments,
  drawdown, per-year ridge plots and by-cycle violins;
- multi-series correlation maps — level & %-change matrices, rolling
  correlations and lead-lag cross-correlograms against up to 6 companions.
