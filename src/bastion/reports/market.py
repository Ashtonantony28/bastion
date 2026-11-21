"""M4 report: trading-book VaR / ES by four methods, stressed VaR, and an 18-year backtest."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bastion.hashing import frame_hash
from bastion.market import backtest, factors, var
from bastion.market.portfolio import load_book
from bastion.reports.common import ACCENT, ACCENT_2, MUTED, RESULTS, connect, savefig
from quantval import acerbi_szekely_z2, basel_traffic_light, christoffersen, kupiec_pof
from quantval.backtest import Z2_RED, Z2_YELLOW

ASOF = "2025-12-31"
STRESS = ("2008-07-01", "2009-06-30")
BT_START, BT_END = "2007-01-01", "2025-12-30"
CLASSES = {
    "equity": ("equity",),
    "rates": ("bond",),
    "credit": ("corporate_bond",),
    "fx": ("fx_forward",),
    "options": ("option",),
}


def _m(x: float) -> str:
    return f"{x / 1e6:,.2f}"


def _book_table(book: list[dict]) -> str:
    rows = []
    for p in book:
        desc = p.get("factor") or (
            f"{p.get('kind')} K={p['strike']:.0%} T={p['expiry']}y"
            if p["type"] == "option"
            else f"{p['coupon']:.1%} {p['maturity']}y"
        )
        rows.append({"type": p["type"], "detail": desc, "notional $m": _m(p["notional"])})
    return pd.DataFrame(rows).to_markdown(index=False)


def build() -> str:
    con = connect()
    md = factors.load(con)
    con.close()
    book = load_book()
    m = var.shock_matrix(md.shocks())
    vol = var.ewma_vol(m)
    asof = pd.Timestamp(ASOF)
    i = m.index.get_loc(asof)
    st = backtest.state_at(md, asof)
    w500, w250 = m.iloc[i - 499 : i + 1], m.iloc[i - 249 : i + 1]
    stress = m.loc[STRESS[0] : STRESS[1]]

    est = {}
    est["Historical simulation, 500 days"] = (
        var.var_es(var.hs(book, st, w500), 0.99)[0],
        var.var_es(var.hs(book, st, w500), 0.975)[1],
    )
    est["Historical simulation, 250 days"] = (
        var.var_es(var.hs(book, st, w250), 0.99)[0],
        var.var_es(var.hs(book, st, w250), 0.975)[1],
    )
    p_fhs = var.fhs(book, st, w500, vol, vol.loc[asof])
    est["Filtered HS (EWMA 0.94), 500 days"] = (
        var.var_es(p_fhs, 0.99)[0],
        var.var_es(p_fhs, 0.975)[1],
    )
    dn99 = var.delta_normal(book, st, w500, 0.99)[0]
    dn975 = var.delta_normal(book, st, w500, 0.975)[1]
    est["Delta-normal (EWMA covariance)"] = dn99, dn975
    p_mc = var.monte_carlo(book, st, w500)
    est["Monte Carlo, Student-t (nu=5), 20k paths"] = (
        var.var_es(p_mc, 0.99)[0],
        var.var_es(p_mc, 0.975)[1],
    )
    p_s = var.hs(book, st, stress)
    est["Stressed VaR: HS on Jul 2008 - Jun 2009"] = (
        var.var_es(p_s, 0.99)[0],
        var.var_es(p_s, 0.975)[1],
    )
    est_table = pd.DataFrame(
        [
            {
                "method": k,
                "1-day VaR 99% $m": _m(v[0]),
                "1-day ES 97.5% $m": _m(v[1]),
                "10-day VaR (sqrt-time) $m": _m(v[0] * np.sqrt(10)),
            }
            for k, v in est.items()
        ]
    ).to_markdown(index=False)

    # risk-class standalone VaR (HS 500) and diversification
    cls_rows, standalone = [], 0.0
    for name, types in CLASSES.items():
        sub = [p for p in book if p["type"] in types]
        v = var.var_es(var.hs(sub, st, w500), 0.99)[0]
        standalone += v
        cls_rows.append({"risk class": name, "standalone VaR 99% $m": _m(v)})
    total = est["Historical simulation, 500 days"][0]
    cls_rows.append({"risk class": "sum of standalone", "standalone VaR 99% $m": _m(standalone)})
    cls_rows.append({"risk class": "portfolio (diversified)", "standalone VaR 99% $m": _m(total)})
    cls_table = pd.DataFrame(cls_rows).to_markdown(index=False)

    # backtest
    bt = backtest.run(md, book, BT_START, BT_END).frame
    bt["year"] = pd.to_datetime(bt["next_date"]).dt.year
    stats_rows, year_rows = [], []
    for meth, label in (("hs", "HS 500d"), ("fhs", "Filtered HS")):
        hits = backtest.exceptions(bt, meth)
        k = kupiec_pof(int(hits.sum()), len(hits), 0.99)
        c = christoffersen(hits, 0.99)
        z2 = acerbi_szekely_z2(
            -bt["pnl"].to_numpy(), bt[f"var975_{meth}"].to_numpy(), bt[f"es975_{meth}"].to_numpy()
        )
        stats_rows.append(
            {
                "method": label,
                "days": len(hits),
                "exceptions (99%)": int(hits.sum()),
                "expected": f"{0.01 * len(hits):.0f}",
                "Kupiec p": f"{k.p_value:.3f}",
                "Christoffersen independence p": f"{c.p_ind:.3f}",
                "conditional coverage p": f"{c.p_cc:.3f}",
                "ES Z2 (97.5%)": f"{z2:+.2f} ({'red' if z2 < Z2_RED else 'yellow' if z2 < Z2_YELLOW else 'green'})",
            }
        )
        for y, g in bt.assign(hit=hits).groupby("year"):
            year_rows.append(
                {"year": int(y), "method": label, "exceptions": int(g["hit"].sum()), "days": len(g)}
            )
    yr = pd.DataFrame(year_rows)
    piv = yr.pivot_table(index="year", columns="method", values="exceptions").astype(int)
    days = yr.groupby("year")["days"].first()
    piv["days"] = days
    for col in ("HS 500d", "Filtered HS"):
        piv[f"{col} zone"] = [
            basel_traffic_light(int(x), int(n)).value
            for x, n in zip(piv[col], piv["days"], strict=True)
        ]
    year_table = piv.reset_index().to_markdown(index=False)

    fig, ax = plt.subplots(figsize=(9, 3.8))
    d = pd.to_datetime(bt["next_date"])
    ax.plot(d, bt["pnl"] / 1e6, color=MUTED, linewidth=0.5, label="hypothetical P&L")
    ax.plot(d, -bt["var99_hs"] / 1e6, color=ACCENT_2, linewidth=1, label="-VaR 99% HS 500d")
    ax.plot(d, -bt["var99_fhs"] / 1e6, color=ACCENT, linewidth=1, label="-VaR 99% filtered HS")
    ax.set_ylabel("$m")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="lower left")
    ax.set_title("Trading book: daily hypothetical P&L vs one-day 99% VaR, 2007-2025", fontsize=10)
    fig_bt = savefig(fig, "m4_var_backtest.png")
    _ = fig_bt

    hashes = {"backtest": frame_hash(bt.drop(columns=["year"]), sort_by=["date"])}
    (RESULTS / "m4-market-hashes.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n"
    )
    s_hs, s_fhs = stats_rows
    y08 = piv.loc[2008] if 2008 in piv.index else None

    md_text = f"""# M4: Market risk on a multi-asset trading book

