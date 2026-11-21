"""M6 report: interest-rate risk in the banking book and liquidity, from public Call Reports."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bastion.alm import backtest
from bastion.alm.balance_sheet import BCBS_CAPS, COVERAGE_MIN, RUN_PRONE, SECURITIES, build_position
from bastion.alm.curves import ZeroCurve, bootstrap
from bastion.alm.irrbb import OUTLIER_THRESHOLD, eve, nii_sensitivity, outlier_ratio
from bastion.alm.liquidity import RUNS, LcrAssumptions, lcr, nsfr, survival_days
from bastion.hashing import frame_hash
from bastion.ingest.fdic import CASE_STUDY_CERTS
from bastion.reports.common import ACCENT, MUTED, RESULTS, connect, pct, savefig

SVB = 24735
FAILED = {24735, 57053, 59017}
LARGE_K = 10_000_000
BACKTESTS = [("2012-12-31", "2013-12-31"), ("2021-12-31", "2022-12-31")]
SCENARIO_LABEL = {
    "parallel_up": "+200bp", "parallel_down": "-200bp", "steepener": "steepener",
    "flattener": "flattener", "short_up": "short +300bp", "short_down": "short -300bp",
}  # fmt: skip


def curve_at(con, d: str) -> ZeroCurve:
    x = con.execute(
        "select tenor_months / 12.0 as t, par_yield_pct from treasury_par_curve where curve_date = "
        "(select max(curve_date) from treasury_par_curve where curve_date <= ?)",
        [d],
    ).df()
    return bootstrap(x["t"], x["par_yield_pct"])


def bank_metrics(row: pd.Series, curve: ZeroCurve) -> dict[str, float]:
    out: dict[str, float] = {}
    for label, nmd in (("caps", BCBS_CAPS), ("runprone", RUN_PRONE)):
        pos = build_position(row, nmd)
        res = eve(pos, curve)
        out[f"eve_worst_t1_{label}"] = outlier_ratio(pos, res)
        out[f"eve_worst_scn_{label}"] = res.worst()[0]  # type: ignore[assignment]
        out[f"eve_up200_t1_{label}"] = (
            -res.delta["parallel_up"] / pos.tier1 if pos.tier1 > 0 else np.nan
        )
        out[f"nii_up_t1_{label}"] = (
            nii_sensitivity(pos, up=True) / pos.tier1 if pos.tier1 > 0 else np.nan
        )
        out[f"nii_down_t1_{label}"] = (
            nii_sensitivity(pos, up=False) / pos.tier1 if pos.tier1 > 0 else np.nan
        )
    out["coverage"] = build_position(row).securities_coverage
    out["lcr"] = lcr(row)
    out["lcr_unins25"] = lcr(row, LcrAssumptions(uninsured_outflow=0.25))
    out["lcr_unins100"] = lcr(row, LcrAssumptions(uninsured_outflow=1.0))
    out["nsfr"] = nsfr(row)
    for i, run in enumerate(RUNS):
        out[f"survival_{i}"] = survival_days(row, run)
    return out


def _days(x: float) -> str:
    return "survives" if x == float("inf") else f"{x:.1f}"


def _backtest_section(con) -> tuple[str, str, dict]:
    rows, results = [], {}
    for t0, t1 in BACKTESTS:
        r = backtest.run(
            con.execute("select * from alm_position where repdte = ?", [t0]).df(),
            con.execute("select * from bank_quarter where repdte = ?", [t0]).df(),
            con.execute("select * from bank_quarter where repdte = ?", [t1]).df(),
            curve_at(con, t0), curve_at(con, t1), t0, t1,
        )  # fmt: skip
        results[t0] = r
        for m, label in (
            ("pred_contractual", "contractual midpoints"),
            ("pred_behavioural", "behavioural lives"),
        ):
            s = r.summary[m]
            rows.append(
                {
                    "year": f"{t0[:4]}->{t1[:4]}",
                    "duration mapping": label,
                    "banks": s["banks"],
                    "correlation": f"{s['corr']:.2f}",
                    "predicted (aggregate)": f"{s['aggregate_predicted_pct']:.1f}%",
                    "reported (aggregate)": f"{s['aggregate_observed_pct']:.1f}%",
                    "median error": f"{s['median_error_pp']:+.1f}pp",
                    "mean abs error": f"{s['mean_abs_error_pp']:.1f}pp",
                }
            )
    r22 = results["2021-12-31"].frame
    fig, ax = plt.subplots(figsize=(6.5, 5))
    ax.scatter(r22["pred_behavioural"], r22["observed"], s=6, color=MUTED, alpha=0.6)
    svb = r22[r22["cert"] == SVB]
    ax.scatter(
        svb["pred_behavioural"], svb["observed"], s=40, color=ACCENT, edgecolor="black", zorder=3
    )
    for _, x in svb.iterrows():
        ax.annotate(
            "SVB",
            (x["pred_behavioural"], x["observed"]),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=9,
        )
    lim = [min(r22["pred_behavioural"].min(), r22["observed"].min()), 0.02]
    ax.plot(lim, lim, color="black", linewidth=0.6, linestyle="--")
    ax.set_xlim(max(lim[0], -0.3), 0.02)
    ax.set_ylim(max(lim[0], -0.3), 0.05)
    ax.set_xlabel("Model: predicted securities value change, 2022")
    ax.set_ylabel("Reported change in unrealized G/L / book, 2022")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"{len(r22):,} banks with > $100m securities (behavioural lives)", fontsize=10)
    savefig(fig, "m6_backtest_2022.png")
    hashes = {f"backtest/{k}": frame_hash(v.frame, sort_by=["cert"]) for k, v in results.items()}
    return pd.DataFrame(rows).to_markdown(index=False), "figures/m6_backtest_2022.png", hashes


def build() -> str:
    con = connect()
    names = dict(con.execute("select cert, name from bank_institution").fetchall())
    bt_table, bt_fig, hashes = _backtest_section(con)
    case = con.execute(
        "select * from alm_position where cert in (select unnest(?)) order by cert, repdte",
        [list(CASE_STUDY_CERTS)],
    ).df()
    all21 = con.execute("select * from alm_position where repdte = '2021-12-31'").df()
    c21, c22 = curve_at(con, "2021-12-31"), curve_at(con, "2022-12-31")
    con.close()

    # SVB at both dates
    svb_rows = []
    for d, c in (("2021-12-31", c21), ("2022-12-31", c22)):
        r = case[(case["cert"] == SVB) & (pd.to_datetime(case["repdte"]) == pd.Timestamp(d))].iloc[
            0
        ]
        m = bank_metrics(r, c)
        svb_rows.append((d, m, r))

    def svb_table() -> str:
        rows = []
        keys = [
            (
                "Worst EVE decline / Tier 1 (BCBS NMD caps)",
                lambda m: (
                    f"{pct(m['eve_worst_t1_caps'], 0)} ({SCENARIO_LABEL[m['eve_worst_scn_caps']]})"
                ),
            ),
            (
                "Worst EVE decline / Tier 1 (uninsured not core)",
                lambda m: (
                    f"{pct(m['eve_worst_t1_runprone'], 0)} ({SCENARIO_LABEL[m['eve_worst_scn_runprone']]})"
                ),
            ),
            ("EVE change at +200bp / Tier 1 (caps)", lambda m: pct(-m["eve_up200_t1_caps"], 0)),
            ("12-month NII at +200bp / Tier 1 (caps)", lambda m: pct(m["nii_up_t1_caps"], 1)),
            ("12-month NII at -200bp / Tier 1 (caps)", lambda m: pct(m["nii_down_t1_caps"], 1)),
            ("LCR proxy (40% uninsured outflow)", lambda m: pct(m["lcr"], 0)),
            ("LCR proxy at 100% uninsured outflow", lambda m: pct(m["lcr_unins100"], 0)),
            ("NSFR proxy", lambda m: pct(m["nsfr"], 0)),
            *[
                (f"Survival days: {run.name}", lambda m, i=i: _days(m[f"survival_{i}"]))
                for i, run in enumerate(RUNS)
            ],
        ]
        for label, f in keys:
            rows.append({"measure": label, **{d: f(m) for d, m, _ in svb_rows}})
        return pd.DataFrame(rows).to_markdown(index=False)

    # Peers at 2021-12-31 (before the hikes) and 2022-12-31
    peer_rows = []
    for d, c in (("2021-12-31", c21), ("2022-12-31", c22)):
        sub = case[pd.to_datetime(case["repdte"]) == pd.Timestamp(d)]
        for _, r in sub.iterrows():
            m = bank_metrics(r, c)
            peer_rows.append({"date": d, "cert": int(r["cert"]), **m})
    peers = pd.DataFrame(peer_rows)

    def peer_table(d: str) -> str:
        p = peers[peers["date"] == d].sort_values("eve_worst_t1_caps", ascending=False)
        rows = []
        for _, x in p.iterrows():
            rows.append(
                {
                    "bank": CASE_STUDY_CERTS[int(x["cert"])]
                    + (" (failed 2023)" if x["cert"] in FAILED else ""),
                    "worst dEVE / T1": pct(x["eve_worst_t1_caps"], 0),
                    "BCBS outlier (>15%)": "yes"
                    if x["eve_worst_t1_caps"] > OUTLIER_THRESHOLD
                    else "no",
                    "dEVE / T1, uninsured not core": pct(x["eve_worst_t1_runprone"], 0),
                    "NII +200 / T1": pct(x["nii_up_t1_caps"], 1),
                    "LCR proxy": pct(x["lcr"], 0),
                    "NSFR proxy": pct(x["nsfr"], 0),
                    "days, LCR-calibrated run": _days(x["survival_1"]),
                    "days, SVB-observed run": _days(x["survival_2"]),
                }
            )
        return pd.DataFrame(rows).to_markdown(index=False)

    # Every bank at 2021-12-31
    sec_cols = [f for f, _ in SECURITIES]
    all21 = all21[all21["sc"].fillna(0) > 0]
    cov = all21[sec_cols].fillna(0).sum(axis=1) / all21["sc"]
    all21 = all21[(cov >= COVERAGE_MIN) & (all21["rbct1j"] > 0)]
    xs = []
    for _, r in all21.iterrows():
        pos = build_position(r)
        res = eve(pos, c21)
        xs.append({"cert": int(r["cert"]), "asset": r["asset"], "worst": outlier_ratio(pos, res)})
    xdf = pd.DataFrame(xs)
    large = xdf[xdf["asset"] >= LARGE_K]
    svb_worst = float(xdf.loc[xdf["cert"] == SVB, "worst"].iloc[0])
    share_out = float((xdf["worst"] > OUTLIER_THRESHOLD).mean())
    share_out_large = float((large["worst"] > OUTLIER_THRESHOLD).mean())
    rank_large = int((large["worst"] >= svb_worst).sum())
    top_large = large.sort_values("worst", ascending=False).head(5)
    hashes["eve_all_banks_2021"] = frame_hash(xdf, sort_by=["cert"])
    hashes["peers"] = frame_hash(
        peers.drop(columns=[c for c in peers.columns if c.startswith("eve_worst_scn")]),
        sort_by=["date", "cert"],
    )
    (RESULTS / "m6-alm-hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")

    m21 = svb_rows[0][1]
    md = f"""# M6: Interest-rate risk in the banking book and liquidity

