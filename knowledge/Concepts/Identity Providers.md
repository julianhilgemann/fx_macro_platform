---
title: Identity Providers
type: concept
status: seedling
tags: [identity, authentication, infrastructure]
created: 2026-09-18
updated: 2026-09-18
aliases: [IdP, Identity Provider]
---

# Identity Providers

An identity provider (IdP) is a service that stores user accounts, authenticates users, and issues the tokens or assertions that other applications trust.

## Why it matters

- It centralizes accounts, so each application does not build and secure its own password store.
- It gives one login across Dagster, Metabase, Grafana and an API gateway, with MFA and sessions managed in one place.
- It owns token issuance and signing key rotation, which is exactly the part OIDC clients should never implement themselves.
- The choice is sticky. Migration cost is real, so decide on protocol support, operational weight and upgrade path, not on a feature checklist.

## How it works

The IdP owns users, credentials, MFA and sessions, and exposes standard OIDC endpoints. A client discovers them at `https://idp.example/.well-known/openid-configuration`, redirects the user to the authorization endpoint, and validates the returned ID token against the published JWKS. Self-hosted options differ mainly in weight: Keycloak is a mature, feature-heavy Java service with its own database; Authentik is Python and Django with a visual flow builder; Zitadel is Go, API-first and comparatively light. All three are open source and OIDC-capable, so the practical differences are operations, resource footprint and admin experience.

## In this platform

No identity provider exists today. The roadmap selects one of Keycloak, Authentik or Zitadel as part of the Hetzner and K3s migration, alongside RBAC and user management, and that work is planned rather than present. Until it lands, the admin plane is Tailscale-only, which answers the login question by removing network reachability instead, and Dagster remains unauthenticated behind that boundary.

## Related

- [[OpenID Connect]]
- [[OAuth 2.0]]
- [[RBAC]]
- [[JWT]]

## Further reading

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [Keycloak documentation](https://www.keycloak.org/documentation)
- [Zitadel documentation](https://zitadel.com/docs)
