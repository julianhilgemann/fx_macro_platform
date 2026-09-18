---
title: Data Mesh
type: concept
status: seedling
tags: [data-mesh, ownership, governance, data-products]
created: 2026-09-18
updated: 2026-09-18
aliases: [Data Mesh Architecture, Decentralised Data Ownership]
---

# Data Mesh
Data mesh is an organisational and ownership pattern for analytical data, not a technology you can buy, in which domain teams own and publish their data as products on a shared self-serve platform under federated governance.

## Why it matters
- It targets the real bottleneck at scale, a central data team, rather than storage or compute.
- It shifts accountability to the people who understand the data best, the domain that produces it.
- It treats data as a product with consumers, expectations, and discoverability, not as a by-product.
- It is contentious: critics argue it fragments standards, duplicates effort, and can become silos with better branding.

## How it works
The pattern has four principles, all organisational rather than technical:

| Principle | What it means |
|---|---|
| Domain ownership | The team producing data owns its analytical outputs |
| Data as a product | Discoverable, addressable, trustworthy, self-describing |
| Self-serve platform | Shared tooling so domains do not rebuild pipelines |
| Federated computational governance | Global rules, enforced automatically |

Technology only supports these principles. Dehghani's later writing stresses that interoperability and governance are what make the pattern work at all.

## In this platform
FX Macro Platform is a single-person project, so the full pattern is not applicable: there are no domain teams to distribute ownership to, and inventing them would be ceremony. The portable ideas are "data as a product" and contracts. The platform already publishes marts to real consumers (the API, Streamlit dashboards, Metabase), and the series catalogue maintained in two places is the kind of integration problem federated governance exists to prevent.

## Related
- [[Data Contracts]]
- [[Domain-Driven Design]]
- [[Data Quality]]
- [[Semantic Layer]]

## Further reading
- [Data Mesh Principles and Logical Architecture (Martin Fowler)](https://martinfowler.com/articles/data-mesh-principles.html)
- [Data Mesh (Zhamak Dehghani, O'Reilly)](https://www.oreilly.com/library/view/data-mesh/9781492092384/)
