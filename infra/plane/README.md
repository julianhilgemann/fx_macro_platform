# Plane — local project management for fx_macro_platform

> ## ⚠️ DECOMMISSIONED — 2026-09-18
>
> This deployment has been **torn down**: all 12 containers, every named volume
> and all 10 Plane images were removed, recovering 1.26 GiB of RAM and ~2.9 GB of
> Docker storage. Nothing here is running, and `plane.sh` will not work.
>
> The roadmap it held was migrated to **GitHub Issues + Projects v2** — see
> [`../github/README.md`](../github/README.md). These files are kept only as a
> record of the deployment and of the Community Edition limitations documented
> below; they are not part of the active toolchain. Safe to delete.

A self-hosted [Plane](https://plane.so) Community Edition instance used to track
the planning and development of this platform. It ran as its own Docker Compose
project (`plane`), fully isolated from the `fx_macro_platform` services.

| | |
|---|---|
| Web UI | <http://localhost:8085> |
| REST API | `http://localhost:8085/api/v1/` |
| Instance admin | <http://localhost:8085/god-mode/> |
| Workspace | `fx-macro-platform` |
| Project | `FXM` — FX Macro Data Platform |
| Credentials | `.credentials.local` (gitignored, mode 600) |
| Version | Plane Community Edition v1.4.2 (pinned) |

## Quick start

```bash
cd infra/plane

./plane.sh up        # pre-pull images, then start the stack
./plane.sh health    # poll until the API answers
./plane.sh ps        # container status
./plane.sh logs api  # follow one service's logs (omit name for all)
./plane.sh stop      # stop containers, keep all data
./plane.sh destroy    # delete containers AND volumes (destroys all Plane data)
```

Data lives in Docker named volumes (`plane_pgdata`, `plane_uploads`,
`plane_redisdata`, `plane_rabbitmq_data`) and survives `stop`/`down`.

## Why there is a wrapper script

Three environment problems made a plain `docker compose up` fail. Each is handled
in `plane.sh` rather than by editing files outside this directory:

1. **Broken Docker credential helper.** This machine's `~/.docker/config.json` sets
   `credsStore: "desktop"`, and `docker-credential-desktop` fails with
   *"A Module Directory Service error has occurred"*, aborting every pull. All
   images here are public, so the wrapper points `DOCKER_CONFIG` at a minimal
   config with no credential helper. `~/.docker/config.json` is left untouched.
   Because `DOCKER_CONFIG` also relocates the CLI-plugin path, the real
   `~/.docker/cli-plugins` directory is symlinked back in so `docker compose`
   itself keeps working.
2. **Compose still calls the credential helper even with the above.**
   `docker compose pull` resolves credentials through a different code path and
   still fails, so the wrapper pre-pulls every image with `docker pull` (which
   works) and then runs `up --pull never`.
3. **MinIO left Docker Hub.** [MinIO ended free Docker Hub distribution in
   October 2025](https://gigazine.net/gsc_news/en/20251023-minio-stops-distributing-free-docker-images),
   so `minio/minio:latest` now returns *pull access denied*.
   `docker-compose.override.yml` repoints the bundled object store to
   `quay.io/minio/minio`, leaving the vendored `docker-compose.yml` byte-identical
   to the upstream v1.4.2 release.

## Isolation from the main platform

* Own compose project (`plane`), so its network is `plane_default`.
* No shared containers, volumes, or networks with `fx_macro_platform`.
* Only the proxy publishes host ports: **8085** (HTTP) and **8443** (HTTPS).
  Postgres, Redis, RabbitMQ and MinIO stay private to the compose network, so
  there is no clash with the platform's own Postgres on 5433.
* Chosen to avoid the ports already in use: 3000, 8001, 8080–8084, 8501, 8978.

## API access

The API token is in `.credentials.local` as `API_KEY`, sent as the `X-API-Key`
header. Verified working for full CRUD:

```bash
source <(grep -E '^(WEB_URL|API_KEY|WORKSPACE_SLUG)=' .credentials.local)

curl -H "X-API-Key: $API_KEY" \
  "$WEB_URL/api/v1/workspaces/$WORKSPACE_SLUG/projects/"
```

To rotate or revoke: **Workspace Settings → API tokens** in the web UI.

Rate limits are raised for local scripting in `plane.env`
(`API_KEY_RATE_LIMIT=300/minute`, `AUTHENTICATION_RATE_LIMIT=30/minute`); the
stock values are 60/minute and 10/minute.

## MCP tool server (how the agent drives Plane)

Plane's official [`plane-mcp-server`](https://github.com/makeplane/plane-mcp-server)
is wired into the DSH harness, so its tools appear to the model as
`mcp__plane__<tool>` — 30 tools covering `workitem`, `module`, `cycle`, `state`,
`label`, `project`, `page`, `workitem_comment`, `workitem_link` and more.

* Registration lives in `~/.dsh/profiles/web/cordis.patch.yml`. The original
  content is backed up under `../../.dsh-cache/plane-mcp/backup/`.
* `plane-mcp-stdio.sh` is the stdio entry point. It reads the API token from
  `.credentials.local`, so **no secret is stored in the harness config**, and
  pins uv's cache/tool/interpreter directories inside `.dsh-cache/` (gitignored)
  so nothing is written to your global `~/.cache` or `~/.local/share`.

> **The MCP tools only appear after the harness reloads.** The patch file
> hot-reloads when edited, but a session that was already running keeps the tool
> list it booted with — start a new session to see `mcp__plane__*`.

To disable, set `cordis.patch.yml` back to `[]`.

## Roadmap content

`seed_roadmap.py` loads `research/plane-roadmap-proposal.json` — an analysis of
this repository derived from `platform-spec.md`, `README.md`, git history and the
current state of the code. Every work item cites the file that justifies it.

```bash
../../.venv/bin/python seed_roadmap.py              # seed / converge
../../.venv/bin/python seed_roadmap.py --verify     # roadmap status report
../../.venv/bin/python seed_roadmap.py --dry-run    # report without writing
../../.venv/bin/python seed_roadmap.py --fresh-project  # drop Plane's demo project first
```

Loaded: **15 modules**, **82 work items**, **25 labels**, **8 workflow states**,
across 6 roadmap themes. The script is idempotent and convergent — it matches by
name and repairs drift, so re-running it never duplicates and it fixes items left
in a wrong state by an earlier partial run.

### Community Edition limits discovered

These cost real debugging time; they are properties of CE v1.4.2, not of this
setup:

* **Initiatives do not exist.** There is no `initiative` route in either the
  public or app API in this release (they are a Plane Cloud/commercial feature).
  The MCP server advertises an `initiative` tool, but it 404s against CE.
  Workaround: each of the 6 roadmap themes is a label named `init: <theme>`,
  applied to every work item in that theme's modules.
* **Milestones do not exist** either. Each module's milestones are preserved as a
  checklist inside the module description.
* **PQL / server-side filtering is unsupported.** The MCP server returns
  *"PQL and structured filters are not supported on this Plane edition"*. Filter
  client-side over the full list instead.
* **`Triage` is a hidden native state.** Plane creates a `Triage` state
  (group `triage`) for every project but hides it from the states API, so creating
  one by name hits a duplicate-key error that Plane's own error handler turns into
  a bare HTTP 500. The seeder treats that name as already present.
* **New projects start with modules disabled.** `module_view` must be enabled
  before modules can be created; the seeder does this automatically.
* **A hidden `POST` flag:** state `group` values must be one of `backlog`,
  `unstarted`, `started`, `completed`, `cancelled` — `triage` is rejected by the
  serializer.

Upgrading to the commercial edition would let Initiatives and Milestones become
first-class objects; the proposal JSON already contains both layers.

## Monitoring

`seed_roadmap.py --verify` prints totals, priority breakdown, per-module progress
bars and flags modules past their target date:

```
in-progress  2026-09-21 → 2026-10-16 [..........]   0%  0/9   Agent Scaffolding & Repo Contracts (M-1)
in-progress  2026-09-21 → 2026-10-30 [###.......]  33%  2/6   Bitemporal Vintage Fidelity
...
overall: 7/82 work items in a closed state (8%)
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `pull access denied` on any image | Credential helper or MinIO — always use `./plane.sh`, never bare `docker compose pull`. |
| `unknown shorthand flag: 'p'` | `DOCKER_CONFIG` set without the `cli-plugins` symlink; run `./plane.sh`. |
| 502 from the proxy | API container still starting — `./plane.sh health`. |
| State creation returns 500 | Duplicate of a hidden native state (e.g. `Triage`); see above. |
| `Modules are not enabled for this project` | PATCH the project with `{"module_view": true}`. |
| MCP tools missing | Start a new harness session; see the MCP section. |

Logs: `./plane.sh logs` for container output, and Plane's own error log at
`/code/plane/logs/plane-error.log` inside the `api` container (it captures full
tracebacks even with `DEBUG=0`).
