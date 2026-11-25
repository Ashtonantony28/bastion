"""SVB 2023 case study from public Call Reports (M7).

Question: what did the public quarterly filings say about Silicon Valley Bank in 2021-2022,
relative to its peers and to every other US bank, and which of those signals would a classic
credit-focused early-warning view have missed?
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bastion.ingest.fdic import CASE_STUDY_CERTS
from bastion.reports.common import (
    ACCENT,
    ACCENT_2,
    ACCENT_3,
    MUTED,
    RESULTS,
    bn,
    connect,
    pct,
    savefig,
)

SVB, SIGNATURE, FIRST_REPUBLIC = 24735, 57053, 59017
FAILED_2023 = {SVB: "SVB", SIGNATURE: "Signature", FIRST_REPUBLIC: "First Republic"}
SNAPSHOT = "2022-12-31"
LARGE_BANK_K = 10_000_000  # $10bn in thousands
# Federal Reserve, "Review of the Federal Reserve's Supervision and Regulation of Silicon Valley
# Bank" (April 2023): $42bn withdrawn on 9 March 2023 and about $100bn more expected on 10 March.
RUN_DAY1_K = 42_000_000
RUN_DAY2_K = 100_000_000

PANEL_SQL = """
select cert, repdte, asset, dep, depuna, sc, scha, schf, scaf, scaa, chbal, rbct1j, asstlt,
       uninsured_deposit_share, securities_to_assets, securities_unrealized_gain_k,
       htm_unrealized_gain_k, unrealized_gain_to_tier1, long_term_assets_share,
       leverage_ratio_pct, noncurrent_loan_ratio, roa_pct
