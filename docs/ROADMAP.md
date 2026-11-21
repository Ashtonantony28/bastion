# Roadmap

Full milestone definitions and Verify commands: [PLAN.md §6](PLAN.md).

| # | Milestone | Status |
|---|---|---|
| M0 | Scaffold + data platform | **done** ([results](results/m0-data-platform.md)) |
| M1 | Credit PD (Freddie Mac scorecard + LightGBM, Home Credit, Lending Club) | next; needs Kaggle token + Freddie Mac account |
| M2 | LGD, EAD, lifetime PD | |
| M3 | IFRS 9 + CECL + IRB capital + portfolio credit VaR | |
| M4 | Market risk (VaR, ES, sVaR, backtesting) | can start now (open data) |
| M5 | Counterparty risk (EE/PFE, CVA, SA-CCR) | |
| M6 | Liquidity, ALM, IRRBB | can start now (FDIC data) |
| M7 | SVB case study + bank early-warning model | **done** ([SVB](results/m7-svb-case-study.md), [EWS](results/m7-early-warning.md)) |
| M8 | Stress testing | after M3 + M6 |
| M9 | Fraud | needs Kaggle |
| M10 | AML | needs Kaggle |
| M11 | Model risk management | after one model per pillar |
| M12 | Dashboard, CRO pack, risk API, Tickforge desk | after M11 |
| M13 | Write-up + audit | last |

Decisions taken 2026-11-19 (all plan recommendations): concept A (full platform), name Bastion,
US-primary regulatory lens with IFRS 9 / Basel alongside (ADR 0002), private data cache once M1
starts, static dashboard, loose Tickforge coupling via file contract + `quantval` (ADR 0006),
ALM bank chosen in M6, in-process event-time streaming for fraud, no LLM features by default.
