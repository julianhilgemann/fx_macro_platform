---
title: CQRS
type: concept
status: seedling
tags: [architecture, data, read-models]
created: 2026-09-18
updated: 2026-09-18
aliases: [Command Query Responsibility Segregation]
---

# CQRS

CQRS separates the model that handles writes from the model that answers reads, so each side can be shaped for its own workload.

## Why it matters

- Writes and reads want different things: writes need validation and invariants, reads need wide, pre-joined, indexed data.
- Read models can be rebuilt or re-projected independently, which suits a warehouse where one source feeds several consumers.
- The write path stays small and auditable while the read path is free to be denormalised for speed.
- The costs are real: eventual consistency, duplicated modelling, and more moving parts, so it is not a default choice.

## How it works

Commands validate and mutate the write model. Queries read a projection, which may live in the same database or a separate one. Full CQRS uses distinct stores and usually events to project between them; a lighter form keeps one store and only separates the models.

```yaml
write_side:  {store: postgres, tables: [observation], rules: [append_only]}
read_side:   {store: postgres, tables: [mart_fx_daily], built_by: dbt}
projection:  dbt run --select marts   # scheduled, not on every write
```

## In this platform

CQRS is not adopted as a named pattern, but the shape is visible. Ingestion writes immutable, bitemporal rows into the Postgres warehouse, and dbt builds staging and mart models that FastAPI, Streamlit, the D3 Germany dashboard, and Metabase read. Because both sides share one Postgres instance and projections refresh on the Dagster daily schedule, this is a read-optimised projection rather than full CQRS. There is no separate read store and no event stream between the two sides.

## Related

- [[Event-Driven Architecture]]
- [[OLTP vs OLAP]]
- [[Semantic Layer]]

## Further reading

- [CQRS, Martin Fowler](https://martinfowler.com/bliki/CQRS.html)
- [CQRS pattern, Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs)
- [CQRS documents, Greg Young](https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf)
