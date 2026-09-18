---
title: Terraform
type: concept
status: seedling
tags: [platform-engineering, iac, provisioning]
created: 2026-09-18
updated: 2026-09-18
aliases: [HashiCorp Terraform]
---

# Terraform

Terraform is an infrastructure as code tool that provisions resources from declarative HCL configuration through provider plugins, tracking what it manages in a state file.

## Why it matters

- One workflow covers many systems, so cloud servers, DNS records, and cluster objects can be described together.
- `terraform plan` shows the exact diff before anything changes, which turns infrastructure into a reviewable proposal.
- The state file maps configuration to real resource identifiers, which is what makes update and destroy possible.
- Modules package a working stack once, so a small platform can rebuild it repeatably instead of retyping it.

## How it works

Configuration declares resources. Providers translate that into API calls. State records the result, and a backend (local file, S3, or Terraform Cloud) stores and locks it, since state can contain secrets.

```hcl
resource "hcloud_server" "k3s" {
  name        = "fx-macro-01"
  server_type = "cpx21"
  image       = "ubuntu-24.04"
  location    = "fsn1"
  user_data   = file("cloud-init/k3s.yaml")
}
```

## In this platform

Terraform is planned, not present. There is no `.tf` file and no Terraform directory in the repo; `infra/` currently holds GitHub and Plane automation scripts, not infrastructure. The plan is for Terraform to provision the Hetzner machine and bootstrap [[K3s]] on it as part of the migration away from the macOS arm64 dev setup. Because there is no CI yet, the first applies would run by hand, which is a reason to write the configuration before the move rather than during it.

## Related

- [[Infrastructure as Code]]
- [[K3s]]
- [[GitOps]]

## Further reading

- [Terraform documentation](https://developer.hashicorp.com/terraform/docs)
- [Terraform: what is it and why](https://developer.hashicorp.com/terraform/intro)
- [Hetzner Cloud provider](https://registry.terraform.io/providers/hetznercloud/hcloud/latest/docs)
