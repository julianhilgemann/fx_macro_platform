---
title: Platform Delivery Plan
type: plan
status: growing
tags: [planning, roadmap, delivery]
created: 2026-09-18
updated: 2026-09-18
aliases: [Consolidated To-Dos, 20 Workstreams]
---

# Platform Delivery Plan

Twenty workstreams consolidating the 82 GitHub issues in
[[FX Macro Platform]] with the architect to-do notes. Each workstream is a
chunk of work you can pick up and finish, not a single commit.

The 82 issues are unchanged and remain the atomic record. This note is the layer
above them: it says **what actually has to be true** for each area to be
considered done, and which tickets that implies.

## How to use this

- Pick **one** workstream per weekly block, not one ticket per week. The tickets
  inside a workstream are usually cheaper together than apart.
- `Done when` is the acceptance test. If you cannot demonstrate it, the
  workstream is not finished.
- **Effort** is the summed estimate of the tickets it covers, in points. It is a
  rough index of size, not a schedule. Point totals came from the ticket
  estimates and were never calibrated against real throughput.
- Workstreams that carry no issue numbers are not in the ticket system yet. They
  come from the architect notes and need tickets creating before they can ship.

## At a glance

| # | Workstream | Track | Points | Issues |
|---|---|---|---|---|
| A1 | Bitemporal vintage fidelity | Trust the data | 23 | 6 |
| A2 | Freshness and staleness detection | Trust the data | 5 | 2 |
| A3 | Data quality and asset checks | Trust the data | 25 | 7 |
| A4 | Warehouse scale and incremental rebuild | Trust the data | 18 | 3 |
| A5 | Series catalogue as single source of truth | Trust the data | 11 | 4 |
| B1 | Unattended daily pipeline | Run unattended | 13 | 4 |
| B2 | CI/CD delivery pipeline | Run unattended | 14 | 4 |
| C1 | Public API contract and gateway | Serve as a product | 20 | 8 |
| C2 | Identity, RBAC and access model | Serve as a product | 9 | 4 |
| C3 | Country scoring and Liveability API | Serve as a product | 33 | 7 |
| D1 | Analytics surface hardening | Real infrastructure | 34 | 11 |
| D2 | Germany macro dashboard | Real infrastructure | 21 | 5 |
| E1 | Repo contracts and a build gate that fails | Foundations | 24 | 9 |
| E2 | K3s on Hetzner with Terraform | Foundations | 11 | 2 |
| F1 | Observability stack | Operations | 8 | 2 |
| F2 | Backup, restore and alerting | Operations | 15 | 4 |
| G1 | Documentation, ADRs and C4 diagrams | Legibility | 0 | 0 |
| G2 | Portfolio, positioning and applications | Legibility | 0 | 0 |
| H1 | Capability track: reading and certifications | Compounding | 0 | 0 |
| H2 | Operating rhythm and roadmap review | Compounding | 0 | 0 |

**282 points of ticketed work** across 82 issues, plus five workstreams (G1, G2,
H1, H2 and the non-issue halves of E2 and F1) that are real work with no tickets
yet.

---

## Track A: Trust the data

The platform's whole claim is that it tells you what was knowable, when. Every
other track rests on this one. If a number in a mart cannot be traced to a
vintage, nothing downstream is worth much.

### A1 · Bitemporal vintage fidelity

**Why.** The product promise is point-in-time correctness
([[Point-in-Time Correctness]]). Today the warehouse records *that* a value
arrived, not what was believed before a revision. A macro series that gets
revised (most of them) silently rewrites history.

**Scope**
- Capture real FRED revision history through the ALFRED real-time parameters
  (`realtime_start` / `realtime_end`), which are currently never sent.
- Apply the spec §6 insert-only-on-change rule to ECB and Bundesbank, which today
  re-stamp the entire history with a fresh `known_at` on every fetch.
