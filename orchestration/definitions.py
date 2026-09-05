"""Dagster Definitions (spec §8)."""
from __future__ import annotations

from dagster import Definitions

from orchestration.assets.dbt import dbt_resource, fx_macro_dbt_assets
from orchestration.assets.ingest import raw_bundesbank, raw_ecb, raw_fred
from orchestration.schedules import daily_schedule, macro_pipeline_job

defs = Definitions(
    assets=[raw_fred, raw_ecb, raw_bundesbank, fx_macro_dbt_assets],
    resources={"dbt": dbt_resource},
    jobs=[macro_pipeline_job],
    schedules=[daily_schedule],
)
