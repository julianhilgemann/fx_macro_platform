---
title: Remote Access
type: reference
status: growing
tags: [platform, infrastructure, remote-access, tailscale, dsh]
created: 2026-09-19
updated: 2026-09-19
aliases: [Phone Access, Tailscale Setup, Remote Access Setup]
---

# Remote Access

How the MacBook Air (and the whole dev stack on it) is reached from an iPhone or
another laptop when they are **not** on the same network — typically the phone on
5G. The transport is Tailscale; the machine stays bound to loopback wherever
possible.

Reconstructed 2026-09-19 from the working setup. Values below are this machine's
actual ones — substitute if the tailnet or hostname ever changes.

## What you get

Two **independent** paths, with different mechanisms and different auth. This
distinction caused most of the confusion during setup, so it is worth fixing
early:

| | Path A — DSH Web GUI | Path B — Docker services |
|---|---|---|
| URL | `https://dopamine-air.tail225b1e.ts.net` | `http://dopamine-air.tail225b1e.ts.net:PORT` |
| Mechanism | `tailscale serve` (reverse proxy) | container publishes on `0.0.0.0` |
| Scheme | HTTPS (real cert) | plain HTTP |
| Auth | pairing QR / device cookie | none |
| Why | `dsh web` binds `127.0.0.1` only | Docker publishes on every interface |

Tailscale does **not** expose every port by itself. Path A needs an explicit
`tailscale serve` mapping because the harness listens on loopback. Path B needs
no mapping at all because the containers already listen on all interfaces.

## Architecture

```
iPhone (5G) ──Tailscale──▶ MacBook Air  "dopamine-air"  100.101.69.13
                            tailnet: tail225b1e.ts.net

Path A:  https://dopamine-air.tail225b1e.ts.net
           └─ tailscale serve ─▶ http://127.0.0.1:3080   (dsh web)

Path B:  http://dopamine-air.tail225b1e.ts.net:8080
           └─ direct ─────────▶ 0.0.0.0:8080            (launchpad container)
```

## Components

| Piece | Version / value | Role |
|---|---|---|
| Tailscale | both devices, same tailnet | private network, MagicDNS |
| HTTPS Certificates | enabled (admin console → DNS) | required for Serve HTTPS |
| DSH | `0.1.5-rc.2` | the agent harness |
| `@gestaltrun/dsh-remote-web-ui` | `0.3.21-gestaltrun.0` | mobile GUI + pairing |
| `pnpm` | via `corepack enable pnpm` | `dsh plugin` forwards to it |
| `sudo pmset -c sleep 0` | — | stops the Mac sleeping mid-session |

## Setup from scratch

```bash
# 1. Tailscale on both devices, same account. Verify:
tailscale status                 # both peers listed
tailscale serve status           # shows current mappings

# 2. Enable HTTPS Certificates in the Tailscale admin console (DNS page).
#    Without this, `tailscale serve` cannot issue an HTTPS URL.

# 3. pnpm is REQUIRED — `dsh plugin` shells out to it.
corepack enable pnpm

# 4. Install the remote-access plugin into the web profile.
dsh plugin --profile web add @gestaltrun/dsh-remote-web-ui@latest

# 5. Add the config row (below) to the profile patch file.

# 6. Front the loopback-bound harness with Tailscale Serve.
tailscale serve --bg --https=443 3080

# 7. Restart the profile so the plugin loads.
dsh web

# 8. Keep the machine awake, or the phone loses it after a minute.
sudo pmset -c sleep 0
```

The profile patch lives at `~/.dsh/profiles/web/cordis.patch.yml` (outside this
repo — it is harness state, not project state):

```yaml
- id: remote-web-ui
  name: '@gestaltrun/dsh-remote-web-ui'
  config:
    publicBaseUrl: https://dopamine-air.tail225b1e.ts.net
    trustedHosts:
      - dopamine-air.tail225b1e.ts.net
    autoTunnel: false
    relay: false
    requirePairingForLan: true
```

What each key is actually for:

