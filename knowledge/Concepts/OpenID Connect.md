---
title: OpenID Connect
type: concept
status: seedling
tags: [authentication, identity, oidc]
created: 2026-09-18
updated: 2026-09-18
aliases: [OIDC]
---

# OpenID Connect

OpenID Connect (OIDC) is an authentication layer on top of OAuth 2.0 that returns a signed ID token stating who logged in, plus a UserInfo endpoint and discovery metadata.

## Why it matters

- OAuth hands out access tokens; OIDC adds identity by defining the ID token as proof of login.
- Standard scopes (`openid`, `profile`, `email`) and a discovery document make clients portable between providers.
- It standardizes key publication and rotation through the provider's JWKS, so clients do not hard-code keys.
- Treating an access token as proof of identity is a common and serious mistake; OIDC exists to avoid exactly that confusion.

## How it works

OIDC runs the OAuth authorization code flow with the `openid` scope added. The token response includes an `id_token`, a JWT with claims such as `iss`, `sub`, `aud`, `exp` and `nonce`. The client fetches `https://idp.example/.well-known/openid-configuration`, reads the `jwks_uri`, verifies the signature, then checks that `aud` equals its own `client_id` and that `nonce` matches the one it sent. The `/userinfo` endpoint returns additional claims. The ID token is for the client to consume; API calls still use the access token.

## In this platform

There is no login today: the admin plane (Dagster, Metabase, the Elementary report) is reachable only over Tailscale, which substitutes network identity for user identity. The planned identity provider choice (Keycloak, Authentik or Zitadel) all speak OIDC, so the platform would consume OIDC rather than implement it. That work is planned rather than present, and it becomes relevant when the public API gets an API gateway in front of it.

## Related

- [[OAuth 2.0]]
- [[JWT]]
- [[Identity Providers]]
- [[RBAC]]

## Further reading

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
