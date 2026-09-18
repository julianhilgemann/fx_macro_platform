---
title: GitOps
type: concept
status: seedling
tags: [platform-engineering, deployment, gitops]
created: 2026-09-18
updated: 2026-09-18
aliases: []
---

# GitOps

GitOps keeps the desired state of a system in Git and runs a controller that continuously reconciles the live system to match it.

## Why it matters

- Git becomes the single source of truth, so the deployed state is reviewable and has history.
- Rollback is a revert, not a manual repair, which shortens recovery from a bad deploy.
- A reconciling controller detects and corrects drift, so out-of-band changes do not silently persist.
- It removes the need for CI to hold cluster credentials, because the controller pulls rather than being pushed to.

## How it works

A controller such as Argo CD or Flux watches a Git repository, renders the manifests, and applies them to a cluster. The loop is pull-based and continuous: commit, sync, observe, reconcile. CI only builds and commits; it does not deploy.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: {name: fx-macro-platform, namespace: argocd}
spec:
  source: {repoURL: https://github.com/org/fx_macro_platform, path: deploy/k3s, targetRevision: main}
  destination: {server: https://kubernetes.default.svc, namespace: fx}
  syncPolicy: {automated: {prune: true, selfHeal: true}}
```

## In this platform

This platform has not adopted GitOps. There is no Argo CD or Flux controller, no CI at all (`.github/workflows/` is absent), and deployments today are Docker Compose services started by hand on a macOS arm64 dev machine. GitOps-driven deploys are planned as part of the move to Hetzner and K3s. Choosing between Argo CD and Flux, and recording that choice as an [[Architecture Decision Records]], is still open.

## Related

- [[Infrastructure as Code]]
- [[Kubernetes]]
- [[K3s]]

## Further reading

- [OpenGitOps principles](https://opengitops.dev/)
- [Argo CD documentation](https://argo-cd.readthedocs.io/)
- [Flux documentation](https://fluxcd.io/docs/)
