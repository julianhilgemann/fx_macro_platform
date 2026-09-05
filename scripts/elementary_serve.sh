#!/usr/bin/env bash
# Generate the Elementary observability report and serve it on :8081.
# Regenerates on an interval so it stays fresh after pipeline runs.
set -uo pipefail

REPORT_DIR="${ELEMENTARY_REPORT_DIR:-/reports}"
REFRESH_SECONDS="${ELEMENTARY_REFRESH_SECONDS:-1800}"   # 30 min
mkdir -p "$REPORT_DIR"

generate() {
  if edr report \
       --project-dir /opt/app/dbt \
       --profiles-dir /opt/app/dbt \
       --file-path "$REPORT_DIR/index.html" >/dev/null 2>&1; then
    echo "[elementary] report generated -> $REPORT_DIR/index.html"
  else
    echo "[elementary] report generation failed (has the pipeline run at least once?)"
  fi
}

generate  # initial report on start

# background refresh loop
( while true; do sleep "$REFRESH_SECONDS"; generate; done ) &

echo "[elementary] serving on :8081 (refresh every ${REFRESH_SECONDS}s)"
exec python -m http.server 8081 --bind 0.0.0.0 --directory "$REPORT_DIR"
