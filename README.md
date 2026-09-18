# FX Macro Data Platform

A data platform for macroeconomic and FX time series, built so that every number
can be traced back to what was knowable at the moment it was published.

Macro data is revised. A GDP print, a CPI reading or a policy rate is released,
then corrected, sometimes repeatedly and sometimes quietly. A platform that keeps
only the latest value has discarded the only version that mattered for a
backtest, a research note or an audit. So this one keeps every vintage: provider
responses are stored immutably, and the warehouse records both the period a value
describes and the date it became known.

> **This platform is under active development.** This README explains what it is
> and how to run it. It deliberately avoids detail that changes week to week.
> [`platform-spec.md`](platform-spec.md) is the authoritative design and build
> contract; the [`knowledge/`](knowledge/00%20Home.md) vault holds working notes,
> concept references and the current delivery plan.

## Shape of the system

```
providers  →  immutable raw landing  →  Postgres warehouse  →  dbt models  →  serving layer
```

- **Ingest** pulls from FRED, the ECB and the Bundesbank. Responses land as
  append-only files indexed by content hash, so re-fetching unchanged data is a
  no-op rather than a duplicate.
- **Warehouse** is Postgres, storing observations at a bitemporal grain: the
  period observed, when the value became knowable, and when it was fetched.
- **Transform** is dbt. Staging models normalise provider quirks; marts serve the
  analytical and serving layers.
- **Orchestrate** is Dagster, which owns the asset graph, the schedule and the dbt
  runs.
- **Serve** is a FastAPI read layer over the marts, alongside Streamlit analytics,
  a Germany economy dashboard, Metabase for BI and an Elementary report for data
  quality.

## Design commitments

The handful of things the platform will not trade away:

- **Raw is immutable.** Provider responses are never edited in place.
- **History is preserved.** A revision becomes a new vintage, not an overwrite.
- **The warehouse is rebuildable from raw** by re-running dbt.
- **Serving is read-only.** Nothing in the serving layer writes warehouse data;
  refresh requests are queued to Dagster, which remains the single orchestrator.
- **Failures should be loud.** Silent degradation is treated as a defect, not a
  nuisance.

## Status

| Area | State |
|---|---|
| Postgres schemas, roles, immutable raw landing | Working |
| Dagster asset graph, dbt integration | Working |
| dbt staging and marts | Working |
| FastAPI read layer, Streamlit analytics, Germany dashboard, Metabase, Elementary | Working |
| Unattended daily schedule | Defined, **not yet enabled** |
| Trustworthy revision history | Partial |
| CI, backups, observability, authentication | Not started |
| K3s deployment | Planned |

The pipeline currently runs by hand. Making it run unattended, and making the
vintage history trustworthy enough to rely on, is where the active work sits. The
backlog and the reasoning behind its ordering are in the
[delivery plan](knowledge/Work/Platform%20Delivery%20Plan.md); an honest account
of what is broken is in [Current State](knowledge/Platform/Current%20State.md).

## Getting started

Requires Docker, and a free FRED API key for live data. Without a key the
pipeline runs against synthetic data.

```bash
cp .env.example .env    # set FRED_API_KEY for live data, otherwise synthetic mode
make up                 # build and start the stack
```

| Entry point | URL |
|---|---|
| Launchpad, the navigation hub | <http://127.0.0.1:8080> |
| Dagster | <http://127.0.0.1:3000> |
| API and OpenAPI docs | <http://127.0.0.1:8000/docs> |
| Streamlit analytics | <http://127.0.0.1:8501> |
| Germany dashboard | <http://127.0.0.1:8084> |
| Metabase | <http://127.0.0.1:3001> |
| dbt lineage and catalog | <http://127.0.0.1:8083> |

The complete service and port inventory is in
[Stack Inventory](knowledge/Platform/Stack%20Inventory.md).

`make check` probes the stack, but note that it currently reports problems
without failing: every probe ends in `|| echo FAIL`, so the target exits 0 even
when something is down. Fixing that is the first item in the delivery plan.

Other useful targets: `make down`, `make psql`, `make reset` (drops volumes so
the init scripts re-run).

## Repository layout

```
ingest/          provider clients and raw landing
dbt/             staging, intermediate and mart models, plus the series seed
orchestration/   Dagster definitions, assets, jobs and schedule
api/             FastAPI read layer over the marts
dashboard/       Streamlit analytics
germany/         Germany economy dashboard
sql/             database, role and schema initialisation
infra/           deployment and project-management tooling
knowledge/       Obsidian vault: project context, concepts, delivery plan
docs/            design documents, provider reference, research
agents/          environment facts and gotchas for agentic builds
scripts/         local utilities and one-off helpers
tests/           tests outside the dbt and Dagster suites
```

## Where to read more

| If you want | Read |
|---|---|
| The authoritative design | [`platform-spec.md`](platform-spec.md) |
| What to work on next | [Platform Delivery Plan](knowledge/Work/Platform%20Delivery%20Plan.md) |
| What is actually working | [Current State](knowledge/Platform/Current%20State.md) |
| How the pieces fit | [knowledge vault](knowledge/00%20Home.md) and its maps of content |
| Upstream provider endpoints and shapes | [`docs/api-calls.md`](docs/api-calls.md) |
| The migration off the earlier DuckDB slice | [`docs/migration-plan.md`](docs/migration-plan.md) |
| Open work items | [GitHub issues](https://github.com/julianhilgemann/fx_macro_platform/issues) and the [Platform board](https://github.com/users/julianhilgemann/projects/3) |

Where this README and `platform-spec.md` disagree, the spec wins.
