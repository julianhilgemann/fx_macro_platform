---
title: Hexagonal Architecture
type: concept
status: seedling
tags: [architecture, ports-and-adapters, testing]
created: 2026-09-18
updated: 2026-09-18
aliases: [Ports and Adapters]
---

# Hexagonal Architecture

Hexagonal architecture keeps domain logic at the centre and connects it to the outside world only through explicit ports served by replaceable adapters.

## Why it matters

- Domain rules can be tested without a database, a network, or an orchestrator in the loop.
- External dependencies become swappable, which helps when a data source changes its API or moves from a vendor to a mock.
- It delays technology choices: the core does not name Postgres, HTTP, or a specific vendor.
- It makes the dependency direction explicit, so infrastructure depends on the domain and never the reverse.

## How it works

Ports are interfaces owned by the core, for example `ObservationSource` or `ObservationStore`. Driving adapters call into the core, driven adapters are called by it. Anything that crosses the boundary is translated at the adapter.

```yaml
core:            [bitemporal rules, revision handling, validation]
ports:           [ObservationSource, ObservationStore, ReportWriter]
driving_adapters: [fastapi_routes, dagster_job, cli]
driven_adapters:  [fred_client, ecb_client, bundesbank_client, postgres]
```

## In this platform

The pattern is not declared as such in the repo, but the pipeline is close to it in spirit. The FastAPI serving layer and the Dagster daily job act as driving adapters, the FRED, ECB, and Bundesbank fetch clients as driven adapters, and the dbt staging and mart models carry most of the domain transformation. An explicit ports layer would matter most for the fetch clients, since those are the parts most likely to change when the platform moves to Hetzner and K3s.

## Related

- [[Domain-Driven Design]]
- [[Data Contracts]]
- [[CQRS]]

## Further reading

- [Hexagonal architecture, Alistair Cockburn](https://alistair.cockburn.us/hexagonal-architecture/)
- [Ports and adapters, Martin Fowler](https://martinfowler.com/bliki/PortsAndAdapters.html)
- [Onion architecture](https://jeffreypalermo.com/2008/07/the-onion-architecture-part-1/)
