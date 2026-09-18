---
title: Reverse Proxy
type: concept
status: seedling
tags: [networking, http, infrastructure]
created: 2026-09-18
updated: 2026-09-18
aliases: [Reverse Proxy Server, Edge Proxy]
---

# Reverse Proxy

A reverse proxy is a server that accepts client requests and forwards them to one or more upstream services on the client's behalf.

## Why it matters
- It gives the platform one public entry point, so clients never need to know internal ports or topology.
- TLS termination, compression, caching, and rate limiting happen once at the edge instead of in every service.
- Access logs and request metrics collect in one place, which makes observability and abuse response far simpler.
- Upstreams can restart or be replaced without clients noticing, if the proxy serves maintenance or retries.

## How it works
The proxy accepts the client connection, picks an upstream, and opens a separate connection to it, forwarding method, path, headers, and body. Because the upstream sees the proxy as the client, the proxy must pass along the origin details:

```nginx
location /api/ {
  proxy_pass http://fastapi:8000/;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
  proxy_set_header Host $host;
}
```

Without those headers, FastAPI logs the proxy's address and builds wrong absolute URLs.

## In this platform
Not used as a proxy yet. Each tool on the dev machine is reached on its own published port, and the browser talks straight to Streamlit, Metabase, or FastAPI. Note that nginx is already in the stack, but only as `launchpad`, a static navigation hub on port 8080 that links to the other services; it forwards nothing. The planned API gateway in front of the public API is exactly the reverse proxy step, and on Hetzner with K3s an ingress controller will play the same role for the whole platform.

## Related
- [[Load Balancing]]
- [[TLS]]
- [[DNS]]
- [[OWASP Top 10]]

## Further reading
- [nginx: Reverse Proxy guide](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/)
- [MDN: Proxy servers and tunneling](https://developer.mozilla.org/en-US/docs/Web/HTTP/Proxy_servers_and_tunneling)
