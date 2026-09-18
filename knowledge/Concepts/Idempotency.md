---
title: Idempotency
type: concept
status: seedling
tags: [api-design, idempotency, reliability]
created: 2026-09-18
updated: 2026-09-18
aliases: [Idempotent Operations, Idempotency Keys]
---

# Idempotency

An operation is idempotent when performing it more than once leaves the system in the same state as performing it once.

## Why it matters
- Networks fail mid-request, so clients retry. Idempotent endpoints make retrying safe instead of duplicating work.
- Pipelines get re-run for late data, backfills, and bug fixes, and the rerun must not corrupt the warehouse.
- It decides which HTTP methods may be retried automatically by a proxy or gateway.
- It is the precondition for at-least-once delivery being tolerable at all.

## How it works
In HTTP, `GET`, `PUT`, `DELETE`, `HEAD`, and `OPTIONS` are idempotent by definition; `POST` is not, because repeating it may create a second resource. `GET` is also safe, meaning no side effects. For non-idempotent operations, the usual pattern is a client-supplied idempotency key: the server records the key with the result of the first execution, and a retry with the same key returns the stored result instead of executing again. Content addressing works the same way, because identical input produces an identical hash.

## In this platform
This is already how the raw landing zone behaves: fetched FRED, ECB, and Bundesbank payloads are written as immutable append-only JSON indexed by sha256, so re-fetching a payload that has not changed deduplicates rather than duplicating. That makes Dagster retries on the daily schedule safe. The serving side is naturally idempotent too, since the FastAPI endpoints in `api/main.py` are reads over the bitemporal marts and carry no side effects.

## Related
- [[REST]]
- [[Data Contracts]]
- [[Data Quality]]
- [[Bitemporal Data]]

## Further reading
- [RFC 9110: Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2)
- [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests)
