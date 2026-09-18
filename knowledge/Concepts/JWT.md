---
title: JWT
type: concept
status: seedling
tags: [tokens, authentication, api-security]
created: 2026-09-18
updated: 2026-09-18
aliases: [JSON Web Token, JWS]
---

# JWT

A JWT (JSON Web Token) is a compact, URL-safe token whose claims are base64url-encoded JSON, protected by a signature or, less commonly, by encryption.

## Why it matters

- Any service can validate a JWT offline from the issuer's public key, with no session store lookup per request.
- A JWT is signed, not encrypted. Anyone holding the token can read the payload, so secrets and personal data must never go in the claims.
- Revocation is the hard part: a stateless token stays valid until it expires even after logout, a password change or a role change.
- Weak validation (`alg: none`, algorithm substitution, unchecked `aud` or `iss`) turns a token format into an authentication bypass.

## How it works

A JWT has three base64url parts joined by dots: `header.payload.signature`. A typical payload:

```json
{
  "iss": "https://idp.example",
  "sub": "user-42",
  "aud": "fx-api",
  "exp": 1790000000,
  "scope": "read:marts"
}
```

The verifier checks the signature against the issuer's JWKS, then `exp`, `aud` and `iss`. Because revocation is the weakness, common mitigations are short `exp` values, refresh tokens issued by the provider, token introspection on each call, or a deny-list keyed on the `jti` claim. All of them trade away some of the statelessness that made the format attractive.

## In this platform

JWTs are not used today. `platform-spec.md` keeps owner-only endpoints on a single API key header and describes OAuth/JWT as ceremony at single-operator scale, with user accounts out of scope for v1. JWTs would appear only if the planned API gateway validates tokens issued by the chosen identity provider, or if the platform later exposes per-user access to the public API.

## Related

- [[OAuth 2.0]]
- [[OpenID Connect]]
- [[RBAC]]

## Further reading

- [RFC 7519: JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725: JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [OWASP JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
