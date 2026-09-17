"""On-demand jobs triggered from the Data Ops UI / owner-only API (spec §8, §10).

Two extra jobs alongside the scheduled ``macro_pipeline``:

* ``refresh_series_job`` — one series: fetch → dedicated dbt transform. The
  selective, interactive path ("give me the newest version of *this* series");
* ``full_refresh_job`` — every source ingested, then the full dbt build, on
  demand and regardless of the 06:00 schedule.

Both are ordinary Dagster jobs, so they are visible and re-runnable from the
Dagster UI (:3000) exactly like the scheduled run — with per-step logs.
"""
from dagster import AssetSelection, define_asset_job, job

from orchestration.assets.dbt import dbt_resource
from orchestration.ops import dbt_refresh_marts, ingest_one_series

#: The "refresh everything" action: every ingest asset plus the whole dbt graph.
#: Same selection as the scheduled run, but on demand and separately recorded.
full_refresh_job = define_asset_job(
    "full_refresh",
    selection=AssetSelection.all(),
    description="Manual full refresh: ingest all sources then run the full dbt build.",
)


@job(
    resource_defs={"dbt": dbt_resource},
    description="Refresh ONE series: fetch it into raw.source_fetch, then run the "
                "dedicated dbt transform chain so it is visible in the marts.",
)
def refresh_series_job():
    # ingest_one_series returns {series_id, source, ...}; dbt_refresh_marts uses
    # the source to pick the right staging model and its downstream graph.
    dbt_refresh_marts(ingest_one_series())
