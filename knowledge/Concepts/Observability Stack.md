---
title: Observability Stack
type: concept
status: seedling
tags: [observability, monitoring, tooling]
created: 2026-09-18
updated: 2026-09-18
aliases: [Prometheus Grafana Loki]
---

# Observability Stack

An observability stack is the concrete tooling that collects, stores, queries, and displays telemetry; here Prometheus for metrics, Loki for logs, and Grafana for display.

## Why it matters

- Responsibilities are split cleanly: applications and exporters emit, Prometheus and Loki store, Grafana only reads.
- Label-based storage allows queries across services, such as all dbt events in the last hour, which per-container logs cannot answer.
- Alert rules live beside the data in Prometheus, so alerting does not depend on someone watching a dashboard.
- Retention and cardinality are configurable, which keeps storage cost proportional to value.

## How it works

Prometheus scrapes HTTP endpoints on an interval. Loki receives log streams, usually from an agent such as Promtail or Alloy. Grafana adds both as datasources. Tracing needs a third store, commonly Tempo.

```yaml
scrape_configs:
  - job_name: node
    static_configs: [{targets: ["localhost:9100"]}]
  - job_name: cadvisor
    static_configs: [{targets: ["localhost:8080"]}]
```

## In this platform

None of this is applied. `docs/observability-plan.md` describes Prometheus, Loki, and Grafana as the target for infrastructure and application signals, and it is a proposal that explicitly warns against rebuilding Dagster and Elementary in Grafana. The stated gaps are Streamlit calculation visibility, unified searchable logs, and container resource history beyond live `docker stats`. The plan aligns with the layer split in `platform-spec.md` and would land on the planned Hetzner and [[K3s]] environment.

## Related

- [[Observability]]
- [[SRE Basics]]
- [[K3s]]

## Further reading

- [Prometheus documentation](https://prometheus.io/docs/introduction/overview/)
- [Grafana Loki documentation](https://grafana.com/docs/loki/latest/)
- [Grafana documentation](https://grafana.com/docs/grafana/latest/)
