---
title: Current State
type: platform
status: growing
tags: [platform, assessment, status]
created: 2026-09-18
updated: 2026-09-18
aliases: [State Assessment, What Works]
---

# Current State

An honest inventory as of 2026-09-18. The point of this note is to be accurate,
not encouraging. Everything here is evidenced by the repository or by a command
that was actually run.

## What genuinely works

- **Ingest to raw landing.** FRED, ECB and Bundesbank fetches land as immutable
  JSON with sha256 indexing and quarantine of failed payloads.
- **The warehouse and models.** Postgres with a bitemporal grain, dbt staging and
  marts, roughly 110 series, real history loaded.
- **Serving.** A FastAPI layer with documented endpoints, Streamlit analytics,
  a D3.js Germany dashboard, Metabase and CloudBeaver, all running locally.
- **Orchestration exists.** Dagster defines the assets and a daily schedule.

## What is incomplete

- **The schedule has never run.** Dagster's `instigators` table is empty. All ten
  runs so far were manual: six succeeded, four failed. See B1 in
  [[Platform Delivery Plan]].
- **Revision history is not captured.** FRED's ALFRED real-time parameters are
  never sent, so every observation in a fetch shares one vintage date. ECB and
  Bundesbank re-stamp the whole history on each fetch. Roughly 6,955 rows in one
  series all carry the same `realtime_start`.
- **No CI.** `.github/workflows/` does not exist.
- **No backups.** There is no `pg_dump` job and no restore has ever been tested.
- **No authentication.** Every admin surface binds to `0.0.0.0` with nothing in
  front of it.
- **`make check` cannot fail.** Every probe ends in `|| echo FAIL`, so the target
  exits 0 even when things are broken. Verified: `make check; echo $?` returns 0
  while printing failures.

## What is actively wrong

- **`ECB_HICP` is 291 days stale**, last observation 2025-12-01. The next worst
  series is 170 days. Nothing flags it. Whether this is an upstream-empty
  response or a parser bug is not yet known, so it is diagnose-then-fix.
- **Staging reads all raw history.** `stg_fred` fans out over every fetch ever
  made, producing 745,450 fact rows and 5,475,118 transform rows, all
  full-refresh. It degrades with every run.
- **`payload_sha256` is written and never read.** The column and its index exist;
  nothing uses them for change detection.
- **The series catalogue is maintained twice**, in `ingest/config.py` and
  `dbt/seeds/series_catalog.csv`, and `docs/api-calls.md` contradicts itself
  about which is authoritative.
- **There are no Dagster asset checks.** `platform-spec.md` §8 asks for four.
  The 97 `asset_check_executions` rows all come from dbt tests via
  `dagster-dbt`, which is not the same guarantee.

## Known documentation drift

- `docs/migration-plan.md` §5.1 says FRED `known_at` degrades to fetch time. The
  detail is subtler: raw payloads do carry `realtime_start`, but it is
  request-scoped, so one date covers a whole response rather than capturing
  revision history. Filed as a vintage-backfill gap, not a simple bug.
- The liveability documents disagree internally on country count (45 / 15 / 18 /
  19) and child cost (about 6% / 28% against a seed of 0.10 / 0.40), and the
  model applies a flat 5% exit-tax haircut while the worked example uses a
  500,000 / 26.375% rule.

## Two claims that were checked and rejected

Recorded so they are not re-raised:

- "The day grain forward-fills a leading NULL." Not true. The calendar starts at
  the series' first observation, so no leading NULL exists. The real issue is
  that forward-filled days are indistinguishable from observed ones.
- "Postgres intervals do not clamp." Tested directly: `date '2024-03-31' -
  interval '1 month'` returns 2024-02-29. Postgres clamps. The period-metrics
  docstring is accurate.

## Related

- [[FX Macro Platform]]
- [[Platform Delivery Plan]]
- [[Stack Inventory]]
- [[Observability]]
