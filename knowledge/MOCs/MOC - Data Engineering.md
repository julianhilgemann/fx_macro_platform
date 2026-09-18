---
title: MOC - Data Engineering
type: moc
status: growing
tags: [moc, data-engineering]
created: 2026-09-18
updated: 2026-09-18
aliases: [Data MOC]
---

# MOC - Data Engineering

The core of the platform. Everything else exists to move this data honestly and
serve it defensibly.

## Agreements and ownership

- [[Data Contracts]], an explicit, testable agreement about shape and meaning
 between producer and consumer.
- [[Data Mesh]], domain ownership and data as a product. An organisational
 pattern, contentious, and only partly applicable to one person.

## Storage and movement

- [[OLTP vs OLAP]], why the warehouse is shaped differently from an application
 database.
- [[Change Data Capture]], deriving a stream of changes from a database's log.
- [[Semantic Layer]], one definition of a metric, defined once and consumed
 everywhere.

## Correctness over time

This is where the platform earns its claim.

- [[Bitemporal Data]], the modelling technique: two independent time axes,
 valid time and knowledge time.
- [[Point-in-Time Correctness]], the guarantee that technique buys: a query
 answered as of a past moment returns only what was knowable then.
- [[Data Quality]], tests, checks and anomaly detection that make failures
 visible.

## Where the platform stands

The bitemporal grain exists in the warehouse, so [[Bitemporal Data]] is
implemented. [[Point-in-Time Correctness]] is not yet guaranteed, because
revision history is not captured: FRED's real-time parameters are never sent and
ECB and Bundesbank re-stamp history on each fetch. A1 in
[[Platform Delivery Plan]] closes exactly that gap, and it is the highest-value
workstream in the plan.

[[Data Quality]] is partial. dbt tests exist and Elementary runs, but there are
no Dagster asset checks and a series sat 291 days stale unnoticed.

## Reading order

[[Bitemporal Data]] and [[Point-in-Time Correctness]] together, since the second
is the reason for the first. Then [[Data Quality]].

## Related

- [[MOC - API Design]]
- [[MOC - Architecture]]
- [[Current State]]
- [[Platform Delivery Plan]]
