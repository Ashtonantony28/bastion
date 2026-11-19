# CLAUDE.md: conventions for Bastion

This file is the contract for anyone (human or agent) touching this repository. Read it before
making changes. The full project plan is `docs/PLAN.md`; the milestone tracker is `docs/ROADMAP.md`.

## Prime directives

1. **Every change ships with a Verify command.** A PR description names the exact command that
   proves it works (`pytest -q`, `bastion build --target ci`, `make report-pd`). If something cannot
   be verified yet, say so and name the milestone that will make it verifiable.
2. **Out-of-time, always.** No random train/test split for any model with a time dimension. Every
   headline metric is out-of-time and shown next to its in-sample value.
3. **Calibrated, not just accurate.** PD and LGD models report calibration tests (binomial,
   Jeffreys, Hosmer-Lemeshow), not only AUC/Gini.
4. **Reconcile to source.** Balance-sheet and portfolio totals reconcile to the public filing or
   dataset totals within a stated tolerance. Reconciliations are dbt tests, not notebook checks.
5. **Independent validation.** Every Tier 1 model has a second, simpler implementation or a
   challenger that checks it (the golden-model habit from the hardware projects).
6. **Deterministic outputs.** Seeded RNG everywhere; model outputs are hashed (`bastion.hashing`);
   fixtures are committed and regenerating one is a reviewed change (`bastion fixtures --check`).
7. **Data is never committed; no PII ever.** Download scripts and checksum pins
   (`src/bastion/ingest/pins.json`) are committed. Re-pinning is a reviewed change.
8. **State limitations.** Each model card lists what public data could not support.
9. **Not a regulatory submission.** Formulas are "modelled on" Basel / IFRS 9 / CECL / SR 11-7, cite
   their source document, and are tested against a published worked example where one exists.

## Architecture Decision Records

- Hard-to-reverse decisions get an ADR in `docs/adr/`, numbered sequentially, from `0000-template.md`.
- ADRs are immutable once Accepted; supersede with a new ADR and mark the old one `Superseded by NNNN`.
- Reference ADR numbers in code comments and PR descriptions.

## Code standards

- Python 3.11+ (CI runs 3.12). `ruff check`, `ruff format --check` and `mypy src` are clean.
- SQL transforms live in `transform/` (dbt-duckdb). Staging models are views over raw files;
  marts are tables. Column names are lower_snake_case; amounts carry their unit in the name or the
  model description (FDIC amounts are thousands of USD).
- Pillar code lives in its own package (`credit/`, `market/`, `alm/`, `ews/`, `stress/`,
  `fincrime/`, `mrm/`), reads marts from DuckDB, and never reads raw files directly.
- No network access in unit tests. Live checks are marked `@pytest.mark.network`.
- Shared validation statistics (purged CV, deflated Sharpe, PSI, Kupiec, calibration tests) go in
  the `quantval` package (ADR 0006) so Tickforge can reuse them.

## Tests

- `pytest -q` from the repo root (network tests deselected by default; `pytest -m network` runs them).
- `bastion build --target ci` runs every dbt model and test over `fixtures/raw`.

## Branch / PR discipline

- Never commit directly to the default branch. One logical change per PR.
- PR description: what changed, **Verify command**, ADRs touched, roadmap milestone.
- Red CI never merges. Commit messages explain *why*.
