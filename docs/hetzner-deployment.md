# Hetzner Deployment Plan (v1)

**Status: planned, not yet deployed.** The platform currently runs locally
(uv + local pipeline + FastAPI). This is the runbook for when we go live on a
single Hetzner box. Nothing here changes the local setup.

## Decision

**Docker + compose, image built on the box, cron on the host.**

Why Docker (it's the *easier* path here, not the harder one):
- Bakes Python 3.12 + uv + deps into the image → no fighting the server's
  environment, no `uv`-not-on-PATH-in-cron gotcha, no systemd unit to hand-write.
- The app is a tiny target: **one long-running service (API)** + **one
  run-to-completion job (pipeline)**. Small Dockerfile + small compose file.
- Build on the Hetzner box (`git clone` + `docker compose build` there) so we
  never cross-compile ARM(Mac)→amd64 and need no registry.

Bare-metal (uv + systemd + host cron) remains a valid fallback but is fiddlier.

## Code changes needed before deploy (not yet done)

1. **`Dockerfile`** — python:3.12-slim base, install uv, copy repo, `uv sync`.
2. **`docker-compose.yml`** — two services and two named volumes:
   - `api`: long-running `uvicorn api.main:app`, `restart: unless-stopped`,
     reads the warehouse volume, `env_file: .env`.
   - `pipeline`: run-to-completion (`run_pipeline.sh`), invoked via
     `docker compose run --rm pipeline`; writes the raw + warehouse volumes.
   - volumes: `raw/` and `warehouse/` (the only stateful things; never baked
     into the image).
3. **DuckDB build-then-swap** in `scripts/run_pipeline.sh` — the one real
   architectural change (see below). Needed with or without Docker.
4. *(Optional, recommended for unattended runs)*
   - Per-source fault tolerance in `ingest/fetch.py`: log-and-continue if one
     source (FRED / Bundesbank) is down, instead of failing the whole run.
   - `/health` reports `max(loaded_at)` so pipeline staleness is visible.

### DuckDB build-then-swap (why it matters)

DuckDB is single-writer: the API (read-only) and the cron pipeline (read-write)
can't hold the same file at once across processes. Overlap → a request 503s, or
worse the pipeline fails to get the lock. Fix, in `run_pipeline.sh`:

```
cp warehouse/fx_macro.duckdb  warehouse/fx_macro.build.duckdb   # or build fresh
# loader + dbt target DUCKDB_PATH=...build.duckdb  (writer never touches live file)
mv warehouse/fx_macro.build.duckdb  warehouse/fx_macro.duckdb   # atomic rename
```

The API reads the live file per request and picks up the new inode on the next
connection. Zero contention, no API code change. Works because **`raw/` is the
source of truth** — the DuckDB file is fully rebuildable from it.

## Deploy runbook

```bash
# On the Hetzner box (Ubuntu), once:
apt install -y docker.io docker-compose-plugin
git clone <repo> /srv/fx_macro_platform && cd /srv/fx_macro_platform
nano .env                       # FRED_API_KEY=..., FX_FETCH_MODE=fred  (never in git)
docker compose build            # builds amd64 image on the box
docker compose up -d            # API starts, restarts on reboot/failure
docker compose run --rm pipeline  # first pipeline run to populate the warehouse
```

### Cron (host crontab)

```
# nightly, after FRED (US close) and Bundesbank (afternoon CET) publish
0 22 * * * cd /srv/fx_macro_platform && flock -n /tmp/fxm.lock docker compose run --rm pipeline >> /srv/fx_macro_platform/pipeline.log 2>&1
```

- `flock` prevents overlapping runs; redirect appends a timestamped log.
- Set `DBT_SEND_ANONYMOUS_USAGE_STATS=false` in `.env`.

## Ops

| Concern | Plan |
|---|---|
| **Secrets** | `.env` on the box only (compose `env_file`). Never committed. |
| **Backups** | Back up `raw/` + `.env`. The DuckDB file is derived and rebuildable. |
| **Disk growth** | Each run stores full-history snapshots (~3 MB/day across 7 files) → ~1–1.5 GB/yr, growing. Mitigate later with gzip (~5–10×) or retention; R2 is the roadmap. |
| **Monitoring** | cron `MAILTO`, or a dead-man's-switch ping at end of a successful run. |
| **Exposure / auth** | **No auth in v1.** Keep the API on localhost / private net (SSH tunnel or Cloudflare Tunnel later). Do not expose publicly until the auth + IP/confidentiality gate is cleared. |
| **Sizing** | CX23-class box is plenty (DuckDB + dbt + uvicorn are light). No orchestrator — cron is the right call; Airflow wouldn't fit. |

## Status checklist

- [x] Pipeline runs clean locally (fetch → load → dbt run + test)
- [x] Live multi-source data (FRED + Bundesbank), full differential panel
- [x] Append-only / point-in-time archive validated
- [ ] Dockerfile
- [ ] docker-compose.yml (api + pipeline services, raw/ + warehouse/ volumes)
- [ ] DuckDB build-then-swap in run_pipeline.sh
- [ ] (optional) per-source fault tolerance + `/health` freshness
- [ ] Provision Hetzner box, deploy, wire host cron
