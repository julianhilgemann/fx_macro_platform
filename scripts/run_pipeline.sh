#!/usr/bin/env bash
# The pipeline: ingest (fetch -> raw.source_fetch) -> dbt seed -> dbt run -> dbt test.
# Ingestion is plain Python; dbt only transforms the already-landed raw table.
# (Dagster replaces this script at M1+; spec §8.)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Load .env (gitignored) if present, so FRED_API_KEY / FX_FETCH_MODE / Postgres vars take effect.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

echo "==> [1/4] ingest (fetch -> raw.source_fetch, mode=${FX_FETCH_MODE:-auto})"
uv run python -m ingest.load

echo "==> [2/4] dbt seed (series catalog)"
uv run dbt seed --project-dir dbt --profiles-dir dbt

echo "==> [3/4] dbt run"
uv run dbt run --project-dir dbt --profiles-dir dbt

echo "==> [4/4] dbt test"
uv run dbt test --project-dir dbt --profiles-dir dbt

echo "==> pipeline complete."
