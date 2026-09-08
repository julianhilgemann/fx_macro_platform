# Observability Plan

> Status: **proposal — nothing applied yet.**
> Aligned with `platform-spec.md` §18 ("Observability"), which already defines the
> three layers and explicitly warns against rebuilding Dagster/Elementary in Grafana.

## 1. Goal

Answer three questions, each with its own tool, so we never feel "blind" about
what the containers are doing:

| Layer | Question | Tool (today → target) |
|---|---|---|
| Pipeline | Did the dbt run work? What broke? | Dagster UI `:3000` — **already built** |
| Data quality | Is the data behaving? | Elementary `:8081` + dbt docs `:8083` — **already built** |
| Infrastructure + app activity | Is the box healthy? What is each container *doing right now*? | **Prometheus + Loki + Grafana — this plan** |

Grafana is only the **display/frontend**. It shows nothing by itself: Prometheus
stores metrics, Loki stores logs, and each app/exporters must *emit* them.

## 2. What is already visible (do not rebuild)

- **dbt runs** → Dagster UI `:3000`: every dbt model runs as a `@dbt_assets` job;
  its logs, timing, lineage and failure state are already there. "Why did the dbt
  run fail" is a Dagster question, not a Grafana question.
- **dbt tests / freshness / anomalies** → Elementary `:8081`.
- **Lineage DAG + catalog** → dbt docs `:8083`.
- **Quick checks** → `docker compose logs -f <svc>` and `docker stats`.

## 3. The gaps

1. **Streamlit calculations** (`:8501`) — no native metrics or task queue; a model
   fit happens invisibly. Needs explicit instrumentation (section 9).
2. **Unified, searchable logs** — per-service `docker compose logs` doesn't let you
   filter "all dbt run events across services in the last hour."
3. **Container resource health** — `docker stats` is a live snapshot only; no
   history, no dashboard, no alerting.

## 4. Target architecture

```
                        ┌─────────────────────────────────────────────┐
                        │                  Grafana  :3005             │
                        │   (dashboards: container health, log search,│
                        │    postgres, streamlit model-fit)           │
                        └──────────────┬────────────────┬─────────────┘
                                       │ queries        │ queries
                        ┌──────────────▼───┐      ┌─────▼──────────┐
                        │  Prometheus :9090│      │   Loki  :3100  │
                        └──────▲───────────┘      └────▲───────────┘
                               │ scrape                │ push
        ┌──────────┬───────────┼────────────┬──────────┴───────────┐
        │          │           │            │                      │
   cAdvisor    postgres    Dagster       FastAPI      Alloy (docker-socket tail)
   :8089       exporter     /metrics      /metrics     → ships every container's
   (per-       (pg stats)   (run stats)   (HTTP stats)   stdout/stderr to Loki
    container                                                           │
    CPU/mem/disk)                                            Streamlit/Pushgateway
                                                             (model-fit durations)
```

## 5. Services to add to `docker-compose.yml`

| Service | Image | Host port | Purpose |
|---|---|---|---|
| `grafana` | `grafana/grafana-oss:latest` | `3005 → 3000` | Dashboards + alerting UI |
| `prometheus` | `prom/prometheus:latest` | `9090` | Metrics TSDB |
| `loki` | `grafana/loki:latest` | `3100` | Log store |
| `alloy` | `grafana/alloy:latest` | — | Tail container logs via Docker socket → Loki |
| `cadvisor` | `gcr.io/cadvisor/cadvisor:latest` | `8089 → 8080` | Per-container CPU/mem/disk/net |
| `pushgateway` | `prom/pushgateway:latest` | `9091` | Ephemeral metrics (Streamlit) |
| `postgres-exporter` | `prometheuscommunity/postgres-exporter` | `9187` | Postgres stats |

Ports chosen to avoid collisions: `3000/3001/8000/8080-8083/8501/8978/5433` are all
already taken by the existing stack.

### Proposed Compose block (not applied)

