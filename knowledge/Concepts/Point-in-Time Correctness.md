---
title: Point-in-Time Correctness
type: concept
status: seedling
tags: [point-in-time, as-of-queries, backtesting, no-lookahead]
created: 2026-09-18
updated: 2026-09-18
aliases: [As-Of Correctness, No Look-Ahead, PIT Correctness]
---

# Point-in-Time Correctness
Point-in-time correctness is the guarantee that a query answered as of a past moment returns only the data that was actually knowable at that moment.

## Why it matters
- Without it, backtests and model evaluations silently learn from the future.
- It is what makes an `as_of` parameter meaningful, reproducible, and safe to publish.
- It lets a number reported last month still be reproduced today, after revisions.
- It is the property consumers need; bitemporal modelling is one way to provide it.

## How it works
Filter to rows known by the as-of date, then take the latest such vintage per observation.

```sql
select distinct on (series_id, obs_date)
  series_id, obs_date, value
from marts.macro_observations
where known_at <= :as_of
order by series_id, obs_date, known_at desc;
```

Keep the two ideas apart. Bitemporal data is the modelling technique: two independent time axes, valid time and transaction time. Point-in-time correctness is the guarantee that technique buys you. You can store perfectly bitemporal rows and still answer incorrectly if the query ignores `known_at`.

## In this platform
The platform needs this guarantee because it exists to support revision-aware FX and macro analysis, and the design exposes an `as_of` parameter through the API. It uses the bitemporal grain to get there. The gap is upstream: with FRED revisions uncollected, every observation in a fetch shares a single vintage date, so an as-of query cannot yet distinguish what was known before a revision from what was known after it.

## Related
- [[Bitemporal Data]]
- [[Semantic Layer]]
- [[Change Data Capture]]
- [[Data Quality]]

## Further reading
- [Point-in-time feature joins (Databricks)](https://docs.databricks.com/aws/en/machine-learning/feature-store/time-series)
- [Look-ahead bias (Wikipedia)](https://en.wikipedia.org/wiki/Look-ahead_bias)
- [Point-in-time correctness (Wikipedia)](https://en.wikipedia.org/wiki/Point-in-time_correctness)
