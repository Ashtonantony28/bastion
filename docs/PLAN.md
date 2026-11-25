# Plan: "Bastion", a bank risk and analytics platform: credit, market, liquidity/ALM, fraud/AML, stress testing and model governance on public data

**Status:** PLAN, awaiting Ashton's review. No code until you say proceed.
**Drafted:** 2026-11-19
**Runs in:** the cloud container by default (see §9). Nothing needs your PC except creating the GitHub repo and registering for two free datasets.
**Sibling project:** Tickforge (`Ashtonantony28/tickforge`). Shared infrastructure is called out in §8.

---

## 0. One-paragraph pitch

Bastion is a miniature but honest version of what a bank's risk function runs. It builds a reproducible lakehouse from public bank and loan data (Freddie Mac loan-level mortgages, Home Credit and Lending Club consumer loans, FFIEC Call Reports for every US bank, HMDA, FRED macro series and the Federal Reserve's published stress scenarios), and on top of it implements the five pillars of bank risk: **credit risk** (PD/LGD/EAD models, IFRS 9 staging, CECL lifetime loss, Basel IRB capital), **market and counterparty risk** (VaR, Expected Shortfall, stressed VaR, backtesting, CVA), **liquidity and ALM** (LCR, NSFR, IRRBB EVE/NII shocks, a deposit-run model, and an SVB 2023 post-mortem from public filings), **fraud and AML** (real-time card-fraud scoring and graph-based money-laundering detection), and a **CCAR-style stress test** that ties them together over a nine-quarter horizon. Every model goes through a **model risk management** layer modelled on Fed SR 11-7: an inventory, auto-generated validation reports, ongoing monitoring, champion/challenger and fair-lending tests. Results are published as an always-on dashboard and a CRO-style risk pack. Tickforge plugs in as the bank's "trading desk", so its strategy P&L feeds the market-risk engine.

## 1. Why this project, and why this shape

- **It fills the gap in your portfolio.** Your projects already cover hardware, ML systems and trading (Tickforge). Bank risk is the largest employer of quant talent outside trading (model development, model validation, risk analytics, treasury/ALM, financial crime), and almost no side projects show it credibly. Those that exist are a single Kaggle credit notebook.
- **What reads as strong is the regulatory framing done right.** Interviewers in bank risk look for: PD models that are calibrated, not just accurate; awareness of IFRS 9 vs CECL; VaR backtesting with the Basel traffic light; IRRBB shocks; and above all *model validation discipline*. Bastion is built around those, with each number traceable to a public source.
- **It reuses your muscles.** Golden-model discipline becomes "independent re-implementation for validation"; bit-exact fixtures become deterministic, hashed model outputs; ADRs and audit loops carry over; Tickforge's purged walk-forward and deflated Sharpe tooling transfers directly.
- **Every pillar has a measurable output:** Gini/KS and calibration tests for PD, Kupiec/Christoffersen p-values for VaR, LCR/NSFR ratios that reconcile to a real bank's filings, precision at fixed alert volume for AML, and a capital ratio path under the Fed's severely adverse scenario.

### Alternatives considered (pick one in §13, D1)
| | Concept | Strength | Weakness |
|---|---|---|---|
| **A (recommended)** | Bastion: full multi-pillar platform with stress testing, governance and dashboards | Covers every bank risk role; the integration (stress test, governance) is what makes it rare | Largest scope; needs strict milestone gates |
| B | Credit-risk deep dive only: mortgage PD/LGD/EAD, IFRS 9 + CECL, IRB capital, stress test, validation | Deepest signal for credit-risk and model-validation roles; smaller | Misses market risk, ALM and fraud/AML roles |
| C | Financial-crime platform only: streaming fraud scoring, graph AML, case management, LLM-assisted SAR drafting | Strong for fintech and FinCrime ML roles; most "engineering" | Less quant; synthetic AML data limits realism |

A contains B and C as milestones, and every milestone is a usable stopping point, so A is the plan below.

## 2. Goals and non-goals

