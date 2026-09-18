---
title: Bitemporal Data
type: concept
status: seedling
tags: [bitemporal, temporal-data, data-modelling, vintages]
created: 2026-09-18
updated: 2026-09-18
aliases: [Bitemporality, Two Time Axes, Valid and Transaction Time]
---

# Bitemporal Data
Bitemporal data is a modelling technique that records two independent time axes per fact: the time the fact describes (valid time) and the time the system learned it (transaction time).

## Why it matters
- It keeps every vintage of a revised value, including values later corrected or superseded.
- It separates "what happened" from "when we knew it", which a simple update conflates.
- It makes restatements and audits answerable without rebuilding history from logs.
- It is the mechanism, not the guarantee: the guarantee it enables is point-in-time correctness.

## How it works
One immutable row per value per vintage; nothing is updated in place.

| series_id | obs_date | value | known_at | fetched_at |
|---|---|---|---|---|
| CPI | 2026-01-01 | 2.9 | 2026-02-10 | 2026-02-10 |
| CPI | 2026-01-01 | 3.1 | 2026-03-10 | 2026-03-10 |

Here `obs_date` is valid time, `known_at` is transaction time, and `fetched_at` is provenance only. The grain is the full key `(series_id, obs_date, known_at)`, so a restated value is a new row, not an overwrite.

## In this platform
The Postgres warehouse stores macro observations at exactly this grain, with `obs_date`, `known_at`, and `fetched_at` as separate columns. The model is sound, but the second axis is under-populated in practice. FRED revision history is not captured because ALFRED's `realtime_start` is never used, so every observation in a fetch shares one vintage date, and ECB and Bundesbank re-stamp the whole history on each fetch instead of inserting only on change. The technique is present; the vintage data feeding it is not yet trustworthy.

## Related
- [[Point-in-Time Correctness]]
- [[Change Data Capture]]
- [[Data Quality]]
- [[Data Contracts]]

## Further reading
- [Developing Time-Oriented Database Applications in SQL (Snodgrass)](https://sigmod.org/publications/anthology/vol6/systems/timeOriented/timeOriented.htm)
- [Temporal database (Wikipedia)](https://en.wikipedia.org/wiki/Temporal_database)
