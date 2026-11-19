# 0003: Dagster software-defined assets for orchestration

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0

## Context
Pipelines span ingest, dbt, Python models and reports. Sessions reset, so work must be resumable
at a fine grain, and lineage from a reported number back to its sources is a governance goal (M11).

## Decision
Each ingest source is a Dagster asset (`raw_<source>`); the dbt build is the `lakehouse` asset;
later each model and report is an asset. The CLI (`bastion ingest/build`) and Dagster share the
same registry (`bastion.ingest.registry`), so neither is required to use the other. Dagster is an
optional dependency (`.[orchestration]`).

## Alternatives considered
Airflow (scheduler-centric, heavy, task- not data-oriented); Prefect (fine, weaker asset lineage);
Makefile only (no lineage, no partial materialisation metadata).

## Consequences
A thread can materialise one asset after a reset. Dagster becomes a moderately heavy dependency;
the CLI path keeps CI light.
