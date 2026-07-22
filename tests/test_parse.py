from datetime import date, datetime, timezone

from ingest.parse import Observation, parse_response


def _payload() -> dict:
    return {
        "observations": [
            {"date": "2026-07-20", "value": "1.0805"},
            {"date": "2026-07-21", "value": "."},        # FRED missing marker
            {"date": "2026-07-22", "value": "1.0830"},
        ]
    }


def test_parse_response_shapes_and_missing_values():
    ts = datetime(2026, 7, 22, 6, 0, 0, tzinfo=timezone.utc)
    records = parse_response(
        _payload(),
        source="fred",
        series_id="DEXUSEU",
        fetch_timestamp=ts,
        raw_file="raw/fred/DEXUSEU/2026-07-22T06:00:00.000000Z.json",
    )

    assert len(records) == 3
    assert all(isinstance(r, Observation) for r in records)

    first = records[0]
    assert first.source == "fred"
    assert first.series_id == "DEXUSEU"
    assert first.reference_period == date(2026, 7, 20)
    assert first.value == 1.0805
    assert first.fetch_timestamp == ts

    # "." is a missing observation, not a parse error — it becomes None.
    assert records[1].value is None
    assert records[2].value == 1.0830


def test_parse_response_empty():
    ts = datetime(2026, 7, 22, tzinfo=timezone.utc)
    records = parse_response(
        {"observations": []},
        source="fred",
        series_id="DFF",
        fetch_timestamp=ts,
        raw_file="x.json",
    )
    assert records == []
