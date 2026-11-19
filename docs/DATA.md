# Data sources

Rules (ADR 0004): scripts and checksum pins are committed, data never is. Every downloaded file is
pinned in `src/bastion/ingest/pins.json`; drift fails ingest until re-pinned in a reviewed change.
Raw files land in `$BASTION_DATA/raw/<source>/...` (default `./data/raw`, git-ignored).

## Available now (no credentials)

| `--source` | Origin | Files | Licence / terms |
|---|---|---|---|
| `fred` | St. Louis Fed FRED, `fred.stlouisfed.org/graph/fredgraph.csv` | `fred/<SERIES>.csv` | Public; some series carry third-party copyright (Case-Shiller, ICE BofA): research use, no redistribution |
| `fed-scenarios` | Federal Reserve DFAST/CCAR scenario tables | `fed_scenarios/<year>/{historic,baseline,severely_adverse}_domestic.csv` | Public domain (US government) |
| `treasury` | US Treasury daily par yield curve | `treasury/par_curve_<year>.csv` | Public domain |
| `fdic-failures` | FDIC BankFind API `/banks/failures` | `fdic/failures.csv` | Public |
| `fdic-institutions` | FDIC BankFind API `/banks/institutions` | `fdic/institutions.csv` | Public |
| `fdic-case-study` | FDIC BankFind API `/banks/financials` (Call Report data) | `fdic/financials/case_study.csv` | Public |
| `fdic-quarter` | same, every insured bank for given report dates | `fdic/financials/all_banks_<YYYYMMDD>.csv` | Public |

FRED series and their meaning: `src/bastion/ingest/fred.py`. FDIC field codes: definitions at
`https://api.fdic.gov/banks/docs/risview_properties.yaml`; the fields we pull are listed in
`src/bastion/ingest/fdic.py`. FDIC amounts are **thousands of USD**.

Call Report caveats: `DEPUNA` (estimated uninsured deposits) is self-reported and only required
for banks over $1bn; ratios such as `NIMY` and `ROA` are FDIC-computed and annualised.

## Planned (credentials needed; requested when the milestone starts)

| Milestone | Source | Access |
|---|---|---|
| M1-M3 | Freddie Mac Single-Family Loan-Level Dataset (sample files) | free account at freddiemac.com; terms forbid redistribution |
| M1 | Home Credit Default Risk, Lending Club 2007-2018 | Kaggle API token |
| M9 | IEEE-CIS Fraud Detection, ULB credit-card fraud | Kaggle |
| M10 | IBM AMLworld (HI/LI Small), Elliptic | Kaggle |
| M11 | HMDA public LAR | open (ffiec.cfpb.gov) |
| M4 | Stooq daily prices, Ken French data library | open |
| M7 | FDIC financials 2005-2023, all banks | open (`fdic-quarter`) |
