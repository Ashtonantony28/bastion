import numpy as np
import pytest

from quantval import (
    TrafficLight,
    basel_traffic_light,
    binomial_test,
    jeffreys_test,
    kupiec_pof,
    psi,
)


@pytest.mark.parametrize(
    ("x", "zone"),
    [(0, "green"), (4, "green"), (5, "yellow"), (9, "yellow"), (10, "red"), (15, "red")],
)
def test_basel_traffic_light_matches_bcbs_1996_table(x, zone):
    # BCBS 1996 Table 2: 250 observations, 99% VaR.
    assert basel_traffic_light(x) == TrafficLight(zone)


def test_kupiec_at_expected_rate_does_not_reject():
    r = kupiec_pof(exceptions=5, observations=500, var_level=0.99)
    assert r.lr_stat == pytest.approx(0.0, abs=1e-12)
    assert r.p_value == pytest.approx(1.0)


def test_kupiec_known_value():
    # 10 exceptions in 250 days at 99%: LR = -2 ln[(.99^240 .01^10) / (.96^240 .04^10)]
    expected = -2 * (
        240 * np.log(0.99) + 10 * np.log(0.01) - 240 * np.log(0.96) - 10 * np.log(0.04)
    )
    r = kupiec_pof(10, 250, 0.99)
    assert r.lr_stat == pytest.approx(expected, rel=1e-12)
    assert r.p_value < 0.001


def test_kupiec_zero_exceptions():
    r = kupiec_pof(0, 250, 0.99)
    assert r.lr_stat == pytest.approx(-2 * 250 * np.log(0.99))


def test_binomial_and_jeffreys_tests():
    # 0 defaults: binomial p-value is P(X >= 0) = 1
    assert binomial_test(0, 1000, 0.01) == pytest.approx(1.0)
    # many more defaults than expected -> PD underestimated -> tiny p-values
    assert binomial_test(40, 1000, 0.01) < 1e-9
    assert jeffreys_test(40, 1000, 0.01) < 1e-9
    # defaults at the expected rate -> Jeffreys p-value near 0.5
    assert 0.4 < jeffreys_test(100, 10_000, 0.01) < 0.6


def test_psi_zero_for_identical_and_large_for_shift():
    rng = np.random.default_rng(0)
    base = rng.normal(size=50_000)
    assert psi(base, base) == pytest.approx(0.0, abs=1e-12)
    assert psi(base, rng.normal(size=50_000)) < 0.01
    assert psi(base, rng.normal(1.0, 1.0, size=50_000)) > 0.25


def test_christoffersen_detects_clustering():
    from quantval import christoffersen

    spread = np.zeros(1000, dtype=int)
    spread[::100] = 1  # 10 isolated hits
    clustered = np.zeros(1000, dtype=int)
    clustered[500:510] = 1  # 10 consecutive hits
    assert christoffersen(spread, 0.99).p_ind > 0.3
    assert christoffersen(clustered, 0.99).p_ind < 1e-6


def test_acerbi_szekely_z2_zero_when_forecast_is_right():
    from quantval import acerbi_szekely_z2

    rng = np.random.default_rng(1)
    from scipy import stats

    n = 200_000
    loss = rng.standard_normal(n)
    v = stats.norm.ppf(0.975)
    es = stats.norm.pdf(v) / 0.025
    assert abs(acerbi_szekely_z2(loss, np.full(n, v), np.full(n, es))) < 0.03
    # forecast ES too small by half -> strongly negative
    assert acerbi_szekely_z2(2 * loss, np.full(n, v), np.full(n, es)) < -1.0