- Settle and record the `known_at` type decision (`date` vs `timestamptz`).
- Prove it with a regression test that queries as-of a past date and shows only
  what was knowable then.

**Done when.** Two consecutive fetches across a known revision produce two
distinct vintages in the fact table, and an as-of query returns the older value
for the earlier date. A test enforces this so it cannot silently regress.

**Covers** #14 #15 #16 #17 #76 #77 · **23 pts** · **Depends on** nothing. Do this
first.

### A2 · Freshness and staleness detection

**Why.** `ECB_HICP` was 291 days stale and nothing noticed. A platform whose
output is quietly months out of date is worse than one that is visibly down.

**Scope**
- Diagnose the 291-day-stale `ECB_HICP` / `ECB_HICP_CORE` pair, which could be an
  upstream-empty response rather than a parser bug. Treat as diagnose-then-fix.
- Add dbt source freshness on `raw.source_fetch`, plus a check that fails on
  breached thresholds.

**Done when.** The HICP question is answered in writing, and a stale series
raises a visible failure within one scheduled run rather than being discovered by
hand months later.

**Covers** #26 #27 · **5 pts** · **Depends on** B1 to actually run on a schedule.

### A3 · Data quality and asset checks

**Why.** `platform-spec.md` §8 asks for four Dagster asset checks and there are
none. The 97 `asset_check_executions` rows come from dbt tests via
`dagster-dbt`, not from checks the platform authors. Tests exist; guarantees do
not.

**Scope**
- Implement the four spec §8 asset checks: freshness, volume, nulls, and
  revision.
- Add the missing relationships test from `fct_macro_observation.series_id` to
  `dim_series`.
- Apply Elementary anomaly tests now that enough history exists.
- Add tests pinning the documented semantics of the grain, transform and
  period-metric marts.
- Mark forward-filled observations in the day-grain mart so interpolated rows are
  distinguishable from observed ones ([[Data Quality]]).
- Resolve the `index_100` base mismatch between the mart and its documentation.

**Done when.** A deliberately corrupted or stalled input fails a check inside
Dagster, and forward-filled rows are identifiable in the mart.

**Covers** #25 #28 #29 #30 #31 #32 #33 · **25 pts** · **Depends on** A1 for the
revision check.

### A4 · Warehouse scale and incremental rebuild

**Why.** Staging reads all raw fetch history, producing 745,450 fact rows and
5,475,118 transform rows, all full-refresh. This gets worse with every fetch, and
`payload_sha256` exists but is never read.

**Scope**
- Use `payload_sha256` to skip downstream work when a fetch is byte-identical.
- Bound the staging fan-out to the newest payload per `(source, resource)`.
- Incrementalise or partition the fact and transform marts.

**Done when.** A rebuild after a no-op fetch does no downstream work, and a
report of run time shows the trend flattening rather than growing linearly with
history.

**Covers** #18 #19 #20 · **18 pts** · **Depends on** A1.

### A5 · Series catalogue as single source of truth

**Why.** 110 series are maintained twice, in `ingest/config.py` and
`dbt/seeds/series_catalog.csv`. They agree today by luck. The platform's own docs
contradict each other about which is authoritative.

**Scope**
- Make `dbt/seeds/series_catalog.csv` the registry and have ingest read it.
- Serve `/ops` catalogue from `marts.dim_series` instead of importing
  `ingest.config`.
- Add a consistency test between seed and ingest during the transition.
- Remove the dead `PENDING_SERIES` placeholder.

**Done when.** Adding a series is a one-line seed change. Editing
`ingest/config.py` is no longer possible or no longer matters.

**Covers** #21 #22 #23 #24 · **11 pts** · **Depends on** nothing.

---

## Track B: Run unattended

### B1 · Unattended daily pipeline

**Why.** Dagster's `instigators` table is empty. All ten runs so far were manual,
six succeeded and four failed. The platform does not yet run itself, which is the
precondition for trusting anything it produces.

