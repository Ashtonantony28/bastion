"""Vanilla fixed-for-floating interest rate swaps, single curve.

Times are year fractions from the valuation date; coupons are paid every 1/freq years on both
legs with accrual 1/freq. A payer swap pays fixed and receives floating. The floating coupon for
period j is fixed at its reset date T_{j-1} at the simple rate implied by P(T_{j-1}, T_j), so the
floating leg is worth N * (P(t, T_j) / P(T_{j-1}, T_j) - P(t, T_n)) between resets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml
from numpy.typing import NDArray

from bastion.alm.curves import ZeroCurve
from bastion.market.ccr.hull_white import HullWhite

EPS = 1e-9
BOOK_DIR = Path(__file__).resolve().parents[1] / "portfolios"

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Swap:
    name: str
    notional: float
    fixed_rate: float
    start: float
    end: float
    payer: bool
    freq: int = 2
    currency: str = "USD"

    def __post_init__(self) -> None:
        periods = (self.end - self.start) * self.freq
        if abs(periods - round(periods)) > EPS or periods < 1:
            raise ValueError(f"{self.name}: tenor must be a whole number of periods")

    @property
    def sign(self) -> float:
        return 1.0 if self.payer else -1.0

    @property
    def pay_times(self) -> Array:
        return np.arange(self.start + 1.0 / self.freq, self.end + EPS, 1.0 / self.freq)

    @property
    def reset_times(self) -> Array:
        return self.pay_times - 1.0 / self.freq

    @property
    def accruals(self) -> Array:
        return np.full(len(self.pay_times), 1.0 / self.freq)

    def annuity(self, curve: ZeroCurve) -> float:
        return float(self.accruals @ curve.df(self.pay_times))

    def par_rate(self, curve: ZeroCurve) -> float:
        float_leg = float(curve.df(self.start) - curve.df(self.end))
        return float_leg / self.annuity(curve)

    def price(self, curve: ZeroCurve) -> float:
        """Value at t = 0 to the holder (forward-starting or spot-starting)."""
        float_leg = float(curve.df(self.start) - curve.df(self.end))
        fixed_leg = self.fixed_rate * self.annuity(curve)
        return self.sign * self.notional * (float_leg - fixed_leg)

    def value_paths(self, model: HullWhite, grid: Array, x: Array) -> Array:
        """(paths, len(grid)) values under the model; every reset time must lie on the grid.

        A coupon paid exactly at t is treated as settled (not part of the value at t).
        """
        n, out = x.shape[0], np.zeros((x.shape[0], len(grid)))
        pay, resets, tau = self.pay_times, self.reset_times, 1.0 / self.freq
        index = {round(t, 9): k for k, t in enumerate(grid)}
        for k, t in enumerate(grid):
            if t >= self.end - EPS:
                continue
            xt = x[:, k][:, None]
            if t < self.start - EPS:
                p = model.bond(t, np.concatenate([[self.start], pay]), xt)
                float_leg = p[:, 0] - p[:, -1]
                fixed_leg = self.fixed_rate * tau * p[:, 1:].sum(axis=1)
            else:
                j = int(np.searchsorted(pay, t + EPS))
                kr = index.get(round(float(resets[j]), 9))
                if kr is None:
                    raise ValueError(f"{self.name}: reset {resets[j]} not on the grid")
                p_reset = model.bond(float(resets[j]), pay[j], x[:, kr])
                p = model.bond(t, pay[j:], xt)
                float_leg = p[:, 0] / p_reset - p[:, -1]
                fixed_leg = self.fixed_rate * tau * p.sum(axis=1)
            out[:, k] = self.sign * self.notional * (float_leg - fixed_leg)
        assert out.shape[0] == n
        return out


def load_netting_set(name: str = "ccr_netting_set") -> tuple[dict, list[Swap]]:
    doc = yaml.safe_load((BOOK_DIR / f"{name}.yaml").read_text())
    swaps = [Swap(**s) for s in doc["swaps"]]
    return doc, swaps
