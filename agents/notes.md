# Agent notes — environment facts & gotchas

Durable reference for agentic builds of this repo. Read this before touching
infra, ingest, dbt, or the API. The authoritative spec is
[`platform-spec.md`](../platform-spec.md); the working delta list is
[`docs/migration-plan.md`](../docs/migration-plan.md).

## Environment facts

- **Host:** macOS, Apple Silicon (arm64 / `aarch64`). Docker Desktop installed.
- **Docker:** server 23.x, Compose v2.17.3. Images must be `linux/arm64`.
- **Python:** 3.12, managed by `uv` (lockfile committed as `uv.lock`).
- **DB:** Postgres 16 in Docker Compose (`docker-compose.yml`). Port 5432 on host.
- **Warehouse roles:** `platform_writer` (ingest/dbt), `platform_reader` (API/BI).
  Dev passwords default to `writer_dev` / `reader_dev` (see below).

## Gotchas (each cost real time once)

1. **Docker Desktop execs bind-mounted `.sh` init scripts.** A shebang of
   `#!/usr/bin/env bash` fails with `bad interpreter: Permission denied` when a
   script in `sql/` (mounted to `/docker-entrypoint-initdb.d`) is executed. Use
   `#!/bin/bash` **and** `chmod 755` on any `.sh` placed in `sql/`.
2. **Init scripts run only on first pgdata volume init.** After that the entry
   point skips `/docker-entrypoint-initdb.d`. To re-run bootstrap:
   `make reset` (= `docker compose down -v`) then `make up`. Editing
   `sql/001_init.sh` alone does nothing on an existing volume.
3. **Role password defaults live in three places and must agree:**
   - `docker-compose.yml` (`PLATFORM_WRITER_PASSWORD:-writer_dev`, reader `reader_dev`)
   - `sql/001_init.sh` (same defaults, creates the roles)
   - host-side clients (`ingest/config.py`, `api/`, dbt `profiles.yml`)
   Change one, change all. Real values belong in `.env` (gitignored), never
   committed; `.env.example` documents placeholders only (spec invariant §22.5.5).
4. **In-container `psql -U <role>` over the unix socket is `trust`** (no
   password) — handy for `docker compose exec postgres psql ...` smoke tests.
   Host TCP connections (psycopg/dbt) authenticate with `scram-sha-256` and
   **must** supply the role password. Superuser host password defaults to
   `postgres` (from `POSTGRES_PASSWORD:-postgres`).
5. **Use `docker compose exec -T` for scripted psql** (no TTY), e.g.
   `docker compose exec -T postgres psql -U postgres -d warehouse -tAc "SELECT ..."`.
6. **`postgres:16` is multi-arch** and runs arm64 natively on M-series — no
   platform flag needed locally, but prod images must stay `linux/arm64` (CAX).
7. **FRED live fetch needs `FRED_API_KEY`** in `.env`; without it `FX_FETCH_MODE`
   auto-selects `synthetic`, which emits deterministic FRED-shaped JSON so the
   pipeline still runs end-to-end. Synthetic is the safe CI/no-key path.
8. **Two specs existed until commit `ed73ff3`.** `platform-spec.md` is the single
   source of truth (Postgres + Dagster + bitemporal + k3s). The old
   `fx-macro-platform-spec.md` (DuckDB + cron) was deleted — do not resurrect it.
9. **`raw.source_fetch` is append-only** (spec §5): no `UPDATE`/`DELETE`, and it
   stores one row per *fetch event* (whole response), not per observation.
   Observations are extracted in dbt staging from the `payload` jsonb. `payload`
   is the parsed-to-JSON body; `payload_raw` is the byte-faithful original;
   `payload_sha256` enables change detection.
10. **Bitemporal fields are distinct** (spec §6): `obs_date` (what period the
    value describes), `known_at` (when it became known — FRED `realtime_start`,
    ECB/Bundesbank `fetched_at::date`), `fetched_at` (when we pulled it). Never
    collapse them; the fact grain is `(series_id, obs_date, known_at)`.
11. **A host-local Postgres occupies `127.0.0.1:5432`** (Homebrew). Docker's
    `0.0.0.0:5432` publish loses the loopback race to it, so any client
    connecting to `127.0.0.1:5432` hits the *local* cluster (which has no
    `platform_writer`/`platform_reader`). Fix: the Compose Postgres publishes on
    host port **5433** (`POSTGRES_PORT`); all host-side clients (`ingest/config.py`,
    dbt `profiles.yml`, the API) default to 5433. Verify with
    `lsof -nP -iTCP:5432 -sTCP:LISTEN` if a role-lookup ever mysteriously fails.
