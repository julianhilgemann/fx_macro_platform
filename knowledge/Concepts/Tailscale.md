---
title: Tailscale
type: concept
status: seedling
tags: [networking, security, vpn, infrastructure]
created: 2026-09-19
updated: 2026-09-19
aliases: [Tailnet, Mesh VPN, WireGuard VPN]
---

# Tailscale

A mesh VPN built on WireGuard. Each device gets a stable private address and can
reach every other device on the same network — the *tailnet* — regardless of what
network either one is actually attached to.

## Why it matters
- It removes the "expose a port on the router" step entirely. Nothing is
  published to the public internet, so there is no port-forward, no dynamic DNS,
  and no attack surface that exists before authentication.
- Identity is per-device key material, not an IP address or a shared password.
  A lost device is revoked in the admin console; the rest of the tailnet is
  unaffected.
- It works from anywhere. A phone on 5G reaches the laptop on home wifi with no
  configuration change on either end, because both are already on the tailnet.
- It gives you a private network *before* you have an identity provider, which is
  what makes it useful as a stopgap rather than a destination.

## How it works
Every device runs a client that holds a keypair and maintains direct encrypted
links to its peers, falling back to relayed connections when NAT traversal fails.
Because the links are established outbound, the network topology on either side
does not matter.

Two features carry most of the practical weight:

- **MagicDNS** gives each device a stable name (`<host>.<tailnet>.ts.net`) that
  resolves to its tailnet address, so bookmarks survive address changes.
- **`tailscale serve`** exposes a local service to the tailnet over HTTPS,
  terminating TLS at the Tailscale edge and proxying to a local port. The public
  counterpart, `tailscale funnel`, is a deliberate separate decision.

HTTPS on Serve requires **HTTPS Certificates** to be enabled for the tailnet in
the admin console under DNS. Without that, Serve cannot issue a certificate.

## In this platform
Installed 2026-09-19 on the MacBook Air and the iPhone, on tailnet
`tail225b1e.ts.net`. This is the first staged step recorded in
[[MOC - Security and Identity]]: *Tailscale to close the admin plane
immediately.*

What it currently covers:

- `tailscale serve --bg --https=443 3080` fronts the DSH harness, which binds
  `127.0.0.1` and so is otherwise unreachable from any other device. The phone
  opens it at `https://dopamine-air.tail225b1e.ts.net`.
- The tailnet is also how the Docker services are reached from off-network, at
  `http://<host>:<port>` — but **not** because of Serve. Those containers publish
  on `0.0.0.0`, so they are already listening on the tailnet interface.

What it does **not** cover yet: the admin plane is still open. Every service in
[[Stack Inventory]] binds `0.0.0.0`, which is reachable on any network the laptop
joins, Tailscale or not. Closing that means moving those ports to loopback (or
the tailnet address) and fronting them with Serve the way the harness already is.
Until then, Tailscale protects the harness and not the platform.

Setup detail and the traps worth remembering are in [[Remote Access]].

## Related
- [[Remote Access]]
- [[Reverse Proxy]]
- [[mTLS]]
- [[MOC - Security and Identity]]
- [[MOC - Networking]]