- **`trustedHosts`** — Tailscale Serve is a reverse proxy, so the `Host` header
  arriving at DSH is `dopamine-air.tail225b1e.ts.net`, not a loopback or LAN
  literal. Without this the pairing endpoints reject that authority with `403`.
  This is the single key that makes a reverse proxy work.
- **`publicBaseUrl`** — the QR/pairing link is built from this. Left unset, the
  plugin advertises a **loopback** URL the phone cannot open. It must match the
  scheme Serve actually listens on — see the scheme trap below.
- **`autoTunnel: false` / `relay: false`** — both would front the app with the
  package author's Cloudflare edge (`cloudflared`, and a `dsh-market.com`
  relay). Tailscale already provides a private, device-authenticated path, so
  these stay off.
- **`requirePairingForLan: true`** — non-loopback clients must ride the gated
  `/remote` channel with a live device cookie.

## Ports

All verified reachable from the phone over the tailnet on 2026-09-19. Substitute
the host for `100.101.69.13` if MagicDNS is unavailable.

| Service | Port | Container |
|---|---|---|
| **launchpad** (nav hub) | 8080 | `fx_macro_platform-launchpad-1` |
| Dagster | 3000 | `...-dagster-webserver-1` |
| Metabase | 3001 | `...-metabase-1` |
| API | 8000 | `...-api-1` (`/docs`; `/` is 404 by design) |
| Elementary report | 8081 | `...-elementary-report-1` |
| dbt-deps report | 8082 | `...-dbt-deps-report-1` |
| dbt docs | 8083 | `...-dbt-docs-1` |
| Germany dashboard | 8084 | `...-germany-dashboard-1` |
| Streamlit dashboard | 8501 | `...-dashboard-1` |
| CloudBeaver | 8978 | `...-cloudbeaver-1` |
| Postgres | 5433 | `...-postgres-1` — **do not expose** |

See also [[Stack Inventory]].

### The launchpad hub

`launchpad/index.html` keeps its tile list in a `TILES` array, with `href` and
`health` written against `127.0.0.1`. On load it rewrites the host to
`location.hostname` whenever the page is **not** being viewed from localhost, so
one file serves both the Mac and the phone with no duplication. Host-local
browsing is untouched, which keeps the Mac experience exactly as it was.

The scheme stays `http://` deliberately: the services are plain HTTP on their
published ports no matter how the hub itself was loaded. Making these links
protocol-relative would break them if the hub were ever served over HTTPS.

The file is bind-mounted into nginx (`./launchpad:/usr/share/nginx/html:ro`), so
edits take effect on the next page load — no container restart. nginx sends
`ETag`/`Last-Modified` but no `Cache-Control`, so a phone holding the old copy
may need a hard refresh or a private tab once.

## Gotchas we actually hit

These cost real time. Most produce misleading errors.

1. **`dsh: pnpm not found on PATH`.** `dsh plugin` is a thin wrapper that
   forwards to pnpm. pnpm is not part of Node. Fix: `corepack enable pnpm`.
2. **Install aborts *after* downloading, leaving the plugin inert.** pnpm ≥10
   blocks postinstall scripts. The run prints
   `Ignored build scripts: cloudflared@0.7.3` and writes a placeholder into the
   profile's `pnpm-workspace.yaml`:
   `cloudflared: set this to true or false`. Until that is replaced with a real
   boolean, every install exits non-zero.
3. **`dependencies` is not enough — the plugin must be in `dsh.profile.bundles`.**
   The same abort above skips that wiring, so the package sits in
   `package.json` doing nothing. Re-running the `add` after fixing (2) completes
   it. Always confirm the bundle list afterwards.
4. **The scheme trap.** `publicBaseUrl` must match what Serve is listening on.
   After upgrading Serve from `--http=80` to `--https=443`, the stale `http://`
   value produced a QR link that failed to connect, because nothing listens on
   port 80 any more.
5. **The pairing panel is loopback-only.** Mint the QR by opening
   `http://127.0.0.1:3080` **on the Mac**. The LAN/public control endpoints
   deliberately refuse non-loopback callers.
