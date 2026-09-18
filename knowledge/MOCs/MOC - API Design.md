---
title: MOC - API Design
type: moc
status: growing
tags: [moc, api]
created: 2026-09-18
updated: 2026-09-18
aliases: [API MOC, Serving MOC]
---

# MOC - API Design

The serving surface. An API is a promise to callers you cannot see, and most of
these notes are about keeping that promise when the implementation underneath
changes.

## Notes

- [[REST]], resources, verbs, status codes. The default style here.
- [[GraphQL]], a typed query language and a single endpoint. Not used, and worth
 knowing why.
- [[gRPC]], HTTP/2 and protobuf for service-to-service calls.
- [[OpenAPI]], the machine-readable contract that makes an API reviewable and
 testable.
- [[Idempotency]], why retrying a write must be safe, and how to guarantee it.
- [[API Versioning]], changing a public interface without breaking callers.

## The platform's stance

The platform serves read-mostly macro data over REST, defined in `api/main.py` and
described by FastAPI's generated OpenAPI schema. Reads dominate, caching matters, and correctness under retry
matters more than throughput. That points at [[REST]] plus [[OpenAPI]] plus
[[Idempotency]] for the write paths, and away from [[GraphQL]] and [[gRPC]] for
the public surface.

C1 in [[Platform Delivery Plan]] is where this becomes real: query bounds,
caching headers, a connection pool, and a gateway with rate limiting.

## Reading order

[[REST]] and [[OpenAPI]] are the working pair. Read [[Idempotency]] before
building any write endpoint, and [[API Versioning]] before publishing anything
you cannot change freely.

## Related

- [[MOC - Networking]]
- [[MOC - Data Engineering]]
- [[Platform Delivery Plan]]
- [[REST]]
