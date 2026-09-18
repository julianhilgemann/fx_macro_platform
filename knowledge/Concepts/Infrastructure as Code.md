---
title: Infrastructure as Code
type: concept
status: seedling
tags: [platform-engineering, automation, reproducibility]
created: 2026-09-18
updated: 2026-09-18
aliases: [IaC]
---

# Infrastructure as Code

Infrastructure as Code is the practice of defining and provisioning infrastructure through versioned, machine-readable files instead of manual steps.

## Why it matters

- A rebuilt environment matches the original, which makes disaster recovery and a second environment realistic.
- Changes arrive as reviewable diffs, so infrastructure gets the same scrutiny as application code.
- Repeated runs converge to the same state, which removes the undocumented manual tweak that nobody remembers.
- It exposes drift: when the live system and the files disagree, the difference is detectable.

## How it works

You describe the desired end state, store it in version control, review a plan or diff, and apply it. Tools are either declarative provisioners (Terraform, Pulumi, CloudFormation) or configuration managers (Ansible, Chef). A hand-written Compose file is a light form of the same idea.

```yaml
services:
  postgres:
    image: postgres:16
    environment: {POSTGRES_DB: warehouse}
    volumes: ["pgdata:/var/lib/postgresql/data"]
```

The practice is the point, not the tool. Any of these can be done badly and still be called IaC.

## In this platform

`docker-compose.yml` already describes the roughly 12 running services in one declarative file, so the local environment is partly codified. It is not fully reproducible yet: the file lives on a single macOS arm64 machine and there is no CI to apply it anywhere. The planned Hetzner and K3s target is where formal IaC starts, with [[Terraform]] provisioning nodes and GitOps-style reconciliation handling what runs on them.

## Related

- [[Terraform]]
- [[GitOps]]
- [[Kubernetes]]

## Further reading

- [Infrastructure as Code, Martin Fowler](https://martinfowler.com/bliki/InfrastructureAsCode.html)
- [Infrastructure as Code, Kief Morris](https://www.oreilly.com/library/view/infrastructure-as-code/9781098114671/)
- [What is infrastructure as code?](https://learn.hashicorp.com/tutorials/terraform/infrastructure-as-code)
