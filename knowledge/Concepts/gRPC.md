---
title: gRPC
type: concept
status: seedling
tags: [api-design, grpc, rpc, http2]
created: 2026-09-18
updated: 2026-09-18
aliases: [gRPC, Google Remote Procedure Call]
---

# gRPC

gRPC is a remote procedure call framework that sends protobuf-encoded messages over HTTP/2.

## Why it matters
- The `.proto` file is a strict contract, and generated stubs keep client and server in step across languages.
- Protobuf is compact and fast to parse compared with JSON, which matters on high-volume internal calls.
- HTTP/2 multiplexes many concurrent streams over one TCP connection, so it avoids HTTP/1.1 head-of-line blocking at the connection level.
- It supports streaming natively: unary, server-streaming, client-streaming, and bidirectional.

## How it works
The service is declared in a schema, and code generation produces typed clients:

```proto
service SeriesService {
  rpc GetSeries (SeriesRequest) returns (SeriesReply);
  rpc StreamObservations (SeriesRequest) returns (stream Observation);
}
```

Each call becomes an HTTP/2 stream: binary length-prefixed frames in the body, method and status carried in trailers rather than an HTTP status line. On failure the client gets a gRPC status code such as `UNAVAILABLE` or `DEADLINE_EXCEEDED`, and deadlines propagate to upstreams.

## In this platform
Not used. All internal traffic in the Compose stack is HTTP with JSON: Streamlit and the D3 dashboard call FastAPI, Metabase and CloudBeaver talk to Postgres over their own native protocols, and Dagster orchestrates by launching runs rather than by RPC. gRPC would be a candidate only for chatty service-to-service calls inside the future K3s cluster, and nothing in the current design needs that yet.

## Related
- [[REST]]
- [[OpenAPI]]
- [[Kubernetes]]
- [[Event-Driven Architecture]]

## Further reading
- [gRPC: Introduction](https://grpc.io/docs/what-is-grpc/introduction/)
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113)
