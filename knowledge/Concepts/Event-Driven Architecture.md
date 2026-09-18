---
title: Event-Driven Architecture
type: concept
status: seedling
tags: [architecture, events, decoupling]
created: 2026-09-18
updated: 2026-09-18
aliases: [EDA, event-driven]
---

# Event-Driven Architecture

Event-driven architecture is a style in which components publish facts about what happened and other components react, instead of calling each other directly.

## Why it matters

- Producers stop needing to know who consumes their output, which allows new consumers without changes to the producer.
- Events are facts about the past, so they can be replayed to rebuild state or backfill a new model.
- Temporal decoupling absorbs load spikes and lets a consumer be down without failing the producer.
- The event log becomes an audit trail, which matters for data whose revisions must be explainable.

## How it works

A producer appends an event to a log or broker. Consumers subscribe, often with a consumer group, and acknowledge after processing. Two common shapes are event notification, which carries only an identifier, and event-carried state transfer, which carries the payload.

```yaml
event:
  type: fx.observation.landed
  key: DEXUSEU
  occurred_at: 2026-09-18T06:00:00Z
  payload: {source: fred, obs_date: 2026-09-17, known_at: 2026-09-18}
  idempotency_key: sha256:9f2c...
```

Delivery is usually at-least-once, so consumers must be idempotent.

## In this platform

FX Macro Platform is not event-driven today. Dagster drives the pipeline from a daily schedule, and Elementary data-quality reports are produced on that same cadence. There is no message broker in the Compose footprint. The closest thing to an event log is the append-only raw JSON landing area indexed by sha256, which records what arrived and when, and would make a natural source of change events if a broker were ever added.

## Related

- [[CQRS]]
- [[Change Data Capture]]
- [[Idempotency]]

## Further reading

- [What do you mean by event-driven? Martin Fowler](https://martinfowler.com/articles/201701-event-driven.html)
- [CloudEvents specification](https://cloudevents.io/)
- [Enterprise Integration Patterns, messaging](https://www.enterpriseintegrationpatterns.com/patterns/messaging/)
