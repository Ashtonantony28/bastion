# 0006: Loose coupling with Tickforge via file contract and a shared `quantval` package

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0 (decision), M4/M12 (implementation)

## Context
Tickforge (`Ashtonantony28/tickforge`) is the user's market-making and research stack. Bastion's
market-risk engine needs a realistic trading desk, and both projects need the same validation
statistics (purged walk-forward CV, deflated Sharpe, PBO, Kupiec/Christoffersen, PSI).

## Decision
- Repositories stay separate.
- Tickforge is Bastion's "trading desk": Bastion reads Tickforge's backtest and paper-trading fill
  logs through a versioned Parquet schema plus its determinism hash (`docs/contracts/` in M4).
- Desk limits (VaR, notional, inventory, loss) are defined once in a limits file that both read.
- Shared statistics live in a small `quantval` package, started inside this repo
  (`src/quantval/`) and published for Tickforge once stable.

## Alternatives considered
Monorepo (couples release cadence and CI of two large projects); no integration (loses the
desk-versus-risk story and duplicates statistics code).

## Consequences
A contract version bump is needed when Tickforge's log schema changes. `quantval` must stay
dependency-light (numpy/scipy only).
