#!/usr/bin/env bash
# stdio entry point for Plane's official MCP server (plane-mcp-server), launched
# by the DSH harness as an MCP tool server and exposed to the model as tools
# named mcp__plane__<tool>.
#
# Design notes:
#   * The API token is read from the gitignored .credentials.local beside this
#     script, so no secret is embedded in the harness profile config. Only the
#     three variables the MCP server needs are exported — notably NOT the admin
#     password, which stays out of the child process environment.
#   * uv's cache, tool and interpreter directories are pinned inside the project
#     (gitignored) so the launcher writes nothing to the user's global ~/.cache
#     or ~/.local/share, and keeps working under a restricted file sandbox.
#   * PATH is set defensively because MCP servers are spawned with a scrubbed
#     ambient environment.
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/../.." && pwd)"
CREDS="$HERE/.credentials.local"

if [[ ! -f "$CREDS" ]]; then
  echo "plane-mcp-stdio: missing $CREDS" >&2
  echo "Run the bootstrap in infra/plane/README.md to generate credentials." >&2
  exit 1
fi

# Read individual keys rather than sourcing, so the password never enters this
# process's exported environment.
cred() { grep -E "^$1=" "$CREDS" | head -1 | cut -d= -f2-; }

PLANE_API_KEY="$(cred API_KEY)"
PLANE_WORKSPACE_SLUG="$(cred WORKSPACE_SLUG)"
PLANE_BASE_URL="$(cred WEB_URL)"
export PLANE_API_KEY PLANE_WORKSPACE_SLUG PLANE_BASE_URL

if [[ -z "$PLANE_API_KEY" ]]; then
  echo "plane-mcp-stdio: API_KEY is empty in $CREDS" >&2
  exit 1
fi

CACHE_ROOT="$PROJECT_ROOT/.dsh-cache/plane-mcp"
export UV_CACHE_DIR="$CACHE_ROOT/uv"
export UV_PYTHON_INSTALL_DIR="$CACHE_ROOT/python"
export UV_TOOL_DIR="$CACHE_ROOT/tools"
export UV_TOOL_BIN_DIR="$CACHE_ROOT/bin"

UVX="${UVX:-/Users/admin/.local/bin/uvx}"
if [[ ! -x "$UVX" ]]; then
  UVX="$(command -v uvx || true)"
fi
if [[ -z "$UVX" ]]; then
  echo "plane-mcp-stdio: uvx not found; install uv (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

exec "$UVX" plane-mcp-server stdio
