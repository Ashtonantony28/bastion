import numpy as np
import pytest

from bastion.alm.curves import bootstrap
from bastion.alm.shocks import SCENARIOS, shock


def test_flat_par_curve_gives_flat_zero_curve():
    tenors = [0.25, 0.5, 1, 2, 5, 10, 30]
    c = bootstrap(tenors, [4.0] * len(tenors))
    z_cont = 2 * np.log1p(0.04 / 2)
    assert np.allclose(c.zero([0.25, 3, 7, 20, 30]), z_cont, atol=1e-10)


def test_bootstrapped_curve_reprices_par_bonds():
    tenors = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 20, 30]
    par = [5.2, 5.3, 5.0, 4.6, 4.4, 4.2, 4.2, 4.1, 4.4, 4.2]
    c = bootstrap(tenors, par)
    for T, y in [(2, 4.6), (5, 4.2), (10, 4.1), (30, 4.2)]:
        times = np.arange(0.5, T + 1e-9, 0.5)
        price = (y / 200) * c.df(times).sum() + c.df(T)
        assert price == pytest.approx(1.0, abs=1e-10)


def test_bcbs_shapes():
    t = np.array([0.0, 1.0, 10.0, 30.0])
    assert np.allclose(shock("parallel_up", t), 0.02)
    assert shock("short_up", 0.0) == pytest.approx(0.03)
    assert shock("short_up", 30.0) < 0.001
    assert shock("steepener", 0.0) < 0 < shock("steepener", 30.0)
    assert shock("flattener", 0.0) > 0 > shock("flattener", 30.0)
    assert len(SCENARIOS) == 6
