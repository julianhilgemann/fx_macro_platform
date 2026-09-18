#!/usr/bin/env bash
# stdio entry point for the official GitHub MCP server, launched by the DSH
# harness as an MCP tool server and exposed to the model as mcp__github__<tool>.
#
# Design notes:
#   * Uses the official prebuilt Darwin arm64 binary rather than the Docker
#     image, so there is no container and no long-lived process — the server
#     exists only for the lifetime of the MCP connection.
#   * The binary is downloaded once into the gitignored .dsh-cache/ and its
#     SHA-256 is verified against the release checksum file before use.
#   * The token is read from infra/github/.token (or GH_TOKEN) at run time, so
#     no secret is ever stored in the harness profile config, and the admin
#     password-style sprawl we had with Plane is avoided.
#
# Toolsets: `labels` and `projects` are NOT in the server's default set, so they
# are enabled explicitly — without `projects` the Projects v2 board and roadmap
# are unreachable. Override with GITHUB_MCP_TOOLSETS if you want more or less.
set -euo pipefail

export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/../.." && pwd)"
TOKEN_FILE="$HERE/.token"

# --- credential ------------------------------------------------------------ #
if [[ -n "${GH_TOKEN:-}" ]]; then
  TOKEN="$GH_TOKEN"
elif [[ -s "$TOKEN_FILE" ]]; then
  TOKEN="$(tr -d '[:space:]' <"$TOKEN_FILE")"
else
  echo "github-mcp-stdio: no credential." >&2
  echo "  Save a fine-grained PAT to $TOKEN_FILE (Issues: RW, Projects: RW)" >&2
  echo "  or export GH_TOKEN." >&2
  exit 1
fi
export GITHUB_PERSONAL_ACCESS_TOKEN="$TOKEN"

# --- binary (cached, checksum-verified) ------------------------------------ #
CACHE="$PROJECT_ROOT/.dsh-cache/github-mcp"
BIN="$CACHE/bin/github-mcp-server"
VERSION="${GITHUB_MCP_VERSION:-v1.12.2}"
ASSET="github-mcp-server_Darwin_arm64.tar.gz"

if [[ ! -x "$BIN" ]]; then
  mkdir -p "$CACHE/bin"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  base="https://github.com/github/github-mcp-server/releases/download/$VERSION"
  echo "github-mcp-stdio: fetching $VERSION ($ASSET)" >&2
  curl -fsSL -o "$tmp/$ASSET" "$base/$ASSET"
  curl -fsSL -o "$tmp/sums.txt" "$base/github-mcp-server_${VERSION#v}_checksums.txt"
  expected="$(grep -F "$ASSET" "$tmp/sums.txt" | awk '{print $1}')"
  actual="$(shasum -a 256 "$tmp/$ASSET" | awk '{print $1}')"
  if [[ -z "$expected" || "$expected" != "$actual" ]]; then
    echo "github-mcp-stdio: checksum mismatch, refusing to use the download." >&2
    exit 1
  fi
  tar xzf "$tmp/$ASSET" -C "$tmp"
  mv "$tmp/github-mcp-server" "$BIN"
  chmod +x "$BIN"
  echo "github-mcp-stdio: cached $VERSION at $BIN" >&2
fi

TOOLSETS="${GITHUB_MCP_TOOLSETS:-default,labels,projects}"
exec "$BIN" stdio --toolsets="$TOOLSETS" "$@"
