"""EWS model mechanics on synthetic data: no leakage across the split, determinism, signal."""

from datetime import date

import numpy as np
import pandas as pd

from bastion.ews.model import CAMELS, LABEL, RATE_AND_RUN, Preprocessor, Split, evaluate, metrics

SPLIT = Split("t", date(2010, 3, 31), date(2012, 12, 31), date(2013, 3, 31), date(2013, 12, 31))


def _panel(seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    quarters = pd.date_range("2010-03-31", "2013-12-31", freq="QE")
    rows = []
    for cert in range(600):
        risk = rng.normal()
        for q in quarters:
            r = {f: rng.normal() for f in {**CAMELS, **RATE_AND_RUN}}
            r["equity_to_assets"] = -risk + 0.3 * rng.normal()
            r["noncurrent_loan_ratio"] = risk + 0.3 * rng.normal()
            p = 1 / (1 + np.exp(-(2.5 * risk - 5)))
            rows.append(
                {
                    "cert": cert,
                    "repdte": q.date(),
                    LABEL: bool(rng.random() < p),
                    "fail_date": None,
                    **r,
                }
            )
    return pd.DataFrame(rows)


def test_preprocessor_uses_train_statistics_only():
    tr = pd.DataFrame({"a": [0.0, 1.0, 2.0, np.nan]})
    te = pd.DataFrame({"a": [100.0, np.nan]})
    pre = Preprocessor(["a"]).fit(tr)
    z = pre.transform(te)
    assert np.isfinite(z).all()
    assert z[0, 0] == pre.transform(pd.DataFrame({"a": [tr["a"].quantile(0.99)]}))[0, 0]


def test_metrics_perfect_ranking():
    m = metrics(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
    assert m["auc"] == 1.0 and m["top_decile_capture"] == 0.5


def test_evaluate_finds_signal_and_is_deterministic():
    df = _panel()
    a = evaluate(df, SPLIT, "camels")
    b = evaluate(df, SPLIT, "camels")
    assert a.scores_hash == b.scores_hash
    assert a.out_of_time["logit"]["auc"] > 0.75
    assert a.out_of_time["gbm"]["auc"] > 0.7
    assert set(pd.to_datetime(a.test_scores["repdte"]).dt.year) == {2013}