Generated by `bastion report market`. Full revaluation of a synthetic multi-asset book on public
daily risk factors, 2005-2025: 12 US industry equity portfolios and the market (Kenneth French
library), Treasury zero curves bootstrapped from the daily par curve, Moody's Baa spread, VIX and
four USD exchange rates (FRED). P&L is hypothetical (positions fixed, no carry or theta), as in
the Basel backtest. Results are research, not a capital calculation.

## The book

{_book_table(book)}

## VaR and Expected Shortfall at {ASOF}

{est_table}

FRTB replaces 99% VaR with 97.5% ES and scales by liquidity horizon per risk factor instead of
sqrt(10); the sqrt-time column is shown only as the familiar Basel 2.5 convention.

### By risk class (HS 500 days, 99%)

{cls_table}

## Backtest, 2007-2025

One-day 99% VaR each day from the previous 500 days, compared with the next day's hypothetical
P&L ({len(bt):,} days).

{pd.DataFrame(stats_rows).to_markdown(index=False)}

Kupiec tests the number of exceptions, Christoffersen whether they cluster, and the Acerbi-Szekely
Z2 statistic whether losses beyond the 97.5% VaR are as large as forecast by ES (0 = right,
below {Z2_YELLOW} yellow, below {Z2_RED} red).

![P&L vs VaR]({"figures/m4_var_backtest.png"})

### Exceptions by year with Basel traffic-light zone

{year_table}

## What this shows

- Over the full period plain historical simulation had {s_hs["exceptions (99%)"]} exceptions
  against about {s_hs["expected"]} expected, filtered HS {s_fhs["exceptions (99%)"]}. The
  difference is concentrated in turbulent years{f" (2008: {int(y08['HS 500d'])} vs {int(y08['Filtered HS'])})" if y08 is not None else ""}:
  a 500-day window reacts slowly when volatility jumps, so its exceptions cluster, which the
  Christoffersen test picks up. Volatility filtering fixes most of that at the cost of a more
  volatile VaR.
- The four estimators at year-end 2025 differ by tens of percent. The delta-normal number is
  the lowest because it misses the option book's convexity and fat tails, which the Monte Carlo
  Student-t and historical methods keep.
- Stressed VaR on the 2008-09 window is several times today's VaR: the gap Basel 2.5 added
  stressed VaR to close.

## Limitations

- Positions are static and synthetic; no intraday trading, so actual-P&L backtesting is not
  possible until the Tickforge desk feed is wired in (M12, ADR 0006).
- Equity risk is at industry-portfolio level, not single names; options use VIX as a flat
  implied volatility (no skew or term structure).
- Corporate credit risk uses a single Baa spread factor.

Hashes: `m4-market-hashes.json`. Reproduce: `bastion ingest --source french,fred,treasury &&
bastion build --target dev && bastion report market`
"""
    out = RESULTS / "m4-market-risk.md"
    out.write_text(md_text)
    return str(out)