### Goals ("done" means all of these)
1. **Data platform:** one command rebuilds the lakehouse from public sources with checksums; every table has lineage back to a source file; outputs are deterministic (same inputs and seed give the same hash).
2. **Credit risk:**
   - Mortgage PD: regulatory-style WoE logistic scorecard plus a LightGBM challenger, out-of-time validated on Freddie Mac vintages; report Gini, KS, binomial and Jeffreys calibration tests by grade.
   - Consumer PD on Home Credit (and Lending Club as a second portfolio).
   - LGD from Freddie Mac realised losses (two-stage cure/severity model), EAD/CCF where data allows (stated limitation where it does not).
   - Lifetime PD term structures (survival or Markov transition models) conditioned on macro paths.
   - IFRS 9 staging (SICR rules, 12-month vs lifetime ECL) and US CECL lifetime ECL on the same portfolio, with a reconciliation of the two.
   - Basel IRB risk-weight formula and RWA, plus a Vasicek one-factor and a Monte Carlo portfolio credit VaR with concentration analysis.
3. **Stress testing:** Fed supervisory scenarios (baseline, severely adverse) drive macro satellite models into PD/LGD and loss paths, a simple PPNR model and a nine-quarter CET1 capital path. Includes one reverse stress test ("what scenario breaks the minimum ratio?").
4. **Market and counterparty risk:** a multi-asset trading book (equities, rates, FX, vanilla options) plus the Tickforge desk. Historical, filtered-historical, parametric and Monte Carlo VaR; 97.5% ES as in FRTB; stressed VaR on the 2008 window; sensitivities (DV01, greeks); backtesting with Kupiec POF, Christoffersen independence and the Basel traffic light. Counterparty exposure (EE/PFE) and CVA for an interest-rate swap book, benchmarked against SA-CCR.
5. **Liquidity and ALM:** a bank balance sheet calibrated to a real bank's public Call Report; LCR and NSFR; repricing gap; IRRBB EVE and NII under the six Basel standardised rate shocks; a non-maturity deposit model (beta and decay); a deposit-run survival-horizon simulation; and an **SVB 2023 case study** showing what these metrics said in 2021-2022 from public filings.
6. **Bank early-warning model:** predict US bank failures (2008-2023) from Call Report ratios (CAMELS-style features) with the FDIC failed-bank list as labels, validated out of time.
7. **Fraud and AML:**
   - Card fraud: a cost-sensitive model on IEEE-CIS, served by a streaming scorer with measured p99 latency.
   - AML: rules for classic typologies (structuring, fan-in/fan-out, cycles) plus a graph neural network on IBM's synthetic AMLworld transactions, reported as precision at a fixed daily alert budget; Elliptic as a second benchmark.
8. **Model risk management:** a model inventory with tiering; a model card and an auto-generated validation report for every model (conceptual soundness, data, performance, benchmarking, sensitivity, limitations); ongoing monitoring (PSI/CSI drift, calibration decay); champion/challenger; fair-lending analysis on HMDA (adverse impact ratios, marginal-effect tests) and adverse-action reason codes for the credit scorecard.
9. **Reporting:** an always-on dashboard (risk appetite, limits, ECL, VaR, liquidity, AML queue) and a generated quarterly "CRO pack" PDF; a small FastAPI risk service (score a loan, price ECL, run VaR on a posted portfolio).
10. **Write-up:** README with results, honest limitations, and an independent audit round with 0 critical/high findings.

### Non-goals (v1)
- No real customer data, no PII, ever. Public, anonymised or synthetic data only.
- Not a production risk system or regulatory submission; no claim of regulatory compliance. "Modelled on" SR 11-7, Basel, IFRS 9 and CECL, not certified against them.
- No full FRTB standardised approach or IMA capital charge (ES and backtesting are in; the full SA sensitivities-based method is a stretch).
- No operational-risk loss modelling (public op-risk data is too thin), except as a stretch using ORX-style published aggregates.
- No credit decisions or advice; the README says so.

## 3. Data sources (all public; availability re-verified in M0 and pinned in `docs/DATA.md`)

