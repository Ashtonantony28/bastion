"""Zero curve bootstrapped from US Treasury par yields.

Treasury publishes bond-equivalent (semi-annual) par yields. Bills (<= 1 year) are treated as
zero-coupon at their quoted yield; coupon tenors are bootstrapped on a semi-annual grid from
linearly interpolated par yields. Zero rates are returned continuously compounded, linearly
interpolated in maturity and flat-extrapolated beyond the ends.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

COUPON_FREQ = 2
BILL_MAX_YEARS = 1.0


@dataclass(frozen=True)
class ZeroCurve:
    t: NDArray[np.float64]  # years
    z: NDArray[np.float64]  # continuously compounded zero rates (decimal)

    def zero(self, t: ArrayLike) -> NDArray[np.float64]:
        return np.interp(np.asarray(t, dtype=float), self.t, self.z)

    def df(self, t: ArrayLike, shock: ArrayLike = 0.0) -> NDArray[np.float64]:
        tt = np.asarray(t, dtype=float)
        return np.exp(-(self.zero(tt) + np.asarray(shock, dtype=float)) * tt)


def bootstrap(tenor_years: ArrayLike, par_yield_pct: ArrayLike) -> ZeroCurve:
    tn = np.asarray(tenor_years, dtype=float)
    py = np.asarray(par_yield_pct, dtype=float) / 100.0
    order = np.argsort(tn)
    tn, py = tn[order], py[order]
    out_t: list[float] = []
    out_z: list[float] = []
    # bills: zero-coupon, bond-equivalent quote -> continuous
    for t, y in zip(tn, py, strict=True):
        if t <= BILL_MAX_YEARS:
            out_t.append(t)
            out_z.append(COUPON_FREQ * np.log1p(y / COUPON_FREQ))
    # coupon bonds on a semi-annual grid
    grid = np.arange(1.0 / COUPON_FREQ, tn.max() + 1e-9, 1.0 / COUPON_FREQ)
    dfs: dict[float, float] = {}
    for g in grid:
        if g <= BILL_MAX_YEARS and out_t:
            dfs[g] = float(np.exp(-np.interp(g, out_t, out_z) * g))
            continue
        c = float(np.interp(g, tn, py)) / COUPON_FREQ
        prior = sum(dfs[k] for k in dfs if k < g - 1e-9)
        dfs[g] = (1.0 - c * prior) / (1.0 + c)
        out_t.append(g)
        out_z.append(-np.log(dfs[g]) / g)
    t_arr, z_arr = np.asarray(out_t), np.asarray(out_z)
    keep = np.argsort(t_arr)
    t_arr, z_arr = t_arr[keep], z_arr[keep]
    _, uniq = np.unique(t_arr, return_index=True)
    return ZeroCurve(t_arr[uniq], z_arr[uniq])
