"""Raw FRED JSON -> validated point-in-time observation records (Pydantic).

`parse_response` is pure and unit-tested; `parse_file` derives the vintage
metadata from the raw path layout raw/{source}/{series_id}/{fetch_ts}.json.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Observation(BaseModel):
    """One point-in-time record. reference_period, value, and fetch_timestamp
    are kept as distinct fields — never collapsed — so vintages stay correct."""

    model_config = ConfigDict(frozen=True)

    source: str
    series_id: str
    reference_period: date
    value: float | None
    fetch_timestamp: datetime
    raw_file: str


def _parse_value(raw: str | float | int | None) -> float | None:
    # FRED encodes a missing observation as ".".
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
    """Pure parser: a FRED observations payload -> validated records."""
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


def _fetch_ts_from_name(name: str) -> datetime:
    # Filename is the ISO fetch timestamp, e.g. 2026-07-22T06:00:03.123456Z.json
    stem = name[:-5] if name.endswith(".json") else name
    ts = datetime.fromisoformat(stem.replace("Z", "+00:00"))
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def parse_file(path: str | Path) -> list[Observation]:
    """Parse one raw file, deriving (source, series_id, fetch_timestamp) from
    its path: raw/{source}/{series_id}/{fetch_ts}.json"""
    path = Path(path)
    payload = json.loads(path.read_text())
    return parse_response(
        payload,
        source=path.parent.parent.name,
        series_id=path.parent.name,
        fetch_timestamp=_fetch_ts_from_name(path.name),
        raw_file=str(path),
    )
