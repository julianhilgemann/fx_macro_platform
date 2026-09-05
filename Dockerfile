# Single image for dagster-webserver, dagster-daemon, and the FastAPI service.
# (Spec §2 splits platform-dagster/platform-api; the api image can drop
# dagster/dbt later to shrink. Multi-arch: builds linux/arm64 on M-series.)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /opt/app

# 1) Dependencies only (layer-cached until pyproject/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Source + project install (editable)
COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/opt/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/opt/app/.venv" \
    PYTHONUNBUFFERED=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

# 3) dbt packages (elementary) + manifest that @dbt_assets reads
RUN cd dbt && dbt deps --profiles-dir . && dbt parse --profiles-dir .

EXPOSE 3000 8000

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000"]
