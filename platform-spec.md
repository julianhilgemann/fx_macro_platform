# Data Platform — Architecture Spec v2

**Status:** build spec — also serves as the shared ground truth for agentic implementation
**Phase 1 payload:** macroeconomic time series (FRED, ECB, Bundesbank)
**Target:** local Docker Compose on macOS/arm64 → single-node k3s on Hetzner
**Execution model:** orchestrator/executor agent split (§22)

**Changes from v1:** Elementary added for data quality (§9, §18); access and
exposure model made explicit (§18a); API rate limiting moved to the edge and
query bounds specified (§10); Metabase confirmed as the internal BI tool;
agentic build model added (§22).

---

## 1. Purpose and design principles

The platform is the deliverable. Macro data is the first payload; relocation
scoring, market analytics, an LLM narration service and a CMS are anticipated
later payloads that must plug in without redesign.

Five principles, in priority order:

1. **Raw is immutable.** Every external response lands byte-faithful, with its
   fetch timestamp, before any parsing. Everything downstream is rebuildable
   from raw by re-running dbt.
2. **Vintages are preserved.** Macro series are revised. The warehouse must be
   able to answer "what did we know on date X," not just "what is true now."
3. **One boring database.** Postgres for the warehouse, Dagster metadata, and
   later the CMS — separate databases, one instance.
4. **Contracts at the edges, freedom in the middle.** How a source lands and
   how a mart is exposed are fixed conventions. Models, marts and dashboards
   are disposable.
5. **Compose first, k3s second.** Nothing moves to the cluster until it has
   run unattended locally for a week.

**Non-goals for v1:** high availability, multi-node, autoscaling, streaming or
sub-daily latency, horizontal scale of any component, user accounts.

---

## 2. Service inventory

| Service | Image | Role | Local port |
|---|---|---|---|
| `postgres` | `postgres:16` | Warehouse + Dagster metadata | 5432 |
| `dagster-webserver` | custom | UI, manual materialization, lineage graph | 3000 |
| `dagster-daemon` | custom (same image) | Schedules, sensors, run queue | — |
| `api` | custom | FastAPI read layer over marts | 8000 |
| `metabase` | `metabase/metabase` | Internal BI exploration | 3001 |

**dbt is not a service.** It is a CLI installed into the Dagster image and
invoked when Dagster materializes dbt assets. **Elementary is not a service
either** — it is a dbt package plus the `edr` CLI, installed into the same
image (§9). Two custom images total: `platform-dagster` and `platform-api`.

**Sizing note:** build and run everything on `linux/arm64` to match both the
MacBook Air and Hetzner's CAX line. Choosing CAX over CX means images built
locally run unmodified in production. Metabase is a JVM app and wants ~1–1.5 GB;
a 4-vCPU/8 GB CAX instance is comfortable, a 2-vCPU/4 GB one is tight once
Postgres and two Dagster processes are also resident.

---

## 3. Data sources

| Source | Auth | Protocol | Vintage support |
|---|---|---|---|
| FRED / ALFRED | free API key | REST + JSON | Yes — `realtime_start` / `realtime_end` return as-published values |
| ECB Data Portal | none | SDMX 2.1 REST | Limited; treat fetch date as vintage |
| Bundesbank | none | SDMX 2.1 REST | Limited; treat fetch date as vintage |

Verify exact base URLs and parameter names against each provider's current
documentation before implementing — these have changed within the last few
years and are not worth hardcoding from memory.

**Implementation note:** FRED's vintage support is the reason it should be
source #1. It lets you build and test the bitemporal model against a source
that actually has real revision history, rather than simulating one.

SDMX is verbose XML. Use `pandasdmx` or parse to JSON at the client boundary,
but store the response as received — parsing belongs in staging, not ingest.

---

## 4. Database layout

One Postgres instance, three databases:

- `warehouse` — all analytical data
- `dagster` — Dagster run/event storage (never touched by dbt)
- `cms` — reserved for a later payload

Schemas inside `warehouse`:

```
raw          -- landing zone, append-only, never modified
staging      -- dbt views, parsing and typing only
intermediate -- dbt, unioning and reshaping
marts        -- dbt tables, the only schema the API and BI may read
meta         -- series catalog, run audit
elementary   -- written by the Elementary dbt package (§9); do not hand-edit
```

Roles:

- `platform_writer` — owned by Dagster/dbt, full rights on all schemas
- `platform_reader` — `SELECT` on `marts`, `meta` and `elementary` only; used by
  FastAPI and Metabase

The reader role is not a formality. It is the thing that guarantees the API
cannot accidentally depend on an intermediate model, which is how "freedom in
the middle" stays true.

---

## 5. The raw landing contract

Every source writes to one table. Adding a new source means writing rows here
and nothing else.