| Pillar | Source | What | Access |
|---|---|---|---|
| Credit (mortgage) | **Freddie Mac Single-Family Loan-Level Dataset** (sample files, ~50k loans per vintage, 1999 onward) | Origination plus monthly performance, delinquency, modification, realised loss | Free registration (D4); no redistribution |
| Credit (mortgage, alt.) | Fannie Mae Single-Family Loan Performance Data | Same idea, second portfolio for benchmarking | Free registration |
| Credit (consumer) | Home Credit Default Risk (Kaggle) | 300k applications plus bureau and payment history | Kaggle API token (D4) |
| Credit (consumer) | Lending Club 2007-2018 loan data (Kaggle mirror) | Term loans with outcomes, grades, rates | Kaggle |
| Credit (benchmarks) | UCI Taiwan credit-card default; Give Me Some Credit (Kaggle) | Small sanity-check datasets | Open |
| Fair lending | **HMDA public LAR** (CFPB / FFIEC) | Mortgage applications with outcomes and demographic fields | Open bulk download |
| Bank balance sheets | **FFIEC Call Reports bulk data** (every US bank, quarterly, since 2001) | Assets, deposits, securities, maturities, capital | Open bulk download |
| Bank metadata | FDIC BankFind Suite API; FDIC failed-bank list | Institution history, failures (labels for early warning) | Open API |
| Holding companies | FR Y-9C (FFIEC NIC) and SEC EDGAR XBRL | Consolidated financials, equity for Merton-style PD | Open |
| Macro | **FRED** (St. Louis Fed) | Unemployment, HPI, GDP, rates, spreads, VIX | Free API key (D4) |
| Stress scenarios | **Federal Reserve supervisory scenarios** (CCAR/DFAST, yearly) | Baseline and severely adverse paths for 28 variables | Open CSV |
| Rates | US Treasury par yield curves; NY Fed SOFR/EFFR reference rates | Curves for ALM, discounting, swaps | Open |
| Equities / FX | Stooq daily data; Ken French data library; FRED FX series | Trading-book risk factors | Open |
| Trading desk | **Tickforge** backtest and paper-trading fill logs | Intraday P&L for a market-making desk | Our own repo |
| Fraud | IEEE-CIS Fraud Detection (Kaggle); ULB credit-card fraud; PaySim | Card and mobile-money transactions | Kaggle |
| AML | **IBM AMLworld** synthetic transactions (NeurIPS 2023, HI/LI Small and Medium); Elliptic Bitcoin dataset | Labelled laundering patterns; transaction graphs | Kaggle |

Rules (same as Tickforge): commit download scripts and checksums, **never data**. Freddie/Fannie terms forbid redistribution, so any cache stays private (D5). Small synthetic fixtures generated by seeded, committed code back the unit tests, so CI never needs credentials.

## 4. Architecture

```
 sources ─▶ ingest/ (Python, idempotent, checksummed) ─▶ raw/ Parquet (immutable, per source + date)
                                                            │
                                     transform/ (dbt-duckdb SQL models, tested)
                                                            ▼
                     ┌─────────────── lakehouse (DuckDB + Parquet) ───────────────┐
                     │ staging → conformed (loan, account, txn, bank_qtr, macro,   │
                     │ curve, position) → marts (credit_panel, alm_bs, aml_graph)  │
                     └───────┬─────────────┬──────────────┬─────────────┬──────────┘
                             ▼             ▼              ▼             ▼
                     credit/          market/        alm/           fincrime/
                     PD LGD EAD       VaR ES sVaR    LCR NSFR       fraud scorer
                     IFRS9 CECL       backtests      IRRBB EVE/NII  (stream)
                     IRB RWA          CCR EE/PFE     deposit model  AML rules + GNN
                     portfolio VaR    CVA, greeks    run simulation early-warning
                             │             │              │             │
                             └──────┬──────┴──────┬───────┴─────────────┘
                                    ▼             ▼
                             stress/          mrm/ (model risk management)
                             scenarios →      inventory · model cards · validation
                             satellites →     reports · monitoring (PSI, calibration)
                             losses, PPNR,    champion/challenger · fair lending
                             CET1 path        · lineage + run registry (MLflow)
                                    │             │
                                    ▼             ▼
                     serve/  FastAPI risk service   ·   report/ static dashboard + CRO pack PDF
                                                            │
 orchestration: Dagster assets (one asset graph, materialisable piece by piece in the cloud container)
```

### 4.1 Platform choices
- **Storage and compute:** DuckDB over Parquet. Single-node, zero servers, fast enough for every dataset here at sample scale, and runs inside the cloud container. Polars for dataframe work.
- **Transforms:** dbt-duckdb, so SQL models carry tests (uniqueness, not-null, accepted values, reconciliation to source totals) and generate lineage docs.
- **Orchestration:** Dagster software-defined assets. Each pillar is a set of assets, so a thread can materialise just "credit PD" without the whole graph, which matters with a container that resets every one to two hours.
- **Models:** scikit-learn, statsmodels (scorecards, calibration tests), LightGBM, lifelines (survival), PyTorch Geometric (AML GNN), QuantLib-Python (curves, swaps, options), numba/JAX for Monte Carlo.
- **Run registry:** MLflow (file backend, committed run manifests, not artefacts) so every reported number links to a code commit, data checksum and seed.
- **Determinism:** seeded RNG everywhere; each model run emits a hash of its outputs; CI re-runs on fixtures and compares hashes, the same pattern as Tickforge's fill-log hash.