Generated by `bastion report alm` from FDIC Call Report repricing buckets (`alm_position`) and
the US Treasury par curve (`treasury_par_curve`). All inputs are public. The measures are
modelled on the BCBS IRRBB standard (d368, 2016) and the US LCR/NSFR rules, simplified to what
the Call Report discloses; they are analytical proxies, not regulatory figures.

## Summary

- **The standard IRRBB test would have flagged SVB before a single hike.** On its
  2021-12-31 balance sheet, with the generous BCBS caps on deposit stability, SVB's worst-case
  EVE decline was {pct(m21["eve_worst_t1_caps"], 0)} of Tier 1, against a supervisory outlier
  threshold of 15%. Among {len(large)} banks over $10bn it ranked {rank_large} of {len(large)}.
  If its uninsured deposits are not treated as stable, the decline is
  {pct(m21["eve_worst_t1_runprone"], 0)}.
- **The test is not unusual to fail.** {pct(share_out_large, 0)} of large banks and
  {pct(share_out, 0)} of all {len(xdf):,} banks breached 15% at end-2021 on this model, because a
  +200bp shock from near-zero rates hits long fixed-rate assets hard (and the backtest below
  shows the model overstates duration somewhat). SVB was in the top seventh of large banks, not
  at the very top; what set it apart was that exposure combined with an uninsured, concentrated
  deposit base.
