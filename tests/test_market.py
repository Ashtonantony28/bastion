"""Market risk (M4): pricing against analytic references, revaluation signs, VaR/ES estimators."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bastion.market.factors import NODES
from bastion.market.portfolio import Shocks, State, bond_price, bs_price, load_book, revalue
from bastion.market.var import delta_normal, ewma_cov, monte_carlo, var_es


def _state(z: float = 0.04) -> State:
    return State(zero=np.full(len(NODES), z), vix=20.0, spread=0.02, fx={})


def _shocks(n: int, **kw) -> Shocks:
    base = dict(
        equity={f: np.zeros(n) for f in ("equity_market", "equity_buseq")},
        fx={"fx_eur": np.zeros(n)},
        dzero=np.zeros((n, len(NODES))),
        dvix=np.zeros(n),
        dspread=np.zeros(n),
    )
    base.update(kw)
    return Shocks(**base)


def test_bond_par_on_flat_curve():
    # With a flat continuous zero rate z, the semi-annual par coupon is 2(e^{z/2} - 1).
    z = 0.05
    c = 2 * (np.exp(z / 2) - 1)
    assert bond_price(c, 10.0, np.full(len(NODES), z))[0] == pytest.approx(1.0, abs=1e-12)


def test_zero_coupon_bond_is_discount_factor():
    z = 0.03
    assert bond_price(0.0, 7.0, np.full(len(NODES), z))[0] == pytest.approx(
        np.exp(-z * 7.0), abs=1e-12
    )


def test_black_scholes_reference_and_parity():
    # Hull, Options Futures and Other Derivatives, Example 15.6: call 4.76, put 0.81.
    s, k, t, r, v = np.array([42.0]), 40.0, 0.5, np.array([0.10]), np.array([0.20])
    call = bs_price("call", s, k, t, r, v)[0]
    put = bs_price("put", s, k, t, r, v)[0]
    assert call == pytest.approx(4.76, abs=0.005)
    assert put == pytest.approx(0.81, abs=0.005)
    assert call - put == pytest.approx(42.0 - k * np.exp(-0.10 * t), abs=1e-10)


def test_revalue_signs():
    st = _state()
    long_eq = [{"type": "equity", "factor": "equity_buseq", "notional": 1e6}]
    sh = _shocks(1, equity={"equity_market": np.zeros(1), "equity_buseq": np.array([-0.01])})
    assert revalue(long_eq, st, sh)[0] == pytest.approx(-1e4)

    long_bond = [{"type": "bond", "coupon": 0.04, "maturity": 10.0, "notional": 1e6}]
    up = _shocks(1, dzero=np.full((1, len(NODES)), 0.01))
    assert revalue(long_bond, st, up)[0] < 0

    corp = [{"type": "corporate_bond", "coupon": 0.055, "maturity": 7.0, "notional": 1e6}]
    wider = _shocks(1, dspread=np.array([0.005]))
    assert revalue(corp, st, wider)[0] < 0

    put = [{"type": "option", "kind": "put", "strike": 0.95, "expiry": 0.25, "notional": 1e6}]
    crash = _shocks(
        1,
        equity={"equity_market": np.array([-0.10]), "equity_buseq": np.zeros(1)},
        dvix=np.array([15.0]),
    )
    assert revalue(put, st, crash)[0] > 0

    book = load_book()
    eq = {p["factor"] for p in book if p["type"] == "equity"} | {"equity_market"}
    fx = {p["factor"] for p in book if p["type"] == "fx_forward"}
    still = _shocks(3, equity={f: np.zeros(3) for f in eq}, fx={f: np.zeros(3) for f in fx})
    assert np.allclose(revalue(book, st, still), 0.0, atol=1e-6)  # no move, no hypothetical P&L


def test_var_es_known_sample():
    pnl = -np.arange(1, 101, dtype=float)  # losses 1..100
    v, es = var_es(pnl, 0.99)
    assert v == 100.0  # 'higher' empirical quantile: conservative order statistic
    assert es == 100.0
    v95, es95 = var_es(pnl, 0.95)
    assert v95 == 96.0 and es95 == pytest.approx(np.mean([96, 97, 98, 99, 100]))


def test_delta_normal_matches_closed_form_for_linear_book():
    # A single linear equity position: VaR = z_alpha * notional * EWMA sigma.
    rng = np.random.default_rng(1)
    cols = ["equity_market", "equity_buseq", "fx_eur", *[f"z{n}" for n in NODES], "vix", "spread"]
    window = pd.DataFrame(rng.normal(0, 0.01, size=(300, len(cols))), columns=cols)
    book = [{"type": "equity", "factor": "equity_buseq", "notional": 1e6}]
    v, es = delta_normal(book, _state(), window, 0.99)
    sigma = 1e6 * np.sqrt(ewma_cov(window)[1, 1])
    assert v == pytest.approx(2.326347874 * sigma, rel=1e-6)
    assert es > v


def test_ewma_cov_weights_sum_to_one():
    m = pd.DataFrame({"a": np.ones(50), "b": -np.ones(50)})
    cov = ewma_cov(m)
    assert cov == pytest.approx(np.array([[1.0, -1.0], [-1.0, 1.0]]))


def test_monte_carlo_is_seeded():
    rng = np.random.default_rng(0)
    cols = ["equity_market", "equity_buseq", "fx_eur", *[f"z{n}" for n in NODES], "vix", "spread"]
    window = pd.DataFrame(rng.normal(0, 0.01, size=(300, len(cols))), columns=cols)
    book = [{"type": "equity", "factor": "equity_buseq", "notional": 1e6}]
    a = monte_carlo(book, _state(), window, n=2000)
    b = monte_carlo(book, _state(), window, n=2000)
    assert np.array_equal(a, b)
    assert var_es(a, 0.99)[0] > 0
