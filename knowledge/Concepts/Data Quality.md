---
title: Data Quality
type: concept
status: seedling
tags: [data-quality, testing, observability, freshness]
created: 2026-09-18
updated: 2026-09-18
aliases: [Data Testing, Data Reliability]
---

# Data Quality
Data quality is the degree to which data is fit for its intended use, usually expressed as measurable expectations for completeness, validity, uniqueness, consistency, timeliness, and accuracy.

## Why it matters
- Tests turn "the dashboard looks wrong" into a specific failure caught early.
- Freshness and volume expectations catch silent ingestion failures that schema tests miss.
- Persisted test history shows whether data is drifting, not just whether it passed today.
- Quality is a property of the data itself, not of the code that produced it.

## How it works
Checks are declared as assertions next to each model and run on every build.

```yaml
models:
  - name: macro_observations
    tests:
      - unique: [series_id, obs_date, known_at]
    columns:
      - name: series_id
        tests: [not_null]
```

It helps to separate categories: schema tests (unique, not_null, relationships), freshness, volume, and distribution anomalies. Schema tests catch structural breakage; the others catch data that is structurally valid but behaving unusually.

## In this platform
dbt tests cover the key columns and the fact grain `(series_id, obs_date, known_at)`, while Elementary persists results and adds anomaly detection on volume, freshness, and column distributions. That coverage is real but not yet scheduled: Elementary runs as a long-lived service rather than being driven by the daily Dagster schedule, and the schedule itself has never fired. The weak spots are concrete: some staging models read the entire raw fetch history, and `payload_sha256` exists but is never used to skip byte-identical fetches, so quality signals are noisier than they need to be. The series catalogue maintained in two places can also drift out of sync.

## Related
- [[Data Contracts]]
- [[Change Data Capture]]
- [[Semantic Layer]]
- [[Data Mesh]]

## Further reading
- [dbt tests](https://docs.getdbt.com/docs/build/tests)
- [Elementary dbt package quickstart](https://docs.elementary-data.com/data-tests/dbt/quickstart-package)
- [DAMA-DMBOK body of knowledge](https://www.dama.org/cpages/body-of-knowledge)