```sql
CREATE TABLE raw.source_fetch (
  fetch_id        bigserial PRIMARY KEY,
  source          text        NOT NULL,     -- 'fred' | 'ecb' | 'bundesbank'
  resource        text        NOT NULL,     -- series id or SDMX key
  request_url     text        NOT NULL,
  request_params  jsonb       NOT NULL DEFAULT '{}',
  fetched_at      timestamptz NOT NULL DEFAULT now(),
  http_status     int         NOT NULL,
  content_type    text,
  payload         jsonb,                    -- parsed-to-JSON body
  payload_raw     bytea,                    -- original bytes (XML, CSV)
  payload_sha256  text        NOT NULL,
  dagster_run_id  text
);

CREATE INDEX ON raw.source_fetch (source, resource, fetched_at DESC);
CREATE INDEX ON raw.source_fetch (payload_sha256);
```

Rules:

- No `UPDATE`, no `DELETE`. Ever.
- `payload_sha256` enables skipping downstream work when a fetch is byte-identical
  to the previous one — a cheap and reliable change-detection mechanism.
- Failed fetches are still recorded (`http_status`, null payload). Ingest
  failures are data, not just log lines.
- Retention: revisit at ~1 year. Partition by `fetched_at` month only if it
  actually grows uncomfortable, which at this volume it will not.

---

## 6. The bitemporal model

This is the part that is hard to retrofit and cheap to get right now.

Every observation has three dates:

- `obs_date` — the period the value describes (2026-Q1)
- `known_at` — when this value became known to us (the vintage)
- `fetched_at` — when we physically pulled it (provenance only)

Grain of the core fact table: **(series_id, obs_date, known_at)**.

```sql
-- marts.fct_macro_observation
series_id     text
obs_date      date
known_at      date
value         numeric
is_latest     boolean    -- convenience flag, recomputed on each build
```

Two consumption patterns:

- **Latest view** — `marts.fct_macro_observation_latest`, filtered to
  `is_latest`. This is what dashboards and casual queries use.
- **As-of query** — the maximum `known_at <= :as_of` per
  `(series_id, obs_date)`. Exposed through the API as an `as_of` parameter.

For ECB and Bundesbank, where the provider does not expose vintages, set
`known_at = fetched_at::date` and only insert a new row when the value differs
from the last known one. This yields an approximate but honest revision history
going forward.

**Why this matters beyond macro:** the same grain serves point-in-time market
data, budget vintages, and any forecast-versus-actual evaluation. It is the
single structural decision that makes later payloads cheap.

---

## 7. Series catalog

```sql
-- meta.series_catalog  (hand-maintained, version controlled as a dbt seed)
series_id       text PRIMARY KEY   -- your canonical id, not the provider's
source          text
source_key      text               -- provider's identifier
title           text
description     text               -- prose; later fed to Cube and the LLM layer
unit            text
frequency       text               -- D | W | M | Q | A
seasonal_adj    boolean
country         text               -- ISO 3166-1 alpha-2
category        text
active          boolean
```

Maintain this as a dbt seed (CSV in the repo). It is configuration, not data —
it belongs in git, it gets reviewed in PRs, and adding a series is a one-line
diff rather than a code change.

The `description` column is doing double duty: it is documentation now, and it
becomes the grounding text for Cube metric definitions and LLM narration later.
Write it properly the first time.

---

## 8. Orchestration (Dagster)

**Asset graph:**

```
seed: series_catalog
   │
   ├─→ raw_fred        ─┐
   ├─→ raw_ecb          ├─→ stg_* ─→ int_macro_unioned ─→ fct_macro_observation
   └─→ raw_bundesbank  ─┘                              ├─→ fct_macro_observation_latest
                                                        └─→ dim_series
```

**Ingest assets** (one per source, plain Python):

- Read active series for that source from the catalog seed
- Fetch each; write to `raw.source_fetch`
- Emit metadata: series attempted, succeeded, failed, rows landed, bytes
- Never raise on a single series failure — record it and continue. One dead
  Bundesbank series must not block the whole run.

**dbt assets:** use Dagster's `@dbt_assets` decorator so each dbt model appears
as an individual asset in the lineage graph, not one opaque "run dbt" step.
This is the entire reason for choosing Dagster; do not collapse it into a
single shell task.

**Partitioning:** start unpartitioned with incremental fetch logic (pull from
last known `obs_date` forward). Macro series update irregularly and a daily
partition mostly produces empty partitions. Add a static partition over source
or series group later if backfills become painful.

**Schedules:** one daily job at 06:00 Europe/Berlin covering all sources plus
the full dbt build. Total runtime should be well under a minute at this volume.

**Asset checks** — Dagster's `@asset_check`, run after materialization:

- Freshness: no active series' latest `obs_date` is older than 2× its expected
  frequency interval
- Volume: row count did not drop versus the previous run
- Nulls: no null values in `fct_macro_observation.value`
- Revision anomaly: no value revised by more than N standard deviations

Failed checks should warn, not fail the run. You want the data to land and the
problem to be visible, not the pipeline to halt.

---

## 9. Transformation (dbt)

```
dbt/
├── dbt_project.yml
├── profiles.yml            # env vars only, no literals
├── seeds/
│   └── series_catalog.csv
├── models/
│   ├── staging/
│   │   ├── _staging__sources.yml
│   │   ├── _staging__models.yml
│   │   ├── stg_fred__observations.sql
│   │   ├── stg_ecb__observations.sql
│   │   └── stg_bundesbank__observations.sql
│   ├── intermediate/
│   │   └── int_macro__observations_unioned.sql
│   └── marts/
│       ├── _marts__models.yml
│       ├── dim_series.sql
│       ├── fct_macro_observation.sql
│       └── fct_macro_observation_latest.sql
└── macros/
    └── generate_schema_name.sql
```

**Materialization:** staging as views, intermediate as views, marts as tables.
At this data volume, full refresh of marts on every run is simpler than
incremental logic and costs nothing. Revisit only when a build exceeds a minute.

**Conventions:**

- Staging models do exactly one thing: unpack the JSON payload into typed
  columns. No business logic, no joins, no filtering beyond malformed rows.
- Source-specific logic never appears downstream of `intermediate`. If a mart
  contains the word `fred`, the layering has leaked.
- Every mart model has a `.yml` entry with a description and at least one test.

**Tests:**

- `unique` on the combination `(series_id, obs_date, known_at)`
- `not_null` on all key columns
- `relationships` from `fct_macro_observation.series_id` to `dim_series`
- `accepted_values` on `frequency`
- dbt source freshness on `raw.source_fetch`

**Elementary (data quality) — in from M2.**

Elementary is a dbt package plus an OSS CLI, not a service. Add it to
`packages.yml` and it installs models into the `elementary` schema; an
`on-run-end` hook persists dbt artifacts, run results, test results and source
freshness into those tables on every build. This turns dbt test outcomes from
transient console output into a queryable history, which is the whole point —
you cannot see a degradation trend in a terminal.

```yaml
# packages.yml
packages:
  - package: elementary-data/elementary
    version: [">=0.16.0", "<0.20.0"]

# dbt_project.yml
models:
  elementary:
    +schema: elementary
on-run-end:
  - "{{ elementary.upload_dbt_artifacts() }}"
```

Beyond persistence, Elementary ships anomaly-detection tests that are used like
any other dbt test — volume, freshness, column distribution, schema change.
Apply these to `fct_macro_observation` once about a month of history exists;
before that there is no baseline to detect anomalies against.

**Division of labour with Dagster asset checks.** Deliberate, not duplicated:

| Concern | Owner |
|---|---|
| Did the ingest run and land rows? | Dagster asset checks |
| Is the pipeline healthy right now? | Dagster UI |
| Is the *data* behaving as it did last month? | Elementary |
| History of every test result over time | Elementary tables |

Elementary's report generation (`edr report`) is a CLI invocation from a
Dagster op after the dbt build. Do not run it as a long-lived service.

---

## 10. API layer (FastAPI)

Read-only over `marts` and `meta`, using `platform_reader`.

**Endpoints:**

```
GET  /health                                  → liveness, no DB
GET  /ready                                   → readiness, checks DB
GET  /v1/series                               → catalog, filterable by country/category/frequency
GET  /v1/series/{series_id}                   → single series metadata
GET  /v1/series/{series_id}/observations      → ?from= &to= &as_of=
GET  /v1/observations                         → ?series_ids=a,b,c &from= &to= &as_of=
GET  /v1/meta/freshness                       → last obs_date and last run per series
```

The multi-series endpoint exists because charts need several series in one
request. Without it the frontend does N calls and you will regret it.

**Response envelope** — consistent across all endpoints:

```json
{
  "data": [...],
  "meta": {
    "series_ids": ["DE_CPI_YOY"],
    "as_of": "2026-08-26",
    "row_count": 412,
    "generated_at": "2026-08-26T06:04:11Z",
    "warehouse_build": "2026-08-26T06:03:52Z"
  }
}
```

`warehouse_build` is not decoration. When a chart looks wrong, the first
question is always whether the data is stale, and this answers it without
opening Dagster.

**Technical requirements:**

- Async SQLAlchemy or asyncpg with a connection pool sized 5–10
- Pydantic response models for every endpoint (gives you OpenAPI for free)
- CORS allowlist naming your site's domain explicitly — never `*`
- `Cache-Control: public, max-age=3600` on observation endpoints; the data
  changes once a day
