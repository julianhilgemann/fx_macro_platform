---
title: Port Binding and Publication
type: concept
status: seedling
tags: [networking, security, ports, infrastructure]
created: 2026-09-19
updated: 2026-09-19
aliases: [Port Binding, Port Publishing, Bind Address, Listening Sockets]
---

# Port Binding and Publication

A listening socket is bound to an address *and* a port. The port decides which
service is reached; the **address decides who is able to reach it at all.**

## Why it matters
- It is the single most consequential line in most service configurations, and
  the one most often left at its default. Binding `0.0.0.0` reaches every network
  the machine is attached to — including untrusted ones.
- "It works on my machine" and "it is exposed to the coffee-shop wifi" are the
  same configuration viewed from two places. Reachability is a property of the
  bind address, not of the service.
- Because the default in many tools and container images is the wildcard, a dev
  stack accumulates exposure without anyone choosing it. That is exactly how the
  admin plane here became open.

## How it works

The bind address determines the set of interfaces a socket accepts connections
on:

| Bind address | Reachable from | Typical intent |
|---|---|---|
| `127.0.0.1`, `::1` | the same host only | local tooling, not yet exposed |
| a specific address | traffic arriving on that interface | one network, e.g. the tailnet |
| `0.0.0.0`, `::` | every interface | "just make it work" — usually unintentional |

Two further rules matter in practice:

- **A port can have only one listener per address.** Binding where something
  already listens fails with `EADDRINUSE`, which is why a native Postgres holds
  5432 and the containerised warehouse has to use another port.
- **Binding is distinct from being published.** A container can *expose* a port
  as image metadata without that port becoming reachable from the host. See
  [[Container Networking]].

To audit what is actually listening, and on which address:

```bash
lsof -nP -iTCP -sTCP:LISTEN
```

The bind address in that output is the whole answer to "who can reach this".

## In this platform
Two opposite choices coexist, and the contrast is the clearest illustration of
the concept here:

- The DSH harness binds **`127.0.0.1:3080`** — deliberately reachable only from
  the machine itself. It is therefore invisible to the LAN *and* to the tailnet,
  which is why reaching it from a phone required fronting it with
  `tailscale serve` rather than simply allowing access.
- Every Compose service publishes on **`0.0.0.0`** (see [[Stack Inventory]]), so
  Dagster, Metabase, CloudBeaver, the dbt reports and Postgres on 5433 are
  reachable on any network the laptop joins, with no authentication in front of
  them. [[Tailscale]] does not cover these, because the wildcard bind already
  answers on the tailnet interface too.

A native Postgres on `127.0.0.1:5432` and the containerised warehouse on
`0.0.0.0:5433` sit side by side: the same port number on two different bind
addresses, one private and one not.

## Related
- [[Container Networking]]
- [[NAT and NAT Traversal]]
- [[Tailscale]]
- [[OWASP Top 10]]
- [[Stack Inventory]]
- [[Remote Access]]
