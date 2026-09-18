---
title: mTLS
type: concept
status: seedling
tags: [tls, authentication, service-to-service]
created: 2026-09-18
updated: 2026-09-18
aliases: [Mutual TLS, Mutual Authentication]
---

# mTLS

Mutual TLS (mTLS) is TLS in which both ends present certificates, so the client proves its identity during the handshake instead of presenting a bearer token with a request.

## Why it matters

- Identity is verified at the transport layer, before any application code parses the request.
- There is no replayable credential: an attacker needs the private key, not just a copied token.
- It fits service-to-service traffic where no human logs in and no browser is involved.
- It is operationally heavy. You run a certificate authority and you own issuance, rotation and revocation.

## How it works

In the TLS handshake the server presents its certificate and requests one from the client, and each side validates the other against a trusted CA. In TLS 1.3 the certificate request and the client certificate are themselves encrypted. Machine identities are usually short-lived certificates from an internal CA, with a workload identity system handling rotation automatically.

A typical server-side configuration fragment:

```yaml
tls:
  clientAuth:
    clientAuthType: RequireAndVerifyClientCert
    caFiles: [/certs/internal-ca.pem]
```

Browsers make mTLS awkward for people (certificate prompts, no clean logout), so it is normally applied to services and devices, with OIDC or session cookies reserved for humans.

## In this platform

There is no mTLS in the current setup: roughly twelve Docker Compose services bind to `0.0.0.0` with no authentication in front of most of them, and they share one Compose network, so service-to-service calls are unauthenticated and in practice unencrypted. The stated roadmap covers an identity provider, RBAC, an API gateway and an OWASP-aligned review, but does not call for mTLS. If it were added, it would protect traffic inside K3s between services, not the public `api.` hostname, where the client is a browser.

## Related

- [[TLS]]
- [[Kubernetes]]
- [[Identity Providers]]

## Further reading

- [RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [RFC 8705: OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705)
- [SPIFFE concepts: workload identity](https://spiffe.io/docs/latest/spiffe-about/spiffe-concepts/)
