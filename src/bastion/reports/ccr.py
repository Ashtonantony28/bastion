"""M5 report: Hull-White exposure simulation, netting and CSA, CVA, SA-CCR vs IMM-style EAD."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bastion.alm.curves import ZeroCurve
from bastion.hashing import frame_hash
from bastion.market import factors
from bastion.market.ccr import exposure, saccr
from bastion.market.ccr.hull_white import HullWhite, fit_historical_vol
from bastion.market.ccr.swap import Swap, load_netting_set
from bastion.reports.common import ACCENT, ACCENT_2, ACCENT_3, RESULTS, connect, savefig

ASOF = "2025-12-31"
VOL_WINDOW = 500  # trading days of zero-rate changes for the vol fit
MIN_FIT_TENOR = 2.0  # policy-anchored short end excluded from the one-factor fit
PATHS = 10_000
SEED = 20251231
VALIDATION_PATHS = 40_000
VALIDATION_DATES = (1.0, 3.0, 5.0, 8.0)


def _m(x: float, nd: int = 2) -> str:
    return f"{x / 1e6:,.{nd}f}"


def _inputs() -> tuple[ZeroCurve, float, pd.DataFrame, HullWhite]:
    con = connect()
    md = factors.load(con)
    con.close()
    asof = pd.Timestamp(ASOF)
    curve = ZeroCurve(factors.NODES.astype(float), md.zero.loc[asof].to_numpy(dtype=float))
    changes = md.zero.loc[:asof].diff().dropna().iloc[-VOL_WINDOW:].to_numpy()
    fit = factors.NODES >= MIN_FIT_TENOR
    a, sigma = fit_historical_vol(changes[:, fit], factors.NODES[fit])
    model = HullWhite(a, sigma, curve)
    obs = changes.std(axis=0, ddof=1) * np.sqrt(252)
    vol = pd.DataFrame(
        {
            "tenor (y)": factors.NODES,
            "zero rate": [f"{z:.2%}" for z in curve.z],
            "observed vol (bp/yr)": (obs * 1e4).round(0),
            "Hull-White vol (bp/yr)": (
                sigma * (1 - np.exp(-a * factors.NODES)) / (a * factors.NODES) * 1e4
            ).round(0),
            "in fit": np.where(fit, "yes", "no"),
        }
    )
    return curve, float(md.spread.loc[asof]), vol, model


def _validation(
    model: HullWhite, spread: float, lgd: float
) -> tuple[pd.DataFrame, dict[str, float]]:
    s = Swap("payer_10y_par", 1e8, 0.0, 0.0, 10.0, payer=True)
    s = Swap(s.name, s.notional, s.par_rate(model.curve), 0.0, 10.0, payer=True)
    sim = exposure.simulate(model, [s], VALIDATION_PATHS, SEED + 1, step=0.5)
    v = sim.values[s.name]
    disc = sim.df * np.maximum(v, 0.0)
    rows = []
    for t in VALIDATION_DATES:
        k = int(np.searchsorted(sim.grid, t))
        rest = s.pay_times[s.pay_times > t + 1e-9]
        analytic = s.notional * model.payer_swaption(t, rest, np.full(len(rest), 0.5), s.fixed_rate)
        mc, se = disc[:, k].mean(), disc[:, k].std(ddof=1) / np.sqrt(len(disc))
        rows.append(
            {
                "t (y)": t,
                "analytic DEE $m (Jamshidian)": _m(analytic, 3),
                "Monte Carlo DEE $m": _m(mc, 3),
                "MC std error $m": _m(se, 3),
                "z-score": round((mc - analytic) / se, 2),
            }
        )
    # CVA: semi-analytic (swaption strip on the reset dates) vs Monte Carlo on the same dates
    times = np.concatenate([[0.0], s.reset_times[1:]])
    dee = np.array(
        [0.0]
        + [
            s.notional
            * model.payer_swaption(
                t,
                s.pay_times[s.pay_times > t + 1e-9],
                np.full(int(round((10 - t) * 2)), 0.5),
                s.fixed_rate,
            )
            for t in times[1:]
        ]
    )
    cva_analytic = exposure.cva(times, dee, spread, lgd)
    idx = np.searchsorted(sim.grid, times)
    surv = exposure.survival(times, spread, lgd)
    pathwise = lgd * (disc[:, idx][:, 1:] * (surv[:-1] - surv[1:])).sum(axis=1)
    return pd.DataFrame(rows), {
        "par_rate": s.fixed_rate,
        "cva_analytic": cva_analytic,
        "cva_mc": float(pathwise.mean()),
        "cva_se": float(pathwise.std(ddof=1) / np.sqrt(len(pathwise))),
    }


def build() -> str:
    curve, spread, vol_table, model = _inputs()
    doc, swaps = load_netting_set()
    lgd = 1.0 - doc["counterparty"]["recovery"]
    threshold = float(doc["csa"]["threshold"])
    mpor_days = int(doc["csa"]["mpor_days"])
    mpor = mpor_days / exposure.TRADING_DAYS

    trades = pd.DataFrame(
        [
            {
                "trade": s.name,
                "direction": "pay fixed" if s.payer else "receive fixed",
                "notional $m": _m(s.notional, 0),
                "start-end (y)": f"{s.start:g}-{s.end:g}",
                "fixed rate": f"{s.fixed_rate:.2%}",
                "par rate today": f"{s.par_rate(curve):.2%}",
                "value today $m": _m(s.price(curve)),
            }
            for s in swaps
        ]
    )
    v0 = sum(s.price(curve) for s in swaps)

    sim = exposure.simulate(model, swaps, PATHS, SEED, mpor=mpor)
    v = sim.netted()
    cases = {
        "No netting": exposure.no_netting(sim),
        "Netted, no collateral": v[:, sim.report_idx],
        f"Netted + CSA (threshold ${threshold / 1e6:g}m, MPOR {mpor_days}d)": exposure.collateralised(
            sim, v, threshold, mpor
        ),
    }
    gross_notional = sum(s.notional for s in swaps)
    rows, profiles = [], {}
    for name, vals in cases.items():
        p = exposure.profile(sim, vals)
        profiles[name] = p
        c, se = exposure.cva_mc_se(sim, vals, spread, lgd)
        rows.append(
            {
                "case": name,
                "EPE 1y $m": _m(p.epe()),
                "EEPE 1y $m": _m(p.eepe()),
                "peak EE $m": _m(float(np.max(p.ee))),
                "peak PFE 97.5% $m": _m(p.peak_pfe),
                "CVA $m": _m(c, 3),
                "CVA MC s.e. $m": _m(se, 3),
                "CVA bp of notional": round(c / gross_notional * 1e4, 1),
            }
        )
    results = pd.DataFrame(rows)

    # SA-CCR vs IMM-style EAD (alpha * EEPE)
    sa_trades = [
        saccr.IrTrade(s.notional, s.start, s.end, 1.0 if s.payer else -1.0, s.price(curve))
        for s in swaps
    ]
    sa_un = saccr.ead(sa_trades)
    vm0 = max(v0 - threshold, 0.0) - max(-v0 - threshold, 0.0)
    sa_m = saccr.ead(
        sa_trades, collateral=vm0, margined=True, threshold=threshold, mpor_days=mpor_days
    )
    net_p = profiles["Netted, no collateral"]
    csa_p = profiles[list(profiles)[2]]
    ead_rows = pd.DataFrame(
        [
            {
                "netting set": "unmargined",
                "SA-CCR RC $m": _m(sa_un.rc),
                "SA-CCR add-on $m": _m(sa_un.addon),
                "multiplier": round(sa_un.multiplier, 3),
                "SA-CCR EAD $m": _m(sa_un.ead),
                "IMM-style EAD = 1.4 x EEPE $m": _m(exposure.ALPHA * net_p.eepe()),
                "SA-CCR / IMM": round(sa_un.ead / (exposure.ALPHA * net_p.eepe()), 2),
            },
            {
                "netting set": "margined (CSA)",
                "SA-CCR RC $m": _m(sa_m.rc),
                "SA-CCR add-on $m": _m(sa_m.addon),
                "multiplier": round(sa_m.multiplier, 3),
                "SA-CCR EAD $m": _m(sa_m.ead),
                "IMM-style EAD = 1.4 x EEPE $m": _m(exposure.ALPHA * csa_p.eepe()),
                "SA-CCR / IMM": round(sa_m.ead / (exposure.ALPHA * csa_p.eepe()), 2),
            },
        ]
    )

    # BCBS 279 Example 1 reproduction
    d3 = saccr.option_delta("put", True, 0.06, 0.05, 1.0)
    ex1 = saccr.ead(
        [
            saccr.IrTrade(10_000, 0.0, 10.0, 1.0, 30.0, "USD"),
            saccr.IrTrade(10_000, 0.0, 4.0, -1.0, -20.0, "USD"),
            saccr.IrTrade(5_000, 1.0, 11.0, d3, 50.0, "EUR", maturity=1.0),
        ]
    )

    val_table, val = _validation(model, spread, lgd)

    fig, ax = plt.subplots(figsize=(8, 4.2))
    colours = (ACCENT, ACCENT_2, ACCENT_3)
    for (name, p), col in zip(profiles.items(), colours, strict=True):
        ax.plot(p.times, p.ee / 1e6, color=col, lw=1.8, label=f"EE: {name}")
        ax.plot(p.times, p.pfe / 1e6, color=col, lw=1.0, ls="--")
    ax.set_xlabel("years from 2025-12-31")
    ax.set_ylabel("$m")
    ax.set_title("Exposure profile of the netting set (solid EE, dashed PFE 97.5%)")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.3)
    fig_path = savefig(fig, "m5_exposure_profiles.png")

    hashes = {
        "results": frame_hash(results),
        "ead": frame_hash(ead_rows),
        "validation": frame_hash(val_table),
    }
    (RESULTS / "m5-ccr-hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n")

    nn, net, csa = (results.iloc[i] for i in range(3))
    md = f"""# M5: Counterparty credit risk