**Scope**
- Enable the daily schedule and prove seven consecutive unattended green runs.
- Add retry/backoff and failure surfacing to the ingest clients.
- Emit bytes and per-source attempt/success/failure counts from the ingest asset.
- Retire `scripts/run_pipeline.sh` or wrap it in Dagster so there is one entry
  point.

**Done when.** Seven consecutive scheduled runs succeed with no manual
intervention, and a failed source is visibly reported rather than absorbed.

**Covers** #45 #46 #47 #48 · **13 pts** · **Depends on** A1 and A2 to be worth
trusting.

### B2 · CI/CD delivery pipeline

**Why.** There is no `.github/workflows/`. Nothing gates a change and no image is
published, so "it works" means "it worked on my machine".

**Scope**
- Add `ci.yml` implementing the spec §16 pipeline.
- Add `deploy.yml` publishing SHA-tagged arm64 images to GHCR.
- Build all three custom images, not just the platform image.
- Pin CI's dbt path to synthetic fetch mode and document the no-key contract.

**Done when.** A pull request runs lint, types, tests, `dbt parse` and a smoke
test, and merging to `main` publishes images tagged with the commit SHA.

**Covers** #10 #11 #12 #13 · **14 pts** · **Depends on** E1 for the gate to have
something to run.

---

## Track C: Serve as a product

### C1 · Public API contract and gateway

**Why.** The API is the product surface. It currently lacks query bounds,
caching, an origin allowlist, and a pooled connection strategy, and there is no
gateway in front of it.

**Scope**
- Enforce the 50-year range and 20-series query bounds with HTTP 400.
- Enforce a maximum page size with HTTP 400.
- Add CORS with an explicit origin allowlist and `Cache-Control` on observation
  endpoints.
- Give the API a connection pool instead of one connection per request.
- Owner-only `/ops` trigger router with a constant-time key comparison.
- Report real dbt build time in `meta.warehouse_build`.
- Add a gateway with rate limiting in front of the public surface, and an
  explicit [[OWASP Top 10]] review before exposure. See [[API Versioning]],
  [[Idempotency]], [[OpenAPI]], [[Reverse Proxy]].

**Done when.** The OpenAPI document is accurate, every documented bound returns
400 rather than a stack trace, and the API sits behind a rate-limited gateway.

**Covers** #34 #35 #36 #37 #38 #75 #78 #79 · **20 pts** · **Depends on** C2 for
real authentication.

### C2 · Identity, RBAC and access model

**Why.** Every admin surface binds to `0.0.0.0` with no authentication. Installed
on a laptop on a shared network, Dagster, Metabase, CloudBeaver and the dbt
reports are all open. The roadmap's own top-ranked item is to fix this before
anything is exposed.

**Scope**
- Install Tailscale and restrict the admin plane **before** any Ingress exists.
- Guarantee Postgres and the k3s API server are never publicly exposed.
- Remove committed credential defaults and document every key in `.env.example`.
- Choose and deploy an identity provider ([[Identity Providers]]: Keycloak,
  Authentik or Zitadel), then add users and roles ([[RBAC]], [[OAuth 2.0]],
  [[OpenID Connect]], [[JWT]], [[mTLS]]).
- Add a Traefik `rateLimit` middleware on the public API Ingress.

**Done when.** No service is reachable from outside the tailnet or the cluster,
and human access goes through the identity provider with roles that differ by
user.

**Covers** #57 #58 #59 #60 · **9 pts** · **Depends on** nothing. This is
genuinely urgent and cheap.

