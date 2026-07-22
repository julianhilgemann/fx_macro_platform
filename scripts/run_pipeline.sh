#!/usr/bin/env bash
# The cron target: fetch -> load -> dbt run -> dbt test.
# Ingestion is plain Python; dbt only transforms the already-landed raw table.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Load .env (gitignored) if present, so FRED_API_KEY / FX_FETCH_MODE take effect.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi

# Single source of truth for the DuckDB file — loader and dbt must agree.
export DUCKDB_PATH="${DUCKDB_PATH:-$REPO_ROOT/warehouse/fx_macro.duckdb}"
mkdir -p "$(dirname "$DUCKDB_PATH")" raw

echo "==> [1/4] fetch (mode=${FX_FETCH_MODE:-auto})"
uv run python -m ingest.fetch

echo "==> [2/4] load"
uv run python -m ingest.load

echo "==> [3/4] dbt run"
uv run dbt run --project-dir dbt --profiles-dir dbt

echo "==> [4/4] dbt test"
uv run dbt test --project-dir dbt --profiles-dir dbt

echo "==> pipeline complete. warehouse: $DUCKDB_PATH"