### 4.2 Credit risk detail
- **Scorecard PD:** binning with monotonic WoE, logistic regression, points scaling, reason codes. Challenger: LightGBM with monotone constraints and SHAP. Out-of-time split by origination vintage, never random.
- **Calibration:** central tendency over a through-the-cycle window, binomial and Jeffreys tests per grade (the ECB TRIM style), Hosmer-Lemeshow, traffic-light per grade.
- **LGD:** two-stage (probability of cure, then severity given loss), beta or fractional regression; downturn LGD from the 2008-2011 vintages.
- **EAD:** amortising-loan exposure for mortgages; CCF only where revolving data exists (Home Credit credit-card balances), documented as a limitation otherwise.
- **Lifetime PD:** discrete-time hazard model with macro covariates, plus a delinquency-state Markov chain as benchmark; both projected under scenario paths.
- **IFRS 9:** stage assignment (30 DPD backstop, relative PD increase for SICR, cure periods), probability-weighted ECL over three scenarios, stage migration report.
- **CECL:** lifetime ECL via PD/LGD/EAD and a vintage-loss (DCF-free) method side by side; reconciliation to IFRS 9 explaining the gap (Stage 1 12-month vs lifetime).
- **Capital:** Basel IRB risk-weight function for residential mortgage and retail, RWA and expected-loss shortfall; Vasicek ASRF and a CreditMetrics-style Monte Carlo for portfolio credit VaR, with sector and geography concentration (Herfindahl, granularity adjustment).

### 4.3 Stress testing
- Satellite models: regress portfolio default rates and LGDs on Fed scenario variables (unemployment, HPI, rates), with stationarity checks and economic-sign constraints.
- Projection engine: nine quarters, balance-sheet held constant (as in DFAST), losses through ECL, simple PPNR (net interest income from the ALM engine, fee and expense ratios from the calibrated bank), taxes, dividends, CET1 ratio path vs minimum plus stress capital buffer.
- Reverse stress test: search for the smallest scenario shift that breaches the minimum ratio.
- Back-test: run the 2008 realised path through the models fitted on pre-2007 data and compare to realised losses.

### 4.4 Market and counterparty risk
- **Book:** synthetic but realistic positions (equity portfolio, Treasury and swap ladder, FX forwards, listed-style vanilla options), plus the Tickforge market-making desk as a separate book.
- **VaR/ES:** historical (500-day and full-history), filtered historical (GARCH-scaled), delta-normal and full-revaluation Monte Carlo; 99% one-day VaR and 97.5% ES; stressed VaR on 2007-2009; liquidity-horizon scaling as FRTB does.
- **Backtesting:** daily hypothetical and actual P&L vs VaR, Kupiec POF, Christoffersen independence, Basel traffic-light zones, and ES backtests (Acerbi-Szekely).
- **Counterparty:** Hull-White simulated rates, swap exposure profiles (EE, PFE at 95%), netting and collateral (CSA with threshold), unilateral CVA from CDS-implied hazard rates, compared with the SA-CCR exposure.

### 4.5 Liquidity, ALM and IRRBB
- **Balance sheet:** map Call Report schedules (RC, RC-B securities, RC-E deposits, RC-C loans, RC-K) to a cash-flow model for a chosen real bank; reconcile totals to the filing.
- **Regulatory ratios:** LCR (HQLA levels and haircuts, outflow rates by deposit type) and NSFR (ASF/RSF factors). Stated simplifications where Call Reports lack detail.
- **IRRBB:** repricing gap, EVE and 12-month NII under the six Basel standardised shocks (parallel up/down, steepener, flattener, short up/down), with a non-maturity deposit model (deposit beta, decay curve).
- **Run model:** daily survival horizon under idiosyncratic and market-wide stress, uninsured-deposit share as a driver, contingency funding (discount window, FHLB, repo of HQLA).
- **SVB case study:** apply the same pipeline to SVB's 2021-Q4 to 2022-Q4 Call Reports and peers; show unrealised HTM losses vs capital, EVE sensitivity, uninsured deposit concentration, and the run-speed scenario. This is the project's flagship narrative.

