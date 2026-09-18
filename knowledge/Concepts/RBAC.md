---
title: RBAC
type: concept
status: seedling
tags: [authorization, access-control, identity]
created: 2026-09-18
updated: 2026-09-18
aliases: [Role-Based Access Control]
---

# RBAC

Role-based access control (RBAC) grants permissions to roles rather than to individual users, and a user receives permissions by being assigned one or more roles.

## Why it matters

- Permissions become reviewable: you audit a handful of roles instead of every account.
- Least privilege is expressible in concrete terms, such as a read-only role for BI and a separate admin role.
- Onboarding, offboarding and role changes become one assignment edit rather than a scatter of per-user grants.
- Roles proliferate without discipline. One role per person is RBAC in name only and hides the same mess it was meant to remove.

## How it works

The model is users to role bindings to roles to permissions on resources. Kubernetes is a concrete example:

```yaml
kind: RoleBinding
metadata:
  name: api-marts-reader
subjects:
  - kind: ServiceAccount
    name: api
roleRef:
  kind: Role
  name: marts-reader
```

Two rules keep it honest: deny by default, and split read from write. In Kubernetes, `Role` and `RoleBinding` are namespaced, while `ClusterRole` and `ClusterRoleBinding` apply cluster-wide, so the narrower kind is the safer default.

## In this platform

The closest thing to RBAC today is the Postgres `platform_reader` role restricted to `marts`, which `platform-spec.md` names as the backstop behind query bounds and edge rate limiting. Human roles are not implemented: Dagster ships with no authentication at all and is kept off the public internet by Tailscale. RBAC and user management are planned alongside the identity provider choice, which would introduce roles such as admin and viewer for the admin plane and the public API.

## Related

- [[Identity Providers]]
- [[OAuth 2.0]]
- [[OWASP Top 10]]

## Further reading

- [NIST: Role Based Access Control](https://csrc.nist.gov/projects/role-based-access-control)
- [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