> [!warning] This workstream breaks the platform spec on purpose
> `platform-spec.md` scopes the opposite. Line 37 lists **user accounts** among
> the things deliberately excluded, line 427 says **"OAuth/JWT is ceremony"** and
> forbids mounting such a router under `/v1`, and lines 429-430 put **"user
> accounts, multi-tenant auth"** explicitly out of scope for v1.
>
> The spec is right for a single-operator data platform. An identity provider,
> RBAC and user management exist here to serve the *portfolio* goal, not the
> platform's own needs: "with RBAC, observability and API-level access control"
> is a claim in the positioning sentence, and it is only true if this workstream
> ships.
>
> That makes it a deliberate scope decision rather than an oversight, and it
> should be recorded as the first [[Architecture Decision Records]] entry, with
> the spec's position quoted and the reason for exceeding it stated. Splitting it
> matters too: Tailscale and closing the admin plane satisfy the spec and are
> urgent on their own, while the IdP and RBAC are portfolio work and can wait.

### C3 · Country scoring and Liveability API

**Why.** This is the concrete product use case the platform exists to serve. It
is also where the documentation and the code disagree most.

**Scope**
- Build the country-level mart over the liveability seed and country series.
- Add `POST /v1/score` accepting user preference weights.
- Collapse the duplicated liveability model into one canonical implementation.
- Reconcile documentation against the seed and the model. The docs disagree
  internally on country count (45 / 15 / 18 / 19) and child cost (about 6%/28%
  against a seed of 0.10/0.40). Choose a winner and record why.
- Replace the flat 5% exit-tax haircut with the documented rule, or label it
  plainly as a placeholder. The worked example uses a 500k / 26.375% rule.
- Wire or delete the unused country-profile fields.

**Done when.** One implementation, one documented number set, and a score
endpoint that a third party could call and reproduce.

**Covers** #39 #40 #41 #42 #43 #44 #82 · **33 pts** · **Depends on** C1 and A1.

---

## Track D: Real infrastructure

### D1 · Analytics surface hardening

**Why.** The Streamlit suite is what a visitor actually sees, and it has zero
test coverage, swallows exceptions, and refits GARCH twice per page load.

**Scope**
- Add unit tests for the analytics modules, currently zero coverage.
- Replace silent exception swallowing with visible failures.
- Consolidate the three duplicated page-level data wrappers into one cached,
  pooled access layer.
- Stop refitting the GARCH family twice per Volatility Studio page load.
- Derive volatility interval quantiles from the requested confidence levels.
- Label synthetic OHLC clearly so range estimators are not read as inference.
- Wire Signal Lab's calendar metrics to the period-metrics mart, or delete the
  dead code path.
- Precomputed grain, transform and period-metric marts for the suite.
- Remove the unused scikit-learn dependency and retire the committed prototype
  artefacts.
- Correct the README claim that the filtered slice feeds every Signal Lab tab.

**Done when.** Analytics logic is tested, a data error surfaces as an error
rather than an empty chart, and page loads do not refit models.

**Covers** #61 #62 #63 #64 #65 #66 #67 #68 #69 #70 #80 · **34 pts** · **Depends
on** A3 for trustworthy inputs.

### D2 · Germany macro dashboard

**Why.** The most complete end-to-end vertical slice, and therefore the best
demonstration of the platform. It also duplicates a data-access layer that should
be shared.

**Scope**
- Real 31-tenor Bundesbank curve.
- Share one data-access layer between the Germany dashboard, the API and the
  Streamlit suite (see D1, same fix).
- Serve the indicator list from `marts.dim_series` rather than a private list.
- Degrade gracefully when a BBSIS tenor is missing rather than 500.
- Endpoint tests.

**Done when.** The dashboard renders from shared marts with no private data
access, and a missing tenor degrades visibly instead of failing.

**Covers** #71 #72 #73 #74 #81 · **21 pts** · **Depends on** D1 (shared access
layer) and A5.

---

## Track E: Foundations

### E1 · Repo contracts and a build gate that fails

**Why.** `make check` prints FAIL-style messages and then exits 0. Every line
ends in `|| echo FAIL`. The gate cannot fail, so it enforces nothing. Everything
else in this plan depends on being able to tell whether a change broke something.

**Scope**
- Make `make check` a real gate: lint, type, test, `dbt parse`, with a truthful
  exit code.