### 4.6 Bank early-warning model
- Features: CAMELS-style ratios from Call Reports (capital, asset quality, earnings, liquidity, rate sensitivity) and their trends.
- Labels: FDIC failures within the next four quarters. Out-of-time evaluation on the 2023 failures with a model trained on 2008-2019.

### 4.7 Fraud and AML
- **Card fraud:** time-ordered split on IEEE-CIS, LightGBM with cost-sensitive thresholds (expected loss per transaction), feature store of rolling aggregates; a streaming scorer (Python with a Redpanda or in-process queue, D9) that replays transactions in event time and reports p50/p99 latency and dollars saved at a fixed decline rate.
- **AML:** rule engine for typologies; graph features (fan-in/out, cycles, temporal motifs); GraphSAGE or GINe GNN on AMLworld; evaluation as precision and recall at a fixed analyst capacity (alerts per day), not just F1; alert-triage queue in the dashboard.
- **Optional LLM step (D10):** draft a SAR-style case narrative from an alert's evidence with Claude, clearly labelled as a draft and evaluated for factual consistency against the evidence.

### 4.8 Model risk management (the differentiator)
- **Inventory:** YAML per model (owner, purpose, tier, inputs, limitations, validation status, next review).
- **Validation reports:** generated from code for every model: conceptual soundness notes, data quality checks, discrimination, calibration, stability, sensitivity and benchmarking against a simpler challenger, outcome analysis, limitations and compensating controls. Validators are independent re-implementations where feasible (for example a second ECL implementation in plain SQL), echoing your golden-model habit.
- **Monitoring:** PSI/CSI on inputs and scores by quarter, calibration drift, triggers that flag a model for review.
- **Fair lending:** on HMDA, adverse impact ratios and regression-based disparity tests for approval and pricing; on the scorecard, reason codes and a proxy-variable check. Documented as analysis, not a legal conclusion.

### 4.9 Reporting and serving
- **Dashboard:** static site (Evidence.dev or a small Next.js/Observable build, D6) rebuilt by CI from the published marts, hosted for free (GitHub Pages or Vercel), so it is always on without a server.
- **CRO pack:** quarterly PDF with risk appetite vs limits, ECL movement, capital ratios, VaR backtest, liquidity ratios, AML stats.
- **Risk API:** FastAPI service with endpoints for PD scoring, ECL calculation and VaR on a posted portfolio; containerised; run in CI for integration tests.

## 5. Verification and honesty rules (CLAUDE.md for the repo)
1. Every PR names its **Verify command**.
2. **Out-of-time, always.** No random splits for any model with a time dimension; every headline metric is out-of-time, next to its in-sample value.
3. **Calibrated, not just accurate.** PD and LGD models report calibration tests, not only AUC.
4. **Reconcile to source.** Balance-sheet and portfolio totals reconcile to the public filing or dataset totals within a stated tolerance; reconciliation tests live in dbt.
5. **Independent validation.** Every Tier 1 model has a second, simpler implementation or challenger that checks it.
6. **Deterministic outputs.** Seeded runs, output hashes, committed fixtures; regenerating a fixture is a reviewed change.
7. **Data is never committed; no PII ever.**
8. **State limitations.** Each model card lists what public data could not support (for example no true revolving EAD for mortgages).
9. ADRs for hard-to-reverse choices (storage, regulatory lens, scenario set, balance-sheet bank, GNN architecture).

## 6. Milestones

