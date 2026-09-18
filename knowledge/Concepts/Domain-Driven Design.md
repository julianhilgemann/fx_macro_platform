---
title: Domain-Driven Design
type: concept
status: seedling
tags: [architecture, domain-modeling, design]
created: 2026-09-18
updated: 2026-09-18
aliases: [DDD]
---

# Domain-Driven Design

Domain-driven design models software around the business domain, using one shared language per boundary and explicit contracts between boundaries.

## Why it matters

- A ubiquitous language removes translation bugs, because "observation date" means the same thing in conversation, SQL, and the API.
- Bounded contexts stop one model from serving every purpose, which is the usual cause of models that are both overloaded and wrong.
- It pushes domain rules into the core instead of scattering them across fetch scripts, SQL, and dashboards.
- Context boundaries are also ownership boundaries, so they suggest where a service, schema, or team should split.

## How it works

The domain is divided into bounded contexts. Each has its own model and vocabulary, and relationships between contexts are named and made explicit, for example shared kernel, customer/supplier, or anticorruption layer.

```yaml
contexts:
  ingestion:    {terms: [source, fetch_run, raw_payload]}
  warehouse:    {terms: [obs_date, known_at, fetched_at]}
  analytics:    {terms: [mart, metric, revision]}
relations:
  ingestion -> warehouse: customer/supplier
  warehouse -> analytics: shared kernel on the bitemporal grain
```

## In this platform

DDD is not formally adopted, but the pipeline stages already behave like boundaries: immutable raw JSON landing, the bitemporal Postgres warehouse, and the dbt marts each carry their own vocabulary and rules. The strongest example is the warehouse grain of `obs_date`, `known_at`, and `fetched_at`, which is the shared language that makes [[Point-in-Time Correctness]] possible. Naming those contexts in `platform-spec.md` would be a documentation change, not a refactor.

## Related

- [[Hexagonal Architecture]]
- [[Data Contracts]]
- [[Bitemporal Data]]

## Further reading

- [Domain-Driven Design, Eric Evans](https://www.domainlanguage.com/ddd/)
- [Bounded context, Martin Fowler](https://martinfowler.com/bliki/BoundedContext.html)
- [DDD reference and glossary](https://www.domainlanguage.com/ddd/reference/)
