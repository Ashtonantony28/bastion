"""VaR and Expected Shortfall estimators on full-revaluation P&L.

- Historical simulation (HS): empirical quantile of revalued historical shocks.
- Filtered HS (FHS): each factor's historical shock is rescaled by the ratio of today's EWMA
  volatility to the volatility on the day of the shock (Hull & White 1998; RiskMetrics lambda).
- Delta-normal: sensitivities by finite difference x EWMA covariance (parametric benchmark).
- Monte Carlo: multivariate Student-t (nu = 5) shocks with EWMA covariance, full revaluation.
VaR is reported as a positive loss at confidence alpha; ES is the mean loss beyond VaR
(FRTB uses ES at 97.5%).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from bastion.market.portfolio import Shocks, State, revalue

EWMA_LAMBDA = 0.94
MC_PATHS = 20_000
MC_NU = 5
SEED = 11


def var_es(pnl: np.ndarray, alpha: float) -> tuple[float, float]:
    losses = -np.asarray(pnl)
    v = float(np.quantile(losses, alpha, method="higher"))
    tail = losses[losses >= v]
    return v, float(tail.mean())


def shock_matrix(sh: dict[str, pd.DataFrame | pd.Series]) -> pd.DataFrame:
    """Flatten the per-class shock frames into one (days x factors) matrix."""
    parts = [
        sh["equity"],
        sh["fx"],
        sh["zero"],
        sh["vix"].rename("vix"),
        sh["spread"].rename("spread"),
    ]
    return pd.concat(parts, axis=1)


def to_shocks(m: pd.DataFrame | np.ndarray, columns: list[str]) -> Shocks:
    a = np.asarray(m, dtype=float)
    col = {c: i for i, c in enumerate(columns)}
    zc = [c for c in columns if c.startswith("z")]
    return Shocks(
        equity={c: a[:, col[c]] for c in columns if c.startswith("equity_")},
        fx={c: a[:, col[c]] for c in columns if c.startswith("fx_")},
        dzero=a[:, [col[c] for c in zc]],
        dvix=a[:, col["vix"]],
        dspread=a[:, col["spread"]],
    )


def ewma_vol(m: pd.DataFrame, lam: float = EWMA_LAMBDA) -> pd.DataFrame:
    """EWMA volatility known at the close of each day (uses shocks up to and including that day)."""
    return np.sqrt((m**2).ewm(alpha=1 - lam, adjust=False).mean())


def ewma_cov(m: pd.DataFrame, lam: float = EWMA_LAMBDA) -> np.ndarray:
    x = m.to_numpy()
    w = (1 - lam) * lam ** np.arange(len(x) - 1, -1, -1)
    w = w / w.sum()
    return (x * w[:, None]).T @ x


def hs(book: list[dict], state: State, window: pd.DataFrame) -> np.ndarray:
    return revalue(book, state, to_shocks(window, list(window.columns)))


def fhs(
    book: list[dict], state: State, window: pd.DataFrame, vol_hist: pd.DataFrame, vol_now: pd.Series
) -> np.ndarray:
    # vol on the day *before* each shock, so the shock is standardised by information then
    prior = vol_hist.shift(1).loc[window.index].replace(0.0, np.nan)
    scaled = window * (vol_now / prior)
    scaled = scaled.where(np.isfinite(scaled), window)
    return revalue(book, state, to_shocks(scaled, list(window.columns)))


def sensitivities(
    book: list[dict], state: State, columns: list[str], scale: pd.Series
) -> np.ndarray:
    """Central-difference P&L per unit factor move, bumping each factor by 1% of its daily vol scale."""
    k = len(columns)
    bumps = np.zeros((2 * k, k))
    h = (scale.reindex(columns).to_numpy() * 0.01).clip(min=1e-8)
    for i in range(k):
        bumps[2 * i, i], bumps[2 * i + 1, i] = h[i], -h[i]
    p = revalue(book, state, to_shocks(bumps, columns))
    return (p[0::2] - p[1::2]) / (2 * h)


def delta_normal(
    book: list[dict], state: State, window: pd.DataFrame, alpha: float
) -> tuple[float, float]:
    cov = ewma_cov(window)
    d = sensitivities(book, state, list(window.columns), window.std())
    sigma = float(np.sqrt(d @ cov @ d))
    z = stats.norm.ppf(alpha)
    return z * sigma, sigma * stats.norm.pdf(z) / (1 - alpha)


def monte_carlo(
    book: list[dict], state: State, window: pd.DataFrame, n: int = MC_PATHS, seed: int = SEED
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    cov = ewma_cov(window)
    chol = np.linalg.cholesky(cov + 1e-14 * np.eye(len(cov)))
    g = rng.standard_normal((n, len(cov))) @ chol.T
    w = rng.chisquare(MC_NU, n) / MC_NU
    t = g / np.sqrt(w)[:, None] * np.sqrt((MC_NU - 2) / MC_NU)  # unit-variance Student-t
    return revalue(book, state, to_shocks(t, list(window.columns)))