| # | Milestone | Output | Verify |
|---|---|---|---|
| **M0** | Scaffold + data platform | Repo, CI (pytest, dbt test, ruff, mypy), CLAUDE.md, ADRs 0001-0005, ingest scripts with checksums for every source, DuckDB lakehouse, Dagster asset graph, synthetic fixtures, `docs/DATA.md` | `pytest -q && dbt build --target ci` green in CI on fixtures; `bastion ingest --source fred,call-reports --pin` fetches and checksums real data in the cloud |
| **M1** | Credit PD | Freddie Mac panel, WoE scorecard + LightGBM challenger, Home Credit + Lending Club PD, calibration suite | Out-of-time Gini/KS and calibration report regenerated by `make report-pd`; hash test on fixtures |
| **M2** | LGD, EAD, lifetime PD | Two-stage LGD, downturn LGD, EAD/CCF, hazard + Markov lifetime PD | Report shows out-of-time LGD error and lifetime PD vs realised cumulative default by vintage |
| **M3** | IFRS 9 + CECL + capital | Staging, scenario-weighted ECL, CECL, reconciliation, IRB RWA, portfolio credit VaR | Independent SQL ECL matches Python ECL exactly on fixtures; IRB function matches Basel worked examples |
| **M4** | Market risk | Trading book, HS/FHS/parametric/MC VaR, ES, sVaR, greeks, backtesting suite | Backtest report with Kupiec/Christoffersen p-values and traffic-light zone; VaR matches a hand-computed case |
| **M5** | Counterparty risk | Hull-White simulation, EE/PFE, netting/CSA, CVA, SA-CCR comparison | Swap pricer matches QuantLib to 1e-8; EE of a single swap matches the analytic profile within MC error |
| **M6** | Liquidity, ALM, IRRBB | Call Report mapping, LCR, NSFR, gap, EVE/NII six shocks, deposit model, run simulation | Balance sheet reconciles to the filing; shock results match a hand calculation on a two-instrument book |
| **M7** | SVB case study + early warning | SVB 2021-22 analysis vs peers; bank-failure model with 2023 out-of-time test | `make report-svb` and `make report-ews`; 2023 failures ranked by the model, AUC reported |
| **M8** | Stress testing | Satellite models, nine-quarter projection, PPNR, CET1 path, reverse stress test, 2008 back-test | Severely adverse run reproducible by hash; 2008 back-test error reported |
| **M9** | Fraud | IEEE-CIS model, cost-sensitive thresholds, streaming scorer with latency benchmark | Time-ordered evaluation report; p99 latency committed and checked in CI on a fixture stream |
| **M10** | AML | Typology rules, graph features, GNN on AMLworld, Elliptic benchmark, alert-capacity metrics | Precision at fixed alert budget vs rules-only baseline; seeded GNN run reproducible |
| **M11** | Model risk management | Inventory, model cards, auto validation reports for every model, PSI/CSI monitoring, champion/challenger, HMDA fair-lending analysis | `make validate-all` produces a report per inventory entry; CI fails if a model lacks a current report |
| **M12** | Dashboard, CRO pack, risk API | Static dashboard deployed, quarterly PDF, FastAPI service + tests; Tickforge desk integrated into market risk | Dashboard build in CI; API integration tests; CRO pack regenerates from one command |
| **M13** | Write-up + audit | README with results, figures, limitations; independent audit round, fixes applied | `make all-reports`; audit finds 0 critical/high |

Dependencies: M0 gates everything. Credit (M1-M3), market (M4-M5), ALM (M6-M7) and fincrime (M9-M10) are independent after M0 and can run as parallel threads. M8 needs M3 and M6. M11 needs at least one model per pillar. M12 needs M11.

**Suggested stopping points:** after M3 you have a complete credit-risk project (concept B); after M8 you have the core bank risk platform; M9-M10 are the fincrime extension (concept C).

## 7. Repository layout (proposed)
```
bastion/
  ingest/        source connectors, checksums, pins (no data)
  transform/     dbt project (staging, conformed, marts, tests)
  pipelines/     Dagster asset definitions
  credit/        PD, LGD, EAD, lifetime, ifrs9, cecl, capital, portfolio
  market/        positions, var, es, backtest, ccr, cva
  alm/           balance sheet, lcr, nsfr, irrbb, deposits, run
  ews/           bank early-warning model
  stress/        scenarios, satellites, projection, reverse
  fincrime/      fraud, aml rules, graph, gnn, streaming
  mrm/           inventory/*.yaml, validation, monitoring, fairness
  serve/         FastAPI risk service
  report/        dashboard source, CRO pack templates
  fixtures/      synthetic seeded data for CI
  docs/          ADRs, DATA.md, ROADMAP.md, results/, case-studies/svb.md
  CLAUDE.md
```

## 8. Shared infrastructure with Tickforge

Tickforge is a trading desk; Bastion is the risk function that oversees desks. That relationship gives a natural, loose integration:

