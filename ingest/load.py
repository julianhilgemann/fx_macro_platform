"""Ingest orchestrator: fetch -> verbatim archive -> raw.source_fetch (Postgres).

One row per *fetch event* per series (spec §5), byte-faithful with a sha256.
Per-series fault tolerance: a failed fetch is recorded (http_status, null
payload) rather than aborting the whole run (spec §8). Parsing to JSON happens
at this boundary; the byte-faithful original is carried in `payload_raw`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from ingest.config import (
    BUNDESBANK_BASE_URL,
    ECB_SDW_BASE_URL,
    FETCH_MODE,
    FRED_BASE_URL,
    PG_DB,
    PG_HOST,
    PG_PORT,
    RAW_DIR,
    RAW_TABLE,
    SERIES,
    WRITER_PASSWORD,
    WRITER_USER,
)
from ingest.fetch import FetchResult, fetch_series
from ingest.parse import parse_bundesbank_csv, parse_ecb_sdmx_csv

_BASE_URLS = {"fred": FRED_BASE_URL, "bundesbank": BUNDESBANK_BASE_URL, "ecb": ECB_SDW_BASE_URL}

INSERT_SQL = f"""
INSERT INTO {RAW_TABLE}
    (source, resource, request_url, request_params, fetched_at,
     http_status, content_type, payload, payload_raw, payload_sha256, dagster_run_id)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _normalize_payload(res: FetchResult) -> dict | None:
    """Parsed-to-JSON body for `payload`. FRED is already JSON; CSV sources are
    converted at the client boundary to a uniform `{"observations": [...]}`."""
    if res.ext == "json":
        try:
            return json.loads(res.body.decode("utf-8"))
        except Exception:
            return None
    text = res.body.decode("utf-8", errors="replace")
    ts = datetime.now(timezone.utc)
    if res.source == "bundesbank":
        records = parse_bundesbank_csv(text, source=res.source, series_id=res.resource, fetch_timestamp=ts, raw_file="")
    elif res.source == "ecb":
        records = parse_ecb_sdmx_csv(text, source=res.source, series_id=res.resource, fetch_timestamp=ts, raw_file="")
    else:
        records = []
    return {
        "observations": [
            {"date": r.reference_period.isoformat(),
             "value": None if r.value is None else str(r.value)}
            for r in records
        ]
    }


def _archive(res: FetchResult, fetch_ts: datetime) -> Path:
    ts = fetch_ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    path = RAW_DIR / res.source / res.resource / f"{ts}.{res.ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(res.body)
    return path


def run() -> dict:
    fetch_ts = datetime.now(timezone.utc)
    as_of = fetch_ts.date()
    rows: list[tuple] = []
    ok = failed = 0
    for series in SERIES:
        try:
            res = fetch_series(series, as_of)
            _archive(res, fetch_ts)
            payload = _normalize_payload(res)
            rows.append((
                res.source, res.resource, res.request_url,
                Jsonb(res.request_params), fetch_ts,
                res.http_status, res.content_type,
                Jsonb(payload) if payload is not None else None,
                res.body, _sha256(res.body), None,
            ))
            ok += 1
            print(f"  {series.series_id:9s} [{series.source:10s}] {res.http_status}  {len(res.body)} bytes")
        except Exception as exc:
            failed += 1
            status = getattr(getattr(exc, "response", None), "status_code", None) or 0
            rows.append((
                series.source, series.series_id, _BASE_URLS.get(series.source, ""),
                Jsonb({}), fetch_ts, status, None, None, None, _sha256(b""), None,
            ))
            print(f"  FAIL {series.series_id:9s} [{series.source:10s}] {exc}")

    landed = 0
    if rows:
        with psycopg.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB,
                             user=WRITER_USER, password=WRITER_PASSWORD) as conn:
            with conn.cursor() as cur:
                cur.executemany(INSERT_SQL, rows)
        landed = len(rows)
    print(f"[ingest] mode={FETCH_MODE}  {ok} ok, {failed} failed, {landed} rows -> {RAW_TABLE}")
    return {"ok": ok, "failed": failed, "landed": landed}


def main() -> None:
    run()


if __name__ == "__main__":
    main()
