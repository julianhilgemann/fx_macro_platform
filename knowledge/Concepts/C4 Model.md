---
title: C4 Model
type: concept
status: seedling
tags: [architecture, documentation, diagrams]
created: 2026-09-18
updated: 2026-09-18
aliases: [C4, C4 diagrams]
---

# C4 Model

The C4 model describes a software system at four zoom levels: context, containers, components, and code.

## Why it matters

- It gives a shared zoom ladder, so a reader can stop at the level they need instead of drowning in one giant diagram.
- It separates what the system is from how it is deployed, which keeps diagrams stable while infrastructure changes.
- It is notation-light: boxes, arrows, and a key, so it works with Structurizr, C4-PlantUML, or a whiteboard.
- It makes gaps visible, such as an unnamed queue or an undocumented external dependency.

## How it works

Level 1 places the system in its environment. Level 2 zooms into deployable containers. Level 3 opens one container into components. Level 4 shows classes and is usually generated, not drawn.

```yaml
context:    [analysts, platform, external data sources]
containers: [ingest, warehouse, dbt, api, dashboards, orchestration]
components: [serving routers, dbt marts, fetch clients]
code:       generated from source, rarely hand-written
```

Each level is a separate diagram with its own audience, and every element carries a one-line description.

## In this platform

The master design document `platform-spec.md` plays the role of the context and container views for FX Macro Platform, but it is prose rather than a C4 diagram. A container view would map well onto the roughly 12 Docker Compose services: ingest, Postgres, dbt, FastAPI, Streamlit, the D3 Germany dashboard, Metabase, Dagster, Elementary, and CloudBeaver. A second version would be needed after the planned Hetzner and K3s move. No C4 diagrams exist in the repo today.

## Related

- [[Architecture Decision Records]]
- [[Domain-Driven Design]]
- [[Hexagonal Architecture]]

## Further reading

- [C4 model](https://c4model.com/)
- [Structurizr](https://structurizr.com/)
- [The C4 model for visualising software architecture](https://www.infoq.com/articles/C4-architecture-model/)