| Shared piece | How | Benefit |
|---|---|---|
| **Tickforge as a trading desk** | Bastion's market-risk engine ingests Tickforge's backtest and paper-trading fill logs through a documented, versioned contract (Parquet schema + hash) | Real intraday P&L for VaR backtesting; a "desk vs risk" story across two repos |
| **Pre-trade and limit framework** | Bastion defines desk limits (VaR, notional, inventory, loss); Tickforge's existing risk checks read the same limit file | One limits source of truth; a breach shows on the Bastion dashboard |
| **Validation statistics library** | Extract a small shared Python package (working name `quantval`): purged walk-forward CV, deflated Sharpe, PBO, Kupiec/Christoffersen, PSI, calibration tests | Written once, used by both; Tickforge's alpha graveyard becomes an MRM inventory entry |
| **Data conventions** | Same `fetch.py`-style idempotent downloaders with `--pin` checksums, the same "scripts not data" rule, the same `docs/DATA.md` format | Familiar tooling; one data-availability check across projects |
| **Determinism and hashing** | Tickforge hashes fill logs; Bastion hashes model outputs the same way | One CI pattern for reproducibility |
| **Market data** | Treasury curves, FRED rates and equity/FX series ingested once by Bastion and exposed as Parquet that Tickforge research can read | Avoids duplicate downloaders |
| **CI and repo conventions** | Same CLAUDE.md prime directives, ADR template, Verify-command rule, audit loop | Consistent portfolio |
| **C++ engine (optional)** | Tickforge's pybind11 engine replays the desk's intraday positions for intraday VaR | Shows the C++ engine used beyond its own repo |

Recommendation (D7): keep the repos separate, couple through the file contract and the shared `quantval` package (start it inside Bastion, have Tickforge depend on it once it stabilises). Do not merge the repos.

## 9. Running in the cloud (your stated preference)
- **Everything runs in the cloud container.** DuckDB, dbt, Dagster, model training (all CPU-sized at sample scale; the GNN fits in CPU memory on AMLworld HI-Small) and report builds.
- **Container resets every one to two hours** and the data cache is lost (seen on Tickforge). Mitigations: Dagster assets are small and resumable; ingest is idempotent with checksums; heavy assets cache to an optional private object store (D5) so a new session does not re-download tens of GB.
- **Data scale is chosen to fit:** Freddie Mac *sample* files rather than the full 50M-loan set; AMLworld Small/Medium rather than Large; Call Reports are a few GB total.
- **Credentials** needed once, stored as cloud environment secrets: Kaggle API token, FRED API key, Freddie Mac (and optionally Fannie Mae) account. Downloads that need an interactive login (Freddie Mac) may need one manual step; if so the fallback is a one-time download on your PC uploaded to the private store.
- **Always-on outputs** (dashboard) are static and hosted, so nothing needs a running machine.
- Your PC is needed only to create the repo (threads cannot create repos) and possibly the one Freddie Mac download.

## 10. Tooling and budget
- **Software (all free):** Python 3.12, DuckDB, Polars, dbt-duckdb, Dagster, scikit-learn, statsmodels, LightGBM, lifelines, PyTorch + PyG, QuantLib-Python, numba, MLflow, FastAPI, Evidence.dev or Observable Framework, WeasyPrint for the PDF.
- **Compute:** cloud container CPU for everything. A GPU is not needed; the GNN optionally trains faster on one.
- **Storage (optional, D5):** a free-tier private bucket (Cloudflare R2 or a private Hugging Face dataset) for the processed cache, roughly 20-40 GB.
- **Usage budget:** this is a large project. Expect each milestone to be one thread; parallel threads for the four pillars after M0 roughly halve elapsed time but not cost.

## 11. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Freddie/Fannie registration or interactive download blocks cloud ingest | Fall back to a one-time manual download into the private store; Home Credit and Lending Club keep credit work moving meanwhile |
| Kaggle mirrors (Lending Club, AMLworld) disappear | Pin checksums; record alternative mirrors in `docs/DATA.md`; Freddie Mac and Home Credit cover credit without Lending Club |
| Public data lacks fields real banks have (revolving EAD, behavioural deposit data, internal ratings) | State each gap in the model card; use documented proxies; never invent data presented as real |
| Call Reports too coarse for exact LCR/NSFR | Document simplifications; show sensitivity of ratios to assumed outflow rates; target "reconciles to filing totals", not "equals the bank's reported LCR" |
| Synthetic AML data makes results look better than reality | Report on two datasets (AMLworld and Elliptic), use alert-capacity metrics, and say plainly that synthetic laundering is easier to catch |
| Scope creep (largest project in the portfolio) | Hard milestone gates; three explicit stopping points (§6); stretch items labelled |
| Container resets lose data and time | Small resumable assets, idempotent ingest, optional private cache |
| Regulatory misstatement in a portfolio piece | Every regulatory formula cites its source document and is tested against a published worked example; README disclaims compliance |
| Fair-lending analysis misread as a legal finding | Frame as statistical analysis on public HMDA data, with limitations, and no claims about named lenders |
| Overfitting and leakage | Out-of-time splits only, leakage tests (future-data injection, as in Tickforge), challenger benchmarks |

