---
title: MOC - Security and Identity
type: moc
status: growing
tags: [moc, security, identity]
created: 2026-09-18
updated: 2026-09-18
aliases: [Security MOC, Identity MOC]
---

# MOC - Security and Identity

Who may do what, and how that is proven. This map covers the gap between the
platform as it runs today, entirely open, and the platform as it needs to be
before anyone else can touch it.

## Authentication

Proving who someone is.

- [[OAuth 2.0]], an authorization framework, not a login protocol. Access
 tokens and scopes.
- [[OpenID Connect]], an authentication layer on top of OAuth 2.0. The ID token,
 UserInfo and discovery.
- [[JWT]], the token format. Signed, not encrypted, and hard to revoke.
- [[Identity Providers]], Keycloak, Authentik, Zitadel. The thing you actually
 deploy.

## Authorization and transport trust

- [[RBAC]], roles to permissions. The model the platform needs for human access.
- [[mTLS]], both sides present certificates. For service-to-service trust.
- [[OWASP Top 10]], the recurring vulnerability classes, and a review checklist
 before exposing anything.

## Where the platform stands

There is no authentication anywhere. Every admin surface binds to `0.0.0.0`, so
Dagster, Metabase, CloudBeaver and the dbt reports are open to the local network.
The roadmap ranks this as its most urgent item, and C2 in
[[Platform Delivery Plan]] is deliberately placed first for that reason.

The staged intent is: Tailscale to close the admin plane immediately, then an
identity provider for real users, then RBAC, then mTLS between internal services
if warranted.

## Reading order

[[OWASP Top 10]] first, because it frames why the rest matters. Then
[[OAuth 2.0]] and [[OpenID Connect]] together, since the distinction between them
is the most commonly misunderstood thing in this area.

## Related

- [[MOC - Networking]]
- [[MOC - Platform Engineering]]
- [[Current State]]
- [[Platform Delivery Plan]]
