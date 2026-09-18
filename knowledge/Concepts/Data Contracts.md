---
title: Data Contracts
type: concept
status: seedling
tags: [data-contracts, data-quality, governance]
created: 2026-09-18
updated: 2026-09-18
aliases: [Data Contract, Schema Contract]
---

# Data Contracts
A data contract is an explicit, versioned agreement between a data producer and its consumers about the shape, meaning, and quality of the data crossing the boundary between them.

## Why it matters
- Breaking changes otherwise fail silently in whatever dashboard or model consumes them.
- It makes ownership explicit: one party owns schema, semantics, and freshness for one dataset.
- It gives tests something declared to assert against, instead of tribal knowledge.
- It moves data quality from a downstream complaint to an upstream, build-time check.

## How it works
A contract typically declares schema, types, nullability, allowed values, a freshness expectation, and an owner. It usually lives as YAML in the producer's repository and is validated in CI before publish.

```yaml
dataset: fx.macro_observations
owner: platform
grain: [series_id, obs_date, known_at]
columns:
  - name: series_id
    type: text
    nullable: false
sla:
  freshness: 36h
```

Consumers read only published outputs, and producers cannot change them without a version bump.

## In this platform
The nearest thing to a contract is the dbt schema YAML plus the fact grain `(series_id, obs_date, known_at)` that `platform-spec.md` calls non-negotiable. There is no machine-readable contract for the roughly 110 macro series, and the series catalogue is maintained in two places at once, which is exactly the drift a contract is meant to prevent. Adding one would also give the Elementary tests a declared target to check against.

## Related
- [[Data Mesh]]
- [[Data Quality]]
- [[Semantic Layer]]
- [[Bitemporal Data]]

## Further reading
- [Open Data Contract Standard](https://docs.datacontract.com/open-data-contract-standard)
- [Data Contract Specification](https://datacontract.com/)
- [Driving Data Quality with Data Contracts (Andrew Jones)](https://www.packtpub.com/en-us/product/driving-data-quality-with-data-contracts-9781837635003)
