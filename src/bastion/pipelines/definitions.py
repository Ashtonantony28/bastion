"""Dagster asset graph (ADR 0003).

Each ingest source is one asset; the dbt lakehouse is a downstream asset. Assets are small and
idempotent so a cloud session that resets mid-run can re-materialise just what it lost:

    dagster asset materialize -m bastion.pipelines.definitions --select raw_fred
"""

import dagster as dg

from bastion import paths
from bastion.ingest.base import HttpClient, Pins, materialise
from bastion.ingest.registry import CORE, SOURCES


def _ingest_asset(source: str) -> dg.AssetsDefinition:
    @dg.asset(name=f"raw_{source.replace('-', '_')}", group_name="ingest")
    def _asset(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
        results = materialise(SOURCES[source](HttpClient(), []), paths.raw_root(), Pins.load())
        for r in results:
            context.log.info(f"{r.status} {r.relpath} {r.sha256[:12]}")
        return dg.MaterializeResult(
            metadata={"files": len(results), "bytes": sum(r.nbytes for r in results)}
        )

    return _asset


INGEST_ASSETS = [_ingest_asset(s) for s in CORE]


@dg.asset(group_name="lakehouse", deps=INGEST_ASSETS)
def lakehouse() -> dg.MaterializeResult:
    """dbt build of staging and marts over $BASTION_DATA/raw."""
    from bastion.cli import run_dbt

    if not run_dbt("dev"):
        raise dg.Failure("dbt build failed")
    return dg.MaterializeResult(metadata={"warehouse": str(paths.warehouse_path("dev"))})


defs = dg.Definitions(assets=[*INGEST_ASSETS, lakehouse])
