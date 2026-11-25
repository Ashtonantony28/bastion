"""Early-warning models and out-of-time evaluation.

Two models are always fitted together (CLAUDE.md rule 5): a regularised logistic regression on
winsorised, standardised CAMELS ratios (the transparent benchmark, the form supervisors'
off-site models such as the Fed's SEER take) and a LightGBM challenger with monotone constraints
where economics dictates a sign. Splits are by report date only (rule 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from bastion.hashing import frame_hash

SEED = 7
LABEL = "fail_within_4q"

# Classic CAMELS-style ratios. Sign = +1 if a higher value should raise failure risk.
CAMELS: dict[str, int] = {
    "log_assets": 0,
    "equity_to_assets": -1,
    "tier1_leverage": -1,
    "noncurrent_loan_ratio": +1,
    "past_due_30_89_ratio": +1,
    "reserve_ratio": 0,
    "net_chargeoff_rate": +1,
    "provision_to_assets": +1,
    "roa": -1,
    "nim": 0,
    "cash_to_assets": -1,
    "securities_to_assets": 0,
    "loans_to_assets": 0,
    "brokered_deposit_share": +1,
    "core_deposit_share": -1,
    "volatile_liability_share": +1,
    "real_estate_loan_share": 0,
    "ci_loan_share": 0,
    "asset_growth_yoy": 0,
    "deposit_growth_yoy": 0,
}
# Interest-rate and run risk: the channel that failed SVB, absent from 2008-era failures.
RATE_AND_RUN: dict[str, int] = {
    "unrealized_gain_to_tier1": -1,
    "uninsured_deposit_share": +1,
    "long_term_assets_share": +1,
}
FEATURE_SETS: dict[str, dict[str, int]] = {
    "camels": CAMELS,
    "camels_rate_run": {**CAMELS, **RATE_AND_RUN},
}
WINSOR_Q = (0.01, 0.99)


@dataclass(frozen=True)
class Split:
    name: str
    train_from: date
    train_to: date
    test_from: date
    test_to: date


# Crisis split: learn from the 2008 wave's start, test on its 2010-2012 tail.
CRISIS = Split(
    "crisis", date(2006, 3, 31), date(2009, 12, 31), date(2010, 3, 31), date(2012, 12, 31)
)
# 2023 split: everything up to 2019 (labels known through 2020), score the 2022-12-31 filings.
Y2023 = Split(
    "y2023", date(2006, 3, 31), date(2019, 12, 31), date(2022, 12, 31), date(2022, 12, 31)
)


@dataclass
class Preprocessor:
    """Winsorise at train quantiles, impute train medians, standardise. Fitted on train only."""

    features: list[str]
    lo: pd.Series = field(default_factory=pd.Series)
    hi: pd.Series = field(default_factory=pd.Series)
    med: pd.Series = field(default_factory=pd.Series)
    mu: pd.Series = field(default_factory=pd.Series)
    sd: pd.Series = field(default_factory=pd.Series)

    def fit(self, x: pd.DataFrame) -> Preprocessor:
        x = x[self.features]
        self.lo, self.hi = x.quantile(WINSOR_Q[0]), x.quantile(WINSOR_Q[1])
        clipped = x.clip(self.lo, self.hi, axis=1)
        self.med = clipped.median()
        filled = clipped.fillna(self.med).fillna(0.0)
        self.mu, self.sd = filled.mean(), filled.std(ddof=0).replace(0.0, 1.0)
        return self

    def transform(self, x: pd.DataFrame) -> np.ndarray:
        z = x[self.features].clip(self.lo, self.hi, axis=1).fillna(self.med).fillna(0.0)
        return ((z - self.mu) / self.sd).to_numpy()


@dataclass
class FittedModels:
    features: list[str]
    pre: Preprocessor
    logit: LogisticRegression
    gbm: lgb.LGBMClassifier

    def score(self, x: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "p_logit": self.logit.predict_proba(self.pre.transform(x))[:, 1],
                "p_gbm": np.asarray(self.gbm.predict_proba(x[self.features].astype(float)))[:, 1],
            },
            index=x.index,
        )


def fit(train: pd.DataFrame, feature_set: str) -> FittedModels:
    spec = FEATURE_SETS[feature_set]
    feats = list(spec)
    y = train[LABEL].astype(int).to_numpy()
    pre = Preprocessor(feats).fit(train)
    logit = LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced")
    logit.fit(pre.transform(train), y)
    gbm = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.03,
        num_leaves=15,
        min_child_samples=50,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        monotone_constraints=[spec[f] for f in feats],
        random_state=SEED,
        deterministic=True,
        force_row_wise=True,
        n_jobs=1,
        verbose=-1,
    )
    gbm.fit(train[feats].astype(float), y)
    return FittedModels(feats, pre, logit, gbm)


def window(df: pd.DataFrame, lo: date, hi: date) -> pd.DataFrame:
    d = pd.to_datetime(df["repdte"])
    return df[(d >= pd.Timestamp(lo)) & (d <= pd.Timestamp(hi))].copy()


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    order = np.argsort(-p, kind="mergesort")
    top = order[: max(1, int(np.ceil(0.10 * len(p))))]
    return {
        "auc": float(roc_auc_score(y, p)),
        "avg_precision": float(average_precision_score(y, p)),
        "top_decile_capture": float(y[top].sum()) / max(1.0, float(y.sum())),
        "brier": float(brier_score_loss(y, p)),
        "n": int(len(y)),
        "positives": int(y.sum()),
    }


@dataclass
class SplitResult:
    split: Split
    feature_set: str
    in_sample: dict[str, dict[str, float]]
    out_of_time: dict[str, dict[str, float]]
    test_scores: pd.DataFrame
    scores_hash: str
    logit_coefs: pd.Series


def evaluate(df: pd.DataFrame, split: Split, feature_set: str) -> SplitResult:
    train = window(df, split.train_from, split.train_to)
    test = window(df, split.test_from, split.test_to)
    models = fit(train, feature_set)
    s_tr, s_te = models.score(train), models.score(test)
    y_tr, y_te = train[LABEL].astype(int).to_numpy(), test[LABEL].astype(int).to_numpy()
    ins = {m: metrics(y_tr, s_tr[f"p_{m}"].to_numpy()) for m in ("logit", "gbm")}
    oot = {m: metrics(y_te, s_te[f"p_{m}"].to_numpy()) for m in ("logit", "gbm")}
    scores = pd.concat([test[["cert", "repdte", LABEL, "fail_date"]], s_te], axis=1)
    for m in ("logit", "gbm"):
        scores[f"rank_{m}"] = scores.groupby("repdte")[f"p_{m}"].rank(ascending=False, method="min")
        scores[f"pctile_{m}"] = scores.groupby("repdte")[f"p_{m}"].rank(pct=True)
    coefs = pd.Series(models.logit.coef_[0], index=models.features).sort_values()
    h = frame_hash(scores[["cert", "repdte", "p_logit", "p_gbm"]], sort_by=["cert", "repdte"])
    return SplitResult(split, feature_set, ins, oot, scores, h, coefs)
