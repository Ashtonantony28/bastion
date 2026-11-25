# M0 results: data platform on real public data

**Run:** 2026-11-19, cloud container, `bastion ingest --source core --pin`,
`bastion ingest --source fdic-quarter --quarters 20221231 --pin`, `bastion build --target dev`.

## Ingest

| Source | Files | Notes |
|---|---|---|
| FRED (fredgraph CSV, window 1990-01-01..2025-12-31) | 14 | no API key needed |
| Fed supervisory scenarios, 2025 + 2026 vintages | 6 | historic, baseline, severely adverse (domestic) |
| US Treasury par yield curve 2005-2025 | 21 | tenor set changes over time ("4 Mo" from 2022, "1.5 Month" from 2025) |
| FDIC failures | 1 | 4,117 records since 1934; 3,036 failures with a CERT after excluding open-bank assistance |
| FDIC financials, case-study banks 2019Q4-2023Q4 | 1 | 12 banks (SVB, Signature, First Republic + 9 regional peers) |
| FDIC financials, all banks 2022-12-31 | 1 | 4,773 insured banks, paginated API |

Total wall time about 30 s. Re-running without `--pin` returned `pinned-ok` for every file, so
the normalised downloads are byte-deterministic.

## dbt build (dev target, real data)

`PASS=24 ERROR=0`. Notable checks:
- **Balance-sheet identity** (`assets = liabilities + total equity`, within 0.1%) holds for all
  4,773 banks at 2022-12-31 and every case-study bank-quarter.
- **No filing after failure.** The first real run caught seven open-bank *assistance*
  transactions (1980s-2009) being treated as failures. `bank_failure` now keeps
  `resolution_type = 'FAILURE'` only, which is the correct label definition for the
  early-warning model (M7).
- Every Fed projection path has exactly 13 quarters.

## Sanity check: SVB at 2022-12-31 vs peers

Unrealized gains/losses on HTM + AFS securities (fair value minus amortised cost) as a share of
Tier 1 capital, from Call Report fields `SCHF-SCHA` and `SCAF-SCAA` over `RBCT1J`:

| Bank (CERT) | Assets $bn | Uninsured deposits % | Securities / assets % | Unrealized G/L / Tier 1 % | Failed |
|---|---:|---:|---:|---:|---|
| Silicon Valley Bank (24735) | 209.0 | 86.4 | 56.1 | **-104.1** | 2023-03-10 |
| KeyBank (17534) | 187.6 | 51.9 | 25.5 | -41.9 | |
| Comerica (983) | 85.5 | 62.0 | 22.3 | -38.9 | |
| Huntington (6560) | 182.3 | 55.9 | 22.2 | -33.5 | |
| Signature Bank (57053) | 110.4 | 89.7 | 23.7 | -32.0 | 2023-03-12 |
| Fifth Third (6672) | 206.3 | 52.1 | 24.6 | -31.8 | |
| First Republic (59017) | 212.6 | 67.7 | 14.9 | -29.9 | 2023-05-01 |
| Banc of California (24045) | 41.2 | 50.2 | 17.3 | -28.5 | |
| Zions (2270) | 89.5 | 49.8 | 26.2 | -21.8 | |
| Western Alliance (57512) | 67.7 | 55.0 | 12.6 | -18.4 | |
| Citizens (57957) | 226.4 | 49.0 | 15.0 | -15.7 | |
| M&T (588) | 200.3 | 47.2 | 12.2 | -9.6 | |

Across all 4,773 banks the median ratio was -20%. 40 banks had losses at or beyond SVB's
-104%, but SVB was the only one with more than $10bn of assets. Signature and First Republic
had ordinary securities losses; their exposure was uninsured-deposit concentration (and, for
First Republic, low-rate loans, which this ratio does not capture). That distinction motivates
the M6/M7 deposit-run and EVE models. These are raw Call Report figures, not the case study's
conclusions.

## Reproduce

```bash
export BASTION_DATA=$HOME/bastion-data
bastion ingest --source core
bastion ingest --source fdic-quarter --quarters 20221231
bastion build --target dev
```
