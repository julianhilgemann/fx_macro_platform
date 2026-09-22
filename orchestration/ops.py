"""Ops backing the on-demand refresh jobs (spec §8, §10 owner-only triggers).

Three things the daily schedule does not cover, all driven from the UI/API:

* ``ingest_one_series`` — fetch + land exactly one series (the selective path);
* ``dbt_refresh_marts`` — the dedicated dbt transform for a single-series
  refresh: re-materialise the staging → intermediate → marts chain that reads
  ``raw.source_fetch``, so a fresh raw row is visible in the API/BI layer;
* ``dbt_build_all`` — the full dbt build, for the "refresh everything" path.

**Why ``package:elementary`` is in the selection.** Elementary's ``on-run-end``
``upload_dbt_artifacts()`` hook fails to compile under a partial ``--select``
whose graph contains no elementary node (``'get_upload_artifact_method' is
undefined``). Including the elementary package in the same selector makes the
hook compile, so a selective build succeeds instead of reporting a false
failure after the data already loaded. See ``agents/notes.md``.
"""
# NOTE: no `from __future__ import annotations` here — the repo-wide gotcha
# (agents/notes.md #11): it stringifies annotations, so Dagster cannot resolve
# `context: OpExecutionContext` and refuses to build the job.

from dagster import Field, OpExecutionContext, String, op
from dagster_dbt import DbtCliResource

from ingest.load import land_series
from orchestration.assets.dbt import DBT_DIR

#: dbt selector template for the single-series refresh path.
#:
#: ``<source tag>+`` selects the staging model that reads the refreshed raw rows
#: *and its downstream graph* — the intermediate union and the marts. The marts
#: also carry ``ops_refresh`` (see ``dbt/models/marts/*.sql``); the staging
#: models carry one tag per source (``ops_refresh_fred`` …).
#:
#: ``package:elementary`` is required: Elementary's ``on-run-end``
#: ``upload_dbt_artifacts()`` hook fails to compile under a partial ``--select``
#: whose graph contains no elementary node (``'get_upload_artifact_method' is
#: undefined``), which would report a false failure *after* the data loaded.
#: See ``agents/notes.md``.
SERIES_REFRESH_SELECT = "tag:{source_tag}+ package:elementary"

#: dbt selector for the full refresh path (everything, incl. elementary + tests).
FULL_BUILD_SELECT = "fqn:*"

#: source -> the per-source tag on its staging model.
_SOURCE_TAGS = {
    "fred": "ops_refresh_fred",
    "ecb": "ops_refresh_ecb",
    "bundesbank": "ops_refresh_bundesbank",
    "ecbwatch": "ops_refresh_ecbwatch",
}


def series_refresh_select(source: str):
    """dbt ``--select`` expression for a refresh of a series from ``source``."""
    tag = _SOURCE_TAGS.get(source)
    if tag is None:
        raise ValueError(f"no ops_refresh tag mapped for source '{source}'")
    return SERIES_REFRESH_SELECT.format(source_tag=tag)


def _dagster_run_id(context: OpExecutionContext):
    """The current run id, for ``raw.source_fetch.dagster_run_id`` lineage."""
    try:
        return context.run_id
    except Exception:  # noqa: BLE001 — lineage is best-effort, never fatal
        return None


#: Run config for a single-series refresh:
#: ``{"ops": {"ingest_one_series": {"config": {"series_id": "DGS10"}}}}``.
REFRESH_SERIES_CONFIG = {"series_id": Field(String, description="Warehouse series id")}


@op(
    description="Fetch and land exactly one series into raw.source_fetch (spec §5).",
    config_schema=REFRESH_SERIES_CONFIG,
)
def ingest_one_series(context: OpExecutionContext) -> str:
    """Land one series and return its source, for the downstream dbt selector."""
    series_id = context.op_config["series_id"]
    stats = land_series(series_id, dagster_run_id=_dagster_run_id(context))
    context.add_output_metadata(stats)
    if stats.get("failed"):
        # The raw row is still landed (with a null payload) for the audit trail,
        # but a refresh that could not fetch is a failed refresh.
        raise RuntimeError(
            f"fetch failed for {series_id}: {stats.get('error', 'unknown error')}"
        )
    return stats["source"]


def _run_dbt(context: OpExecutionContext, dbt: DbtCliResource, args):
    """Run one dbt CLI invocation and fail the op if it fails.

    ``dbt --select`` with a selector that matches nothing **exits 0**, so a typo
    in a selector silently "succeeds" while transforming nothing. Any op that
    runs a selection therefore checks the selection first (see
    :func:`_assert_selection_matches`).
    """
    context.log.info("dbt %s", " ".join(args))
    invocation = dbt.cli(args, context=context)
    # Stream the invocation so its stdout/stderr reaches the Dagster event log,
    # then assert success — matches how the @dbt_assets path reports failures.
    invocation.stream()
    if not invocation.is_successful():
        raise RuntimeError(f"dbt {' '.join(args)} failed: {invocation.get_error()}")


def _assert_selection_matches(context: OpExecutionContext, select: str) -> int:
    """Fail loudly when a dbt selector matches no nodes.

    ``dbt build --select <typo>`` **exits 0** having transformed nothing, so
    without this check a per-series refresh would report SUCCESS while the marts
    still held stale data. dbt's in-process API is used purely as a graph query;
    the build itself still goes through Dagster's ``DbtCliResource`` so its logs
    and artifacts land in the Dagster event log.
    """
    from dbt.cli.main import dbtRunner

    result = dbtRunner().invoke([
        "ls", "--output", "json",
        "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR),
        "--select", select,
    ])
    if not result.success:
        raise RuntimeError(f"dbt ls --select '{select}' failed: {result.exception}")
    nodes = list(result.result or [])
    if not nodes:
        raise RuntimeError(
            f"dbt selector '{select}' matched no nodes — refusing to run a build that "
            "would transform nothing (check the dbt tags / selector syntax)"
        )
    context.log.info("dbt selector '%s' matched %d nodes", select, len(nodes))
    return len(nodes)


@op(description="Run the dedicated dbt transform chain for a refreshed series.")
def dbt_refresh_marts(context: OpExecutionContext, dbt: DbtCliResource, source: str):
    select = series_refresh_select(source)
    _assert_selection_matches(context, select)
    _run_dbt(context, dbt, ["build", "--select", select])


@op(description="Run the full dbt build (all models + tests + Elementary artifacts).")
def dbt_build_all(context: OpExecutionContext, dbt: DbtCliResource):
    _assert_selection_matches(context, FULL_BUILD_SELECT)
    _run_dbt(context, dbt, ["build", "--select", FULL_BUILD_SELECT])
