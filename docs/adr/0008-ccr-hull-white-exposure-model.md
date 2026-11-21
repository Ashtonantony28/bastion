# 0008: Counterparty exposure under one-factor Hull-White with historical volatility

- **Status:** Accepted
- **Date:** 2026-11-21
- **Milestone:** M5

## Context
Exposure simulation needs a rate model that reproduces today's curve, prices swaps in closed form
on every path (so 10,000 paths x 1,600 dates stays fast), and has an analytic exposure benchmark.
Swaption volatilities, the usual calibration target, are not freely available.

## Decision
- One-factor Hull-White in G1++ form, fitted exactly to the Treasury zero curve; simulated
  exactly (joint Gaussian x and its integral), antithetic, seeded.
- (a, sigma) fitted to the historical vol of daily zero-rate changes at tenors >= 2y over the last
  500 trading days. The short end is excluded because its realised vol is policy-anchored.
- Validation: swap pricer and Jamshidian swaption vs QuantLib (1e-8); Monte Carlo discounted EE
  vs the analytic swaption profile within Monte Carlo error; SA-CCR vs BCBS 279 Example 1.
- Variation margin uses an exact MPOR lag (shadow dates on the grid); collateral before the
  first MPOR is the margin settled on today's value.

## Consequences
- No curve twists, so netting between offsetting tenors is overstated; a two-factor (G2++)
  model is the natural successor (would supersede this ADR).
- Historical-measure vol means CVA is not a market price; it is labelled as such.
- Tickforge or future FX/equity trades need additional factors before they join a netting set.
