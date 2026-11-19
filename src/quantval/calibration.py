"""PD calibration tests per rating grade.

- One-sided binomial test: p-value = P(X >= defaults | n, pd). Small values mean the PD is
  underestimated (BCBS WP14, 2005, "Studies on the Validation of Internal Rating Systems").
- Jeffreys test: p-value = Beta(d + 1/2, n - d + 1/2).cdf(pd), the test the ECB prescribes in its
  instructions for reporting the validation results of IRB models (2019).
"""

from __future__ import annotations

from scipy import stats


def _check(defaults: int, n: int, pd: float) -> None:
    if not 0 <= defaults <= n or n <= 0:
        raise ValueError("need 0 <= defaults <= n and n > 0")
    if not 0.0 < pd < 1.0:
        raise ValueError("pd must be in (0, 1)")


def binomial_test(defaults: int, n: int, pd: float) -> float:
    _check(defaults, n, pd)
    return float(stats.binom.sf(defaults - 1, n, pd))


def jeffreys_test(defaults: int, n: int, pd: float) -> float:
    _check(defaults, n, pd)
    return float(stats.beta.cdf(pd, defaults + 0.5, n - defaults + 0.5))