- Cursor or limit/offset pagination on `/v1/series`, with a hard max page size

**Query bounds — enforced in Pydantic, not in SQL:**

| Bound | Value | On violation |
|---|---|---|
| Page size | max 1000 rows | `400`, not silent truncation |
| Date range per request | max 50 years | `400` |
| `series_ids` per multi-series call | max 20 | `400` |

Reject loudly. A silently clamped response is a bug report from your own
frontend six weeks later.

**Rate limiting belongs at the edge, not in the process.** In-process limiters
such as `slowapi` keep counters per worker; §15 runs the API at `replicas: 2`,
so a "100/minute" limit silently becomes 200/minute and drifts further with
every replica. Use Traefik's `rateLimit` middleware on the Ingress, or
Cloudflare in front of it. Locally under Compose this does not matter and can be
skipped entirely.

**Threat model.** The payload is public FRED/ECB numbers. The realistic risk is
not theft, it is resource abuse: someone requesting 400 series across 80 years
in a loop and saturating Postgres. The bounds above and edge rate limiting are
the defence; the `platform_reader` role restricted to `marts` is the backstop.

**Owner-only endpoints** (anything that triggers work rather than reads data)
live on a separate router behind a single API key header, compared with
`secrets.compare_digest`. At single-operator scale this is sufficient and
OAuth/JWT is ceremony. Never mount such a router under `/v1`.

**Explicitly out of scope for v1:** writes to warehouse data, user accounts,
multi-tenant auth.

---

## 11. Visualization

Two consumers, different purposes:

**Metabase** (container, internal, behind auth) — exploratory analysis for you.
Connects directly to Postgres as `platform_reader`. This is where you look at
things while building, and it is deliberately not the public artifact.

**Your Astro site** (external) — fetches `/v1/observations` and renders charts
client-side. This is the public face. Keep the site on Cloudflare Pages: static,
free, globally cached, and unable to break when the box does.

The seam is one JSON endpoint over HTTPS. That is the whole integration.

**Deferred:** Cube as a semantic layer. It earns its place when a second
programmatic consumer appears — a second payload sharing metric definitions, or
an LLM narration service. Adding it early means maintaining YAML models to
answer queries a dbt mart already answers. The eventual split: Cube serves
anything that is a metric over a dimension; FastAPI serves everything with real
computation behind it.

---

## 12. Repository layout

Single repo. Splitting this across repos at this scale creates coordination
overhead with no benefit.

```
platform/
├── README.md
├── docker-compose.yml
├── docker-compose.override.yml     # local-only, gitignored
├── .env.example
├── Makefile
├── images/
│   ├── dagster/Dockerfile
│   └── api/Dockerfile
├── orchestration/                  # Dagster code location
│   ├── definitions.py
│   ├── assets/
│   │   ├── ingest_fred.py
│   │   ├── ingest_ecb.py
│   │   ├── ingest_bundesbank.py
│   │   └── dbt.py
│   ├── resources/
│   ├── checks/
│   └── schedules.py
├── dbt/                            # as laid out in §9
├── api/
│   ├── main.py
│   ├── routers/
│   ├── models/                     # Pydantic
│   └── db.py
├── sql/
│   └── 001_init.sql                # schemas, roles, raw.source_fetch
├── k8s/
│   ├── base/
│   └── overlays/prod/
└── .github/workflows/
    ├── ci.yml
    └── deploy.yml
```

A `Makefile` with `make up`, `make down`, `make ingest`, `make dbt`, `make test`
saves more time than it looks like it should.

---

## 13. Configuration and secrets

All configuration via environment variables. No literals in code, no
credentials in git.

```
POSTGRES_HOST / PORT / DB / USER / PASSWORD
WAREHOUSE_READER_USER / WAREHOUSE_READER_PASSWORD
DAGSTER_POSTGRES_DB
FRED_API_KEY
DBT_TARGET                # dev | prod
API_CORS_ORIGINS          # comma-separated
LOG_LEVEL
```

Local: `.env`, gitignored, with a committed `.env.example` documenting every key.
Production: Kubernetes `Secret` for credentials, `ConfigMap` for non-sensitive
config. Do not commit sealed secrets to git in v1 — the ceremony exceeds the
benefit for a single-operator system.

---

## 14. Local Compose specification

