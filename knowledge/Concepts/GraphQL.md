---
title: GraphQL
type: concept
status: seedling
tags: [api-design, graphql, query-language]
created: 2026-09-18
updated: 2026-09-18
aliases: [GraphQL API]
---

# GraphQL

GraphQL is a query language and runtime where clients ask for exactly the fields they need from a typed schema served over one endpoint.

## Why it matters
- Clients fetch one shaped response instead of chaining REST calls or over-fetching whole records.
- The schema is the contract: types, nullability, and fields are introspectable, so clients can be generated.
- One endpoint means fewer round trips, which helps dashboards that assemble a page from several entities.
- The tradeoff is real: caching, rate limiting, and query cost control all get harder, because every request is a `POST` to the same URL.

## How it works
The server publishes a schema, and clients send a document naming the fields they want:

```graphql
query {
  series(id: "USCPI") {
    title
    observations(from: "2024-01-01") { obsDate value }
  }
}
```

Resolvers fetch each field, and the runtime assembles the response in the requested shape. The classic failure mode is the N+1 query: a list field resolving one database call per row. The usual fix is batching with DataLoader against the warehouse.

## In this platform
Not used, and there is no plan for it. The serving layer is FastAPI with REST endpoints defined in `api/main.py` and described by FastAPI's generated OpenAPI schema, which fits the read pattern here: a small number of known queries over bitemporal macro series. GraphQL would only earn its place if external consumers needed many different field combinations against the marts, and that is not in the current design.

## Related
- [[REST]]
- [[OpenAPI]]
- [[Semantic Layer]]
- [[API Versioning]]

## Further reading
- [GraphQL: Introduction](https://graphql.org/learn/)
- [GraphQL: Thinking in Graphs](https://graphql.org/learn/thinking-in-graphs/)
