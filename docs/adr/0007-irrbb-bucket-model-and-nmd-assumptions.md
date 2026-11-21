# 0007: IRRBB from Call Report buckets, behavioural lives, BCBS NMD caps

- **Status:** Accepted
- **Date:** 2026-11-21
- **Milestone:** M6

## Context
Public data gives repricing/maturity buckets (Call Report RC-B Memo 2, RC-C Memo 2, time-deposit
and borrowing maturities), not cash flows. EVE and NII must be computed from those, and the
assumptions about non-maturity deposits (NMDs) dominate the answer.

## Decision
- Each bucket is a zero-coupon position. Mortgage pass-throughs, CMOs and residential loans use
  pre-specified behavioural average lives (`BEHAVIOURAL_LIFE`); other buckets use midpoints.
- NMDs: insured = retail, uninsured = wholesale; core share and average maturity at the BCBS
  d368 Table 2 caps, with a run-prone variant where uninsured deposits are not core. Both are
  always reported.
- Shocks: the six BCBS USD scenarios on a Treasury zero curve bootstrapped from par yields.
- The model is validated out of sample against reported fair-value changes (2013 and 2022);
  the duration mapping is chosen between two pre-specified variants, never fitted.

## Alternatives considered
Full cash-flow engine with prepayment models (no public loan-level data per bank); duration
approximations without a curve (cannot express non-parallel shocks).

## Consequences
The backtest shows a 2-3pp overstatement of value changes (coupons ignored). Results are
conservative and comparable across banks. A cash-flow engine for the Freddie Mac portfolio
(M2/M3) can later replace the mortgage bucket for that book.
