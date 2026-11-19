# 0001: DuckDB + dbt-duckdb lakehouse over raw files

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0

## Context
Bastion runs mainly in a cloud container that resets every one to two hours, has no managed
database, and handles datasets from kilobytes (scenarios) to tens of GB (Freddie Mac, AMLworld).
Transformations must be testable (reconciliation tests are a prime directive) and leave lineage.

## Decision
Single-node **DuckDB** as the engine; raw files (CSV/Parquet) as the source of truth under
`$BASTION_DATA/raw`; **dbt-duckdb** for all SQL transforms with staging views reading raw files
directly through `read_csv`/`read_parquet`, and marts materialised as tables in one `.duckdb` file.
The same dbt models run over `fixtures/raw` in CI (`--target ci`), so CI exercises the real SQL.

## Alternatives considered
- Postgres: needs a server that a resetting container would lose; slower for analytics.
- Spark / Databricks: unnecessary at sample scale; heavy to run in the container; costs money.
- Pandas/Polars scripts only: no declarative tests or lineage; reconciliation checks would drift
  into notebooks.

## Consequences
Zero servers; the whole warehouse rebuilds from raw in minutes. Concurrency is single-writer,
which is fine for batch risk runs. If a dataset outgrows one node, Parquet files can be queried by
another engine without rewriting staging logic much.
