---
title: OWASP Top 10
type: concept
status: seedling
tags: [security, appsec, risk]
created: 2026-09-18
updated: 2026-09-18
aliases: [OWASP Top Ten]
---

# OWASP Top 10

The OWASP Top 10 is a periodically refreshed consensus list of the ten most critical web application security risk categories, published as an awareness document rather than a standard.

## Why it matters

- It gives a security review a shared checklist instead of ad hoc probing, which matters before anything is exposed publicly.
- The 2025 edition is the current one: it promotes software supply chain failures to A03 and security misconfiguration to A02, both relevant to a platform assembled from many third-party images.
- Each category is a risk theme covering many CWEs, so it guides design decisions, not just bug fixing.
- It is awareness, not compliance. It does not replace a threat model of your own system.

## How it works

The 2025 categories are A01 Broken Access Control, A02 Security Misconfiguration, A03 Software Supply Chain Failures, A04 Cryptographic Failures, A05 Injection, A06 Insecure Design, A07 Authentication Failures, A08 Software and Data Integrity Failures, A09 Security Logging and Alerting Failures, and A10 Mishandling of Exceptional Conditions. Relative to the 2021 edition, server-side request forgery was folded into A01, security misconfiguration rose to A02, and the old vulnerable components category was broadened into A03 Software Supply Chain Failures. The list is revised every few years from contributed data and survey input.

## In this platform

The pressing risk here is exposure, not data theft: the payload is public FRED and ECB numbers, and the roadmap flags restricting the admin plane before any Ingress. A02 and A01 map directly onto unauthenticated services: Dagster has no authentication of its own, and the observability plan notes that exporters have no auth beyond binding to the Tailscale interface. A03 and A08 map onto the roughly twelve third-party container images, and A06 maps onto the threat model in `platform-spec.md`, which already names resource abuse as the realistic risk. The OWASP-aligned review is planned, not yet performed.

## Related

- [[RBAC]]
- [[Identity Providers]]
- [[TLS]]
- [[Reverse Proxy]]

## Further reading

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [OWASP API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/)
