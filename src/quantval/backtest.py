"""VaR backtesting statistics.

- Kupiec (1995), "Techniques for Verifying the Accuracy of Risk Measurement Models", proportion of
  failures likelihood-ratio test.
- BCBS (1996), "Supervisory framework for the use of backtesting in conjunction with the internal
  models approach", traffic-light zones by cumulative binomial probability (green < 95%,
  yellow < 99.99%, red otherwise). For 250 days at 99% this gives green 0-4, yellow 5-9, red 10+.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from scipy import stats

GREEN_CUTOFF = 0.95
RED_CUTOFF = 0.9999


@dataclass(frozen=True)
class KupiecResult:
    exceptions: int
    observations: int
    expected_rate: float
    lr_stat: float
    p_value: float


def kupiec_pof(exceptions: int, observations: int, var_level: float) -> KupiecResult:
    """Kupiec POF test. ``var_level`` is the VaR confidence, e.g. 0.99 (exception rate 1%)."""
    if not 0 <= exceptions <= observations or observations <= 0:
        raise ValueError("need 0 <= exceptions <= observations and observations > 0")
    p = 1.0 - var_level
    x, t = exceptions, observations
    phat = x / t

    def _ll(rate: float) -> float:
        # log-likelihood of x exceptions in t trials; 0*log(0) treated as 0
        a = (t - x) * np.log1p(-rate) if t - x > 0 else 0.0
        b = x * np.log(rate) if x > 0 else 0.0
        return float(a + b)

    lr = -2.0 * (_ll(p) - _ll(phat)) if 0 < phat < 1 else -2.0 * (_ll(p) - 0.0)
    lr = max(lr, 0.0)
    return KupiecResult(x, t, p, lr, float(stats.chi2.sf(lr, df=1)))


class TrafficLight(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


def basel_traffic_light(
    exceptions: int, observations: int = 250, var_level: float = 0.99
) -> TrafficLight:
    cdf = float(stats.binom.cdf(exceptions, observations, 1.0 - var_level))
    if cdf < GREEN_CUTOFF:
        return TrafficLight.GREEN
    if cdf < RED_CUTOFF:
        return TrafficLight.YELLOW
    return TrafficLight.RED
