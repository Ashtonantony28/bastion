import numpy as np
import pandas as pd
import pytest

from bastion.alm import backtest
from bastion.alm.balance_sheet import BCBS_CAPS, RUN_PRONE, _slot, build_position
from bastion.alm.curves import bootstrap
from bastion.alm.irrbb import eve, nii_sensitivity, outlier_ratio
from bastion.alm.liquidity import RunScenario, hqla, lcr, survival_days

FLAT = bootstrap([0.25, 1, 2, 5, 10, 30], [4.0] * 6)


def _row(**kw) -> pd.Series:
    base = {
        "cert": 1,
        "repdte": "2021-12-31",
        "rbct1j": 100.0,
        "dep": 0.0,
        "depuna": 0.0,
        "sc": 0.0,
    }
    base.update(kw)
    return pd.Series(base)


def test_nmd_slots_have_target_average_maturity():
    t, a = _slot(100.0, 4.0)
    assert a.sum() == pytest.approx(100.0)
    assert np.average(t, weights=a) == pytest.approx(4.0)


def test_long_assets_funded_overnight_lose_value_when_rates_rise():
    # $1,000 of 5-15y non-mortgage securities funded by repo, Tier 1 = 100
    row = _row(sc=1000.0, scnm5t15=1000.0, frepp=1000.0)
    pos = build_position(row)
    res = eve(pos, FLAT)
    assert res.delta["parallel_up"] < 0 < res.delta["parallel_down"]
    # zero-coupon at t=10: dPV = 1000 * exp(-z*10) * (exp(-0.02*10) - 1)
    z = FLAT.zero(10.0)
    expected = 1000 * np.exp(-z * 10) * (np.exp(-0.2) - 1) - (
        1000 * np.exp(-z / 365) * (np.exp(-0.02 / 365) - 1)
    )
    assert res.delta["parallel_up"] == pytest.approx(expected, rel=1e-9)
    assert outlier_ratio(pos, res) > 0.15


def test_uninsured_core_assumption_changes_eve():
    row = _row(sc=1000.0, scnm5t15=1000.0, dep=1000.0, depuna=800.0, trn=200.0)
    caps = eve(build_position(row, BCBS_CAPS), FLAT).delta["parallel_up"]
    run = eve(build_position(row, RUN_PRONE), FLAT).delta["parallel_up"]
    assert run < caps  # treating uninsured as overnight removes the liability hedge


def test_nii_gap_sign():
    # floating assets, fixed long funding -> NII rises with rates
    row = _row(lnot3les=1000.0, otbfhov5=1000.0)
    assert nii_sensitivity(build_position(row), up=True) > 0
    assert nii_sensitivity(build_position(row), up=False) < 0


def test_lcr_hand_calculation():
    row = _row(chbal=100.0, dep=1000.0, depuna=500.0, scaa=0.0, scha=0.0)
    # HQLA = 100; outflows = 500*5% + 500*40% = 225
    assert hqla(row)["total"] == pytest.approx(100.0)
    assert lcr(row) == pytest.approx(100.0 / 225.0)


def test_survival_days_fractional():
    row = _row(chbal=150.0, dep=1000.0, depuna=1000.0)
    run = RunScenario("t", [0.1] * 5, 0.0, 0.0)
    assert survival_days(row, run) == pytest.approx(1.5)
    assert survival_days(_row(chbal=1e6, dep=1000.0, depuna=1000.0), run) == float("inf")


def test_backtest_prediction_for_parallel_shift():
    c1 = bootstrap([0.25, 1, 2, 5, 10, 30], [5.0] * 6)
    row = _row(scnm3t5=100.0)
    dz = c1.zero(4.0) - FLAT.zero(4.0)
    assert backtest.predicted_change(row, FLAT, c1, False) == pytest.approx(np.exp(-dz * 4) - 1)
