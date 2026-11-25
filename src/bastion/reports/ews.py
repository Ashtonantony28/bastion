"""Early-warning model report (M7): two out-of-time tests, two models, two feature sets."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd

from bastion.ews.model import (
    CRISIS,
    FEATURE_SETS,
    LABEL,
    RATE_AND_RUN,
    Y2023,
    SplitResult,
    evaluate,
    metrics,
)
from bastion.reports.common import ACCENT, MUTED, RESULTS, connect, savefig

NAMES_SQL = "select cert, name, fail_date from bank_failure"


def load_features() -> pd.DataFrame:
    con = connect()
    df = con.execute("select * from ews_features order by cert, repdte").df()
    con.close()
    df[LABEL] = df[LABEL].astype(bool)
    return df


def _metrics_table(results: list[SplitResult]) -> str:
    rows = []
    for r in results:
        for m in ("logit", "gbm"):
            rows.append(
                {
                    "features": r.feature_set,
                    "model": {"logit": "logistic", "gbm": "LightGBM"}[m],
                    "AUC in-sample": f"{r.in_sample[m]['auc']:.3f}",
                    "AUC out-of-time": f"{r.out_of_time[m]['auc']:.3f}",
                    "avg precision OOT": f"{r.out_of_time[m]['avg_precision']:.3f}",
                    "top-decile capture OOT": f"{100 * r.out_of_time[m]['top_decile_capture']:.0f}%",
                }
            )
    return pd.DataFrame(rows).to_markdown(index=False)


WELL_CAPITALISED = 0.05  # Tier 1 leverage; PCA "well capitalized" threshold


def _well_capitalised(results: list[SplitResult], df: pd.DataFrame) -> str:
    """OOT AUC excluding banks already near the PCA closure trigger, so the score is not just
    re-discovering the rule that critically undercapitalised banks must be closed."""
    rows = []
    for r in results:
        t = r.test_scores.merge(df[["cert", "repdte", "tier1_leverage"]], on=["cert", "repdte"])
        t = t[t["tier1_leverage"] >= WELL_CAPITALISED]
        y = t[LABEL].astype(int).to_numpy()
        for m in ("logit", "gbm"):
            rows.append(
                {
                    "features": r.feature_set,
                    "model": {"logit": "logistic", "gbm": "LightGBM"}[m],
                    "bank-quarters": f"{len(t):,}",
                    "failures": int(y.sum()),
                    "AUC out-of-time": f"{metrics(y, t[f'p_{m}'].to_numpy())['auc']:.3f}",
                }
            )
    return pd.DataFrame(rows).to_markdown(index=False)


def _failure_ranks(results: list[SplitResult], names: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    rows = []
    for r in results:
        s = r.test_scores[r.test_scores[LABEL]].merge(
            names[["cert", "name"]], on="cert", how="left"
        )
        n = len(r.test_scores)
        for _, x in s.iterrows():
            for m in ("logit", "gbm"):
                rows.append(
                    {
                        "bank": str(x["name"]).title(),
                        "failed": str(x["fail_date"])[:10],
                        "features": r.feature_set,
                        "model": m,
                        "rank": f"{int(x[f'rank_{m}'])} of {n}",
                        "riskier than": f"{100 * (1 - (x[f'rank_{m}'] - 1) / n):.0f}% of banks",
                    }
                )
    df = pd.DataFrame(rows)
    piv = df.pivot_table(
        index=["bank", "failed"], columns=["features", "model"], values="rank", aggfunc="first"
    )
    piv.columns = [f"{f} / {'logistic' if m == 'logit' else 'LightGBM'}" for f, m in piv.columns]
    return piv.reset_index().sort_values("failed").to_markdown(index=False), df


def _failures_by_year(df: pd.DataFrame) -> str:
    f = df[df[LABEL]].drop_duplicates("cert")
    counts = pd.to_datetime(f["fail_date"]).dt.year.value_counts().sort_index()
    fig, ax = plt.subplots(figsize=(7.5, 3))
    years = counts.index.to_numpy()
    colors = [ACCENT if y >= 2023 else MUTED for y in years]
    ax.bar(years, counts.to_numpy(), color=colors)
    ax.set_ylabel("failures with a Call Report\nin the prior 4 quarters", fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("FDIC-insured bank failures by year", fontsize=10)
    savefig(fig, "m7_failures_by_year.png")
    return "figures/m7_failures_by_year.png"


def build() -> tuple[str, str]:
    df = load_features()
    con = connect()
    names = con.execute(NAMES_SQL).df()
    con.close()
    crisis = [evaluate(df, CRISIS, fs) for fs in FEATURE_SETS]
    y23 = [evaluate(df, Y2023, fs) for fs in FEATURE_SETS]
    fig_years = _failures_by_year(df)
    rank_table, ranks = _failure_ranks(y23, names)
    coefs = y23[0].logit_coefs
    top = pd.concat([coefs.head(5), coefs.tail(5)])
    hashes = {f"{r.split.name}/{r.feature_set}": r.scores_hash for r in crisis + y23}
    (RESULTS / "m7-ews-hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    svb_rank = ranks[(ranks["bank"].str.contains("Silicon"))]

    def r23(fs: str, m: str) -> str:
        x = svb_rank[(svb_rank["features"] == fs) & (svb_rank["model"] == m)]
        return x["rank"].iloc[0] if len(x) else "n/a"

    rc = y23[1].logit_coefs
    rate_coefs = ", ".join(f"{f} {rc[f]:+.2f}" for f in RATE_AND_RUN)
    n_bq = len(df)
    n_banks = df["cert"].nunique()
    md = f"""# M7: Bank early-warning model

