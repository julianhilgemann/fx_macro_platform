---
title: OpenAPI
type: concept
status: seedling
tags: [api-design, openapi, documentation, contracts]
created: 2026-09-18
updated: 2026-09-18
aliases: [OpenAPI Specification, Swagger]
---

# OpenAPI

OpenAPI is a machine-readable specification that describes an HTTP API: its paths, operations, parameters, schemas, and responses.

## Why it matters
- One document drives interactive docs, client SDK generation, and request validation, so they cannot drift apart.
- It makes the API contract reviewable in a pull request instead of only in prose.
- Tooling can diff two versions and flag breaking changes before release.
- It turns an API into something a consumer can explore and script against without reading the source.

## How it works
A document declares metadata, then paths and components:

```yaml
paths:
  /v1/series/{series_id}:
    get:
      parameters:
        - name: series_id
          in: path
          required: true
          schema: { type: string }
        - name: known_at
          in: query
          schema: { type: string, format: date-time }
      responses:
        "200":
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Observation" }
```

FastAPI derives this from type hints and Pydantic models and serves it at `/openapi.json`, with Swagger UI and ReDoc alongside.

## In this platform
FastAPI generates the OpenAPI document for the serving layer automatically, so the public surface of the marts is already described mechanically. Note that `docs/api-calls.md` is the upstream provider reference for FRED, ECB and Bundesbank, not documentation of this platform's own API; the human-readable contract for this API is the spec section that defines the endpoints. Once an API gateway sits in front of the public API, the same document becomes the input for gateway route configuration and for consumer SDKs.

## Related
- [[REST]]
- [[API Versioning]]
- [[Data Contracts]]
- [[Idempotency]]

## Further reading
- [OpenAPI Specification 3.1](https://spec.openapis.org/oas/v3.1.0)
- [FastAPI: OpenAPI](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/)
