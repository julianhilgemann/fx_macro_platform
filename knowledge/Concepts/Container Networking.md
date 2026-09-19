---
title: Container Networking
type: concept
status: seedling
tags: [docker, containers, networking, infrastructure]
created: 2026-09-19
updated: 2026-09-19
aliases: [Docker Networking, Compose Networking, Service Discovery]
---

# Container Networking

How containers get addresses and names, how they reach each other, and how a
port inside a container becomes reachable outside it.

## Why it matters
- It explains the two questions that come up constantly in a Compose stack: why
  services address each other by name (`postgres`) while you reach them on
  `localhost:5433`, and why `localhost` *inside* a container means the container
  rather than the machine.
- Publication is where a private container becomes a public host port. Choosing
  the bind address there is a security decision made once per service, usually
  by default rather than deliberately — see [[Port Binding and Publication]].
- On macOS there is an extra layer that surprises people: containers are not on
  the host's network stack at all.

## How it works

**A Compose project gets its own network.** Unless `networks:` is declared,
Compose creates a bridge network named `<project>_default` and attaches every
service to it. Containers on that network receive an internal IP from a private
range and can reach each other on any port, with no publication involved.

**Service names are DNS names.** Docker runs an embedded DNS resolver, and each
container is registered under its service name. That is why `POSTGRES_HOST:
postgres` resolves, and why `localhost` in that position would resolve to the
container itself and fail.

**Publication is explicit and directional.** `ports: ["HOST:CONTAINER"]` maps a
port on the host to a port in the container, so the order is
host-first. The common errors are reversing those two numbers, and expecting the
container to sit on the host port internally.

**Exposure is not publication.** A port listed in a Dockerfile `EXPOSE` — or
declared by an image — is metadata announcing intent. It appears in `docker ps`
output but is reachable only from inside the container network, not from the
host. `docker ps` therefore shows both, and they must be read differently.

**On macOS the host is a VM.** Docker Desktop runs a Linux virtual machine, and
containers live there. Published ports are not opened by the container directly;
they are forwarded by a Docker Desktop helper process on macOS, which is why
`lsof` attributes those listeners to `com.docker.backend` rather than to the
service. Host networking is consequently not equivalent to Linux, and a container
cannot simply bind to the Mac's tailnet interface.

## In this platform
Compose auto-creates `fx_macro_platform_default` (bridge driver); the compose
file declares no network of its own. Inter-service addressing relies on the
embedded DNS:

```yaml
POSTGRES_HOST: postgres
DAGSTER_URL: http://dagster-webserver:3000
```

Three mappings are worth reading closely, because host and container ports differ:

| Host | Container | Why |
|---|---|---|
| 5433 | 5432 | 5432 is held by a native Postgres on the Mac |
| 3001 | 3000 | Metabase listens on 3000 inside |
| 8080 | 80 | the launchpad is nginx, serving on 80 |

Two services also expose ports that are deliberately *not* published — `api` on
3000 and `dagster-webserver` on 8000 — so they are reachable to their peers on the
network but not from the host. This is the expose/publish distinction in the same
stack, and it is why `docker ps` shows bare `3000/tcp` next to `0.0.0.0:8000->8000/tcp`.

One consequence worth stating, because it caused a real bug: the launchpad is
inside the network and *could* address its peers by service name, but it is a
static page rendered by a browser that sits outside the network. Its links must
therefore use host-reachable addresses, which is why they are host ports rather
than service names. See [[Remote Access]].

## Related
- [[Port Binding and Publication]]
- [[Stack Inventory]]
- [[Kubernetes]]
- [[Remote Access]]
- [[MOC - Platform Engineering]]
