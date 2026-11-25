"""Rolling one-day VaR / ES backtest of the trading book on hypothetical P&L.

Each day t the book is revalued at that day's market state using the previous WINDOW days of
shocks (HS) or the same shocks volatility-rescaled to t (FHS). The realised hypothetical P&L is
the revaluation of the same book under the actual shock of day t+1. No information after t is
used to forecast day t+1.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bastion.market.factors import MarketData
from bastion.market.portfolio import State, revalue
from bastion.market.var import ewma_vol, fhs, hs, shock_matrix, to_shocks, var_es

WINDOW = 500
VAR_LEVEL = 0.99
ES_LEVEL = 0.975


def state_at(md: MarketData, d: pd.Timestamp) -> State:
    return State(
        zero=md.zero.loc[d].to_numpy(),
        vix=float(md.vix.loc[d]),
        spread=float(md.spread.loc[d]),
        fx={c: float(md.fx.loc[d, c]) for c in md.fx.columns},
    )


@dataclass
class BacktestSeries:
    frame: pd.DataFrame  # date (forecast for next day), pnl, var99/es975/var975 for hs and fhs


def run(md: MarketData, book: list[dict], start: str, end: str) -> BacktestSeries:
    m = shock_matrix(md.shocks())
    cols = list(m.columns)
    vol = ewma_vol(m)
    dates = m.index
    rows = []
    for i in range(WINDOW, len(dates) - 1):
        d = dates[i]
        if d < pd.Timestamp(start) or d > pd.Timestamp(end):
            continue
        st = state_at(md, d)
        window = m.iloc[i - WINDOW + 1 : i + 1]
        p_hs = hs(book, st, window)
        p_fhs = fhs(book, st, window, vol, vol.loc[d])
        realised = float(revalue(book, st, to_shocks(m.iloc[[i + 1]], cols))[0])
        r = {"date": d, "next_date": dates[i + 1], "pnl": realised}
        for name, p in (("hs", p_hs), ("fhs", p_fhs)):
            r[f"var99_{name}"], _ = var_es(p, VAR_LEVEL)
            r[f"var975_{name}"], r[f"es975_{name}"] = var_es(p, ES_LEVEL)
        rows.append(r)
    return BacktestSeries(pd.DataFrame(rows))


def exceptions(frame: pd.DataFrame, method: str) -> np.ndarray:
    return (-frame["pnl"] > frame[f"var99_{method}"]).to_numpy().astype(int)
