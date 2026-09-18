---
title: TLS
type: concept
status: seedling
tags: [networking, tls, security, encryption]
created: 2026-09-18
updated: 2026-09-18
aliases: [Transport Layer Security, SSL]
---

# TLS

TLS is the protocol that encrypts and authenticates traffic between two endpoints over an untrusted network.

## Why it matters
- It gives confidentiality and integrity, so intermediaries cannot read or quietly alter payloads.
- Server certificates prove the client reached the intended host, which is what makes public APIs safe to call.
- Browsers, dashboards, and token flows assume HTTPS; plain HTTP breaks or degrades them.
- It is the transport that carries JWTs and OAuth 2.0 tokens without exposing them.

## How it works
A TLS 1.3 handshake costs one round trip. The client sends a ClientHello with SNI, supported cipher suites, and a key share. The server replies with its chosen parameters, its certificate, and a CertificateVerify signature proving it holds the private key. Both sides derive session keys with ephemeral ECDHE, so a later compromise of the private key does not decrypt past sessions, then exchange Finished messages. Encrypted application data follows. TLS 1.2 needed two round trips for the same result.

## In this platform
Nothing terminates TLS yet: the dev machine runs Streamlit, the D3 dashboard, Metabase, FastAPI, and CloudBeaver over plain HTTP on localhost ports. TLS arrives with the Hetzner and K3s work, where the ingress or the planned API gateway terminates certificates for the public API. From there mTLS becomes a realistic option for traffic between internal services.

## Related
- [[mTLS]]
- [[Reverse Proxy]]
- [[OAuth 2.0]]
- [[DNS]]

## Further reading
- [RFC 8446: The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)
- [MDN: Transport Layer Security](https://developer.mozilla.org/en-US/docs/Web/Security/Transport_Layer_Security)