```yaml
services:
  postgres:
    image: postgres:16
    environment: [...]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER"]
      interval: 10s
    ports: ["5432:5432"]        # local only; remove in prod

  dagster-webserver:
    build: { context: ., dockerfile: images/dagster/Dockerfile }
    command: dagster-webserver -h 0.0.0.0 -p 3000
    depends_on:
      postgres: { condition: service_healthy }
    volumes:
      - ./orchestration:/opt/app/orchestration    # dev hot-reload
      - ./dbt:/opt/app/dbt
    ports: ["3000:3000"]

  dagster-daemon:
    build: { context: ., dockerfile: images/dagster/Dockerfile }
    command: dagster-daemon run
    depends_on:
      postgres: { condition: service_healthy }

  api:
    build: { context: ., dockerfile: images/api/Dockerfile }
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
    depends_on:
      postgres: { condition: service_healthy }
    ports: ["8000:8000"]

  metabase:
    image: metabase/metabase:latest
    volumes: [metabase_data:/metabase-data]
    ports: ["3001:3000"]

volumes:
  pgdata:
  dagster_home:
  metabase_data:
```

Both Dagster services must run the **same image** with a shared `DAGSTER_HOME`
and identical `dagster.yaml`. A mismatch here produces confusing "run not found"
errors that are hard to diagnose.

---

## 15. k3s migration specification

The containers do not change. This is the point of doing Compose first.

**What changes around them:**

| Compose concept | k8s equivalent |
|---|---|
| `service:` | `Deployment` + `Service` |
| `volumes:` | `PersistentVolumeClaim` (k3s `local-path` provisioner) |
| `environment:` | `ConfigMap` + `Secret` |
| `ports:` published | `Ingress` (Traefik, bundled with k3s) |
| `depends_on` + healthcheck | `readinessProbe` / `livenessProbe` |
| `docker compose up -d` | `kubectl apply -k k8s/overlays/prod` |

**Manifests required** (namespace `platform`):

- `postgres`: Deployment (`replicas: 1`, `strategy: Recreate`), PVC 20 Gi,
  Service (ClusterIP, no ingress — never expose Postgres publicly)
- `dagster-webserver`: Deployment, Service, Ingress
- `dagster-daemon`: Deployment, no Service
- `api`: Deployment (2 replicas — it is stateless, and this gives you zero-downtime
  rollouts), Service, Ingress
- `metabase`: Deployment, PVC 5 Gi, Service, Ingress
- `pg-backup`: CronJob, nightly
- `cert-manager` ClusterIssuer for Let's Encrypt

**Probes matter more than they look.** `livenessProbe` on `/health` restarts a
hung process that has not exited — the failure mode Compose cannot catch and one
of the few concrete operational wins of moving to k8s. `readinessProbe` on
`/ready` keeps traffic away from a pod whose DB connection is not up yet.

**Ingress routing:**

```
api.<yourdomain>        → api:8000              (public)
dagster.<yourdomain>    → dagster-webserver:3000 (auth required)
bi.<yourdomain>         → metabase:3000          (Metabase's own auth)
```

Dagster's UI has **no built-in authentication**. Exposing it publicly means
anyone can trigger runs and read your config. Either put Traefik basic-auth
middleware in front of it, or do not expose it at all and reach it over
Tailscale. This is the single easiest way to get this setup compromised.

**Cluster access:** do not expose the k3s API server (6443) to the internet.
Install Tailscale on the node and run `kubectl` over it.

**Resource requests** — set these, or a single runaway process starves the node:

```
postgres:           request 512Mi / 250m   limit 2Gi / 1000m
dagster-webserver:  request 256Mi / 100m   limit 1Gi  / 500m
dagster-daemon:     request 256Mi / 100m   limit 1Gi  / 500m
api:                request 128Mi / 100m   limit 512Mi / 500m
metabase:           request 1Gi   / 250m   limit 2Gi  / 1000m
```

---

## 15a. Access and exposure model

Two planes, and the distinction is the whole security design.

**Public plane — exactly one hostname.**

```
api.<yourdomain>   → api:8000   (TLS via cert-manager, behind Cloudflare)
```

That is the entire public attack surface. Nothing else gets an Ingress with a
public DNS record.

**Admin plane — Tailscale only.** Dagster, Metabase, the Elementary report and
(later) Grafana bind to the node's Tailscale interface. No public port, no
login page to attack, no TLS to manage, no credentials to rotate.

```
dagster.<tailnet>.ts.net    → dagster-webserver:3000
bi.<tailnet>.ts.net         → metabase:3000
reports.<tailnet>.ts.net    → elementary report (static files)
```

**Dagster's UI ships with no authentication whatsoever.** Anyone who reaches it
can trigger runs, read resource configuration and browse your environment. A
public Ingress pointing at it is the single most likely way this setup gets
compromised. Tailscale removes the question rather than answering it.

**Never expose:** Postgres (5432), the k3s API server (6443). Run `kubectl`
over the tailnet.

If a browser-reachable admin portal is ever wanted from a machine without
Tailscale, the alternative is Cloudflare Tunnel plus Cloudflare Access on the
free tier — identity at the edge, still no public origin port. Do not build a
login portal yourself.

---

