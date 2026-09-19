---
title: NAT and NAT Traversal
type: concept
status: seedling
tags: [networking, connectivity, vpn, infrastructure]
created: 2026-09-19
updated: 2026-09-19
aliases: [NAT, NAT Traversal, Hole Punching, CGNAT]
---

# NAT and NAT Traversal

Network Address Translation rewrites addresses and ports as packets cross a
router. NAT traversal is the set of techniques for getting *inbound*
connectivity to a machine that sits behind it anyway.

## Why it matters
- It is the reason a laptop on home wifi has no reachable address, and therefore
  the reason "just connect to my machine" needs a mechanism rather than an
  address. Every remote-access approach is a response to this one constraint.
- The traditional answer — a port-forwarding rule on the router — carries three
  costs: it needs a public address, it needs administrative control of every
  network you might sit on, and it publishes the service to the entire internet
  so authentication becomes the only remaining defence.
- On mobile networks those costs are not merely inconvenient but often
  impossible, because carrier-grade NAT removes the ability to create inbound
  rules at all.

## How it works

**Why inbound fails by default.** Private address ranges (RFC 1918: `10/8`,
`172.16/12`, `192.168/16`) are not routable on the public internet. When an
internal host opens an *outbound* connection, the router records a stateful
mapping — internal address and port to public address and port — and return
traffic is permitted because it matches that mapping. An unsolicited inbound
packet matches nothing, so it is dropped. The block is not a firewall policy
that can be switched off; it is the absence of state.

**The traditional fix: static port forwarding.** A permanent NAT rule maps a
public `address:port` to an internal `address:port`, manufacturing the state that
inbound traffic needs. It works, and it is why the technique is still widespread,
but the service is now reachable by anyone who finds the port.

**Why mobile is worse: CGNAT.** Carriers place many subscribers behind a single
public address, so the address a phone appears to use is not one the subscriber
controls. Inbound rules generally cannot be created, which is why port forwarding
is not a viable plan for a phone on 5G no matter how the home network is
configured.

**Traversal instead of forwarding.** Rather than making either side addressable,
both peers open *outbound* connections to a coordination service, which tells
each one the public address and port the other appears to be coming from. Each
peer then sends to that address and port at the same time. Because the outbound
packets already created mappings on both routers, the arriving packets match
existing state and are admitted. This is hole punching.

It fails against some NAT implementations (notably symmetric NAT, which allocates
a different mapping per destination). The fallback is a relay: both peers keep an
outbound connection to a third party that forwards between them. Connectivity
degrades from direct to relayed, and stops being peer-to-peer, but it still works
and still needs no inbound rule on either side.

## In this platform
Neither end of the remote-access setup can be port-forwarded. The MacBook Air sits
behind a home router, and the iPhone on 5G is almost certainly behind CGNAT. No
router configuration was changed to make [[Remote Access]] work, and no inbound
rule exists on either side — which is the point of using [[Tailscale]] rather
than a forwarding rule plus dynamic DNS.

The practical consequence worth remembering: the tailnet is a private overlay on
top of whatever networks the devices already use, not a route to them. Tailscale
obtains a direct path where it can and falls back to a relay where it cannot, so
latency and throughput may differ between networks without anything being
misconfigured.

## Related
- [[Tailscale]]
- [[Port Binding and Publication]]
- [[Remote Access]]
- [[DNS]]
- [[MOC - Networking]]
