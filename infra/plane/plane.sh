#!/usr/bin/env bash
# Manage the local, isolated Plane Community Edition stack for fx_macro_platform.
#
# Why this wrapper exists rather than a plain `docker compose` call:
#   1. This machine's ~/.docker/config.json sets `credsStore: "desktop"`, and the
#      docker-credential-desktop helper fails with "A Module Directory Service
#      error has occurred". Every pull therefore aborts before it starts. All the
#      images this stack needs are public, so we point DOCKER_CONFIG at a minimal
#      config with no credential helper. Your global Docker config is untouched.
#   2. The stack lives in its own compose project (`plane`) with its own network
#      and named volumes, so it cannot entangle the fx_macro_platform services.
#   3. The env file is `plane.env`, not compose's default `.env`, so it must be
#      passed explicitly every time.
#
# Usage:
#   ./plane.sh up          # pull (if needed) and start, in the background
#   ./plane.sh stop        # stop containers, keep data
#   ./plane.sh down        # remove containers, keep named volumes/data
#   ./plane.sh destroy     # remove containers AND volumes (deletes all Plane data)
#   ./plane.sh ps          # container status
#   ./plane.sh logs [svc]  # follow logs (all services, or one)
#   ./plane.sh pull        # pull the pinned images
#   ./plane.sh url         # print the web UI and API base URLs
#   ./plane.sh health      # poll the API until it answers
#   ./plane.sh config      # validate the composed config
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="plane"
ENV_FILE="$HERE/plane.env"
COMPOSE_FILE="$HERE/docker-compose.yml"
# Local layer over the vendored file (repoints the MinIO image; see the file).
OVERRIDE_FILE="$HERE/docker-compose.override.yml"

# Isolated Docker client config: public images only, no credential helper.
export DOCKER_CONFIG="$HERE/.docker"
mkdir -p "$DOCKER_CONFIG"
if [[ ! -f "$DOCKER_CONFIG/config.json" ]]; then
  printf '{\n  "auths": {}\n}\n' >"$DOCKER_CONFIG/config.json"
fi

# DOCKER_CONFIG also relocates the CLI-plugin search path, which would hide
# `docker compose` itself (it ships as a plugin in ~/.docker/cli-plugins). Link
# the real plugin directory back in so compose stays available.
if [[ ! -e "$DOCKER_CONFIG/cli-plugins" && -d "$HOME/.docker/cli-plugins" ]]; then
  ln -s "$HOME/.docker/cli-plugins" "$DOCKER_CONFIG/cli-plugins"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found." >&2
  echo "Copy variables.env.reference to plane.env and fill in the secrets." >&2
  exit 1
fi

# shellcheck disable=SC1090
HTTP_PORT="$(grep -E '^LISTEN_HTTP_PORT=' "$ENV_FILE" | cut -d= -f2)"
HTTP_PORT="${HTTP_PORT:-8085}"

compose() {
  if [[ -f "$OVERRIDE_FILE" ]]; then
    docker compose -p "$PROJECT" --env-file "$ENV_FILE" \
      -f "$COMPOSE_FILE" -f "$OVERRIDE_FILE" "$@"
  else
    docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  fi
}

# Fetch every image this stack references using `docker pull`, which honours the
# credential-free DOCKER_CONFIG. `docker compose pull` does NOT: the compose
# plugin still calls the broken docker-credential-desktop helper and aborts, so
# we never let compose do the pulling (see `up`, which passes --pull never).
pull_images() {
  local imgs total i=0 img
  imgs="$(compose config --images | sort -u | sed '/^$/d')"
  total="$(printf '%s\n' "$imgs" | wc -l | tr -d ' ')"
  while IFS= read -r img; do
    [[ -z "$img" ]] && continue
    i=$((i + 1))
    echo "[$i/$total] pulling $img"
    docker pull "$img"
  done <<<"$imgs"
}

case "${1:-}" in
  up)
    shift
    pull_images
    # --pull never: images are already local, and this keeps compose away from
    # the registry (and therefore away from the credential helper).
    compose up -d --pull never "$@"
    echo
    echo "Plane starting. Web UI:  http://localhost:$HTTP_PORT"
    echo "API base:               http://localhost:$HTTP_PORT/api/v1/"
    echo "First run runs DB migrations; give it 60-90s, then: $0 health"
    ;;
  stop)    shift; compose stop "$@" ;;
  start)   shift; compose start "$@" ;;
  down)    shift; compose down "$@" ;;
  destroy)
    echo "This deletes containers AND all Plane named volumes (all workspaces, issues, uploads)."
    read -r -p "Type 'yes' to continue: " reply
    [[ "$reply" == "yes" ]] || { echo "aborted"; exit 1; }
    compose down -v
    ;;
  ps|status)  shift; compose ps "$@" ;;
  logs)       shift; compose logs -f --tail=100 "$@" ;;
  pull)       shift; pull_images "$@" ;;
  restart)    shift; compose restart "$@" ;;
  config)     shift; compose config "$@" >/dev/null && echo "compose config valid" ;;
  url)
    echo "web:  http://localhost:$HTTP_PORT"
    echo "api:  http://localhost:$HTTP_PORT/api/v1/"
    ;;
  health)
    echo -n "waiting for Plane API on http://localhost:$HTTP_PORT"
    for i in $(seq 1 60); do
      code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:$HTTP_PORT/api/v1/" || true)"
      if [[ "$code" =~ ^(200|401|403|404)$ ]]; then
        echo " -> up (HTTP $code)"
        exit 0
      fi
      echo -n "."
      sleep 5
    done
    echo " -> timed out after 5 minutes"
    echo "Check: $0 ps  &&  $0 logs"
    exit 1
    ;;
  *)
    sed -n '2,25p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
