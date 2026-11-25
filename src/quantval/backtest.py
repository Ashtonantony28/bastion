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


@dataclass(frozen=True)
class ChristoffersenResult:
    lr_ind: float
    p_ind: float
    lr_cc: float
    p_cc: float


def christoffersen(hits: np.ndarray, var_level: float) -> ChristoffersenResult:
    """Christoffersen (1998) independence and conditional-coverage tests on a 0/1 exception
    series. Independence: do exceptions cluster (P(hit | hit yesterday) != P(hit | no hit))?
    Conditional coverage = Kupiec POF + independence, chi-squared with 2 dof."""
    h = np.asarray(hits, dtype=int)
    prev, cur = h[:-1], h[1:]
    n00 = int(((prev == 0) & (cur == 0)).sum())
    n01 = int(((prev == 0) & (cur == 1)).sum())
    n10 = int(((prev == 1) & (cur == 0)).sum())
    n11 = int(((prev == 1) & (cur == 1)).sum())

    def ll(p: float, a: int, b: int) -> float:
        out = 0.0
        if a:
            out += a * np.log1p(-p) if p < 1 else -np.inf
        if b:
            out += b * np.log(p) if p > 0 else -np.inf
        return float(out)

    pi = (n01 + n11) / max(1, n00 + n01 + n10 + n11)
    pi01 = n01 / max(1, n00 + n01)
    pi11 = n11 / max(1, n10 + n11)
    lr_ind = max(
        -2.0 * (ll(pi, n00 + n10, n01 + n11) - ll(pi01, n00, n01) - ll(pi11, n10, n11)), 0.0
    )
    pof = kupiec_pof(int(h.sum()), len(h), var_level).lr_stat
    lr_cc = pof + lr_ind
    return ChristoffersenResult(
        lr_ind, float(stats.chi2.sf(lr_ind, 1)), lr_cc, float(stats.chi2.sf(lr_cc, 2))
    )


# Acerbi & Szekely (2014), "Backtesting Expected Shortfall", Z2 test at 97.5%: thresholds for
# 5% and 0.01% significance (their Table 1, approximately stable across distributions).
Z2_YELLOW = -0.70
Z2_RED = -1.80


def acerbi_szekely_z2(
    losses: np.ndarray, var: np.ndarray, es: np.ndarray, es_level: float = 0.975
) -> float:
    """Z2 = 1 - sum(L_t * 1[L_t > VaR_t] / ES_t) / (T * (1 - es_level)); 0 if ES is right,
    negative if realised tail losses exceed the forecast ES. ``var`` is the VaR at ``es_level``."""
    loss, v, e = (np.asarray(x, dtype=float) for x in (losses, var, es))
    hit = loss > v
    return float(1.0 - np.sum(loss[hit] / e[hit]) / (len(loss) * (1.0 - es_level)))
