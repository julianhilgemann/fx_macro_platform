from datetime import date, datetime, timezone

from ingest.parse import Observation, parse_bundesbank_csv, parse_response


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
        series_id="FEDFUNDS",
        fetch_timestamp=ts,
        raw_file="x.json",
    )
    assert records == []


# A trimmed real Bundesbank BBSSY CSV: metadata header rows, then data rows,
# with "." for a missing observation.
_BBK_CSV = (
    '"",BBSSY.D.REN.EUR.A610.000000WT0202.A,BBSSY.D.REN.EUR.A610.000000WT0202.A_FLAGS\n'
    '"",Daily yield of the current (two-year) Federal Treasury notes,\n'
    "Decimals,2,\n"
    "unit,PROZENT,\n"
    "2014-01-02,0.21,\n"
    "2014-01-04,.,No value available\n"
    "2026-07-22,2.81,\n"
)


def test_parse_bundesbank_csv_skips_headers_and_missing():
    ts = datetime(2026, 7, 22, 6, 0, 0, tzinfo=timezone.utc)
    records = parse_bundesbank_csv(
        _BBK_CSV,
        source="bundesbank",
        series_id="DE2Y",
        fetch_timestamp=ts,
        raw_file="raw/bundesbank/DE2Y/2026-07-22T06:00:00.000000Z.csv",
    )

    # Only the 3 date-led rows become records; metadata rows are skipped.
    assert len(records) == 3
    assert all(isinstance(r, Observation) for r in records)
    assert records[0].source == "bundesbank"
    assert records[0].reference_period == date(2014, 1, 2)
    assert records[0].value == 0.21
    assert records[1].value is None            # "." -> missing
    assert records[2].reference_period == date(2026, 7, 22)
    assert records[2].value == 2.81