- Add ruff and mypy with repo configuration and dev dependency entries.
- Add `scripts/smoke.sh` asserting 200/400 on every documented endpoint.
- Add pytest coverage for the API layer's bounds and envelope.
- Commit `CLAUDE.md` as the binding agent contract at repo root.
- Record decision records for services added beyond the spec's five-service
  baseline ([[Architecture Decision Records]]).
- Split the single image into `platform-dagster` and `platform-api`.
- Refresh `docs/migration-plan.md` and fix README/Makefile/compose
  contradictions about starting the stack.

**Done when.** Breaking a test makes `make check` exit non-zero, and the repo
describes itself accurately. This is the highest-leverage workstream in the plan.

**Covers** #1 #2 #3 #4 #5 #6 #7 #8 #9 · **24 pts** · **Depends on** nothing.
Start here or alongside A1.

### E2 · K3s on Hetzner with Terraform

**Why.** The platform is a portfolio claim that currently only runs on one
laptop. Production-shaped deployment is what turns it into evidence.

**Scope**
- Author `k8s/base` and `overlays/prod` manifests for the full stack.
- Add liveness/readiness probes and the spec's resource requests and limits.
- Provision the VPS and cluster with [[Terraform]] ([[Infrastructure as Code]]),
  then DNS, TLS, secrets and backups. See [[K3s]], [[Kubernetes]], [[DNS]],
  [[TLS]], [[Load Balancing]].
- Adopt [[GitOps]] so the cluster reconciles from the repo.
- Write the first ADR: why K3s on Hetzner rather than Azure or Fabric.

**Done when.** The full stack runs on Hetzner from a clean provision, deploys
from the repo, and survives a node reboot without manual steps.

**Covers** #55 #56 · **11 pts** of ticketed work, plus substantial unticketed
Terraform, DNS, TLS and secrets work · **Depends on** E1 and C2.

---

## Track F: Operations

### F1 · Observability stack

**Why.** You cannot operate what you cannot see, and right now diagnostics are
bare `print()` calls.

**Scope**
- Decide and deliver observability layer 3, or record a deliberate deferral
  ([[Observability]], [[Observability Stack]]).
- Replace bare `print()` diagnostics in ingest and the API with structured JSON
  logging ([[Observability Stack]]).
- Metrics, logs and traces with Prometheus and Grafana, then basic alerting.
  `docs/observability-plan.md` already exists and should be the starting point.

**Done when.** A failing scheduled run is visible on a dashboard and raises an
alert, without anyone reading container logs by hand.

**Covers** #53 #54 · **8 pts** of ticketed work, plus unticketed
Prometheus/Grafana/Loki deployment · **Depends on** B1 and E2.

### F2 · Backup, restore and alerting

**Why.** There is no backup. For a platform whose value is accumulated history,
that is the single largest uninsured risk in the plan.

**Scope**
- Nightly `pg_dump` to object storage with 30-day retention.
- Test a full restore into a fresh local Compose stack and write the runbook.
- Extend coverage to non-Postgres state: Metabase's H2 store and CloudBeaver.
- Build the weekly digest as the pipeline's obligation to the operator.

**Done when.** A restore has actually been performed from a backup into a clean
environment, and the runbook is one someone else could follow.

**Covers** #49 #50 #51 #52 · **15 pts** · **Depends on** E2 for object storage.

---

## Track G: Legibility

### G1 · Documentation, ADRs and C4 diagrams

**Why.** The work is worth more than the code. A reviewer cannot assess a
platform they cannot navigate, and future-you cannot remember why a choice was
made.

**Scope**
- Hand-draw C4 L1 (system context) and L2 (container) diagrams, then formalise
  them in Structurizr or Mermaid ([[C4 Model]]).
