# Migration Plan — DuckDB slice → `platform-spec.md` v2

> **Status:** M0–M3 + M1 complete — Postgres (Compose + schemas/roles +
> `raw.source_fetch`), ingest → raw → dbt → FastAPI all running on Postgres, and
> Dagster orchestrating the whole graph (ingest assets + `@dbt_assets` + daily
> schedule) via `uv run dagster dev`. Remaining: Metabase/Elementary (M2+),
> containerized Dagster in Compose + daily schedule unattended (M5), k3s (M7).
> The DuckDB slice and its specs were removed.

**Single source of truth:** [`platform-spec.md`](../platform-spec.md). That document
is the architecture spec and the build contract. This file is *only* the plan for
moving the existing code onto it — it is not a second architecture doc and should
be retired once the milestones below are complete.

## 1. Where we are today

A working **v1 vertical slice**: DuckDB + cron + plain Python, three sources,
thirteen series, one EUR/USD differential panel, running end to end.

| Component | What exists |
|---|---|
| `ingest/` | series registry (`config.py`), per-source fetch clients (`fetch.py`: FRED JSON, Bundesbank CSV, ECB SDW CSV), parsers (`parse.py`), DuckDB loader (`load.py`) |
| `dbt/` | staging → intermediate → mart (views + tables) with uniqueness/not-null tests |
| `api/main.py` | FastAPI over DuckDB: `/health`, `/series/{id}`, `/panel` |
| `raw/` + `warehouse/fx_macro.duckdb` | append-only raw store + DuckDB file (both gitignored) |
| `tests/`, `scripts/run_pipeline.sh`, `docs/` | parser tests, cron target, docs |

This slice already validated the data-shape assumptions and, more importantly,
the fiddly upstream integrations. Its fetch/parse code is the seed for the v2
ingest assets — everything else is rebuilt per the spec.

## 2. Where we're going

Postgres warehouse with a bitemporal grain, Dagster orchestration, dbt +
Elementary, a FastAPI read layer, Metabase for BI, then single-node k3s +
Tailscale on Hetzner. The four hard pivots from today:

| Today | v2 (spec ref) |
|---|---|
| DuckDB file + raw JSON/CSV on disk | Postgres `raw.source_fetch` with `payload`/`payload_raw`/`payload_sha256` (§4, §5) |
| cron + `run_pipeline.sh` | Dagster webserver + daemon, assets, checks, schedule (§8) |
| `fetch_timestamp` doubles as vintage key | `obs_date` + `known_at` + `fetched_at`; grain `(series_id, obs_date, known_at)` (§6) |
| series registry in Python | `meta.series_catalog` as a dbt seed (§7) |

## 3. File map — current → target

| Current file | Disposition | Target (per spec §12) |
|---|---|---|
| `ingest/fetch.py` (3 clients + synthetic) | **Port** | `orchestration/assets/ingest_fred.py`, `ingest_ecb.py`, `ingest_bundesbank.py`; synthetic generator becomes a dev/test helper |
| `ingest/parse.py` | **Port → staging** | parsing belongs in staging (§3, §9); re-express as `stg_*` SQL or a shared helper invoked by staging |
| `ingest/load.py` | **Rewrite** | ingest assets write to `raw.source_fetch` (parsed-to-JSON + verbatim bytes + sha256), not DuckDB |
| `ingest/config.py` (`SERIES`) | **Port → seed** | `dbt/seeds/series_catalog.csv` (§7); canonical `series_id` convention decided first |
| `dbt/models/staging/stg_fred__observations.sql` (reads all 3 sources despite the name) | **Split** | `stg_fred__observations.sql`, `stg_ecb__observations.sql`, `stg_bundesbank__observations.sql` |
| `dbt/models/intermediate/int_series_latest_vintage.sql` | **Rewrite** | `int_macro__observations_unioned` + bitemporal `fct_macro_observation` (§6, §8) |
| `dbt/models/intermediate/int_daily_panel.sql` | **Demote** | becomes an analytics mart over the generic fact table, not the core model |
| `dbt/models/mart/mart_series.sql` | **Rewrite** | `dim_series` + `fct_macro_observation_latest` |
| `dbt/models/mart/mart_eurusd_panel.sql` | **Demote/rename** | analytics mart (EUR/USD panel) over the fact table |
| `api/main.py` | **Rewrite** | `api/main.py` + `routers/` + `models/` + `db.py`; Postgres `platform_reader`, envelope, bounds (§10) |
| `tests/test_parse.py` | **Keep** | parsers remain valid; add staging + API tests |
| `scripts/run_pipeline.sh` | **Supersede** | `Makefile` (`make ingest`, `make dbt`) + Dagster schedule; keep only as a local convenience |
| `docs/api-calls.md` | **Keep** | upstream-provider reference; unaffected by the storage pivot |
| `raw/`, `warehouse/fx_macro.duckdb` | **Retire** | raw bytes move into `raw.source_fetch.payload_raw`; DuckDB file replaced by Postgres |