Generated by `bastion report ews`. Predicts whether an FDIC-insured bank fails within the next
four quarters from its Call Report. Data: {n_bq:,} bank-quarters for {n_banks:,} banks,
2005-2023 (`ews_features`). Labels: FDIC failures (open-bank assistance excluded).

Two models are always fitted side by side: a regularised logistic regression on winsorised,
standardised ratios (the benchmark) and a LightGBM challenger with monotone constraints. Two
feature sets: **camels** (capital, asset quality, earnings, liquidity, concentration, growth)
and **camels_rate_run**, which adds unrealized securities G/L to Tier 1, uninsured deposit share
and the share of long-term assets.

![Failures by year]({fig_years})

## Test 1: the 2008 crisis tail

Train on report dates 2006-Q1 to 2009-Q4, test on 2010-Q1 to 2012-Q4. No test-period data is
used for fitting, winsorising, imputing or scaling.

{_metrics_table(crisis)}

These AUCs are high partly because failure is mechanical: Prompt Corrective Action requires a
critically undercapitalised bank to be closed, so a bank whose leverage ratio is collapsing is
easy to rank. Restricting the test to banks that were still **well capitalised** (Tier 1
leverage at least 5%) at the report date removes that shortcut:

{_well_capitalised(crisis, df)}

## Test 2: the 2023 failures

Train on 2006-Q1 to 2019-Q4 (labels known through 2020), then score every bank's
2022-12-31 Call Report. Rank 1 = highest predicted risk.

{rank_table}

AUC on this snapshot (only {y23[0].out_of_time["logit"]["positives"]} failures, so treat as
indicative): {", ".join(f"{r.feature_set}/{m} {r.out_of_time[m]['auc']:.2f}" for r in y23 for m in ("logit", "gbm"))}.

## What this shows

- On credit-driven failures the models work out of time, including on banks that still looked
  well capitalised.
- **SVB stayed in the middle of the pack.** With CAMELS features it ranked
  {r23("camels", "logit")} (logistic) and {r23("camels", "gbm")} (LightGBM). Adding rate and run
  features moved it to {r23("camels_rate_run", "logit")} and {r23("camels_rate_run", "gbm")}.
  The rate and run terms are learned with moderate weights (logistic coefficients:
  {rate_coefs}), and they lift the 2023 failures as a group (snapshot AUC rises from
  {y23[0].out_of_time["logit"]["auc"]:.2f} to {y23[1].out_of_time["logit"]["auc"]:.2f} for the
  logistic model; Signature and First Republic move into the riskiest sixth). But SVB's strong
  capital ratio, earnings and loan quality outweigh them, because 2006-2019 contains almost no
  failures in which a well-capitalised, profitable bank was killed by rate losses plus a run. A
  statistical model cannot weight a failure mode it has barely seen. That is the argument for
  scenario-based rate and liquidity stress tests (M6, M8) next to statistical models, and the
  main lesson of the case study.
- Citizens Bank (Sac City, Iowa), a small credit failure, ranks in the top 15 under every model:
  the classic failure the model was built for.

## Most influential logistic terms (camels, 2006-2019 fit)

Standardised coefficients; positive raises failure risk.

{top.round(3).rename("coefficient").to_frame().to_markdown()}

## Reproducibility

Score hashes for each run are in `m7-ews-hashes.json` (ADR 0005). LightGBM runs single-threaded
with `deterministic=True`, so the same data gives the same hash.

## Limitations

- The FDIC API's Call Report fields are harmonised but coarse: no loan-level rate risk, no
  intra-quarter funding data, and `DEPUNA` exists only for banks that report it.
- Failures are rare outside 2009-2012, so post-2013 performance estimates are noisy.
- No supervisory (CAMELS rating) or market data is used; both would help, neither is public.

Reproduce: `bastion ingest --source fdic-failures && bastion ingest --source fdic-quarter
--quarters <2005Q1..2023Q4> && bastion build --target dev && bastion report ews`
"""
    note = (
        "## Would an early-warning model have flagged SVB?\n\n"
        f"Not one trained on history. Scored on its 2022-12-31 filing, SVB ranked "
        f"{r23('camels', 'logit')} under the CAMELS logistic model and {r23('camels_rate_run', 'gbm')} "
        "under LightGBM with rate and run features. See "
        "[m7-early-warning.md](m7-early-warning.md)."
    )
    (RESULTS / "m7-ews-note.md").write_text(note + "\n")
    out = RESULTS / "m7-early-warning.md"
    out.write_text(md)
    return str(out), note
