---
title: REST
type: concept
status: seedling
tags: [api-design, rest, http]
created: 2026-09-18
updated: 2026-09-18
aliases: [Representational State Transfer, RESTful API]
---

# REST

REST is an HTTP API style built on resources, standard methods, and stateless requests.

## Why it matters
- It reuses HTTP instead of inventing a protocol, so caches, proxies, browsers, and client libraries work without special support.
- Statelessness means any request can go to any replica, which is what makes horizontal scaling simple.
- Status codes give callers machine-readable outcomes: 200, 201, 404, 422, 429, 500.
- It keeps the public surface predictable, which matters for a documented data API that others script against.

## How it works
A resource gets a URL, and the method states the intent. `GET /v1/series/USCPI` reads and must have no side effects. `POST /v1/series` creates and is not idempotent. `PUT /v1/series/USCPI` replaces idempotently. `DELETE` removes. Responses carry `Content-Type: application/json`, and collections support `?limit=` and `?offset=` for paging. FastAPI expresses this directly:

```python
@app.get("/v1/series/{series_id}")
def get_series(series_id: str, obs_date: date | None = None):
    ...
```

## In this platform
REST is the shape of the FastAPI serving layer that sits after the dbt marts, and the public endpoints that Streamlit, the D3.js Germany dashboard, and external callers consume. Because those endpoints read bitemporal warehouse data, the natural REST pattern is a filter on `series_id` plus `obs_date` and `known_at` query parameters rather than a single opaque resource id.

## Related
- [[OpenAPI]]
- [[Idempotency]]
- [[API Versioning]]
- [[GraphQL]]

## Further reading
- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [MDN: HTTP request methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods)
