"""Economic value of equity (EVE) and 12-month net interest income (NII) sensitivity.

EVE: present value of rate-sensitive assets minus liabilities on the bootstrapped Treasury zero
curve, base vs each BCBS shock (bastion.alm.shocks). The BCBS supervisory outlier test flags a
decline in EVE larger than 15% of Tier 1 capital (d368, Principle 12).

NII: repricing-gap method over one year. A position repricing at time t < 1 earns the shock for
the remaining (1 - t) of the year; non-maturity deposits reprice immediately with their beta
(pass-through) instead of fully. Parallel shocks only, as in the BCBS standard.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bastion.alm.balance_sheet import OVERNIGHT, Position
from bastion.alm.curves import ZeroCurve
from bastion.alm.shocks import SCENARIOS, USD_PARALLEL, shock

OUTLIER_THRESHOLD = 0.15
NII_HORIZON = 1.0


@dataclass(frozen=True)
class EveResult:
    base_eve: float
    delta: dict[str, float]  # scenario -> change in EVE ($000)

    def worst(self) -> tuple[str, float]:
        name = min(self.delta, key=lambda k: self.delta[k])
        return name, self.delta[name]


def pv(t: np.ndarray, amt: np.ndarray, curve: ZeroCurve, scenario: str | None = None) -> float:
    s = shock(scenario, t) if scenario else 0.0
    return float(np.sum(amt * curve.df(t, s)))


def _eve_value(pos: Position, curve: ZeroCurve, scenario: str | None) -> float:
    return (
        pv(pos.assets_t, pos.assets_amt, curve, scenario)
        - pv(pos.liabs_t, pos.liabs_amt, curve, scenario)
        - pv(pos.nmd_t, pos.nmd_amt, curve, scenario)
    )


def eve(pos: Position, curve: ZeroCurve) -> EveResult:
    base = _eve_value(pos, curve, None)
    delta = {sc: _eve_value(pos, curve, sc) - base for sc in SCENARIOS}
    return EveResult(base, delta)


def outlier_ratio(pos: Position, res: EveResult) -> float:
    """Worst EVE decline as a share of Tier 1 (positive = loss)."""
    return -res.worst()[1] / pos.tier1 if pos.tier1 > 0 else float("nan")


def _reprice_weight(t: np.ndarray) -> np.ndarray:
    return np.clip(NII_HORIZON - t, 0.0, None)


def nii_sensitivity(pos: Position, up: bool = True) -> float:
    """Change in 12-month NII ($000) for a +/-200bp parallel shock."""
    d = USD_PARALLEL if up else -USD_PARALLEL
    a = float(np.sum(pos.assets_amt * _reprice_weight(pos.assets_t))) * d
    contractual = float(np.sum(pos.liabs_amt * _reprice_weight(pos.liabs_t))) * d
    nmd = pos.nmd_beta_weighted * d * NII_HORIZON
    return a - contractual - nmd


__all__ = ["OVERNIGHT", "EveResult", "eve", "nii_sensitivity", "outlier_ratio", "pv"]
