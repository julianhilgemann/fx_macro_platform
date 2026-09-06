"""dbt assets via @dbt_assets — each dbt model appears as its own asset (spec §8).

The `raw.source_fetch` dbt source is wired to depend on the three ingest assets,
so materializing the dbt models first lands fresh raw data.
"""
from pathlib import Path

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"

dbt_project = DbtProject(
    project_dir=str(DBT_DIR),
    profiles_dir=str(DBT_DIR),
)

dbt_resource = DbtCliResource(project_dir=dbt_project)


class _FxMacroDbtTranslator(DagsterDbtTranslator):
    """Staging models depend on the ingest assets, so ingest runs before dbt.

    The raw.source_fetch dbt source is an external (non-materializable) asset, so
    it does not pull its own upstream deps into a run. Adding the ingest assets
    as direct deps of the staging models enforces ingest -> dbt ordering.
    """

    def get_asset_spec(self, manifest, unique_id, project):
        spec = super().get_asset_spec(manifest, unique_id, project)
        if unique_id.startswith("model."):
            name = self.get_resource_props(manifest, unique_id).get("name", "")
            if name.startswith("stg_"):
                spec = spec.merge_attributes(
                    deps=[
                        AssetKey("raw_fred"),
                        AssetKey("raw_ecb"),
                        AssetKey("raw_bundesbank"),
                    ]
                )
        return spec


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=_FxMacroDbtTranslator(),
)
def fx_macro_dbt_assets(context: AssetExecutionContext, dbt: DbtCliResource):
    # NOTE: Elementary's on-run-end artifact upload fails to compile under a
    # partial `--select`, so materialize the full dbt asset group (or run the
    # daily schedule, which selects everything -> `--select fqn:*`).
    yield from dbt.cli(["build"], context=context).stream()

    # Refresh the lineage DAG + catalog after every successful build so the
    # shared `dbt/target` volume stays current for the dbt-docs server (:8083).
    docs_invocation = dbt.cli(["docs", "generate"], context=context)
    docs_invocation.wait()
    if not docs_invocation.is_successful():
        raise RuntimeError(f"dbt docs generate failed: {docs_invocation.get_error()}")
    context.log.info("dbt docs generated -> dbt/target (manifest.json + catalog.json)")
