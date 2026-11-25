"""Out-of-sample check of the EVE bucket model against reported fair values.

For each bank, take its securities repricing buckets at t0, revalue them under the actual
Treasury zero-curve move from t0 to t1, and compare the predicted percentage value change with
the reported change in unrealized gain/loss over the same year, (UGL_t1 - UGL_t0) / book_t0.
Portfolio turnover, spread moves and the passage of time make this noisy bank by bank; the test
is whether the model gets the cross-section and the size right. Two pre-specified duration
mappings are compared (contractual midpoints vs behavioural average lives); neither is fitted.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bastion.alm.balance_sheet import COVERAGE_MIN, SECURITIES, behavioural
from bastion.alm.curves import ZeroCurve

MIN_SECURITIES_K = 100_000  # $100m


def predicted_change(row: pd.Series, c0: ZeroCurve, c1: ZeroCurve, behavioural_life: bool) -> float:
    spec = behavioural(SECURITIES) if behavioural_life else SECURITIES
    t = np.array([m for _, m in spec])
    a = np.array([0.0 if pd.isna(row.get(f)) else float(row[f]) for f, _ in spec])
    if a.sum() <= 0:
        return float("nan")
    dz = c1.zero(t) - c0.zero(t)
    return float(np.sum(a * (np.exp(-dz * t) - 1.0)) / a.sum())


@dataclass
class BacktestResult:
    t0: str
    t1: str
    frame: pd.DataFrame  # cert, observed, pred_contractual, pred_behavioural, sc_k
    summary: dict[str, dict[str, float]]


def run(
    alm_t0: pd.DataFrame,
    fin_t0: pd.DataFrame,
    fin_t1: pd.DataFrame,
    c0: ZeroCurve,
    c1: ZeroCurve,
    t0: str,
    t1: str,
) -> BacktestResult:
    cols = ["cert", "scha", "schf", "scaf", "scaa"]
    f0 = fin_t0[cols].rename(columns={c: c + "_0" for c in cols[1:]})
    f1 = fin_t1[cols].rename(columns={c: c + "_1" for c in cols[1:]})
    df = alm_t0.merge(f0, on="cert").merge(f1, on="cert")
    bucket_total = df[[f for f, _ in SECURITIES]].fillna(0).sum(axis=1)
    df = df[(df["sc"] >= MIN_SECURITIES_K) & (bucket_total >= COVERAGE_MIN * df["sc"])].copy()
    book0 = df["scha_0"] + df["scaa_0"]
    ugl0 = (df["schf_0"] - df["scha_0"]) + (df["scaf_0"] - df["scaa_0"])
    ugl1 = (df["schf_1"] - df["scha_1"]) + (df["scaf_1"] - df["scaa_1"])
    df["observed"] = (ugl1 - ugl0) / book0
    df["pred_contractual"] = [predicted_change(r, c0, c1, False) for _, r in df.iterrows()]
    df["pred_behavioural"] = [predicted_change(r, c0, c1, True) for _, r in df.iterrows()]
    df = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["observed", "pred_contractual", "pred_behavioural"]
    )
    # drop banks whose book value moved by >50% (portfolio restructured; not comparable)
    book1 = df["scha_1"] + df["scaa_1"]
    df = df[(book1 / (df["scha_0"] + df["scaa_0"])).between(0.5, 1.5)]
    summary = {}
    w = df["sc"]
    for m in ("pred_contractual", "pred_behavioural"):
        err = df[m] - df["observed"]
        summary[m] = {
            "banks": int(len(df)),
            "corr": float(np.corrcoef(df[m], df["observed"])[0, 1]),
            "median_error_pp": float(100 * err.median()),
            "mean_abs_error_pp": float(100 * err.abs().mean()),
            "aggregate_predicted_pct": float(100 * np.average(df[m], weights=w)),
            "aggregate_observed_pct": float(100 * np.average(df["observed"], weights=w)),
        }
    keep = ["cert", "sc", "observed", "pred_contractual", "pred_behavioural"]
    return BacktestResult(t0, t1, df[keep].reset_index(drop=True), summary)
