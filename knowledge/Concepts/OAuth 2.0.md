---
title: OAuth 2.0
type: concept
status: seedling
tags: [authorization, api-security, identity]
created: 2026-09-18
updated: 2026-09-18
aliases: [OAuth2, OAuth 2]
---

# OAuth 2.0

OAuth 2.0 is a framework that lets a client obtain limited access to an HTTP service, either on behalf of a user or on its own behalf, without handling that user's password.

## Why it matters

- It replaces password sharing with scoped, expiring, revocable access tokens (RFC 6749).
- Scopes bound what a token can do, so a leaked token is not automatically full account takeover.
- It is the plumbing under delegated access: "let this app read my data" without giving it my credentials.
- OAuth 2.0 is authorization, not authentication. It says what a client may access, not who the user is, so on its own it is not a login protocol.

## How it works

Four roles: resource owner, client, authorization server, resource server. The mainstream flow is authorization code with PKCE (RFC 7636):

1. The client redirects the browser to the authorization server with `client_id`, `redirect_uri`, `scope`, `state` and a PKCE `code_challenge`.
2. The user consents; the server redirects back with a short-lived `code`.
3. The client exchanges the `code` plus `code_verifier` for an access token.
4. The client calls the API with `Authorization: Bearer <token>` (RFC 6750).

Access tokens are opaque to the client per spec, so the authorization server chooses the format. The client credentials grant covers machine-to-machine calls with no user present.

## In this platform

Most services currently bind to `0.0.0.0` with no authentication in front of them, so OAuth 2.0 is not in use today. `platform-spec.md` puts owner-only endpoints behind a single API key compared with `secrets.compare_digest`, and calls OAuth/JWT ceremony at single-operator scale; user accounts and multi-tenant auth are explicitly out of scope for v1. OAuth becomes relevant with the planned Hetzner/K3s deployment, where an identity provider and an API gateway would sit in front of the public API.

## Related

- [[OpenID Connect]]
- [[JWT]]
- [[RBAC]]
- [[Identity Providers]]

## Further reading

- [RFC 6749: The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750: The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