6. **Direct `/api` from a non-loopback origin returns `403` even when paired.**
   This is expected on DSH `0.1.5-rc.2`: the runtime ships no emitter for the
   plugin's `api/gate` seam, so the harness transport fence keeps governing
   direct `/api` and the phone reaches the app only through the plugin's gated
   `/remote` channel. Not a misconfiguration — do not chase it.
7. **macOS idle-sleeps in 1 minute by default.** The whole premise is a laptop
   acting as an always-on server. Without `pmset`, the phone loses the host as
   soon as you walk away. `caffeinate -s` is only a stopgap — it dies with the
   terminal that started it.
8. **The launchpad hardcoded `127.0.0.1` in its links and health checks.**
   Fixed 2026-09-19. The page loaded fine on the phone, then every service link
   opened the phone itself and every status dot read *offline*, because on iOS
   `127.0.0.1` means the phone. See "The launchpad hub" above.

## Verifying it works

Run these on the Mac. None need the phone.

```bash
# Transport is up and mapped to the right port
tailscale serve status

# Harness reachable through Serve with a valid cert (401 = auth gate, expected)
curl -sS -o /dev/null -w '%{http_code}\n' https://dopamine-air.tail225b1e.ts.net/

# Plugin host half is mounted and config applied — simulates the proxy's Host header
curl -sS -H 'Host: dopamine-air.tail225b1e.ts.net' http://127.0.0.1:3080/pair-accept

# Fence is scoped, not a blanket bypass — this must be 403
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H 'Host: evil.example.com' http://127.0.0.1:3080/pair-accept

# Which container ports are actually published
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

`--dump-config` composes the profile without booting it, which is the safe way to
validate a patch edit before restarting:

```bash
dsh --profile web --dump-config | grep -A8 remote-web-ui
```

## Daily use

1. Confirm Tailscale VPN is **on** in the iOS app (5G is fine — that is the
   point).
2. Open `https://dopamine-air.tail225b1e.ts.net` for the DSH GUI, or
   `http://dopamine-air.tail225b1e.ts.net:8080` for the launchpad.
3. Re-pair only if the device session expired. Open `http://127.0.0.1:3080` on
   the Mac → phone icon beside Settings → scan.

Because Serve is HTTPS, the phone page is a **secure context**, so the plugin's
reopen service worker registers and bookmarks survive. On plain HTTP they would
not, and every reopen would need a fresh scan.

## Security notes

- **A paired device is full control credentials** — chat, sessions, settings,
  stored secrets, workspace files. Pair only devices you control. `stop` in the
  panel revokes all of them.
- **Path B is unauthenticated.** Anything that publishes `0.0.0.0` is reachable
  on *every* network the Mac joins, coffee-shop wifi included. That currently
  includes Postgres on 5433. Tailscale protects Path A; it does not protect
  Path B, because the `0.0.0.0` binding sidesteps it.
- **The plugin phones home.** Its browser half sends one anonymous install
  heartbeat per UTC day to `dsh-market.com`. The relay and tunnel features
  (both off here) would route traffic through the author's Cloudflare edge.
- Prefer `brew install <tool>` over `curl … | sh` where a package exists.

## Undo

```bash
# Stop exposing the harness
tailscale serve reset

# Stop loading the plugin: delete the remote-web-ui block from
# ~/.dsh/profiles/web/cordis.patch.yml, then restart
dsh web

# Restore normal sleep behaviour
sudo pmset -c sleep 1
```

## Not done yet

- **No LaunchAgent.** `dsh web` does not come back by itself after a reboot; it
  must be started manually. This is the remaining gap in the always-on story.

## Related

- [[Reverse Proxy]] — why `trustedHosts` is needed at all
- [[NAT and NAT Traversal]] — why no port forwarding was needed on either end
- [[Port Binding and Publication]] — the loopback-versus-wildcard split in this setup
- [[Container Networking]] — how the published service ports actually work
- [[Secure Context]] — why the HTTPS upgrade changed what the phone can do
- [[Stack Inventory]] — full service and port list
- [[Current State]] — what is actually working
- [[FX Macro Platform]]
