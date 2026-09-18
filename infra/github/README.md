# GitHub Issues + Projects v2 — roadmaps for fx_macro_platform

The project-tracking system for this repository, replacing the self-hosted Plane
deployment that was decommissioned on 2026-09-18.

| | |
|---|---|
| Repository | `julianhilgemann/fx_macro_platform` (public) |
| Board / roadmap | <https://github.com/users/julianhilgemann/projects> |
| Credential | `.token` (gitignored, fine-grained PAT) |
| MCP server | official `github/github-mcp-server` v1.12.2, tools as `mcp__github__*` |

**Why GitHub instead of a self-hosted tool:** Plane CE cost 12 containers and
1.26 GiB of RAM, and still had no Initiatives or Milestones (both are
Cloud/commercial features — not configuration, the routes do not exist in the
v1.4.2 backend). GitHub Projects has native Milestones, a Board layout *and* a
Roadmap (timeline) layout, and an official MCP server that runs as a single
prebuilt binary with **no container and no long-lived process** — and it is
already where this repository's code and pull requests live.

## How the roadmap maps across

| GitHub | ← Proposal | Count |
|---|---|---|
| **Milestones** (due date = module target date) | modules | 15 |
| **Labels** (`init: <theme>` for roadmap themes) | proposed labels + themes | 19 + 6 |
| **Issues** (description, acceptance criteria, evidence) | work items | 82 |
| **Project v2 fields** | Status, Priority, Initiative, Estimate, Start date, Target date | 6 |

Because Community Edition had no Initiatives, each roadmap theme is carried as an
`init: <theme>` label — filter on it to see a theme across every module. Module
start dates live on the Project's `Start date` field, since GitHub milestones
carry only a due date.

## Running the migration

```bash
cd infra/github

# 0. verify the token can do the migration — catches a mis-scoped PAT before
#    anything is written (Projects permission is the usual culprit)
../../.venv/bin/python migrate_roadmap.py --preflight

# 1. labels, milestones, issues   (REST; ~4 min, paced for rate limits)
../../.venv/bin/python migrate_roadmap.py --dry-run
../../.venv/bin/python migrate_roadmap.py

# 2. project board, fields, values (GraphQL)
../../.venv/bin/python build_project.py --dry-run
../../.venv/bin/python build_project.py

#    ...or populate an EXISTING project by number instead of creating one:
../../.venv/bin/python build_project.py --project-number 3
```

`build_project.py` creates a project titled `PROJECT_TITLE` if none exists, or
reuses one with that title. Use `--project-number N` to bring a project you made
by hand up to parity — it adds any missing fields, adds any issues not yet on the
board, and populates field values, while keeping your existing views (a
board-layout view named "Kanban" is respected, not duplicated).

Field values are populated **additively**: only blanks are filled, so re-running
never overwrites manual triage. Pass `--force-values` to deliberately overwrite
everything from the proposal.

Run `--preflight` first: without it, a fine-grained token missing the *Projects*
account permission only fails partway through step 2, as an opaque GraphQL
permission error.

Both scripts are **idempotent and convergent**: labels, milestones and issues are
matched by name and repaired rather than duplicated, so re-running after a
partial failure is safe. `--verify` on either prints current state.

`migrate_roadmap.py` writes `.issues-map.json` (issue name → number/node id) which
`build_project.py` consumes; run them in that order.

## Credential

Saved as a single line in `.token` (gitignored) and read at run time by both the
scripts and the MCP launcher, so it is never stored in the harness profile
config.

**Issues, labels and milestones work with a fine-grained PAT:**

* **Repository permissions:** Issues *Read and write*, Pull requests *Read and write*, Contents *Read*

**The Projects v2 board additionally requires a classic PAT.** This is a GitHub
limitation, not a preference: for **user-owned** projects the Projects GraphQL
API rejects fine-grained tokens with *"Resource not accessible by personal access
token"*, and [GitHub's documentation](https://github.github.com/gh-aw/reference/auth-projects/)
directs you to a classic PAT for user-owned projects. Fine-grained tokens only
cover *organization*-owned projects. Create one with:

* scopes: **`project`** (plus `repo` if project items come from private repos)
* at <https://github.com/settings/tokens/new>

`migrate_roadmap.py --preflight` verifies Projects access **before** any write,
probing project content rather than just a count — `totalCount` is readable
without the permission, so a count-only check passes while every real project
call fails.

```bash
pbpaste > infra/github/.token    # after copying the token in GitHub's UI
```

## Current state

Fully migrated and verified live on `julianhilgemann/fx_macro_platform`:

| | |
|---|---|
| Issues | 82 (75 open, 7 closed) |
| Milestones | 15, one per module, with target dates and progress |
| Labels | 34 (25 created + GitHub's 9 defaults) |
| Project | [#3 — Platform](https://github.com/users/julianhilgemann/projects/3): 82 items, 11 fields (6 custom), 492 field values, **Roadmap** + **Kanban** + **Full** views |

Re-running either script is safe and converges rather than duplicating.

## If you would rather not use a classic PAT

Not needed — a classic PAT with the `project` scope is now in place and the board
is built. This is kept only as a record of what the fallback looks like, since it
is the only part of the migration that depends on the token type:

* **Milestones** — one per module, with target dates and progress:
  <https://github.com/julianhilgemann/fx_macro_platform/milestones>
* **Labels** — one per roadmap theme (`init: <theme>`), filterable across modules
* **Issues** — all 82 work items with acceptance criteria and evidence

That still covers planning and tracking; what it lacks is the kanban board and the
timeline layout. Note that writing issues/labels/milestones needs `repo` or
`public_repo`; the current token has only `project`, which is sufficient because
the migration is already complete (preflight warns about this rather than failing).

## MCP tool server

`github-mcp-stdio.sh` is the stdio entry point registered in
`~/.dsh/profiles/web/cordis.patch.yml`:

* Downloads the official **Darwin arm64** binary once into `.dsh-cache/github-mcp/`
  and verifies its SHA-256 against the release checksum before use.
* Reads the token from `.token` at run time — no secret in the profile config.
* Enables `--toolsets=default,labels,projects`. This matters: **`labels` and
  `projects` are not in the server's default toolset**, so without them the board
  and roadmap are unreachable. Override with `GITHUB_MCP_TOOLSETS=all` if wanted.
* The binary is 24 MB and runs only for the lifetime of the MCP connection —
  no container, no daemon.

> **MCP tools appear only after the harness reloads.** Start a new session to see
> `mcp__github__*`.
>
> All 50 tools work with the classic PAT in `.token`. Verified by calling
> `list_label`, `list_issues`, `projects_get`, `projects_list` (views) and
> `projects_list` (items) against the real repository and board.

## Related

* `../../research/plane-roadmap-proposal.json` — the source roadmap: 6 themes,
  15 modules, 82 work items, each citing the file that justifies it.
* `../plane/README.md` — the decommissioned Plane deployment, kept for reference.

## Known environment issue

`gh` CLI is installed but its stored token is invalid, and `security
find-internet-password` fails with *"A Module Directory Service error has
occurred"* — the same fault that breaks `docker-credential-desktop` on this
machine. The macOS keychain integration is misbehaving; both scripts and the MCP
launcher therefore read the token from a file instead of relying on it. Worth
fixing independently — it likely affects other tools.
