---
title: Stack Inventory
type: reference
status: growing
tags: [platform, infrastructure, services]
created: 2026-09-18
updated: 2026-09-18
aliases: [Services, Ports]
---

# Stack Inventory

What runs, where it listens, and what it is for. Local development topology as of
2026-09-18, on macOS arm64 under Docker Compose.

## Services and host ports

Every published port binds to `0.0.0.0`, so all of these are reachable from the
local network, not only from the machine. See C2 in [[Platform Delivery Plan]].

| Host port | Service | Purpose |
|---|---|---|
| 3000 | `dagster-webserver` | Orchestration UI |
| 3001 | `metabase` | BI dashboards |
| 5433 | `postgres` | Warehouse |
| 8000 | `api` | FastAPI serving layer |
| 8080 | `launchpad` | nginx navigation hub |
| 8081 | `elementary-report` | Data-quality report |
| 8082 | `dbt-deps-report` | dbt package report |
| 8083 | `dbt-docs` | dbt lineage and catalogue |
| 8084 | `germany-dashboard` | Germany economy dashboard |
| 8501 | `dashboard` | Streamlit analytics |
| 8978 | `cloudbeaver` | SQL workbench |

`dagster-daemon` publishes nothing. It runs schedules and sensors only.

## Port 5432 is not yours

A native Postgres runs directly on macOS and holds 5432. That is why the compose
file maps the warehouse to 5433: `"${POSTGRES_PORT:-5433}:5432"`. Do not assume a
port is free because no container claims it.

## Free ports

8085 and 8443 were used by a now-removed Plane deployment, and are free again,
along with 80, 443 and 8086.

## The stack

| Layer | Tool | Note |
|---|---|---|
| Ingestion | Python clients for FRED, ECB, Bundesbank | Raw landing is append-only |
| Orchestration | Dagster | Assets defined, schedule never enabled |
| Transformation | dbt | Staging then marts, full-refresh |
| Warehouse | Postgres 16 | Bitemporal grain |
| Serving | FastAPI | Public API |
| Analytics | Streamlit, D3.js | Two surfaces |
| BI | Metabase | |
| Data quality | Elementary, dbt tests | No Dagster asset checks |
| SQL access | CloudBeaver | |
| Navigation | nginx Launchpad | Static index of the above |

## Not present yet

Naming these explicitly, because a stack inventory that only lists what exists
implies completeness:

- Kubernetes or K3s, and any cluster manifests
- Terraform or any infrastructure as code
- CI or CD of any kind
- An identity provider, and therefore any user accounts or roles
- Prometheus, Grafana or Loki
- An API gateway, reverse proxy or TLS termination
- Object storage for backups

Every one of those is planned. See [[Platform Delivery Plan]].

## Related

- [[FX Macro Platform]]
- [[Current State]]
- [[Kubernetes]]
- [[Terraform]]
- [[Observability Stack]]
