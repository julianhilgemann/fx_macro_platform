---
title: K3s
type: concept
status: seedling
tags: [platform-engineering, kubernetes, lightweight]
created: 2026-09-18
updated: 2026-09-18
aliases: [K3s]
---

# K3s

K3s is a lightweight, CNCF-certified Kubernetes distribution shipped as a single binary and aimed at small, resource-constrained, and edge deployments.

## Why it matters

- It fits where a full control plane would not: one small VM or a device can host a real cluster.
- It is certified Kubernetes, so standard manifests, APIs, and tools work unchanged rather than a reduced dialect.
- Installation is one command, which keeps a hobby-scale platform reproducible without a managed control plane bill.
- Defaults are opinionated: SQLite instead of etcd, bundled containerd, flannel networking, Traefik ingress, and a local path provisioner, all of which can be swapped or disabled.

## How it works

The server runs the control plane and, by default, also runs workloads. Agents join with a token. An embedded datastore avoids external dependencies for a single node.

```bash
curl -sfL https://get.k3s.io | sh -
# production single node, with add-ons you will replace yourself
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable traefik --disable servicelb" sh -
```

## In this platform

K3s is planned, not present. Nothing in the repo references it yet, and no cluster exists. It is the intended runtime for the move to Hetzner, where the roughly 12 Compose services would run as Kubernetes workloads, with [[Terraform]] provisioning the node and [[GitOps]] delivering manifests once a controller is chosen. For a single-node, low-budget platform, the reduced footprint is the main reason to prefer it over upstream Kubernetes.

## Related

- [[Kubernetes]]
- [[Terraform]]
- [[GitOps]]

## Further reading

- [K3s](https://k3s.io/)
- [K3s documentation](https://docs.k3s.io/)
- [CNCF: K3s project](https://www.cncf.io/projects/k3s/)
