"""SA-CCR for interest rate derivatives (BCBS 279, March 2014; US rule 12 CFR 217.132(c)).

EAD = alpha * (RC + multiplier * AddOn), alpha = 1.4.
- Adjusted notional d = N * SD, SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05 (S, E in years).
- Maturity factor: unmargined sqrt(min(M, 1)); margined 1.5 * sqrt(MPOR / 1 year).
- Effective notional per currency hedging set aggregates the three maturity buckets
  (<1y, 1-5y, >5y by end date) with correlations 1.4 / 1.4 / 0.6 (BCBS 279 para 166).
- AddOn_IR = 0.5% * sum over hedging sets of effective notional.
- Multiplier = min(1, 0.05 + 0.95 * exp((V - C) / (2 * 0.95 * AddOn))).
- RC unmargined max(V - C, 0); margined max(V - C, TH + MTA - NICA, 0).
Tested against BCBS 279 Annex 4, Example 1 (EAD 569).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

ALPHA = 1.4
SF_IR = 0.005
SD_RATE = 0.05
FLOOR = 0.05
OPTION_VOL_IR = 0.5
BUCKET_EDGES = (1.0, 5.0)
DAYS_PER_YEAR = 250  # BCBS 279 para 164 uses 250 business days


@dataclass(frozen=True)
class IrTrade:
    notional: float
    start: float  # S, years
    end: float  # E, years
    delta: float  # +1 long the floating rate (payer swap), -1 short; options per para 159
    mtm: float
    currency: str = "USD"
    maturity: float | None = None  # M; defaults to end

    @property
    def supervisory_duration(self) -> float:
        return (np.exp(-SD_RATE * self.start) - np.exp(-SD_RATE * self.end)) / SD_RATE

    @property
    def adjusted_notional(self) -> float:
        return self.notional * self.supervisory_duration

    @property
    def bucket(self) -> int:
        return 1 if self.end < BUCKET_EDGES[0] else (2 if self.end <= BUCKET_EDGES[1] else 3)


def option_delta(
    kind: str,
    bought: bool,
    underlying: float,
    strike: float,
    expiry: float,
    vol: float = OPTION_VOL_IR,
) -> float:
    """Supervisory delta for options (para 159)."""
    d1 = (np.log(underlying / strike) + 0.5 * vol**2 * expiry) / (vol * np.sqrt(expiry))
    d = norm.cdf(d1) if kind == "call" else -norm.cdf(-d1)
    return float(d if bought else -d)


def maturity_factor(m: float, margined: bool, mpor_days: int = 10) -> float:
    if margined:
        return 1.5 * np.sqrt(mpor_days / DAYS_PER_YEAR)
    return float(np.sqrt(min(m, 1.0)))


def effective_notional(d: Iterable[float]) -> float:
    d1, d2, d3 = d
    return float(np.sqrt(d1**2 + d2**2 + d3**2 + 1.4 * d1 * d2 + 1.4 * d2 * d3 + 0.6 * d1 * d3))


def addon_ir(
    trades: list[IrTrade], margined: bool = False, mpor_days: int = 10
) -> tuple[float, dict[str, float]]:
    by_ccy: dict[str, list[float]] = {}
    for tr in trades:
        b = by_ccy.setdefault(tr.currency, [0.0, 0.0, 0.0])
        mf = maturity_factor(
            tr.maturity if tr.maturity is not None else tr.end, margined, mpor_days
        )
        b[tr.bucket - 1] += tr.delta * tr.adjusted_notional * mf
    eff = {c: effective_notional(b) for c, b in by_ccy.items()}
    return SF_IR * sum(eff.values()), eff


def multiplier(v_minus_c: float, addon: float) -> float:
    if addon <= 0:
        return 1.0
    return float(min(1.0, FLOOR + (1 - FLOOR) * np.exp(v_minus_c / (2 * (1 - FLOOR) * addon))))


@dataclass(frozen=True)
class SaCcr:
    rc: float
    addon: float
    multiplier: float
    ead: float
    effective_notional: dict[str, float]


def ead(
    trades: list[IrTrade],
    collateral: float = 0.0,
    margined: bool = False,
    threshold: float = 0.0,
    mta: float = 0.0,
    nica: float = 0.0,
    mpor_days: int = 10,
) -> SaCcr:
    v_c = sum(t.mtm for t in trades) - collateral
    rc = max(v_c, threshold + mta - nica, 0.0) if margined else max(v_c, 0.0)
    add, eff = addon_ir(trades, margined, mpor_days)
    mult = multiplier(v_c, add)
    return SaCcr(rc, add, mult, ALPHA * (rc + mult * add), eff)