## 16. CI/CD

**`ci.yml`** — on every push:
`ruff` → `mypy` → `pytest` → `dbt parse` → `dbt build` against ephemeral Postgres
(GitHub Actions service container) → build both images to validate the
Dockerfiles.

**`deploy.yml`** — on merge to `main`:
build `linux/arm64` images → tag with git SHA **and** `latest` → push to GHCR →
`kubectl set image` for each Deployment.

Tagging with the SHA is what makes `kubectl rollout undo` meaningful. Deploying
only `latest` gives you no rollback target and defeats one of the main reasons
for running k8s at all.

Do not add ArgoCD in v1.

---

## 17. Backup and recovery

`warehouse` is derived — rebuildable from `raw` by re-running dbt. But `raw`
itself is **not** reproducible: FRED will not give you back a response you failed
to store, and revision history accumulated over months is genuinely irreplaceable.

Nightly CronJob: `pg_dump` all three databases → gzip → Hetzner Object Storage
(S3-compatible), 30-day retention.

**Test the restore.** An untested backup is a hypothesis. Restore into a local
Compose stack once, before you have anything worth losing.

---

## 18. Observability

Three distinct layers. Conflating them is how observability becomes a project
of its own.

| Layer | Question | Tool | When |
|---|---|---|---|
| Pipeline | Did it run? What broke? | Dagster UI | M1 |
| Data quality | Is the data behaving? | Elementary (§9) | M2 |
| Infrastructure | Is the box healthy? | Prometheus + Grafana | after M8 |

**Do not rebuild layer 1 in Grafana.** Dagster already has run history, lineage,
materialization metadata and check results. Pointing Prometheus at it duplicates
a working UI.

Add on top in phase 1:

- Structured JSON logging from FastAPI and ingest code
- A weekly digest — the pipeline's obligation to you. Series updated, checks
  failed, largest revisions, freshness violations. Delivered by email or as a
  page on your site. This is the thing that keeps the system alive: if it breaks,
  you notice, because you were going to read it.

**Phase 2 (after M8):** the `kube-prometheus-stack` Helm chart gives Prometheus,
Alertmanager, Grafana and node-exporter in one install. Budget ~1.5 GB RAM,
which is why it waits until the CAX21 is otherwise settled. Add
`postgres_exporter` alongside it. Grafana is a stateless query frontend —
Prometheus holds the data — so it costs nothing to throw away and redo.

Deferred until there is something worth waking up for: Alertmanager routing.
Loki is not needed at one node with `kubectl logs`.

---

## 19. Extension points

How a future payload plugs in, with no changes to anything above:

**New data source** → a Dagster ingest asset writing to `raw.source_fetch`,
rows in `series_catalog`, a `stg_` model. Nothing else.

**Equity / market payload** → identical ingest pattern, its own mart schema, its
own API router. Reuses the bitemporal grain directly for point-in-time data.

**Energy payload (ENTSO-E, SMARD)** → same ingest pattern, same bitemporal
grain, hourly rather than monthly resolution. Explicitly deferred: it is listed
here only to record that the architecture already accommodates it, so the
decision can be made later on evidence rather than now on enthusiasm.

**Relocation scoring** → a mart schema over country-level series plus a scoring
module behind a `POST /v1/score` endpoint taking user preference weights. The
sensitivity analysis is computation, so it belongs in FastAPI, not Cube.

**LLM narration** → separate container. Hard rule: the semantic layer computes,
the model narrates. Numbers never originate in the model. The service takes a
question, emits a constrained query spec validated against the schema, executes
it, and passes only the returned numbers plus catalog descriptions back for
verbalization.

**CMS** → separate `cms` database, separate FastAPI service, own migrations.
dbt never touches it. Astro pulls at build time, so the public site stays static
and survives the box being down. Note that this database holds source-of-truth
data, not derived data — the backup obligation is real rather than precautionary.

---

## 20. Build order

| # | Milestone | Done when |
|---|---|---|
| M-1 | Agent scaffolding (§22) | `make check` exists and exits 0 on an empty repo; `CLAUDE.md` committed |
| M0 | Repo, Compose, Postgres, schemas, roles | `make up` gives a healthy Postgres with `raw`/`marts` created |
| M1 | FRED ingest as a Dagster asset | Clicking materialize in the Dagster UI lands rows in `raw.source_fetch` |
| M2 | dbt staging → mart as Dagster assets; Elementary installed | `fct_macro_observation_latest` is populated, lineage renders, `elementary` tables have one run recorded |
| M3 | FastAPI with observations endpoints | `curl` returns correct JSON with the envelope; bounds return `400` |
| M4 | One chart on the Astro site from the live API | Chart renders from your machine |
| M5 | Daily schedule, unattended, one week | Seven consecutive green runs, no manual intervention |
| M6 | ECB + Bundesbank added | Three sources, unified mart, no source names below `intermediate` |
| M7 | Hetzner CAX + k3s + Tailscale, manifests, ingress, TLS, backup | Public HTTPS on `api.` only; admin plane reachable solely over the tailnet; restore tested |
| M8 | GitHub Actions build → GHCR → deploy | Merge to `main` reaches production untouched |

