"""Liquidity metrics from public Call Report data: LCR and NSFR proxies and a deposit-run
survival horizon.

These are *proxies*. The real LCR (12 CFR 249) and NSFR need counterparty, encumbrance and
contractual cash-flow detail that the Call Report does not publish, and they applied in full only
to the largest banks (SVB was not subject to the LCR in 2022). Factors below follow the US rule's
categories; where the Call Report cannot separate a category, the assumption is named and it is
a parameter, so the report can show sensitivity to it.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DAYS = 30
MONTHS_IN_YEAR = 12


@dataclass(frozen=True)
class LcrAssumptions:
    insured_outflow: float = 0.05  # blend of stable (3%) and less-stable (10%) retail
    uninsured_outflow: float = 0.40  # non-operational wholesale, non-financial
    l2a_haircut: float = 0.15
    l2b_haircut: float = 0.50
    l2_cap: float = 0.40  # level 2 at most 40% of HQLA
    l2b_cap: float = 0.15
    inflow_rate: float = 0.50
    inflow_cap: float = 0.75


def _g(row: pd.Series, f: str) -> float:
    v = row.get(f)
    return 0.0 if v is None or pd.isna(v) else float(v)


def fv_ratio(row: pd.Series) -> float:
    """Fair value / book value of debt securities (HQLA counts at fair value)."""
    book = _g(row, "scaa") + _g(row, "scha")
    fv = _g(row, "scaf") + _g(row, "schf")
    return fv / book if book > 0 else 1.0


def securities_fair_value(row: pd.Series) -> float:
    return _g(row, "scaf") + _g(row, "schf")


def hqla(row: pd.Series, a: LcrAssumptions = LcrAssumptions()) -> dict[str, float]:
    r = fv_ratio(row)
    agency_mbs = max(
        sum(
            _g(row, f)
            for f in (
                "scpt3les",
                "scpt3t12",
                "scpt1t3",
                "scpt3t5",
                "scpt5t15",
                "scptov15",
                "sco3yles",
                "scoov3y",
            )
        )
        - _g(row, "scgnm"),
        0.0,
    )
    l1 = _g(row, "chbal") + r * (_g(row, "scust") + _g(row, "scgnm"))
    l2a = r * agency_mbs * (1 - a.l2a_haircut)
    l2b = r * _g(row, "scmuni") * (1 - a.l2b_haircut)
    # caps (simplified form of the US rule's adjusted-excess formula)
    l2b = min(l2b, a.l2b_cap / (1 - a.l2b_cap) * (l1 + l2a))
    l2 = min(l2a + l2b, a.l2_cap / (1 - a.l2_cap) * l1)
    return {"l1": l1, "l2": l2, "total": l1 + l2}


def lcr(row: pd.Series, a: LcrAssumptions = LcrAssumptions()) -> float:
    dep = _g(row, "dep")
    unins = min(_g(row, "depuna"), dep)
    ins = dep - unins
    short_borrow = _g(row, "frepp") + (_g(row, "otbfh1l") + _g(row, "otbot1l")) / MONTHS_IN_YEAR
    outflows = ins * a.insured_outflow + unins * a.uninsured_outflow + short_borrow
    loans_30d = (_g(row, "lnrs3les") + _g(row, "lnot3les")) / 3.0
    inflows = min(loans_30d * a.inflow_rate, a.inflow_cap * outflows)
    net = outflows - inflows
    return hqla(row, a)["total"] / net if net > 0 else float("inf")


def nsfr(row: pd.Series) -> float:
    """Available / required stable funding (US NSFR categories, simplified)."""
    dep = _g(row, "dep")
    unins = min(_g(row, "depuna"), dep)
    ins = dep - unins
    long_borrow = sum(
        _g(row, f) for f in ("otbfh1t3", "otbfh3t5", "otbfhov5", "otbot1t3", "otbot3t5", "otbotov5")
    )
    short_fhlb = _g(row, "otbfh1l")
    asf = _g(row, "eqtot") + 0.90 * ins + 0.50 * unins + long_borrow + 0.25 * short_fhlb
    r = fv_ratio(row)
    secs_fv = securities_fair_value(row)
    l1_secs = r * (_g(row, "scust") + _g(row, "scgnm"))
    other_secs = max(secs_fv - l1_secs, 0.0)
    loans = _g(row, "lnlsgr")
    resi = _g(row, "lnreres")
    other_assets = max(_g(row, "asset") - _g(row, "chbal") - _g(row, "sc") - loans, 0.0)
    rsf = (
        0.05 * l1_secs
        + 0.15 * other_secs
        + 0.65 * resi
        + 0.85 * max(loans - resi, 0.0)
        + other_assets
    )
    return asf / rsf if rsf > 0 else float("inf")


@dataclass(frozen=True)
class RunScenario:
    name: str
    daily_uninsured: list[float]  # fraction of initial uninsured deposits leaving each day
    daily_insured: float  # fraction of initial insured deposits leaving per day
    securities_haircut: float  # fire-sale / repo haircut on fair value


RUNS = [
    RunScenario("slow (2008-style): 1%/day of uninsured", [0.01] * 90, 0.001, 0.02),
    RunScenario(
        "LCR-calibrated: 40% of uninsured over 30 days", [0.40 / DAYS] * DAYS, 0.05 / DAYS, 0.02
    ),
    RunScenario(
        "SVB-observed: 24% then 57% of deposits in 2 days", [0.24 / 0.86, 0.57 / 0.86], 0.0, 0.05
    ),
]


def survival_days(row: pd.Series, run: RunScenario) -> float:
    """Days until outflows exceed cash plus unencumbered securities at fair value (after haircut).

    Returns the fractional day of exhaustion, or ``inf`` if the bank survives the scenario.
    """
    dep = _g(row, "dep")
    unins = min(_g(row, "depuna"), dep)
    ins = dep - unins
    r = fv_ratio(row)
    unencumbered = max(securities_fair_value(row) - r * _g(row, "scpledge"), 0.0)
    liquid = _g(row, "chbal") + unencumbered * (1 - run.securities_haircut)
    cum = 0.0
    for day, frac in enumerate(run.daily_uninsured, start=1):
        need = min(frac * unins, unins) + run.daily_insured * ins
        if cum + need > liquid:
            return day - 1 + (liquid - cum) / need if need > 0 else float(day)
        cum += need
    return float("inf")


__all__ = [
    "RUNS",
    "LcrAssumptions",
    "RunScenario",
    "fv_ratio",
    "hqla",
    "lcr",
    "nsfr",
    "survival_days",
]