- **Liquidity proxies looked adequate at end-2021 and stopped mattering in March 2023.** The
  LCR proxy assumes 40% of uninsured deposits leave in 30 days; SVB lost about a quarter of all
  deposits in one day. Under the observed two-day run, SVB's cash plus unencumbered securities
  (at fair value, after a 5% haircut) lasted {_days(svb_rows[1][1]["survival_2"])} days on its
  2022-12-31 balance sheet.
- **The rate model is checked against what banks later reported.** Revaluing each bank's
  securities buckets under the actual curve move predicts the reported change in unrealized
  losses with correlation 0.6-0.7 across 1,300-1,500 banks, in both the 2013 taper tantrum and
  2022. It overstates the size by 2-3 percentage points, mainly because buckets are treated as
  zero-coupon positions; that bias is conservative and is stated, not tuned away.

## SVB, before and after the hikes

{svb_table()}

## Validating the rate model against reported fair values

For each bank: revalue its securities repricing buckets at t0 under the actual Treasury zero
curve at t1, and compare with the reported change in unrealized gain/loss over the year,
divided by book value at t0. Banks whose securities book changed by more than 50% are dropped.
Both duration mappings were fixed before the test; neither was fitted.

{bt_table}

The behavioural mapping (amortising MBS and residential loans at conventional average lives) is
used for EVE everywhere else in this report.