**Tailscale is installed before the first Ingress exists, not after.** The
window between "the box is on the internet" and "access control is configured"
is the one that gets exploited.

**M5 is the milestone people skip.** A week of unattended daily runs surfaces
every bad assumption about credentials, retries, timezones, idempotency and
API rate limits. Find them on the Air, not on Hetzner.

Only after M8 should Cube, the LLM layer, or a second payload be considered.

---

## 21. Open decisions

- Canonical `series_id` naming convention — suggest `{ISO2}_{CONCEPT}_{TRANSFORM}`,
  e.g. `DE_CPI_YOY`. Decide before writing the seed; renaming later is painful.
- Whether `known_at` should be `date` or `timestamptz`. `date` is simpler and
  sufficient for macro; market data may later want `timestamptz`. Consider
  `timestamptz` now to avoid a migration.
- ~~Metabase versus Grafana~~ — **decided: Metabase**, for exploration and as
  the BI-tool demonstration. Grafana arrives separately in phase 2 for infra
  metrics, not as a replacement.
- Hetzner instance size — start CAX21 (4 vCPU / 8 GB). Verify current pricing
  directly; it is in the region of a few euros per month either way.
- Which milestones are built by hand rather than by agent (§22, last note).
  Decide before M0, not during it.

---

## 22. Agentic build model

The build is executed by an orchestrator/executor agent split. This section is
written to be read *by the agents* as well as by the operator — it is the
contract, not commentary.

### 22.1 Model assignment

| Tier | Model | Role | Why |
|---|---|---|---|
| Orchestrator | `claude-fable-5` | Decomposition, sequencing, review, acceptance | Low token volume, highest leverage per token |
| Executor | `claude-opus-5` | Implementation, wiring, debugging loops | High token volume, half the per-token cost |
| Mechanical | `claude-sonnet-5` | Boilerplate, docstrings, test scaffolds, formatting | Repetitive, verifiable, cheap |

The economics are the point of this arrangement. Output tokens dominate an
agentic bill, and output volume concentrates in implementation and debugging,
not in planning. Putting the expensive model where token volume is *lowest* and
leverage is *highest* is the correct structure — the same reasoning as sizing a
capacity unit against the query that consumes it.

**Corollary that is easy to get wrong:** do not let the orchestrator write code.
Every time it does, you are paying 2× for tokens whose value is 1×. Its outputs
should be briefs, reviews and accept/reject decisions — nothing that ends up in
a file.

### 22.2 Repo preconditions (M-1)

Agents cannot verify their own work against a spec they cannot execute. Before
any implementation begins, the repo must contain a machine-checkable definition
of "done".

```makefile
check: lint type test dbt-parse      # ONE command, exit code is the verdict
lint:      ruff check . && ruff format --check .
type:      mypy orchestration api
test:      pytest -q
dbt-parse: cd dbt && dbt parse
up:        docker compose up -d --wait
smoke:     ./scripts/smoke.sh        # curl every endpoint, assert 200/400
```

`make check` returning 0 is the only acceptance signal an executor may claim.
"I have implemented X" without a green `make check` is not a completed task.

**`CLAUDE.md` at repo root** — loaded into every agent's context. Contents:

- Pointer to this spec as the authoritative design document
- The five design principles (§1), verbatim
- The invariants list (§22.5)
- Commands: `make up`, `make check`, `make smoke`, how to reach Dagster locally
- Environment facts: macOS, arm64, Docker Desktop, Compose not k3s until M7
- The rule that **no agent edits `sql/001_init.sql` or the bitemporal grain
  without an explicit human decision**

### 22.3 Sub-agent taxonomy

Six executors, each with a bounded blast radius. The boundaries follow the
directory structure so that two agents never contend for the same file.

| Agent | Owns | Model | Never touches |
|---|---|---|---|
| `infra` | `docker-compose.yml`, `images/`, `Makefile`, `k8s/` | Opus | `dbt/`, `api/` |
| `ingest` | `orchestration/assets/ingest_*.py`, `resources/` | Opus | `dbt/models/`, `api/` |
| `transform` | `dbt/` (models, seeds, tests, Elementary config) | Opus | `orchestration/`, `api/` |
| `api` | `api/` (routers, Pydantic models, db) | Opus | `dbt/`, `orchestration/` |
| `verify` | Nothing — read and run only | **Fable** | Every file |
| `scaffold` | Tests, docstrings, `.env.example`, README | Sonnet | Logic of any kind |