from bank_quarter where repdte between '2019-12-31' and '2022-12-31'
"""


def _names() -> dict[int, str]:
    con = connect()
    rows = con.execute("select cert, name from bank_institution").fetchall()
    con.close()
    return {int(c): n for c, n in rows}


def _derive(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["htm_share_of_securities"] = df["scha"] / (df["scha"] + df["scaf"])
    # Tier 1 if every security were marked to market (AFS AOCI is filtered out of regulatory
    # capital for banks below the advanced-approaches threshold, and HTM is at amortised cost).
    df["mtm_tier1_leverage"] = (df["rbct1j"] + df["securities_unrealized_gain_k"]) / df["asset"]
    # Same-day liquid resources at fair value vs uninsured deposits.
    df["liquid_fv_k"] = df["chbal"] + df["scaf"] + df["schf"]
    df["liquid_to_uninsured"] = df["liquid_fv_k"] / df["depuna"]
    df = df.sort_values(["cert", "repdte"])
    df["deposit_growth_yoy"] = df.groupby("cert")["dep"].pct_change(4, fill_method=None)
    return df


def _timeline(svb: pd.DataFrame) -> str:
    rows = []
    for _, r in svb.iterrows():
        rows.append(
            {
                "quarter": str(r["repdte"])[:10],
                "assets $bn": bn(r["asset"]),
                "deposit growth y/y": pct(r["deposit_growth_yoy"], 0),
                "uninsured share": pct(r["uninsured_deposit_share"], 0),
                "securities / assets": pct(r["securities_to_assets"], 0),
                "HTM share of securities": pct(r["htm_share_of_securities"], 0),
                "unrealized G/L $bn": bn(r["securities_unrealized_gain_k"]),
                "unrealized G/L / Tier 1": pct(r["unrealized_gain_to_tier1"], 0),
                "reported leverage": f"{r['leverage_ratio_pct']:.1f}%",
                "MTM leverage": pct(r["mtm_tier1_leverage"]),
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def _peers(snap: pd.DataFrame, large: pd.DataFrame) -> str:
    peer = snap[snap["cert"].isin(CASE_STUDY_CERTS)].copy()
    rows = []
    cols = [
        "uninsured_deposit_share",
        "unrealized_gain_to_tier1",
        "liquid_to_uninsured",
        "mtm_tier1_leverage",
    ]
    for _, r in peer.sort_values("unrealized_gain_to_tier1").iterrows():
        # percentile among large banks; for loss and coverage metrics, low is bad
        def rank(col: str, row: pd.Series = r) -> str:
            return f"{100 * (large[col] < row[col]).mean():.0f}"

        rows.append(
            {
                "bank": CASE_STUDY_CERTS[int(r["cert"])]
                + (" (failed 2023)" if r["cert"] in FAILED_2023 else ""),
                "assets $bn": bn(r["asset"]),
                "uninsured share": pct(r[cols[0]], 0),
                "unrealized G/L / Tier 1": pct(r[cols[1]], 0),
                "pctile (large banks)": rank(cols[1]),
                "liquid FV / uninsured": pct(r[cols[2]], 0),
                "MTM leverage": pct(r[cols[3]]),
                "noncurrent loans": pct(r["noncurrent_loan_ratio"], 2),
                "ROA": f"{r['roa_pct']:.2f}%",
            }
        )
    return pd.DataFrame(rows).to_markdown(index=False)


def _scatter(large: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(7.5, 5))
    others = large[~large["cert"].isin(FAILED_2023)]
    sizes = lambda s: 8 + 120 * np.sqrt(s / large["asset"].max())  # noqa: E731
    ax.scatter(
        others["uninsured_deposit_share"],
        others["unrealized_gain_to_tier1"],
        s=sizes(others["asset"]),
        color=MUTED,
        alpha=0.6,
        label="other banks > $10bn",
    )
    for cert, color in zip(FAILED_2023, (ACCENT, ACCENT_2, ACCENT_3), strict=True):
        r = large[large["cert"] == cert]
        if r.empty:
            continue
        ax.scatter(
            r["uninsured_deposit_share"],
            r["unrealized_gain_to_tier1"],
            s=sizes(r["asset"]),
            color=color,
            edgecolor="black",
            linewidth=0.6,
            zorder=3,
        )
        ax.annotate(
            FAILED_2023[cert],
            (r["uninsured_deposit_share"].iloc[0], r["unrealized_gain_to_tier1"].iloc[0]),
            xytext=(6, 4),
            textcoords="offset points",
            fontsize=9,
        )
    ax.axhline(-1.0, color="black", linewidth=0.6, linestyle="--")
    ax.text(
        0.02, -1.0, " losses = Tier 1", va="bottom", fontsize=8, transform=ax.get_yaxis_transform()
    )
    ax.set_xlabel("Estimated uninsured deposits / total deposits")
    ax.set_ylabel("Unrealized securities gain (loss) / Tier 1 capital")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_title("US banks over $10bn, 31 Dec 2022 (Call Reports)", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    savefig(fig, "m7_svb_scatter_2022q4.png")
    return "figures/m7_svb_scatter_2022q4.png"


def _trend(panel: pd.DataFrame) -> str:
    peers = panel[panel["cert"].isin(CASE_STUDY_CERTS) & ~panel["cert"].isin(FAILED_2023)]
    med = peers.groupby("repdte")["unrealized_gain_to_tier1"].median()
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.plot(
        pd.to_datetime(med.index),
        med.values,
        color=MUTED,
        linewidth=2,
        label="median of 9 regional peers",
    )
    for cert, color in zip(FAILED_2023, (ACCENT, ACCENT_2, ACCENT_3), strict=True):
        s = panel[panel["cert"] == cert]
        ax.plot(
            pd.to_datetime(s["repdte"]),
            s["unrealized_gain_to_tier1"],
            color=color,
            linewidth=2,
            label=FAILED_2023[cert],
        )
    ax.axhline(0, color="black", linewidth=0.5)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_ylabel("Unrealized G/L / Tier 1")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    savefig(fig, "m7_unrealized_trend.png")
    return "figures/m7_unrealized_trend.png"


EWS_NOTE = RESULTS / "m7-ews-note.md"


def build(ews_note: str = "") -> str:
    if not ews_note and EWS_NOTE.exists():
        ews_note = EWS_NOTE.read_text()
    con = connect()
    panel = _derive(con.execute(PANEL_SQL).df())
    con.close()
    panel["repdte"] = pd.to_datetime(panel["repdte"])
    snap = panel[panel["repdte"] == pd.Timestamp(SNAPSHOT)]
    large = snap[(snap["asset"] >= LARGE_BANK_K) & snap["rbct1j"].gt(0)]
    svb = panel[panel["cert"] == SVB]
    s = svb[svb["repdte"] == pd.Timestamp(SNAPSHOT)].iloc[0]
    deeper = int((large["unrealized_gain_to_tier1"] <= s["unrealized_gain_to_tier1"]).sum())
    unins_rank = int((large["uninsured_deposit_share"] >= s["uninsured_deposit_share"]).sum())
    both = large[
        (large["unrealized_gain_to_tier1"] <= -0.5) & (large["uninsured_deposit_share"] >= 0.6)
    ]
    run1, run2 = RUN_DAY1_K / s["dep"], (RUN_DAY1_K + RUN_DAY2_K) / s["dep"]
    scatter, trend = _scatter(large), _trend(panel)
    names = _names()

    md = f"""# M7: Silicon Valley Bank, read from its public Call Reports

