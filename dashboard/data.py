"""Read-only Postgres access for the dashboard.

Mirrors the API/Metabase pattern (spec §11): the compute container connects
directly to the warehouse as `platform_reader`, which is SELECT-only on
`marts`/`meta`. No write path exists here.
"""
from __future__ import annotations

import os

import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

PG_HOST: str = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB: str = os.getenv("POSTGRES_DB", "warehouse")
READER_USER: str = os.getenv("PLATFORM_READER_USER", "platform_reader")
READER_PASSWORD: str = os.getenv("PLATFORM_READER_PASSWORD", "reader_dev")


def connect() -> psycopg.Connection:
    """Open a connection as the read-only warehouse role."""
    return psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        dbname=PG_DB,
        user=READER_USER,
        password=READER_PASSWORD,
    )


def _query_df(sql: str, params=None) -> pd.DataFrame:
    """Run a query and return the result as a DataFrame (no SQLAlchemy)."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


def load_catalog() -> pd.DataFrame:
    """Series catalog (dim_series), ordered by series_id."""
    return _query_df("SELECT * FROM marts.dim_series ORDER BY series_id")


def load_observations(series_id: str) -> pd.DataFrame:
    """Latest-vintage observations for one series, ascending by obs_date."""
    df = _query_df(
        """
        SELECT obs_date, value
        FROM marts.fct_macro_observation_latest
        WHERE series_id = %s
        ORDER BY obs_date
        """,
        [series_id],
    )
    if df.empty:
        return df
    df["obs_date"] = pd.to_datetime(df["obs_date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])
