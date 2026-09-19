---
title: Secure Context
type: concept
status: seedling
tags: [web, security, tls, browsers]
created: 2026-09-19
updated: 2026-09-19
aliases: [Secure Contexts, Trustworthy Origin]
---

# Secure Context

A browser guarantee that a page was delivered over an authenticated, encrypted
transport. A page either has one or does not, and a large set of powerful browser
APIs exist only when it does.

## Why it matters
- Some capabilities are not merely discouraged over plain HTTP, they are absent.
  A page can be perfectly reachable and still lack the feature you built the
  page for, which makes the failure look like an application bug rather than a
  transport problem.
- It is the difference between a web page and an app-like experience: offline
  caching, background behaviour and installability all sit behind this gate.
- Reachability and capability are separate questions. Solving the first — a
  working URL — does not imply the second.

## How it works

A page is in a secure context when it is loaded over `https://` with a
certificate the browser accepts, or from a genuinely local origin such as
`localhost` or `127.0.0.1`. Plain `http://` to a LAN address, a tailnet address or
a tunnel hostname does **not** qualify: the address being private to you is not
what the browser checks.

Capabilities gated on it include service workers (and therefore offline caching
and progressive-web-app behaviour), `crypto.subtle`, geolocation, and clipboard
access. A certificate warning is not a secure context either — self-signed
certificates count as untrusted until explicitly installed as trusted, which on a
phone is awkward enough to be worth avoiding.

## In this platform
This is why the HTTP-to-HTTPS upgrade of the tailnet endpoint was more than
tidiness. `tailscale serve --https` obtains a real, publicly trusted certificate
for the `*.ts.net` name, so a phone opening the DSH interface gets a genuine
secure context over a private network.

The concrete consequence: the remote-access plugin's reopen service worker
registers, so a page opened from a bookmark or restored from history returns
straight into the application. Over plain HTTP that worker never registers, and
every reopen lands on the harness authentication failure instead — meaning a
fresh QR scan each time. The same network path, a materially different tool.

## Related
- [[TLS]]
- [[Tailscale]]
- [[Remote Access]]
- [[Reverse Proxy]]
