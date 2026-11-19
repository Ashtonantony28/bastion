# 0005: Deterministic runs and output hashing

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0

## Context
Tickforge proved the value of hashing fill logs: any behavioural change is caught bit-exactly.
Risk models are numerically noisier (floating point, library versions), but reported numbers
still have to be reproducible for model validation.

## Decision
All randomness is seeded. `bastion.hashing.frame_hash` hashes a DataFrame canonically (sorted
columns, optional row sort, floats rendered to 12 significant digits). Each model run records its
output hash with the code commit, data pins and seed. CI compares hashes of models run over
fixtures; a changed hash is either a bug or an intended change recorded in the PR.

## Consequences
Library upgrades can change low-order float bits and therefore hashes; the 12-digit rendering
absorbs most of this, and the rest is handled by re-recording hashes in a reviewed PR.
