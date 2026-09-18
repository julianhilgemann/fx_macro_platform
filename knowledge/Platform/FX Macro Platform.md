---
title: FX Macro Platform
type: platform
status: growing
tags: [platform, overview, architecture]
created: 2026-09-18
updated: 2026-09-18
aliases: [The Platform, fx_macro_platform]
---

# FX Macro Platform

A point-in-time FX and macroeconomic data platform. It ingests macro series from
public sources, preserves every vintage immutably, models them in a warehouse,
and serves them through an API and a set of analytical surfaces.

The distinguishing claim is not that it stores macro data. Anyone can do that.
The claim is that it can answer **what was knowable on a given date**, which is
the question a backtest, a research note or an audit actually asks.

## The pipeline

```
FRED / ECB / Bundesbank
        |
        v
immutable raw landing          append-only JSON, sha256-indexed,
                               failed payloads quarantined
        |
        v
Postgres warehouse             bitemporal grain:
                               obs_date / known_at / fetched_at
        |
        v
dbt models                     staging -> marts
        |
        +--> FastAPI           public serving surface
        +--> Streamlit         analytics dashboards
        +--> D3.js             Germany economy dashboard
        +--> Metabase          BI
        |
        v
Dagster                        daily orchestration
Elementary                     data-quality reports
CloudBeaver                    SQL workbench
```

About 110 macro series across roughly 12 Docker Compose services.

## Why it is shaped this way

Macro data is revised. A GDP print, a CPI reading or a policy rate is published,
then corrected, sometimes repeatedly and sometimes quietly. A platform that keeps
only the latest value has destroyed the only thing that mattered. Hence the
bitemporal grain: `obs_date` is the period observed, `known_at` is when that value
became knowable, and `fetched_at` records the collection. The first two are the
product. The third is provenance.

That design choice drives almost everything else. It is why raw landing is
append-only, why `payload_sha256` exists, and why the highest-priority workstream
in [[Platform Delivery Plan]] is the one that makes revision capture actually
work.

## What it is for

The concrete use case is country-level scoring and a liveability index, served
through the API. See C3 in [[Platform Delivery Plan]].

Everything else exists to make that answer trustworthy rather than merely
available.

## Reading order

1. [[Current State]] for what is actually true today.
2. [[Platform Delivery Plan]] for what to do about it.
3. [[MOC - Architecture]] for how the pieces fit.
4. [[Stack Inventory]] for what runs where.

## Related

- [[Current State]]
- [[Stack Inventory]]
- [[Platform Delivery Plan]]
- [[MOC - Architecture]]

## Further reading

- `platform-spec.md` at the repository root, the authoritative design document
- [Dagster documentation](https://docs.dagster.io/)
- [dbt documentation](https://docs.getdbt.com/)
