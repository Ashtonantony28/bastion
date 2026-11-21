"""One-factor Hull-White model fitted to today's zero curve (G1++ form, Brigo & Mercurio ch. 3).

r(t) = x(t) + phi(t), dx = -a x dt + sigma dW, x(0) = 0; phi is chosen so that the model
reproduces the initial discount curve exactly. Everything here is closed form:

- zero-coupon bond P(t, T | x) (B&M eq. 3.39 in G1++ form);
- European put on a zero-coupon bond (B&M eq. 3.41) and, by Jamshidian's decomposition, a
  European payer swaption. The swaption price is the analytic discounted EE of a swap at a reset
  date, which is how the Monte Carlo exposure engine is validated;
- exact joint simulation of (x, integral of x), so path discount factors carry no
  discretisation bias (Glasserman 2004, sec. 3.3.1).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import brentq, least_squares
from scipy.stats import norm

from bastion.alm.curves import ZeroCurve

TRADING_DAYS = 252
A_BOUNDS = (1e-3, 1.0)
SERIES_U = 1e-2  # below this a*tau, V uses its Taylor series (error < u^6)
JAMSHIDIAN_BRACKET = 1.0  # x* is searched in [-1, 1] (a 100% short-rate move)

Array = NDArray[np.float64]


@dataclass(frozen=True)
class HullWhite:
    a: float
    sigma: float
    curve: ZeroCurve

    def p0(self, t: ArrayLike) -> Array:
        return self.curve.df(t)

    def b(self, t: ArrayLike, big_t: ArrayLike) -> Array:
        tau = np.asarray(big_t, dtype=float) - np.asarray(t, dtype=float)
        return (1.0 - np.exp(-self.a * tau)) / self.a

    def v(self, t: ArrayLike, big_t: ArrayLike) -> Array:
        """Variance of the integral of x over [t, T] given x(t)."""
        a, tau = self.a, np.asarray(big_t, dtype=float) - np.asarray(t, dtype=float)
        u = a * tau
        # f(u) = u + 2(e^-u - 1) - (e^-2u - 1)/2 cancels to O(u^3); use its series for small u
        exact = u + 2.0 * np.expm1(-u) - 0.5 * np.expm1(-2.0 * u)
        series = u**3 / 3.0 - u**4 / 4.0 + 7.0 * u**5 / 60.0
        return (self.sigma**2 / a**3) * np.where(u < SERIES_U, series, exact)

    def bond(self, t: float, big_t: ArrayLike, x: ArrayLike) -> Array:
        """P(t, T) given x(t); broadcasts over x (paths) and T."""
        big_t = np.asarray(big_t, dtype=float)
        amp = (
            self.p0(big_t)
            / self.p0(t)
            * np.exp(0.5 * (self.v(t, big_t) - self.v(0.0, big_t) + self.v(0.0, t)))
        )
        return amp * np.exp(-self.b(t, big_t) * np.asarray(x, dtype=float))

    def zbp(self, expiry: float, maturity: float, strike: float) -> float:
        """Time-0 price of a European put (expiry T) on a zero-coupon bond maturing at S."""
        a = self.a
        sp = (
            self.sigma
            * np.sqrt((1.0 - np.exp(-2.0 * a * expiry)) / (2.0 * a))
            * float(self.b(expiry, maturity))
        )
        p_t, p_s = float(self.p0(expiry)), float(self.p0(maturity))
        h = np.log(p_s / (p_t * strike)) / sp + 0.5 * sp
        return float(strike * p_t * norm.cdf(-h + sp) - p_s * norm.cdf(-h))

    def payer_swaption(
        self, expiry: float, pay_times: Array, accruals: Array, rate: float
    ) -> float:
        """Jamshidian: payer swaption = sum of puts on the coupon bond's zero components (unit notional)."""
        c = rate * np.asarray(accruals, dtype=float)
        c[-1] += 1.0

        def coupon_bond(x: float) -> float:
            return float(c @ self.bond(expiry, pay_times, x)) - 1.0

        x_star = brentq(coupon_bond, -JAMSHIDIAN_BRACKET, JAMSHIDIAN_BRACKET, xtol=1e-14)
        strikes = self.bond(expiry, pay_times, x_star)
        return float(
            sum(
                ci * self.zbp(expiry, ti, ki)
                for ci, ti, ki in zip(c, pay_times, strikes, strict=True)
            )
        )

    def simulate(self, times: Array, n: int, seed: int) -> tuple[Array, Array]:
        """Paths of x and of the discount factor D(0, t) on `times` (first time must be 0).

        Uses antithetic pairs, so n must be even.
        """
        if times[0] != 0.0 or n % 2:
            raise ValueError("times must start at 0 and n must be even")
        a, s = self.a, self.sigma
        rng = np.random.default_rng(seed)
        k = len(times)
        x = np.zeros((n, k))
        integral = np.zeros((n, k))
        for j in range(1, k):
            h = times[j] - times[j - 1]
            e = np.exp(-a * h)
            var_x = s**2 / (2 * a) * (1 - e**2)
            var_i = float(self.v(0.0, h))
            cov = s**2 / (2 * a**2) * (1 - e) ** 2
            chol = np.linalg.cholesky(np.array([[var_x, cov], [cov, var_i]]))
            half = rng.standard_normal((n // 2, 2))
            z = np.vstack([half, -half]) @ chol.T
            integral[:, j] = integral[:, j - 1] + x[:, j - 1] * (1 - e) / a + z[:, 1]
            x[:, j] = x[:, j - 1] * e + z[:, 0]
        df = self.p0(times)[None, :] * np.exp(-0.5 * self.v(0.0, times)[None, :] - integral)
        return x, df


def fit_historical_vol(zero_changes: NDArray[np.float64], nodes: Array) -> tuple[float, float]:
    """Fit (a, sigma) so that the model's zero-rate vol term structure sigma*B(tau)/tau matches
    the annualised standard deviation of daily zero-rate changes at each node.

    This is a historical-measure calibration: free swaption volatilities are not available
    (stated in the M5 limitations).
    """
    obs = np.std(zero_changes, axis=0, ddof=1) * np.sqrt(TRADING_DAYS)

    def resid(p: Array) -> Array:
        a, s = p
        return s * (1 - np.exp(-a * nodes)) / (a * nodes) - obs

    fit = least_squares(
        resid, x0=[0.05, float(obs[0])], bounds=([A_BOUNDS[0], 1e-5], [A_BOUNDS[1], 0.1])
    )
    return float(fit.x[0]), float(fit.x[1])
