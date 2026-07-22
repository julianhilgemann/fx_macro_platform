"""Raw response bodies -> validated point-in-time observation records (Pydantic).

Multi-source: FRED lands JSON, Bundesbank lands CSV. `parse_file` dispatches on
the raw file's extension; each source's pure parser is unit-tested. reference_period,
value, and fetch_timestamp are kept distinct so vintages stay correct.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Observation(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    series_id: str
    reference_period: date
    value: float | None
    fetch_timestamp: datetime
    raw_file: str


def _parse_value(raw: str | float | int | None) -> float | None:
    # Both FRED and Bundesbank encode a missing observation as ".".
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = raw.strip()
    if s in ("", "."):
        return None
    return float(s)


def parse_response(
    payload: dict,
    *,
    source: str,
    series_id: str,
    fetch_timestamp: datetime,
    raw_file: str,
) -> list[Observation]:
    """Pure parser: a FRED observations payload (dict) -> validated records."""
    records: list[Observation] = []
    for obs in payload.get("observations", []):
        records.append(
            Observation(
                source=source,
                series_id=series_id,
                reference_period=date.fromisoformat(obs["date"]),
                value=_parse_value(obs.get("value")),
                fetch_timestamp=fetch_timestamp,
                raw_file=raw_file,
            )
        )
    return records


def parse_bundesbank_csv(
    text: str,
    *,
    source: str,
    series_id: str,
    fetch_timestamp: datetime,
    raw_file: str,
) -> list[Observation]:
    """Pure parser: a Bundesbank BBSSY CSV body -> validated records.

    The file has metadata header rows (Comment, Decimals, ...) followed by
    `YYYY-MM-DD,value[,flag]` rows; missing values are ".". Data rows are the
    ones whose first column is an ISO date, so header rows are skipped naturally.
    """
    records: list[Observation] = []
    for row in csv.reader(io.StringIO(text)):
        if not row or not _ISO_DATE.match(row[0].strip()):
            continue
        records.append(
            Observation(
                source=source,
                series_id=series_id,
                reference_period=date.fromisoformat(row[0].strip()),
                value=_parse_value(row[1] if len(row) > 1 else None),
                fetch_timestamp=fetch_timestamp,
                raw_file=raw_file,
            )
        )
    return records


def parse_ecb_sdmx_csv(
    text: str,
    *,
    source: str,
    series_id: str,
    fetch_timestamp: datetime,
    raw_file: str,
) -> list[Observation]:
    """Pure parser: an ECB Data Portal (SDW) `csvdata` body -> validated records.

    Wide SDMX CSV with a header row; the observation columns are TIME_PERIOD and
    OBS_VALUE. Key ECB rate series are change-point (one row per rate change) —
    the daily panel forward-fills them into step functions.
    """
    records: list[Observation] = []
    for row in csv.DictReader(io.StringIO(text)):
        period = (row.get("TIME_PERIOD") or "").strip()
        if not _ISO_DATE.match(period):
            continue
        records.append(
            Observation(
                source=source,
                series_id=series_id,
                reference_period=date.fromisoformat(period),
                value=_parse_value(row.get("OBS_VALUE")),
                fetch_timestamp=fetch_timestamp,
                raw_file=raw_file,
            )
        )
    return records


def _fetch_ts_from_name(name: str) -> datetime:
    # Filename is the ISO fetch timestamp, e.g. 2026-07-22T06:00:03.123456Z.json
    stem = name.rsplit(".", 1)[0]
    ts = datetime.fromisoformat(stem.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def parse_file(path: str | Path) -> list[Observation]:
    """Parse one raw file, deriving (source, series_id, fetch_timestamp) from its
    path raw/{source}/{series_id}/{fetch_ts}.{ext} and the parser from {ext}."""
    path = Path(path)
    meta = dict(
        source=path.parent.parent.name,
        series_id=path.parent.name,
        fetch_timestamp=_fetch_ts_from_name(path.name),
        raw_file=str(path),
    )
    text = path.read_text()
    # .json is always FRED-shaped (real FRED and the synthetic generator).
    if path.suffix == ".json":
        return parse_response(json.loads(text), **meta)
    # .csv formats differ by provider, so dispatch on source.
    if path.suffix == ".csv":
        if meta["source"] == "bundesbank":
            return parse_bundesbank_csv(text, **meta)
        if meta["source"] == "ecb":
            return parse_ecb_sdmx_csv(text, **meta)
    raise ValueError(f"no parser for source '{meta['source']}' file {path}")
