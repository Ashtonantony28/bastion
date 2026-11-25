"""Daily market states and one-day shocks for full revaluation.

State at date t: equity index levels are not needed (positions are notional exposures), but the
zero curve (at fixed nodes), VIX, Baa spread and FX levels are. A historical shock for day d is
(equity simple returns, FX relative changes, zero-rate changes, VIX change, spread change).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bastion.alm.curves import bootstrap

NODES = np.array([0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0])
START = "2005-01-01"


@dataclass
class MarketData:
    dates: pd.DatetimeIndex
    equity: pd.DataFrame  # simple returns, columns = equity factors
    fx: pd.DataFrame  # levels (USD per unit foreign)
    zero: pd.DataFrame  # zero rates at NODES (continuous, decimal)
    vix: pd.Series  # vol points
    spread: pd.Series  # Baa - 10y, decimal

    def shocks(self) -> dict[str, pd.DataFrame | pd.Series]:
        """One-day shocks indexed by the day the move happened (t-1 -> t)."""
        return {
            "equity": self.equity.iloc[1:],
            "fx": (self.fx / self.fx.shift(1) - 1.0).iloc[1:],
            "zero": self.zero.diff().iloc[1:],
            "vix": self.vix.diff().iloc[1:],
            "spread": self.spread.diff().iloc[1:],
        }


def zero_panel(curve_long: pd.DataFrame) -> pd.DataFrame:
    """Bootstrap one zero curve per date from (curve_date, tenor_months, par_yield_pct)."""
    rows = {}
    for d, g in curve_long.groupby("curve_date"):
        c = bootstrap(g["tenor_months"].to_numpy() / 12.0, g["par_yield_pct"].to_numpy())
        rows[pd.Timestamp(d)] = c.zero(NODES)
    return pd.DataFrame.from_dict(
        rows, orient="index", columns=[f"z{n:g}" for n in NODES]
    ).sort_index()


def load(con) -> MarketData:
    f = con.execute(
        "select obs_date, factor, value from market_factor_daily where obs_date >= ?", [START]
    ).df()
    wide = f.pivot_table(index="obs_date", columns="factor", values="value", aggfunc="first")
    wide.index = pd.to_datetime(wide.index)
    curves = con.execute(
        "select curve_date, tenor_months, par_yield_pct from treasury_par_curve where curve_date >= ?",
        [START],
    ).df()
    z = zero_panel(curves)
    eq_cols = sorted(c for c in wide.columns if c.startswith("equity_"))
    fx_cols = sorted(c for c in wide.columns if c.startswith("fx_"))
    # trading days on which every factor is observed; FRED holidays/gaps are forward-filled one day
    lv = wide[fx_cols + ["vix", "baa_spread"]].ffill(limit=1)
    idx = wide.index.intersection(z.index)
    panel = pd.concat([wide.loc[idx, eq_cols], lv.loc[idx], z.loc[idx]], axis=1).dropna()
    return MarketData(
        dates=panel.index,
        equity=panel[eq_cols],
        fx=panel[fx_cols],
        zero=panel[list(z.columns)],
        vix=panel["vix"],
        spread=panel["baa_spread"] / 100.0,
    )