```yaml
  # ---- Observability (local dev) ----
  prometheus:
    image: prom/prometheus:latest
    command:
      - --config.file=/etc/prometheus/prometheus.yml
      - --storage.tsdb.retention.time=15d
    ports: ["9090:9090"]
    volumes:
      - ./observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus

  cadvisor:
    image: gcr.io/cadvisor/cadvisor:latest
    privileged: true            # required for full host metrics
    ports: ["8089:8080"]
    volumes:
      - /:/rootfs:ro
      - /var/run:/var/run:ro
      - /sys:/sys:ro
      - /var/lib/docker/:/var/lib/docker:ro

  loki:
    image: grafana/loki:latest
    ports: ["3100:3100"]

  alloy:
    image: grafana/alloy:latest
    volumes:
      - ./observability/alloy.alloy:/etc/alloy/config.alloy:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro   # docker-source tailing

  pushgateway:
    image: prom/pushgateway:latest
    ports: ["9091:9091"]

  postgres-exporter:
    image: prometheuscommunity/postgres-exporter:latest
    environment:
      DATA_SOURCE_NAME: "postgresql://platform_reader:${PLATFORM_READER_PASSWORD:-reader_dev}@postgres:5432/warehouse?sslmode=disable"
    ports: ["9187:9187"]

  grafana:
    image: grafana/grafana-oss:latest
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}
    ports: ["3005:3000"]
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on: [prometheus, loki]
```

Add to the existing `volumes:` section: `prometheus_data:` and `grafana_data:`.

> ⚠️ **macOS caveat (Docker Desktop):** `cadvisor` reports metrics for the LinuxKit
> VM, not the raw Mac hardware; treat "host" CPU/mem as the Docker VM, which is what
> the containers actually see. Log shipping must use the **Docker socket** driver
> (`loki.source.docker` / `discovery.docker` in Alloy), *not* a host-path mount of
> `/var/lib/docker/containers` (that path lives inside the VM on macOS).

## 6. Prometheus scrape targets (`observability/prometheus.yml`)

```yaml
scrape_configs:
  - job_name: cadvisor
    static_configs: [{ targets: ["cadvisor:8080"] }]
  - job_name: prometheus
    static_configs: [{ targets: ["localhost:9090"] }]
  - job_name: postgres-exporter
    static_configs: [{ targets: ["postgres-exporter:9187"] }]
  - job_name: dagster
    static_configs: [{ targets: ["dagster-webserver:3000"] }]   # /metrics
  - job_name: api
    static_configs: [{ targets: ["api:8000"] }]                # /metrics
  - job_name: pushgateway
    honor_labels: true
    static_configs: [{ targets: ["pushgateway:9091"] }]
```

Dagster's webserver serves Prometheus-format metrics on `/metrics` — **confirm the
exact path at runtime** before finalizing.

## 7. Log shipping (Alloy → Loki)

Alloy tails every container's stdout/stderr through the Docker socket and labels
each stream with `compose_service`, `compose_project`, and `container_name`, so
Loki queries become:

```
{compose_project="fx_macro_platform", compose_service=~"dagster-webserver|dagster-daemon"}
|~ "dbt"          # every dbt log line across the pipeline
```

Sketch of `observability/alloy.alloy`:

```alloy
discovery.docker "containers" { host = "unix:///var/run/docker.sock" }

discovery.relabel "containers" {
  targets = discovery.docker.containers.targets
  rule {
    source_labels = ["__meta_docker_container_name"]
    regex         = "/(.*)"
    target_label  = "container_name"
  }
  rule {
    source_labels = ["__meta_docker_container_label_com_docker_compose_service"]
    target_label  = "compose_service"
  }
  rule {
    source_labels = ["__meta_docker_container_label_com_docker_compose_project"]
    target_label  = "compose_project"
  }
}

loki.source.docker "default" {
  host    = "unix:///var/run/docker.sock"
  targets = discovery.relabel.containers.output
  forward_to = [loki.write.default.receiver]
}

loki.write "default" {
  endpoint { url = "http://loki:3100/loki/api/v1/push" }
}
```

## 8. App instrumentation

### FastAPI (`api/`)
- Add `prometheus-fastapi-instrumentator` (a `pyproject.toml`/`uv.lock` change) to
  expose request counts, latency, and status codes at `:8000/metrics`.