Generated by `bastion report ccr`. Valuation date {ASOF}. A synthetic netting set of five USD
interest rate swaps with one Baa-rated corporate counterparty is simulated under a one-factor
Hull-White model fitted to that day's Treasury zero curve. Exposure, CVA and regulatory EAD are
compared without netting, with netting, and with a variation-margin CSA. All market inputs are
public (Treasury par curves, FRED Baa spread); the trades are illustrative.

## Summary

- **Netting cuts exposure by about a quarter.** Peak expected exposure falls from
  ${nn["peak EE $m"]}m with no netting to ${net["peak EE $m"]}m netted; CVA falls from
  ${nn["CVA $m"]}m to ${net["CVA $m"]}m. The payer and receiver swaps partly offset.
- **A CSA caps exposure near the threshold.** With a ${threshold / 1e6:g}m threshold and a
  {mpor_days}-day margin period of risk, peak PFE drops from ${net["peak PFE 97.5% $m"]}m to
  ${csa["peak PFE 97.5% $m"]}m and CVA to ${csa["CVA $m"]}m. What remains is the threshold plus
  ten days of rate moves.
- **SA-CCR is more conservative than the simulation.** Its EAD is
  {ead_rows.iloc[0]["SA-CCR / IMM"]}x the IMM-style 1.4 x EEPE for the unmargined set and
  {ead_rows.iloc[1]["SA-CCR / IMM"]}x for the margined set. SA-CCR adds a fixed supervisory
  add-on to today's replacement cost and gives little credit for offsetting cash-flow timing;
  the simulation sees today's (moderate) rate volatility and the actual offsets.
