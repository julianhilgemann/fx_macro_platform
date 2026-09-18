---
title: Architecture Decision Records
type: concept
status: seedling
tags: [architecture, documentation, decision-making]
created: 2026-09-18
updated: 2026-09-18
aliases: [ADR, ADRs]
---

# Architecture Decision Records

An architecture decision record is a short, dated file that captures one significant decision, the context that forced it, and its consequences.

## Why it matters

- It records the why, which code and configuration cannot: rejected options otherwise disappear.
- It is immutable. A changed decision becomes a new record that supersedes the old one, so history stays readable.
- It lowers onboarding cost: a newcomer reads a handful of short files instead of asking a handful of questions.
- It forces a decision to be stated before it is implemented, which surfaces disagreement early.

## How it works

A record is one numbered file with a title and a few sections. Status moves from proposed to accepted, then to superseded or deprecated.

```yaml
adr: "0007"
title: Use K3s on Hetzner instead of managed Kubernetes
status: proposed        # proposed | accepted | superseded
date: 2026-09-18
context: single macOS arm64 dev machine, low budget, about 12 services
decision: provision one Hetzner node with K3s through Terraform
consequences: [cheap, some operational burden, no managed control plane]
```

## In this platform

A `docs/adr/` folder is planned but does not exist yet. Several decisions are already waiting for a record: the Hetzner and K3s migration, GitOps-driven deploys, the Prometheus, Grafana, and Loki stack, and the identity choice between Keycloak, Authentik, and Zitadel. Until those records exist, `platform-spec.md` at the repo root is the only place holding design intent, and it is one large document rather than a decision log.

## Related

- [[C4 Model]]
- [[GitOps]]
- [[Infrastructure as Code]]

## Further reading

- [Architecture decision records](https://adr.github.io/)
- [MADR: Markdown ADRs](https://adr.github.io/madr/)
- [Documenting architecture decisions, Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
