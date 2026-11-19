# Bastion

A bank risk and analytics platform built entirely on public data: credit risk (PD/LGD/EAD,
IFRS 9, CECL, Basel IRB), market and counterparty risk (VaR, ES, backtesting, CVA), liquidity and
ALM (LCR, NSFR, IRRBB, an SVB 2023 case study), a bank-failure early-warning model, fraud and AML
analytics, a CCAR-style stress test, and an SR 11-7-style model risk management layer.

> Research and portfolio project. Not a production risk system, not a regulatory submission,
> not investment or credit advice. No real customer data is used.

**Status:** M0 (data platform) complete. See [docs/ROADMAP.md](docs/ROADMAP.md) and the full
[plan](docs/PLAN.md).

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,models,orchestration]"

pytest -q                          # unit tests + dbt build over synthetic fixtures
bastion build --target ci          # dbt models and data tests over fixtures/raw

export BASTION_DATA=$HOME/bastion-data
bastion ingest --source core       # FRED, Fed scenarios, Treasury curves, FDIC failures + case study
bastion ingest --source fdic-quarter --quarters 20221231   # every insured bank, one quarter
bastion build --target dev         # build the lakehouse over real data
```

No credentials are needed for the core sources. Later milestones need a Kaggle API token and a
Freddie Mac account (see [docs/DATA.md](docs/DATA.md)).

## Layout

```
src/bastion/ingest/   checksummed downloaders + pins.json (no data in git)
src/bastion/pipelines Dagster asset graph
transform/            dbt-duckdb project: staging views, marts, reconciliation tests
fixtures/raw/         synthetic, seeded CI fixtures in each source's raw format
docs/                 PLAN, ROADMAP, DATA, ADRs, results
```

## First real-data sanity check (M0)

From the FDIC Call Report data the lakehouse builds, Silicon Valley Bank's unrealized securities
losses reached **104% of its Tier 1 capital at 2022-12-31**, with **86% of deposits uninsured**,
the two facts at the heart of its March 2023 failure. See
[docs/results/m0-data-platform.md](docs/results/m0-data-platform.md). The full case study is M7.