- **Validated two ways.** The swap pricer matches QuantLib to 1e-8 per unit notional and the
  Jamshidian swaption price matches QuantLib's engine (both in `tests/test_ccr.py`). The Monte
  Carlo discounted EE of a single swap matches its analytic swaption profile within Monte Carlo
  error (table below), and the SA-CCR code reproduces BCBS 279 Example 1 exactly
  (EAD {ex1.ead:,.0f} vs 569 published).

![Exposure profiles](figures/{fig_path.name})

## Model inputs

Hull-White one-factor, fitted to the volatility of daily zero-rate changes over the last
{VOL_WINDOW} trading days at tenors of {MIN_FIT_TENOR:g} years and above: mean reversion
a = {model.a:.4f}, sigma = {model.sigma * 1e4:.0f}bp per year. Counterparty credit spread
{spread:.2%} (Baa minus 10y Treasury), recovery {doc["counterparty"]["recovery"]:.0%}, flat hazard
rate {spread / lgd:.2%}.

{vol_table.to_markdown(index=False)}

The short end (below 2 years) is excluded: with policy rates anchored for long stretches its
realised volatility is hump-shaped, which a one-factor model with positive mean reversion cannot
produce. The fit therefore overstates very short-dated rate volatility.

## Trades

{trades.to_markdown(index=False)}