Generated by `bastion report svb` from the FDIC Call Report data in the lakehouse
(`bank_quarter`). Amounts in USD; all inputs are public quarterly filings. This is an
analysis of public data, not a statement about any bank's supervision.

## Summary

- **The loss was visible a year early.** SVB's unrealized securities losses passed half of its
  Tier 1 capital in **2022-Q1** and exceeded all of it by **2022-Q3**
  ({pct(svb.loc[svb["repdte"] == pd.Timestamp("2022-09-30"), "unrealized_gain_to_tier1"].iloc[0], 0)}).
  At 2022-12-31 it held {bn(-s["securities_unrealized_gain_k"])}bn of unrealized losses against
  {bn(s["rbct1j"])}bn of Tier 1. Among the {len(large)} US banks with more than $10bn of assets,
  {"it was the deepest" if deeper == 1 else f"{deeper} banks were at least as deep"}.
- **The funding was the fragile part.** {pct(s["uninsured_deposit_share"], 0)} of deposits were
  uninsured ({"the highest" if unins_rank == 1 else f"rank {unins_rank}"} among large banks).
  Only {len(both)} large bank(s) combined losses beyond 50% of Tier 1 with uninsured deposits
  above 60%: {"; ".join(sorted(names.get(int(c), str(int(c))) for c in both["cert"]))}.
- **Reported capital looked fine; marked-to-market capital did not.** Reported Tier 1 leverage
  was {s["leverage_ratio_pct"]:.1f}%. With securities at fair value it was
  {pct(s["mtm_tier1_leverage"])}.
- **Credit metrics gave no warning.** Noncurrent loans were {pct(s["noncurrent_loan_ratio"], 2)}
  of loans and ROA was {s["roa_pct"]:.2f}%. A model trained on credit-driven failures
  (2008-2012) has nothing to react to here; see the early-warning results below.
- **Run arithmetic.** The Fed's April 2023 review reports $42bn withdrawn on 9 March and about
  $100bn more requested for 10 March. That is {pct(run1, 0)}, and then a cumulative {pct(run2, 0)}, of the
  deposits reported at 2022-12-31, against liquid resources at fair value (cash + AFS + HTM
  fair value) equal to {pct(s["liquid_to_uninsured"], 0)} of uninsured deposits, most of them
  securities that could only be sold or pledged at a loss.

![Uninsured deposits vs unrealized losses, banks over $10bn]({scatter})

## SVB quarter by quarter

{_timeline(svb)}

"MTM leverage" = (Tier 1 + unrealized gain/loss on HTM and AFS securities) / total assets. It is
an analytical measure, not a regulatory ratio.

![Unrealized G/L as a share of Tier 1]({trend})

## Peers at 2022-12-31

Percentile = share of banks over $10bn with a *lower* (worse) ratio, so 0 means the worst.

{_peers(snap, large)}

Signature's securities losses were ordinary; its exposure was the most concentrated uninsured
(largely crypto-linked) deposit base. First Republic's losses sat mostly in low-rate mortgages
held at amortised cost, which these securities fields do not capture; M6's EVE model covers
loans. Both points show why the early-warning model needs rate and run features, not only
credit ones.

{ews_note}

## Method and limitations

- Fields: unrealized G/L = (SCHF - SCHA) + (SCAF - SCAA); Tier 1 = RBCT1J; uninsured deposits =
  DEPUNA (self-reported estimate, required only above $1bn); cash = CHBAL.
- Fair-value losses on loans are not in Call Report schedule RC-B, so the loss and MTM measures
  understate rate exposure for loan-heavy banks such as First Republic.
- Quarter-end snapshots miss intra-quarter moves; the run figures come from the Fed's review,
  not from filings.

Reproduce: `bastion ingest --source fdic-case-study,fdic-failures && bastion ingest --source
fdic-quarter --quarters 20221231 && bastion build --target dev && bastion report svb`
"""
    out = RESULTS / "m7-svb-case-study.md"
    out.write_text(md)
    return str(out)