## 12. What you'll be able to say at the end
"I built a bank risk platform on public data: Freddie Mac mortgage PD/LGD models validated out of time with calibration tests, IFRS 9 and CECL ECL reconciled to each other, Basel IRB capital, a nine-quarter Fed stress test to a CET1 path, VaR and ES with Basel backtesting on a trading book that includes my own market-making desk, LCR, NSFR and IRRBB on a real bank's Call Report, an SVB post-mortem from public filings, a bank-failure early-warning model tested on the 2023 failures, real-time fraud scoring and graph-based AML, and an SR 11-7-style model risk framework that generates a validation report for every model."

## 13. Decisions needed from you before "proceed"
- **D1 Concept:** A (Bastion, full platform, recommended), B (credit-risk deep dive) or C (financial-crime platform).
- **D2 Name:** "Bastion" or your pick.
- **D3 Regulatory lens:** US primary (CECL, CCAR/DFAST, SR 11-7, US LCR) with IFRS 9 and Basel side by side (recommended, since the public data is US), or EU/UK primary (IFRS 9, EBA stress test, PRA SS1/23).
- **D4 Credentials:** create a Kaggle API token, a FRED API key and a Freddie Mac account (all free), and add them as cloud environment secrets. I can give step-by-step instructions; threads cannot create accounts for you.
- **D5 Persistent data cache:** rebuild from source each session (simplest, slower), or a free private bucket (Cloudflare R2 or private Hugging Face dataset, recommended once M1 starts).
- **D6 Dashboard stack:** static site on GitHub Pages or Vercel (recommended, always on, no server), or Streamlit (quicker to build, needs a host to stay up).
- **D7 Tickforge integration:** loose coupling via file contract plus a shared `quantval` package (recommended), Bastion-only with no integration, or a monorepo.
- **D8 Bank for the ALM model:** a mid-size regional bank picked in M6 (recommended, Claude proposes three with clean filings), or one you choose. SVB stays as the case study either way.
- **D9 Streaming for fraud:** in-process event-time replay (recommended, simplest in the cloud) or Redpanda/Kafka in Docker (more realistic, heavier).
- **D10 LLM features:** none, or an optional Claude-drafted SAR narrative and validation-report summary in M10/M11 (needs an `ANTHROPIC_API_KEY` secret).
- **D11 Repo:** threads cannot create GitHub repos. If you approve, create `Ashtonantony28/bastion` (empty, private or public) and the build starts at M0.

## 14. Reading list for M0-M3
- Federal Reserve SR 11-7, "Guidance on Model Risk Management" (2011); PRA SS1/23.
- BCBS, "An Explanatory Note on the Basel II IRB Risk Weight Functions" (2005); Basel III LCR (2013) and NSFR (2014) standards; BCBS IRRBB standards (2016).
- IFRS 9 *Financial Instruments* (impairment section); FASB ASC 326 (CECL).
- Federal Reserve, "Dodd-Frank Act Stress Test: Supervisory Stress Test Methodology" (latest year) and that year's scenario release.
- Siddiqi, *Intelligent Credit Scoring* (scorecards, WoE, reject inference).
- Baesens, Rösch, Scheule, *Credit Risk Analytics* (PD, LGD, EAD, validation).
- Hull, *Risk Management and Financial Institutions* (VaR, ES, backtesting, CVA, liquidity).
- Gregory, *The xVA Challenge* (counterparty exposure and CVA).
- Altman et al., IBM AMLworld paper, "Realistic Synthetic Financial Transactions for Anti-Money Laundering Models" (NeurIPS 2023).
- Federal Reserve OIG and FDIC reports on the failure of Silicon Valley Bank (2023) for the case study.