Net value today: ${_m(v0)}m to the bank (positive = the counterparty owes us).

## Exposure and CVA

{results.to_markdown(index=False)}

{PATHS:,} antithetic paths on a two-week grid (plus every reset date and every date one MPOR
earlier, so margin lags are exact). EPE and EEPE are averaged over the first year (Basel CRE53).
CVA is unilateral with independent exposure and default.

## Regulatory exposure: SA-CCR vs IMM-style

{ead_rows.to_markdown(index=False)}

Margined SA-CCR uses variation margin held today of ${_m(vm0)}m (value above the threshold),
RC = max(V - C, threshold, 0) and a maturity factor of 1.5 x sqrt(MPOR / 250). The IMM-style
figure is not an approved internal model: it uses the risk-neutral simulation, no stressed
calibration and no alpha estimate of our own.

## Validation

### Monte Carlo vs analytic exposure, single 10-year par payer swap ($100m)

At each reset date the discounted EE of a payer swap equals a European payer swaption on the
remaining swap, priced in closed form by Jamshidian's decomposition.

{val_table.to_markdown(index=False)}

Par rate {val["par_rate"]:.3%}. CVA of this swap: semi-analytic ${_m(val["cva_analytic"], 4)}m,
Monte Carlo ${_m(val["cva_mc"], 4)}m (standard error ${_m(val["cva_se"], 4)}m).

### SA-CCR vs BCBS 279 Annex 4, Example 1

Supervisory delta of the swaption {d3:.4f} (published -0.27); effective notional USD
{ex1.effective_notional["USD"]:,.0f} (59,270), EUR {ex1.effective_notional["EUR"]:,.0f} (10,083);
add-on {ex1.addon:,.0f} (347); EAD {ex1.ead:,.0f} (569).

## Limitations

- One-factor model: rates at all tenors move together, so the curve cannot twist. Offsetting
  payer and receiver swaps at different tenors look like better hedges than they are, which
  overstates the netting benefit.
- Volatility is historical-measure. Free swaption volatility data is not available, so the model
  is not calibrated to option prices as a production CVA desk would do.
- Single curve (no OIS/SOFR basis), no cash flows inside the margin period of risk, no minimum
  transfer amount, no initial margin, no wrong-way risk, unilateral CVA (no DVA or FVA).
- Because cash flows inside the margin period are ignored, the CSA profile dips on coupon dates:
  collateral still reflects a coupon that has just been paid.
- SA-CCR is implemented for the interest rate class only (BCBS 279 / 12 CFR 217.132).

Reproduce: `bastion ingest --source treasury,fred && bastion build --target dev && bastion report ccr`
"""
    out = RESULTS / "m5-counterparty-risk.md"
    out.write_text(md)
    return str(out)