- Create `docs/adr/` and backfill ADRs for decisions already made ([[Architecture Decision Records]]).
- Write `roadmap.md`.
- Write `docs/history.md`, a retrospective reconstructed from past commits.
- Write [[FX Macro Platform]] so the repo explains itself end to end.
- Refresh README, CHANGELOG and `/docs`.

**Done when.** A competent stranger can understand what the platform is, how it
is put together and why, without reading source.

**No tickets yet** · **Depends on** nothing. Can run in parallel with any track.

### G2 · Portfolio, positioning and applications

**Why.** The strategy is explicit: Azure and Fabric for credibility and
cashflow, the open-source K3s platform as the differentiator. That only converts
if it is visible and described in architect language.

**Scope**
- Reframe identity as systems builder and platform architect, not dashboard
  developer.
- Update CV and LinkedIn with architect language.
- One blog post per phase, drawn from real work rather than written from scratch.
- Target roles: Solutions Architect (Data and Integration), Platform Architect,
  Cloud Solution Architect (Data and AI), Product or Technical Product Architect,
  Founding Platform Engineer, Staff Engineer (Data Platform).
- Avoid as destinations: pure BI, governance, dashboard factories, managing
  analysts.
- Apply to startups, scale-ups, Microsoft partners and consultancies.

Use this line:

> I built a composable open-source data platform: Dagster + dbt + Postgres +
> FastAPI + Metabase + Streamlit + D3.js, containerised on K3s, deployed via
> Terraform, with RBAC, observability and API-level access control.

**Done when.** CV and LinkedIn say architect, at least one blog post is published
per completed phase, and applications are going out.

**No tickets yet** · **Depends on** G1 and a deployed E2.

---

## Track H: Compounding

### H1 · Capability track: reading and certifications

**Why.** The plan above is mostly things you already know how to do. The reading
list is what makes the next tier reachable, and certification is what makes it
legible to employers.

**Scope**
- Reading, in this order: *Designing Data-Intensive Applications* (Kleppmann),
  *Platform Engineering on Kubernetes* (Salatino), *Fundamentals of Software
  Architecture* (Richards and Ford), *Terraform: Up and Running* (Brikman),
  *Software Architecture: The Hard Parts* (Ford, Richards et al).
- Work through the vault: [[MOC - Networking]], [[MOC - API Design]],
  [[MOC - Architecture]], [[MOC - Platform Engineering]],
  [[MOC - Security and Identity]], [[MOC - Data Engineering]].
- Consider AZ-305 (Azure Solutions Architect Expert) and DP-600 (Fabric Analytics
  Engineer).

**Done when.** One book finished and its ideas reflected in an ADR or a diagram,
not merely read.

**No tickets yet** · **Depends on** nothing.

### H2 · Operating rhythm and roadmap review

**Why.** This plan fails by drift, not by difficulty. The rhythm is the control
that prevents it.

**Scope**
- One 3 to 4 hour focused block per week. Non-negotiable.
- Ship one workstream chunk per block.
- Write one worklog entry and one ADR per significant decision.
- One diagram per phase, one blog post per phase.
- Monthly roadmap review: re-read this note, re-rank the tracks, record what
  changed and why.

**Done when.** Four consecutive weeks with a shipped chunk and a worklog entry.
If that does not happen, the plan is wrong, not you. Cut scope rather than break
the rhythm.

**No tickets yet** · **Depends on** nothing.

---

## Suggested order

1. **E1** and **C2** first. A gate that fails and an admin plane that is not
   exposed. Both are cheap and everything else leans on them.
2. **A1**, then **B1**. Real vintages, then a pipeline that runs itself.
3. **A2** and **A3** to make failure visible.
4. **C1**, then the rest in whatever order energy allows.
5. **F2** before any real data accumulates. Backups are unglamorous until they
   are the only thing that matters.
6. **G1** and **H2** run continuously in the background rather than as phases.

## Related

- [[FX Macro Platform]]
- [[Current State]]
- [[MOC - Career and Growth]]
- [[Weekly Rhythm]]
