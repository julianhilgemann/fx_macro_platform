---
title: API Versioning
type: concept
status: seedling
tags: [api-design, versioning, compatibility]
created: 2026-09-18
updated: 2026-09-18
aliases: [API Versioning Strategies, Breaking Change Management]
---

# API Versioning

API versioning is the practice of letting an API change over time while existing consumers keep working.

## Why it matters
- Dashboards, notebooks, and external scripts break silently when a response shape changes under them.
- A version is a promise: within it, fields are only added, never removed or retyped.
- It gives a defined retirement path, so old versions can be measured, announced, and switched off.
- Additive changes usually need no new version, which keeps the surface small.

## How it works
The common placements are the URI path (`/v1/series`), a query parameter (`?version=1`), a media type (`Accept: application/vnd.fx.v2+json`), or a custom header. Path versioning is the most visible and the easiest to route at a gateway. The rule that keeps it cheap is to distinguish additive from breaking: adding an optional field or a new endpoint is additive, while renaming a field, tightening validation, changing a default, or removing a parameter is breaking. Breaking changes go in a new version, and the old one gets a sunset date.

## In this platform
No versioning scheme is documented yet: the serving layer's endpoints live in `api/main.py` and `platform-spec.md` is the master design (`docs/api-calls.md` is the upstream provider reference, not public API documentation), and neither pins a versioning convention in the context available here. Path versioning under `/v1/` is the natural fit for the FastAPI serving layer, because the planned API gateway can route and rate limit by prefix, and because the bitemporal marts make additive evolution realistic once `known_at` and `obs_date` are first-class filters.

## Related
- [[REST]]
- [[OpenAPI]]
- [[Data Contracts]]
- [[Idempotency]]

## Further reading
- [RFC 8594: The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
- [Google Cloud API Design Guide: Versioning](https://cloud.google.com/apis/design/versioning)
