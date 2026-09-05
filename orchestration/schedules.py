"""Jobs and schedules (spec §8: one daily job covering all sources + dbt)."""
from __future__ import annotations

from dagster import AssetSelection, ScheduleDefinition, define_asset_job

macro_pipeline_job = define_asset_job(
    "macro_pipeline",
    selection=AssetSelection.all(),
    description="Ingest all sources then run the full dbt build.",
)

daily_schedule = ScheduleDefinition(
    job=macro_pipeline_job,
    cron_schedule="0 6 * * *",
    execution_timezone="Europe/Berlin",
    description="Daily 06:00 Europe/Berlin: ingest FRED/ECB/Bundesbank + dbt build.",
)