### New (does not exist yet, per spec §12)

```
docker-compose.yml            docker-compose.override.yml
images/dagster/Dockerfile     images/api/Dockerfile
orchestration/                definitions.py · assets/ · resources/ · checks/ · schedules.py
dbt/seeds/series_catalog.csv  dbt/macros/generate_schema_name.sql  dbt/packages.yml
sql/001_init.sql              k8s/base/ · k8s/overlays/prod/
.github/workflows/ci.yml      .github/workflows/deploy.yml
Makefile                      CLAUDE.md        scripts/smoke.sh
```

## 4. Decisions to lock before M0 (spec §21 + findings)

1. **Canonical `series_id` convention** — spec suggests `{ISO2}_{CONCEPT}_{TRANSFORM}`
   (e.g. `DE_CPI_YOY`). Current ids (`DEXUSEU`, `DE2Y`, `ECB_MRO`) don't follow it.
   Decide before writing the seed; renaming later is painful.
2. **`known_at` type** — `date` vs `timestamptz` (§21). Macro is fine with `date`;
   market data may want `timestamptz`. Decide now to avoid a migration.
3. **Architecture** — `linux/arm64` + Hetzner CAX (§2). The old docs' `amd64`/CX23
   is obsolete.
4. **Hand-built vs agent-built split** (§22.8). Decide before M0, not mid-build.

## 5. Fixes to fold in while porting

1. **FRED vintage is not actually captured today.** `fetch_fred` calls the plain
   `/series/observations` endpoint without `realtime_start`/`realtime_end`, so
   `known_at` currently degrades to "when we pulled it." Switch to ALFRED
   parameters so FRED's real revision history feeds `known_at` (§3, §6).
2. **Per-series fault tolerance.** Ingest assets must never raise on a single
   series failure — record and continue (§8). Today `fetch_fred` raises on the
   first bad response.
3. **Misnamed staging model.** `stg_fred__observations` reads all three sources;
   split per source so no source name leaks below `intermediate` (invariant §22.5).
4. **sha256 dedup + failed-fetch recording** (§5) are currently absent.

## 6. Milestone sequence

Annotated from spec §20. "Carries over" marks what the current slice already
satisfies and should be preserved rather than rebuilt.

| # | Milestone | Done when | Carries over from today |
|---|---|---|---|
| M-1 | Agent scaffolding | `make check` green; `CLAUDE.md` committed | — (new) |
| M0 | Repo, Compose, Postgres, schemas, roles | `make up` → healthy Postgres, `raw`/`marts` created | — (new; replaces DuckDB) |
| M1 | FRED ingest as a Dagster asset | materialize lands rows in `raw.source_fetch` | `fetch_fred` + `parse_response` (ported), catalog seed |
| M2 | dbt staging → mart; Elementary | `fct_macro_observation_latest` populated; lineage renders | dbt layering concept, tests |
| M3 | FastAPI observations endpoints | `curl` returns envelope; bounds return `400` | `/series` + `/panel` semantics (reshaped) |
| M4 | One chart on Astro site | chart renders | — |
| M5 | Daily schedule, unattended, one week | 7 consecutive green runs | — (replaces cron) |
| M6 | ECB + Bundesbank | 3 sources, unified mart, no source names below `intermediate` | `fetch_ecb` + `fetch_bundesbank` + their parsers (ported) |
| M7 | Hetzner CAX + k3s + Tailscale + TLS + backup | public HTTPS on `api.` only; restore tested | — |
| M8 | GitHub Actions build → GHCR → deploy | merge to `main` reaches prod untouched | — |

**Keep the DuckDB slice running as the reference implementation for provider
behavior** until M2 lands; its raw/ files are the fixture set for staging tests.

## 7. Retiring this plan

Delete this file once M0–M8 are complete and `platform-spec.md` is the only
document describing the live system. Until then it is the working delta list.
