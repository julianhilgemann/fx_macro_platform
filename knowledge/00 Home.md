---
title: Home
type: moc
status: growing
tags: [index, moc]
created: 2026-09-18
updated: 2026-09-18
aliases: [Index, Start Here, Vault Home]
---

# Home

Working knowledge base for the [[FX Macro Platform]] build, and for the
architect-track study that runs alongside it.

Two audiences, deliberately in one vault:

- **Project context.** What the platform is, how it is put together, what is
 broken, and what to do next.
- **Concept notes.** Atomic references for the ideas the work depends on. Written
 to be read once and re-read when a decision needs grounding.

## Start here

- [[Platform Delivery Plan]], the 19 consolidated workstreams. The actionable
 layer over the 82 GitHub issues.
- [[FX Macro Platform]], what the platform is and why it exists.
- [[Current State]], an honest inventory of what works, what is stubbed and what
 is broken.
- [[Weekly Rhythm]], the operating cadence that keeps the plan moving.

## Maps of content

| Map | Covers |
|---|---|
| [[MOC - Architecture]] | Structure, decisions and boundaries |
| [[MOC - Platform Engineering]] | Running it: IaC, Kubernetes, SRE, observability |
| [[MOC - Security and Identity]] | Auth, access control, exposure |
| [[MOC - Data Engineering]] | Contracts, modelling, correctness |
| [[MOC - API Design]] | The serving surface |
| [[MOC - Networking]] | DNS, TLS, proxies, load balancing |

## Conventions

Notes use a shared front matter block:

```yaml
---
title: Note Title
type: concept # concept | platform | plan | moc | reference
status: seedling # seedling | growing | evergreen
tags: [lowercase, kebab-case]
created: YYYY-MM-DD
updated: YYYY-MM-DD
aliases: [Alternative Name]
---
```

Bodies follow a fixed shape: a one-line definition, then `Why it matters`,
`How it works`, `In this platform`, `Related` and `Further reading`.

`In this platform` is the section that earns its keep. It states plainly whether
the concept is in use, planned, or absent, and it must not claim more than the
repository supports. If a note says something is planned, it is not built.

Links are wiki links: `[[Note Name]]`. A link to a note that does not exist yet is
a useful signal, not an error. Obsidian will show it as unresolved, which is a
prompt to write it.

## What this vault is not

Not a substitute for `platform-spec.md`, which remains the authoritative design
document. Where the two disagree, the spec wins and this vault has a bug.
