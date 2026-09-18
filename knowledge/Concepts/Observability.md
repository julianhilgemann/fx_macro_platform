---
title: Observability
type: concept
status: seedling
tags: [observability, operations, telemetry]
created: 2026-09-18
updated: 2026-09-18
aliases: []
---

# Observability

Observability is the ability to understand a system's internal state from the data it emits, chiefly metrics, logs, and traces.

## Why it matters

- It answers questions that were not anticipated in advance, without shipping new code or guessing.
- The three signals complement each other: metrics are cheap aggregates, logs carry detail, traces show where time went across services.
- It turns incidents into evidence-based debugging, so symptoms can be separated from causes.
- It is the measurement basis for reliability work, because SLOs need data before they can be defined.

## How it works

Instrumentation emits telemetry, a backend stores it, and a query layer makes it explorable. Correlation is what makes the set useful: a shared trace or request identifier across logs, metrics, and traces.

```yaml
signals:
  metrics: "aggregatable numbers over time, cheap to keep, watch cardinality"
  logs:    "timestamped events, richest detail, most expensive to store"
  traces:  "one request across services, shows latency and failure path"
correlation: [trace_id, service_name, run_id]
```

## In this platform

The discipline is not yet in place, though there is a written plan. `docs/observability-plan.md` exists and is explicitly a proposal with nothing applied, and `platform-spec.md` already defines the three layers and warns against rebuilding Dagster or Elementary in Grafana. Today the visible signals are Dagster run status, Elementary data-quality reports, and manual `docker compose logs` and `docker stats`. This note covers the discipline; the concrete tooling is [[Observability Stack]].

## Related

- [[Observability Stack]]
- [[SRE Basics]]
- [[Data Quality]]

## Further reading

- [CNCF observability whitepaper](https://github.com/cncf/tag-observability/blob/main/whitepaper.md)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
- [Observability Engineering, O'Reilly](https://www.oreilly.com/library/view/observability-engineering/9781492076438/)
