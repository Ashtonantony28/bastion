"""Exposure profiles, netting, variation margin and CVA.

Metric definitions follow Basel CRE53 (IMM): EE(t) = E[max(V(t), 0)], EPE = time average of EE
over the first year, effective EE is EE made non-decreasing, EEPE = time average of effective EE
over the first year, and the IMM exposure is alpha * EEPE with alpha = 1.4. PFE is a quantile of
the exposure distribution. Expectations are taken under the simulation (risk-neutral) measure;
discounted EE is E[D(0,t) max(V(t), 0)].

Variation margin (CSA): collateral held at t is the margin call made on the value one margin
period of risk earlier, C(t) = max(V(t - MPOR) - H, 0) - max(-V(t - MPOR) - H, 0) for a
two-way threshold H, ignoring the minimum transfer amount and cash flows inside the MPOR.

CVA (unilateral, independent exposure and default): CVA = LGD * sum_k DEE(t_k) * PD(t_{k-1}, t_k)
with a flat hazard rate lambda = s / LGD from the counterparty's credit spread s.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from bastion.market.ccr.hull_white import HullWhite
from bastion.market.ccr.swap import Swap

ALPHA = 1.4
PFE_Q = 0.975
ONE_YEAR = 1.0
MPOR_DAYS = 10
TRADING_DAYS = 252
STEP = 1.0 / 26  # two-weekly exposure grid

Array = NDArray[np.float64]


def build_grid(
    swaps: Iterable[Swap], horizon: float, step: float = STEP, mpor: float = 0.0
) -> tuple[Array, NDArray[np.intp]]:
    """Simulation grid and the indices of the reporting dates within it.

    The grid holds the regular reporting dates, every swap reset date, and (if mpor > 0) each
    reporting date shifted back by the MPOR so lagged collateral is exact.
    """
    report = np.round(np.arange(0.0, horizon + 1e-9, step), 9)
    pts = set(report.tolist())
    for s in swaps:
        pts.update(np.round(s.reset_times, 9).tolist())
    if mpor > 0:
        pts.update(np.round(report[report >= mpor] - mpor, 9).tolist())
    grid = np.array(sorted(p for p in pts if 0.0 <= p <= horizon), dtype=float)
    idx = np.searchsorted(grid, report)
    return grid, idx


@dataclass
class Simulation:
    grid: Array
    report_idx: NDArray[np.intp]
    df: Array  # (n, len(grid))
    values: dict[str, Array]  # trade -> (n, len(grid))

    @property
    def times(self) -> Array:
        return self.grid[self.report_idx]

    def netted(self, names: Iterable[str] | None = None) -> Array:
        keys = list(self.values) if names is None else list(names)
        return np.sum([self.values[k] for k in keys], axis=0)


def simulate(
    model: HullWhite, swaps: list[Swap], n: int, seed: int, step: float = STEP, mpor: float = 0.0
) -> Simulation:
    horizon = max(s.end for s in swaps)
    grid, idx = build_grid(swaps, horizon, step, mpor)
    x, df = model.simulate(grid, n, seed)
    return Simulation(grid, idx, df, {s.name: s.value_paths(model, grid, x) for s in swaps})


def collateralised(sim: Simulation, v: Array, threshold: float, mpor: float) -> Array:
    """Exposure value after variation margin, on reporting dates."""
    t = sim.times
    # before one MPOR has elapsed, the collateral held is the margin settled on today's value
    lag = np.searchsorted(sim.grid, np.round(np.maximum(t - mpor, 0.0), 9))
    v_now, v_lag = v[:, sim.report_idx], v[:, lag]
    coll = np.maximum(v_lag - threshold, 0.0) - np.maximum(-v_lag - threshold, 0.0)
    return v_now - coll


@dataclass(frozen=True)
class Profile:
    times: Array
    ee: Array
    pfe: Array
    dee: Array  # discounted EE

    def epe(self, horizon: float = ONE_YEAR) -> float:
        return _time_avg(self.times, self.ee, horizon)

    def eepe(self, horizon: float = ONE_YEAR) -> float:
        return _time_avg(self.times, np.maximum.accumulate(self.ee), horizon)

    @property
    def peak_pfe(self) -> float:
        return float(np.max(self.pfe))


def _time_avg(t: Array, y: Array, horizon: float) -> float:
    m = t <= horizon + 1e-9
    tt, yy = t[m], y[m]
    if len(tt) < 2:
        return float(yy[0])
    dt = np.diff(tt)
    return float((yy[1:] * dt).sum() / dt.sum())


def profile(sim: Simulation, v_report: Array) -> Profile:
    """v_report: (n, reporting dates) exposure values (netted or collateralised)."""
    e = np.maximum(v_report, 0.0)
    return Profile(
        times=sim.times,
        ee=e.mean(axis=0),
        pfe=np.quantile(e, PFE_Q, axis=0),
        dee=(sim.df[:, sim.report_idx] * e).mean(axis=0),
    )


def no_netting(sim: Simulation) -> Array:
    """Sum of trade-level positive exposures, expressed as an exposure value per path."""
    return np.sum([np.maximum(v[:, sim.report_idx], 0.0) for v in sim.values.values()], axis=0)


def survival(t: Array, spread: float, lgd: float) -> Array:
    return np.exp(-spread / lgd * np.asarray(t, dtype=float))


def cva(times: Array, dee: Array, spread: float, lgd: float) -> float:
    """Right-endpoint rule on the exposure dates."""
    s = survival(times, spread, lgd)
    return float(lgd * (dee[1:] * (s[:-1] - s[1:])).sum())


def cva_mc_se(sim: Simulation, v_report: Array, spread: float, lgd: float) -> tuple[float, float]:
    """CVA and its Monte Carlo standard error (pathwise estimator)."""
    s = survival(sim.times, spread, lgd)
    dpd = s[:-1] - s[1:]
    pathwise = lgd * (
        sim.df[:, sim.report_idx][:, 1:] * np.maximum(v_report[:, 1:], 0.0) * dpd
    ).sum(axis=1)
    return float(pathwise.mean()), float(pathwise.std(ddof=1) / np.sqrt(len(pathwise)))
