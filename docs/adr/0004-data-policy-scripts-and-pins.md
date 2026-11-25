# 0004: Data policy: scripts and checksum pins in git, data never

- **Status:** Accepted
- **Date:** 2026-11-19
- **Milestone:** M0

## Context
Several sources forbid redistribution (Freddie Mac, Fannie Mae, some FRED series). Silent changes
in upstream data (FRED revisions, a re-published Call Report) would silently change every model.

## Decision
- Downloaders are committed; data is not (`data/` is git-ignored).
- Each downloaded file's SHA-256 is recorded in `src/bastion/ingest/pins.json` with `--pin`.
  Ordinary runs fail on mismatch (`PinMismatchError`) and write nothing; `--allow-drift` downgrades
  to a warning for exploratory work. Re-pinning is a reviewed change.
- JSON APIs (FDIC) are normalised to CSV with a fixed column order and sorted rows so their bytes
  are deterministic and pinnable. FRED requests use a fixed observation window.
- CI uses synthetic, seeded fixtures in each source's raw format (`fixtures/raw`), never real data.
- A private object-store cache (decision D5) may hold processed data later; it is never public.

## Consequences
Reproducibility is checkable. Upstream revisions surface as a failing ingest, which is the point.
Some sources (FRED) will need occasional re-pinning.
