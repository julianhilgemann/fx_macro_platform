"""Dagster Definitions (spec §8)."""
from __future__ import annotations

from dagster import Definitions

from orchestration.assets.dbt import dbt_resource, fx_macro_dbt_assets
from orchestration.assets.ingest import raw_bundesbank, raw_ecb, raw_fred
from orchestration.jobs import full_refresh_job, refresh_series_job
from orchestration.schedules import daily_schedule, macro_pipeline_job

defs = Definitions(
    assets=[raw_fred, raw_ecb, raw_bundesbank, fx_macro_dbt_assets],
    resources={"dbt": dbt_resource},
    # macro_pipeline: the scheduled full run.
    # full_refresh / refresh_series: on-demand triggers from the Data Ops UI and
    # the owner-only API router (spec §10).
    jobs=[macro_pipeline_job, full_refresh_job, refresh_series_job],
    schedules=[daily_schedule],
)
