"""Load raw JSON files into the DuckDB raw table. Dumb and re-runnable.

Idempotent on the point-in-time grain (source, series_id, reference_period,
fetch_timestamp): re-running never duplicates; new fetch timestamps append.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import polars as pl

from ingest.config import DUCKDB_PATH, RAW_DIR, RAW_TABLE
from ingest.parse import Observation, parse_file

DDL = f"""
CREATE TABLE IF NOT EXISTS {RAW_TABLE} (
    source            VARCHAR   NOT NULL,
    series_id         VARCHAR   NOT NULL,
    reference_period  DATE      NOT NULL,
    value             DOUBLE,
    fetch_timestamp   TIMESTAMP NOT NULL,
    raw_file          VARCHAR   NOT NULL,
    loaded_at         TIMESTAMP NOT NULL,
    PRIMARY KEY (source, series_id, reference_period, fetch_timestamp)
);
"""


def _records_to_df(records: list[Observation], loaded_at: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source": [r.source for r in records],
            "series_id": [r.series_id for r in records],
            "reference_period": [r.reference_period for r in records],
            "value": [r.value for r in records],
            # DuckDB TIMESTAMP is naive; store UTC wall-clock.
            "fetch_timestamp": [r.fetch_timestamp.replace(tzinfo=None) for r in records],
            "raw_file": [r.raw_file for r in records],
            "loaded_at": [loaded_at for _ in records],
        },
        schema={
            "source": pl.Utf8,
            "series_id": pl.Utf8,
            "reference_period": pl.Date,
            "value": pl.Float64,
            "fetch_timestamp": pl.Datetime("us"),
            "raw_file": pl.Utf8,
            "loaded_at": pl.Datetime("us"),
        },
    )


def run() -> int:
    files = sorted(RAW_DIR.rglob("*.json"))
    records: list[Observation] = []
    for f in files:
        records.extend(parse_file(f))

    if not records:
        print("[load] no raw records found — run the fetch step first")
        return 0

    loaded_at = datetime.now(timezone.utc).replace(tzinfo=None)
    incoming = _records_to_df(records, loaded_at)

    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    try:
        con.execute(DDL)
        before = con.execute(f"SELECT count(*) FROM {RAW_TABLE}").fetchone()[0]
        con.register("incoming", incoming)
        # INSERT OR IGNORE => existing grains skipped, new vintages appended.
        con.execute(
            f"""
            INSERT OR IGNORE INTO {RAW_TABLE}
            SELECT source, series_id, reference_period, value,
                   fetch_timestamp, raw_file, loaded_at
            FROM incoming
            """
        )
        after = con.execute(f"SELECT count(*) FROM {RAW_TABLE}").fetchone()[0]
    finally:
        con.close()

    print(f"[load] parsed {len(records)} records from {len(files)} raw files")
    print(f"[load] {RAW_TABLE}: {before} -> {after} rows (+{after - before} new)")
    return after - before


def main() -> None:
    run()


if __name__ == "__main__":
    main()