![Predicted vs reported 2022 securities value change]({bt_fig})

## Peers

### 31 December 2021 (before the first hike)

{peer_table("2021-12-31")}

### 31 December 2022

{peer_table("2022-12-31")}

## All banks at 31 December 2021

Largest worst-case EVE declines among banks over $10bn:

{pd.DataFrame([{"bank": names.get(int(r.cert), str(int(r.cert))), "assets $bn": f"{r.asset / 1e6:,.1f}", "worst dEVE / T1": pct(r.worst, 0)} for r in top_large.itertuples()]).to_markdown(index=False)}

## Method

- **Positions.** Securities (RC-B Memo 2), loans (RC-C Memo 2), time deposits and borrowings
  by repricing or remaining-maturity bucket, each a zero-coupon position at the bucket
  midpoint, or at a behavioural average life for MBS, CMOs and residential loans. Cash reprices
  overnight. Non-rate-sensitive assets, other liabilities and equity are excluded.
- **Deposits without a maturity.** Insured = retail, uninsured = wholesale; transaction
  accounts (TRN) set the retail transactional share. Core shares and average maturities at the
  BCBS d368 Table 2 caps (90%/5y, 70%/4.5y, 50%/4y). The "uninsured not core" variant makes
  wholesale deposits reprice overnight. NII uses deposit betas of 0.35 (retail) and 0.70
  (wholesale), or 1.0 in the run-prone variant.
- **Curves and shocks.** Treasury par yields bootstrapped to a continuous zero curve
  (`bastion.alm.curves`, tested to reprice par bonds); six BCBS USD shocks (200/300/150bp).
- **LCR proxy.** HQLA = cash + Treasuries + GNMA (Level 1), other agency MBS at 85% (Level 2A),
  munis at 50% (Level 2B), securities at fair value, with the 40%/15% caps. Outflows: 5% insured,
  40% uninsured, repo and 1/12 of borrowings due within a year. Inflows: half of loans repricing
  within 30 days, capped at 75% of outflows. Not captured: commitments, derivatives,
  operational deposits, encumbrance detail.
- **NSFR proxy.** ASF: equity 100%, insured deposits 90%, uninsured 50%, borrowings over a year
  100%; RSF: Level 1 securities 5%, other securities 15%, residential mortgages 65%, other loans
  85%, other assets 100%.
- **Survival.** Cash plus unencumbered securities at fair value (pledged securities removed),
  after a haircut, against cumulative daily outflows. No discount-window or FHLB capacity is
  assumed beyond what the balance sheet already shows.

## Limitations

- The bucket model ignores coupons inside a bucket and loan fair values, so it overstates
  duration (see the backtest) and cannot see First Republic's main exposure: low-rate jumbo
  mortgages held as loans, which the loan buckets capture only by repricing date.
- Uninsured deposit estimates (DEPUNA) are self-reported and only required above $1bn.
- Run speed in 2023 was driven by concentration and social-media coordination that no balance
  sheet ratio measures; the SVB-observed scenario is taken from the Fed's April 2023 review.

Hashes of every result table: `m6-alm-hashes.json`. Reproduce: `bastion ingest --source
fdic-alm-case-study,fdic-alm-quarter --quarters 20121231,20131231,20211231,20221231 && bastion
build --target dev && bastion report alm`
"""
    out = RESULTS / "m6-alm-liquidity.md"
    out.write_text(md)
    return str(out)
