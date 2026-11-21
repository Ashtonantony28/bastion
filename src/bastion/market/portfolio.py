"""Positions and vectorised full revaluation under one-day shocks.

Hypothetical one-day P&L: positions are held fixed and revalued at the shocked market state;
carry, theta and roll-down are excluded (as in the Basel hypothetical-P&L backtest).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from scipy.stats import norm

from bastion.market.factors import NODES

BOOK_DIR = Path(__file__).resolve().parent / "portfolios"
COUPON_FREQ = 2
MIN_VOL = 0.05
OPTION_UNDERLYING = "equity_market"


@dataclass
class State:
    zero: np.ndarray  # (N,) zero rates at NODES
    vix: float
    spread: float  # decimal
    fx: dict[str, float]


@dataclass
class Shocks:
    """S scenarios of one-day factor moves."""

    equity: dict[str, np.ndarray]  # factor -> (S,) simple returns
    fx: dict[str, np.ndarray]  # factor -> (S,) relative changes
    dzero: np.ndarray  # (S, N)
    dvix: np.ndarray  # (S,)
    dspread: np.ndarray  # (S,)

    @property
    def n(self) -> int:
        return int(self.dzero.shape[0])


def _interp_matrix(t: np.ndarray) -> np.ndarray:
    """(K, N) weights so that z(t_k) = W @ z_nodes, linear with flat extrapolation."""
    w = np.zeros((len(t), len(NODES)))
    for k, tk in enumerate(np.clip(t, NODES[0], NODES[-1])):
        j = int(np.searchsorted(NODES, tk))
        if j == 0:
            w[k, 0] = 1.0
        elif NODES[j - 1] == tk or j == len(NODES):
            w[k, min(j, len(NODES)) - 1] = 1.0
        else:
            a = (tk - NODES[j - 1]) / (NODES[j] - NODES[j - 1])
            w[k, j - 1], w[k, j] = 1 - a, a
    return w


def bond_price(
    coupon: float, maturity: float, z_nodes: np.ndarray, spread: np.ndarray | float = 0.0
) -> np.ndarray:
    """Price per unit face; z_nodes is (N,) or (S, N); spread scalar or (S,)."""
    t = np.arange(1.0 / COUPON_FREQ, maturity + 1e-9, 1.0 / COUPON_FREQ)
    cf = np.full(len(t), coupon / COUPON_FREQ)
    cf[-1] += 1.0
    z = np.atleast_2d(z_nodes) @ _interp_matrix(t).T + np.atleast_1d(spread)[:, None]
    return np.exp(-z * t) @ cf


def bs_price(
    kind: str, s: np.ndarray, k: float, t: float, r: np.ndarray, vol: np.ndarray
) -> np.ndarray:
    vol = np.maximum(vol, MIN_VOL)
    d1 = (np.log(s / k) + (r + 0.5 * vol**2) * t) / (vol * np.sqrt(t))
    d2 = d1 - vol * np.sqrt(t)
    if kind == "call":
        return s * norm.cdf(d1) - k * np.exp(-r * t) * norm.cdf(d2)
    return k * np.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)


def load_book(name: str = "trading_book") -> list[dict]:
    return list(yaml.safe_load((BOOK_DIR / f"{name}.yaml").read_text())["positions"])


def revalue(book: list[dict], state: State, sh: Shocks) -> np.ndarray:
    """(S,) portfolio P&L in USD."""
    pnl = np.zeros(sh.n)
    z1 = state.zero[None, :] + sh.dzero
    for p in book:
        typ = p["type"]
        if typ == "equity":
            pnl += p["notional"] * sh.equity[p["factor"]]
        elif typ == "fx_forward":
            pnl += p["notional"] * sh.fx[p["factor"]]
        elif typ == "bond":
            p0 = bond_price(p["coupon"], p["maturity"], state.zero)[0]
            pnl += p["notional"] * (bond_price(p["coupon"], p["maturity"], z1) - p0)
        elif typ == "corporate_bond":
            p0 = bond_price(p["coupon"], p["maturity"], state.zero, state.spread)[0]
            p1 = bond_price(p["coupon"], p["maturity"], z1, state.spread + sh.dspread)
            pnl += p["notional"] * (p1 - p0)
        elif typ == "option":
            t = float(p["expiry"])
            w = _interp_matrix(np.array([t]))[0]
            r0 = np.array([state.zero @ w])
            v0 = bs_price(
                p["kind"], np.array([1.0]), p["strike"], t, r0, np.array([state.vix / 100])
            )[0]
            s1 = 1.0 + sh.equity[OPTION_UNDERLYING]
            v1 = bs_price(p["kind"], s1, p["strike"], t, z1 @ w, (state.vix + sh.dvix) / 100)
            pnl += p["notional"] * (v1 - v0)
        else:
            raise ValueError(f"unknown position type {typ}")
    return pnl
