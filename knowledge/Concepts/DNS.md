---
title: DNS
type: concept
status: seedling
tags: [networking, dns, service-discovery]
created: 2026-09-18
updated: 2026-09-18
aliases: [Domain Name System, DNS Resolution]
---

# DNS

DNS is the naming system that turns human-readable hostnames into IP addresses and other records.

## Why it matters
- Every service call, container start, and TLS certificate depends on name resolution succeeding first.
- Stale records or a wrong resolver look exactly like an application failure, so DNS is the first suspect to clear.
- Names decouple configuration from addressing: a host can move without clients changing.
- Inside containers and clusters, DNS is the service discovery mechanism, not just public naming.

## How it works
A resolver walks the hierarchy: root, then the top-level domain, then the authoritative nameserver, caching each answer for its TTL. Record types carry different jobs: `A` and `AAAA` hold IPv4 and IPv6 addresses, `CNAME` aliases one name to another, `MX` routes mail, `TXT` holds verification strings.

Docker Compose puts every service on a shared network and runs an embedded DNS server at 127.0.0.11, so one container reaches Postgres by the hostname `postgres` with no configuration.

## In this platform
The roughly 12 Docker Compose services already depend on this: containers address each other by service name, while the host reaches the warehouse through published ports, 5433 for the platform Postgres and 5432 for the separate local one. When the platform moves to Hetzner with K3s, service naming shifts to cluster DNS and ingress hostnames, and public names for the API will have to point at that ingress.

## Related
- [[Reverse Proxy]]
- [[Load Balancing]]
- [[Kubernetes]]
- [[TLS]]

## Further reading
- [RFC 1034: Domain Names, Concepts and Facilities](https://www.rfc-editor.org/rfc/rfc1034)
- [Cloudflare Learning Center: What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/)
