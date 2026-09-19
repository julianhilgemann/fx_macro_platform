---
title: MOC - Platform Engineering
type: moc
status: growing
tags: [moc, platform-engineering, infrastructure]
created: 2026-09-18
updated: 2026-09-19
aliases: [Platform MOC, Infrastructure MOC]
---

# MOC - Platform Engineering

Running software for other people, repeatably. This is the map that turns
[[FX Macro Platform]] from a project on a laptop into something operated.

## Declaring infrastructure

- [[Infrastructure as Code]], the practice. Infrastructure described in files
 that are reviewed and versioned.
- [[Terraform]], the most common implementation of that practice.
- [[GitOps]], the cluster reconciles itself from the repository, so the repo is
 the source of truth for what runs.

## Running workloads

- [[Container Networking]], what actually runs today: Compose bridge networks,
 service-name DNS, and publishing a container port to the host.
- [[Kubernetes]], the orchestration platform and its object model.
- [[K3s]], a lightweight Kubernetes distribution, and the intended target here.

## Operating them

- [[SRE Basics]], error budgets, SLOs, and treating reliability as a feature
 with a cost.
- [[Observability]], the discipline: inferring internal state from outputs.
- [[Observability Stack]], the concrete Prometheus, Grafana and Loki tooling.

## Where the platform stands

None of this is built. The platform runs under Docker Compose on one machine,
with no IaC, no cluster, no CI and no metrics. That is a normal starting point and
which is why E2 and F1 in [[Platform Delivery Plan]] exist.

The intended path is deliberately narrow: K3s on a single Hetzner node,
provisioned with Terraform, reconciled by GitOps, observed with
Prometheus/Grafana/Loki. Resist expanding it.

## Reading order

[[Infrastructure as Code]] then [[Terraform]] then [[K3s]]. [[Observability]]
before [[Observability Stack]], because the tools are easy and the discipline is
not.

## Related

- [[MOC - Networking]]
- [[MOC - Security and Identity]]
- [[MOC - Architecture]]
- [[Stack Inventory]]
