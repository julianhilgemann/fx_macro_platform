---
title: MOC - Networking
type: moc
status: growing
tags: [moc, networking]
created: 2026-09-18
updated: 2026-09-18
aliases: [Networking MOC]
---

# MOC - Networking

How traffic reaches a service, and how it is trusted on the way. This is the
layer that has to exist before anything can be exposed publicly, and it is
currently the least built part of [[FX Macro Platform]].

## Notes

- [[DNS]], names to addresses. What has to exist before TLS can be issued.
- [[TLS]], encrypting and authenticating the transport. Certificates, handshake,
 termination.
- [[Reverse Proxy]], one entry point routing to many backends. Where TLS usually
 terminates.
- [[Load Balancing]], spreading traffic across replicas. Becomes relevant only
 once something runs more than one copy.

## Why this map matters now

Today the stack publishes eleven ports directly to the host on `0.0.0.0`, with no
proxy, no TLS and no authentication. That is fine on a laptop and unacceptable
anywhere else. The planned shape is a single Ingress into the cluster with TLS
termination, a rate limiter, and everything else unreachable from outside. See C2
and E2 in [[Platform Delivery Plan]].

## Reading order

Read [[DNS]] and [[TLS]] first, because almost every other networking decision
assumes them. Then [[Reverse Proxy]], which is where the two combine. Leave
[[Load Balancing]] until you actually run replicas.

## Related

- [[MOC - Platform Engineering]]
- [[MOC - Security and Identity]]
- [[Kubernetes]]
- [[Stack Inventory]]