- Structured JSON logging (stdlib `logging` + `python-json-logger`, or `structlog`);
  uvicorn JSON access logs. Every request becomes a Loki-searchable line.

### Ingest (`ingest/fetch.py`)
- Replace bare `print(...)` with structured JSON logs: `{event, series_id, n_rows,
  duration_ms, fetch_mode}`. Ship to Loki via stdout. (Spot-checked: current code
  uses `print`/`json.dumps` for API payloads — move diagnostics to a logger.)

### Streamlit (`dashboard/`)
The important one, because a model fit is otherwise invisible:
- Wrap fits/predicts in `st.status("Fitting SARIMAX…")` / `st.spinner()` for in-UI
  progress.
- Structured log each step: `{event:"model_fit", series, horizon, duration_ms}` → stdout → Loki.
- Push a `streamlit_model_fit_seconds` summary metric to **Pushgateway** `:9091`
  (Streamlit's process is ephemeral, so a scrape endpoint doesn't survive long
  enough; push is the correct pattern). Chart it in Grafana.

### dbt / Dagster
- No Grafana work needed: runs are already in the Dagster UI + Elementary.
- Optional: run dbt with `--log-format json` so its own log lines are also cleanly
  queryable in Loki (Dagster already captures them regardless).

### Postgres
- `postgres-exporter` for connections, cache-hit ratio, slow queries.
- Note: richer `pg_stat_statements`/`pg_monitor` metrics need a privileged role;
  start with the defaults the `platform_reader` role permits and escalate only if
  a dashboard needs more.

### Metabase / CloudBeaver / nginx (launchpad)
- Ship logs to Loki only. Skip app-level metrics initially (Metabase is JVM/Micrometer,
  CloudBeaver is a workbench — low value for the effort). `nginx-prometheus-exporter`
  is optional and not worth it for a static nav page.

## 9. Grafana dashboards (first cut)

1. **Containers** — cAdvisor panels: CPU %, memory, network rx/tx, disk I/O per
   container (`container_name` selector).
2. **Logs** — Loki datasource + a log-panel dashboard; saved queries for
   `dbt` events, `model_fit` events, and ERROR-level lines.
3. **Postgres** — exporter panels: active connections, cache hit ratio, slow queries.
4. **Streamlit model-fit** — Pushgateway gauge: fit duration by series over time.

Provision these as code (Grafana "provisioning" directory or a small bootstrap
script) so they're reproducible, not hand-built in the UI.

## 10. Rollout (mapped to spec §18)

- **Phase 0 (done)** — Dagster UI, Elementary, dbt docs. Layers 1 & 2 complete.
- **Phase 1 (this plan, local Compose)** — add the observability group; structured
  logging in FastAPI/ingest/Streamlit; the four dashboards; optionally the spec's
  "weekly digest" (email/page) as the human-facing tripwire.
- **Phase 2 (after M8, k8s)** — unchanged from spec: `kube-prometheus-stack` +
  `postgres_exporter` on the CAX21. Grafana is stateless and disposable, so the
  local dashboards can be exported and reused.

## 11. Resource budget & caveats

- Roughly **+1–2 GB RAM** for Prometheus + Loki + Grafana + exporters on the dev Mac
  (same order as the spec's ~1.5 GB estimate for the k8s stack).
- Prometheus retention set to `15d` to cap disk; raise only if history is needed.
- **No auth on exporters** — fine on localhost, but bind to the Tailscale interface
  only (per spec §18) before anything is exposed beyond the machine.
- cAdvisor needs `privileged: true` — acceptable for a local dev stack, reconsider
  before the k8s deploy (use node-exporter/kubelet there instead).
- Alloy vs Promtail: Alloy is the forward path (Promtail is deprecated upstream);
  Promtail has more copy-paste docs if Alloy's config syntax fights back.

## 12. Open decisions

1. **Weekly digest** (spec §18) — email, or a simple page in the launchpad? Not
   part of the Grafana work, but it's the spec's chosen "tripwire."
2. **Grafana auth** — default `admin/admin` for local, or set a password in `.env`
   from day one?
3. **Dashboards as code** — commit provisioning YAML, or bootstrap via the Grafana
   HTTP API script (`scripts/` already has metabase bootstrap scripts to mirror)?
