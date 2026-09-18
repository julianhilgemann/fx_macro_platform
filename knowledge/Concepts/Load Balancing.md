---
title: Load Balancing
type: concept
status: seedling
tags: [networking, scalability, reliability]
created: 2026-09-18
updated: 2026-09-18
aliases: [Load Balancer, Traffic Distribution]
---

# Load Balancing

Load balancing spreads incoming requests across several identical backends so no single instance carries all the traffic.

## Why it matters
- Capacity becomes horizontal: adding replicas adds throughput instead of replacing a bigger machine.
- One failing backend is dropped from rotation, so a crash degrades capacity rather than the service.
- Rolling deploys become possible, since instances can be drained and replaced one at a time.
- It removes the single point of failure that one API process or one dashboard container creates.

## How it works
A layer 4 balancer forwards TCP or UDP connections and never inspects the payload, which is fast but blind to HTTP. A layer 7 balancer parses HTTP, so it can route by path or host, retry idempotent requests, and terminate TLS. Common algorithms are round robin, least connections, and consistent hashing for cache affinity. Health checks decide the rotation: an endpoint that fails repeated probes is removed until it passes again. Sticky sessions are often needed when state lives in the process rather than in a shared store.

## In this platform
Not used yet, because each Compose service runs as a single container on the dev machine. It becomes relevant with the K3s move: a Kubernetes Service already balances across pod replicas, and the planned API gateway with rate limiting will sit in front of the public FastAPI API, which is where balancing policy and health checks would be configured.

## Related
- [[Reverse Proxy]]
- [[Kubernetes]]
- [[K3s]]
- [[SRE Basics]]

## Further reading
- [Kubernetes: Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [nginx: HTTP Load Balancing](https://docs.nginx.com/nginx/admin-guide/load-balancer/http-load-balancer/)
