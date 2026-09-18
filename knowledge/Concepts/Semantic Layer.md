---
title: Semantic Layer
type: concept
status: seedling
tags: [semantic-layer, metrics, bi, consistency]
created: 2026-09-18
updated: 2026-09-18
aliases: [Metrics Layer, Headless BI]
---

# Semantic Layer
A semantic layer is a defined set of metrics, dimensions, and joins that sits between physical tables and the tools people query, so a metric is defined once and computed the same way everywhere.

## Why it matters
- It stops the same metric being redefined in every dashboard, notebook, and API route.
- It gives BI tools and services a stable, governed interface over tables that keep changing.
- It centralises tricky definitions such as "latest vintage" or "value as of a date".
- It improves trust, because numbers reconcile across Streamlit, Metabase, and the API.

## How it works
Metrics are declared once and compiled to SQL per engine.

```yaml
metrics:
  - name: value_as_of
    expr: max(value) filter (where known_at <= :as_of)
    dimensions: [series_id, obs_date]
```

A good semantic layer also encodes access rules and time semantics. Note that a marts layer is not automatically a semantic layer: marts are physical tables, while the semantic layer is the queryable definition sitting on top of them.

## In this platform
The dbt marts plus the FastAPI serving layer are the closest thing the platform has to a semantic layer. The `as_of` parameter on the API is a point-in-time metric definition that should be written once and reused, rather than reimplemented inside each Streamlit page, the D3 Germany dashboard, and Metabase. There is no formal semantic layer today, and the series catalogue maintained in two places is a symptom of missing shared definitions.

## Related
- [[Point-in-Time Correctness]]
- [[Data Contracts]]
- [[Bitemporal Data]]
- [[OLTP vs OLAP]]

## Further reading
- [dbt Semantic Layer architecture](https://docs.getdbt.com/docs/use-dbt-semantic-layer/sl-architecture)
- [Semantic Layer configurations (dbt)](https://docs.getdbt.com/reference/semantic-layer-reference)
