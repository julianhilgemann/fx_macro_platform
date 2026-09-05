#!/bin/bash
# M0 bootstrap — runs once, on first pgdata volume init (docker-entrypoint-initdb.d).
#
# Creates the roles, databases, schemas and the raw landing table described in
# platform-spec.md §4–§5. Passwords come from the postgres container's
# environment (compose injects them from .env); they are never hardcoded here.
# Dev defaults keep `make up` zero-config.
set -euo pipefail

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER:-postgres}" \
  --dbname "${POSTGRES_DB:-warehouse}" <<-EOSQL
    -- Roles (spec §4). platform_writer = Dagster/dbt; platform_reader = API/BI.
    CREATE ROLE platform_writer LOGIN PASSWORD '${PLATFORM_WRITER_PASSWORD:-writer_dev}';
    CREATE ROLE platform_reader LOGIN PASSWORD '${PLATFORM_READER_PASSWORD:-reader_dev}';

    -- Three databases on one instance (spec §4). warehouse = POSTGRES_DB.
    CREATE DATABASE dagster;
    CREATE DATABASE cms;

    -- Schemas inside warehouse (spec §4).
    CREATE SCHEMA raw;
    CREATE SCHEMA staging;
    CREATE SCHEMA intermediate;
    CREATE SCHEMA marts;
    CREATE SCHEMA meta;
    CREATE SCHEMA elementary;

    -- Raw landing contract (spec §5). Append-only; never UPDATE/DELETE.
    CREATE TABLE raw.source_fetch (
      fetch_id        bigserial PRIMARY KEY,
      source          text        NOT NULL,     -- 'fred' | 'ecb' | 'bundesbank'
      resource        text        NOT NULL,     -- series id or SDMX key
      request_url     text        NOT NULL,
      request_params  jsonb       NOT NULL DEFAULT '{}',
      fetched_at      timestamptz NOT NULL DEFAULT now(),
      http_status     int         NOT NULL,
      content_type    text,
      payload         jsonb,                    -- parsed-to-JSON body
      payload_raw     bytea,                    -- original bytes (XML, CSV)
      payload_sha256  text        NOT NULL,
      dagster_run_id  text
    );
    CREATE INDEX source_fetch_source_resource_fetched_idx
      ON raw.source_fetch (source, resource, fetched_at DESC);
    CREATE INDEX source_fetch_sha256_idx
      ON raw.source_fetch (payload_sha256);

    -- Grants (spec §4).
    GRANT CONNECT ON DATABASE warehouse, dagster, cms TO platform_writer;
    GRANT CONNECT ON DATABASE warehouse TO platform_reader;

    GRANT USAGE, CREATE
      ON SCHEMA raw, staging, intermediate, marts, meta, elementary
      TO platform_writer;
    -- raw.source_fetch is owned by the bootstrap superuser; the writer needs
    -- explicit rights to land rows in it (and to use its bigserial sequence).
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA raw TO platform_writer;
    GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw TO platform_writer;

    -- The reader is SELECT-only on the served schemas (spec §4 — the backstop).
    GRANT USAGE ON SCHEMA marts, meta, elementary TO platform_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA marts, meta, elementary TO platform_reader;

    -- Future dbt tables (created by platform_writer) auto-readable by the reader.
    ALTER DEFAULT PRIVILEGES FOR ROLE platform_writer
      IN SCHEMA marts, meta, elementary
      GRANT SELECT ON TABLES TO platform_reader;
EOSQL

# Dagster metadata DB (spec §4): let platform_writer create run/event/schedule
# tables there. (PG15+ revokes CREATE on public from everyone by default.)
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname dagster <<-EOSQL
    GRANT CREATE ON SCHEMA public TO platform_writer;
EOSQL

echo "[init] M0 complete: roles, databases, schemas, raw.source_fetch"
