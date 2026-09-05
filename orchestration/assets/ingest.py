"""Ingest assets — one per source (spec §8). Each fetches + archives its source's
series and lands rows in `raw.source_fetch`. A single series failure never raises."""
from dagster import AssetExecutionContext, asset

from ingest.load import land_source


@asset(description="Fetch and land FRED series in raw.source_fetch (spec §5, §8).")
def raw_fred(context: AssetExecutionContext) -> dict:
    stats = land_source("fred")
    context.add_output_metadata(stats)
    return stats


@asset(description="Fetch and land ECB SDW series in raw.source_fetch.")
def raw_ecb(context: AssetExecutionContext) -> dict:
    stats = land_source("ecb")
    context.add_output_metadata(stats)
    return stats


@asset(description="Fetch and land Bundesbank series in raw.source_fetch.")
def raw_bundesbank(context: AssetExecutionContext) -> dict:
    stats = land_source("bundesbank")
    context.add_output_metadata(stats)
    return stats
