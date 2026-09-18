---
title: Kubernetes
type: concept
status: seedling
tags: [platform-engineering, containers, orchestration]
created: 2026-09-18
updated: 2026-09-18
aliases: [K8s]
---

# Kubernetes

Kubernetes is an open-source container orchestration platform that schedules workloads across a cluster and continuously reconciles them toward a declared state.

## Why it matters

- Control loops make the cluster self-healing: a failed container restarts, and a lost node's pods are rescheduled.
- Rolling updates and health probes allow deploys without hand-managed downtime.
- Services, ConfigMaps, and Secrets give a standard way to wire and configure workloads across environments.
- It is portable, so the same manifests run on a laptop cluster, a Hetzner node, or a managed cloud.

## How it works

You submit manifests to the API server. Controllers compare desired and observed state and act on the difference. The scheduler places pods on nodes, and the kubelet runs them.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: {name: api}
spec:
  replicas: 1
  selector: {matchLabels: {app: api}}
  template:
    metadata: {labels: {app: api}}
    spec:
      containers:
        - name: api
          image: ghcr.io/org/fx-api:sha-abc123
          ports: [{containerPort: 8000}]
```

## In this platform

Kubernetes is not used today. The platform runs as roughly 12 Docker Compose services on a macOS arm64 dev machine, which covers scheduling, networking, and restarts without a cluster. The planned target is a Hetzner machine running [[K3s]], a lightweight Kubernetes distribution. Note the boundary: Kubernetes is the platform, K3s is one distribution of it, and [[GitOps]] is how manifests would reach the cluster.

## Related

- [[K3s]]
- [[GitOps]]
- [[RBAC]]

## Further reading

- [Kubernetes documentation](https://kubernetes.io/docs/home/)
- [Kubernetes: concepts](https://kubernetes.io/docs/concepts/)
- [CNCF landscape](https://landscape.cncf.io/)