**`verify` is the one that matters and the one that gets cut.** It runs
`make check` and `make smoke` independently, reads the diff against this spec,
and returns `ACCEPT` or `REJECT` with specific findings. It must be at least the
same tier as the implementer, and preferably higher — when generation is cheap,
verification is the bottleneck, and a reviewer weaker than the writer is
decoration.

`verify` may not edit files. If it could, it would fix what it found and stop
reporting, and you would lose the signal.

### 22.4 Task brief contract

The orchestrator's only artifact. A sub-agent starts in a fresh context and sees
none of the orchestration conversation — everything it needs must be in the
brief. Incomplete briefs are the dominant failure mode of this architecture, far
ahead of model capability.

```
TASK:        <one sentence, one milestone or smaller>
SPEC REFS:   <section numbers from this document>
FILES:       <exact paths this agent may create or modify>
FORBIDDEN:   <paths it must not touch>
PRECONDITION:<what is already true — e.g. "M0 complete, postgres healthy">
DONE WHEN:   <a command and its expected exit code / output>
CONTEXT:     <decisions already made that are not in the spec>
BUDGET:      <soft turn limit; escalate rather than grind>
```

`DONE WHEN` must be executable. "The API works" is not a completion criterion;
`make smoke` exiting 0 is.

**Escalation rule:** an executor that fails the same check three times stops and
returns the failure to the orchestrator. It does not keep trying. Three failed
attempts at $25/M output is how a $200 build becomes an $800 one, and the fourth
attempt is almost never the one that works — the brief was wrong.

### 22.5 Invariants — agents may not violate these without human approval

1. `raw.source_fetch` is append-only. No `UPDATE`, no `DELETE`, no schema change.
2. The fact grain is `(series_id, obs_date, known_at)`. Not negotiable, not
   "simplified for now".
3. No source name (`fred`, `ecb`) appears in any model at or below `marts`.
4. The API connects as `platform_reader` and reads only `marts`/`meta`/`elementary`.
5. No credential, API key or connection string is written to any file except
   `.env` (gitignored) or `.env.example` (placeholders only).
6. No new service is added to `docker-compose.yml` without an explicit decision.
   Agents add services when stuck; that is how a five-container stack becomes
   eleven.
7. Nothing binds to `0.0.0.0` on a public interface. Local port publishing is
   for Compose on the laptop only.

Put these in `CLAUDE.md` verbatim. An invariant an agent cannot see is not an
invariant.

### 22.6 Execution sequence per milestone

```
orchestrator (Fable)
  ├─ reads spec section + current repo state
  ├─ writes task brief(s)
  │
  ├─→ executor (Opus)  implements, runs `make check` itself, iterates ≤3
  │
  ├─→ verify (Fable)   independent `make check` + `make smoke` + diff review
  │                     → ACCEPT / REJECT + findings
  │
  ├─ on REJECT: revised brief (not "try again")
  └─ on ACCEPT: commit, next milestone
```

One milestone per orchestration cycle. Do not let the orchestrator plan M0
through M8 in one pass — the state of the repo after M2 changes what M3's brief
should say, and a plan written before M0 will be stale by M3.

### 22.7 Cost control mechanics

- **Prompt caching is not optional.** `CLAUDE.md` plus the spec is a large
  stable prefix repeated on every turn. Cached reads bill at 10% of input rate;
  without caching this prefix alone can be a third of the bill.
- **Keep sessions short and scoped.** Cost scales with context length × turns.
  A fresh session per milestone is cheaper than one long-running session that
  drags the whole history through every turn.
- **Batch what can wait.** Documentation passes, docstring sweeps and test
  backfills are asynchronous work; the Batch API is 50% off both sides.
- **Do not run the orchestrator on trivia.** File renames, formatting and
  dependency bumps go to Sonnet or to you.
- **Instrument from turn one.** Record spend per milestone. After M2 you will
  have a real cost-per-milestone figure and every estimate below becomes
  obsolete — which is the intended outcome.

### 22.8 What should not be delegated

The k3s work (§15) and the bitemporal model (§6) were chosen partly for what
building them teaches. An agent that builds them well leaves you with a working
cluster and no operational intuition, which defeats one of the project's stated
purposes.

Suggested split:

- **Agent-built:** Compose scaffolding, Dockerfiles, Pydantic models, dbt
  staging models, tests, CI YAML, README — anything where the value is the
  artifact.
- **Hand-built, agent-assisted:** the k8s manifests, the ingress and Tailscale
  configuration, the first backup restore, the bitemporal SQL — anything where
  the value is the debugging.

Decide this before M0. Deciding it mid-build reliably resolves toward "let the
agent do it", because by then you are tired.
