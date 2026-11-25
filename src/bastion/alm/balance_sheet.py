"""Map a bank's Call Report ALM fields to rate-sensitive cash-flow buckets.

Each Call Report repricing/maturity bucket becomes a zero-coupon position at the bucket
midpoint (years). This is the simplified standardised approach: it ignores amortisation and
prepayment inside a bucket, so it overstates duration for amortising mortgages and MBS. The M6
backtest (bastion.alm.backtest) measures how much that matters against reported fair values.

Non-maturity deposits (NMDs) are split into a core part, slotted evenly over (0, 2M] so the
average repricing maturity is M, and a non-core part that reprices overnight. Defaults are the
BCBS d368 Table 2 caps (retail transactional 90% core / 5y, retail non-transactional 70% /
4.5y, wholesale 50% / 4y); insured deposits are treated as retail and uninsured as wholesale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

OVERNIGHT = 1.0 / 365.0
COVERAGE_MIN = 0.90  # securities buckets must cover >= 90% of SC (see dbt reconciliation test)
NMD_SLICES = 10

# (field, midpoint years). RC-B Memo 2: other mortgage securities split at 3 years only.
SECURITIES = [
    ("scnm3les", 0.125), ("scnm3t12", 0.625), ("scnm1t3", 2.0), ("scnm3t5", 4.0), ("scnm5t15", 10.0), ("scnmov15", 20.0),
    ("scpt3les", 0.125), ("scpt3t12", 0.625), ("scpt1t3", 2.0), ("scpt3t5", 4.0), ("scpt5t15", 10.0), ("scptov15", 20.0),
    ("sco3yles", 1.5), ("scoov3y", 7.0),
]  # fmt: skip
LOANS = [
    ("lnrs3les", 0.125), ("lnrs3t12", 0.625), ("lnrs1t3", 2.0), ("lnrs3t5", 4.0), ("lnrs5t15", 10.0), ("lnrsov15", 20.0),
    ("lnot3les", 0.125), ("lnot3t12", 0.625), ("lnot1t3", 2.0), ("lnot3t5", 4.0), ("lnot5t15", 10.0), ("lnotov15", 20.0),
]  # fmt: skip
# Behavioural variant: amortising mortgage pass-throughs, CMOs and residential loans placed at a
# conventional expected average life instead of the contractual bucket midpoint (pre-specified,
# not fitted; tested out of sample in bastion.alm.backtest).
BEHAVIOURAL_LIFE = {
    "scpt1t3": 1.5, "scpt3t5": 3.0, "scpt5t15": 5.0, "scptov15": 7.0,
    "sco3yles": 1.25, "scoov3y": 4.0,
    "lnrs1t3": 1.5, "lnrs3t5": 3.0, "lnrs5t15": 5.0, "lnrsov15": 7.0,
}  # fmt: skip


def behavioural(spec: list[tuple[str, float]]) -> list[tuple[str, float]]:
    return [(f, BEHAVIOURAL_LIFE.get(f, m)) for f, m in spec]


TIME_DEPOSITS = [
    ("cd3less", 0.125), ("cd3t12s", 0.625), ("cd1t3s", 2.0), ("cdov3s", 4.0),
    ("cd3les", 0.125), ("cd3t12", 0.625), ("cd1t3", 2.0), ("cdov3", 4.0),
]  # fmt: skip
BORROWINGS = [
    ("otbfh1l", 0.5), ("otbfh1t3", 2.0), ("otbfh3t5", 4.0), ("otbfhov5", 7.0),
    ("otbot1l", 0.5), ("otbot1t3", 2.0), ("otbot3t5", 4.0), ("otbotov5", 7.0),
]  # fmt: skip


@dataclass(frozen=True)
class NmdAssumptions:
    retail_transactional_core: float = 0.90
    retail_transactional_maturity: float = 5.0
    retail_other_core: float = 0.70
    retail_other_maturity: float = 4.5
    wholesale_core: float = 0.50
    wholesale_maturity: float = 4.0
    # NII pass-through (deposit beta) for the 12-month NII measure
    retail_beta: float = 0.35
    wholesale_beta: float = 0.70


BCBS_CAPS = NmdAssumptions()
# A run-prone view: uninsured deposits are not core at all and reprice fully.
RUN_PRONE = NmdAssumptions(wholesale_core=0.0, wholesale_beta=1.0)


@dataclass
class Position:
    """Rate-sensitive positions in $000: arrays of (time in years, amount)."""

    cert: int
    repdte: pd.Timestamp
    assets_t: np.ndarray = field(default_factory=lambda: np.zeros(0))
    assets_amt: np.ndarray = field(default_factory=lambda: np.zeros(0))
    liabs_t: np.ndarray = field(
        default_factory=lambda: np.zeros(0)
    )  # contractual: time deposits, borrowings, repo
    liabs_amt: np.ndarray = field(default_factory=lambda: np.zeros(0))
    nmd_t: np.ndarray = field(default_factory=lambda: np.zeros(0))  # behavioural NMD slices
    nmd_amt: np.ndarray = field(default_factory=lambda: np.zeros(0))
    securities_t: np.ndarray = field(default_factory=lambda: np.zeros(0))
    securities_amt: np.ndarray = field(default_factory=lambda: np.zeros(0))
    nmd: float = 0.0
    nmd_beta_weighted: float = 0.0
    securities_coverage: float = float("nan")
    tier1: float = float("nan")


def _g(row: pd.Series, f: str) -> float:
    v = row.get(f)
    return 0.0 if v is None or pd.isna(v) else float(v)


def _buckets(row: pd.Series, spec: list[tuple[str, float]]) -> tuple[np.ndarray, np.ndarray]:
    t = np.array([m for _, m in spec], dtype=float)
    a = np.array([_g(row, f) for f, _ in spec], dtype=float)
    return t, a


def _slot(amount: float, maturity: float) -> tuple[np.ndarray, np.ndarray]:
    """Spread ``amount`` evenly over (0, 2*maturity] so its average maturity is ``maturity``."""
    edges = np.linspace(0.0, 2.0 * maturity, NMD_SLICES + 1)
    mids = 0.5 * (edges[:-1] + edges[1:])
    return mids, np.full(NMD_SLICES, amount / NMD_SLICES)


def build_position(
    row: pd.Series, nmd: NmdAssumptions = BCBS_CAPS, behavioural_life: bool = True
) -> Position:
    sec_spec = behavioural(SECURITIES) if behavioural_life else SECURITIES
    loan_spec = behavioural(LOANS) if behavioural_life else LOANS
    st, sa = _buckets(row, sec_spec)
    sc = _g(row, "sc")
    cov = float(sa.sum()) / sc if sc > 0 else float("nan")
    lt, la = _buckets(row, loan_spec)
    cash = _g(row, "chbal")
    assets_t = np.concatenate([[OVERNIGHT], st, lt])
    assets_amt = np.concatenate([[cash], sa, la])

    tdt, tda = _buckets(row, TIME_DEPOSITS)
    bt, ba = _buckets(row, BORROWINGS)
    dep = _g(row, "dep")
    time_dep = tda.sum()
    nmd_total = max(dep - time_dep, 0.0)
    uninsured = min(_g(row, "depuna"), dep)
    wholesale = nmd_total * (uninsured / dep) if dep > 0 else 0.0
    retail = nmd_total - wholesale
    trn_share = min(_g(row, "trn") / nmd_total, 1.0) if nmd_total > 0 else 0.0
    parts = [
        (retail * trn_share, nmd.retail_transactional_core, nmd.retail_transactional_maturity),
        (retail * (1 - trn_share), nmd.retail_other_core, nmd.retail_other_maturity),
        (wholesale, nmd.wholesale_core, nmd.wholesale_maturity),
    ]
    nt_list: list[np.ndarray] = []
    na_list: list[np.ndarray] = []
    for amount, core, mat in parts:
        if amount <= 0:
            continue
        t_core, a_core = _slot(amount * core, mat)
        nt_list += [t_core, np.array([OVERNIGHT])]
        na_list += [a_core, np.array([amount * (1 - core)])]
    beta_w = retail * nmd.retail_beta + wholesale * nmd.wholesale_beta
    return Position(
        cert=int(row["cert"]),
        repdte=pd.Timestamp(row["repdte"]),
        assets_t=assets_t,
        assets_amt=assets_amt,
        liabs_t=np.concatenate([tdt, bt, [OVERNIGHT]]),
        liabs_amt=np.concatenate([tda, ba, [_g(row, "frepp")]]),
        nmd_t=np.concatenate(nt_list) if nt_list else np.zeros(0),
        nmd_amt=np.concatenate(na_list) if na_list else np.zeros(0),
        securities_t=st,
        securities_amt=sa,
        nmd=nmd_total,
        nmd_beta_weighted=beta_w,
        securities_coverage=cov,
        tier1=_g(row, "rbct1j"),
    )
