"""Counterparty risk (M5): Hull-White, swap pricer vs QuantLib, MC exposure vs Jamshidian, SA-CCR."""

from __future__ import annotations

import numpy as np
import pytest

from bastion.alm.curves import ZeroCurve
from bastion.market.ccr import exposure, saccr
from bastion.market.ccr.hull_white import HullWhite, fit_historical_vol
from bastion.market.ccr.swap import Swap

NODES = np.array([0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0])
ZEROS = np.array([0.043, 0.042, 0.040, 0.037, 0.036, 0.037, 0.039, 0.041, 0.046, 0.047])
CURVE = ZeroCurve(NODES, ZEROS)
HW = HullWhite(a=0.03, sigma=0.01, curve=CURVE)


def test_bond_at_zero_reproduces_curve():
    t = np.array([0.5, 3.0, 12.0])
    assert HW.bond(0.0, t, 0.0) == pytest.approx(CURVE.df(t), rel=1e-14)


def test_simulated_discount_factors_are_martingale_consistent():
    grid = np.round(np.arange(0.0, 10.0 + 1e-9, 0.25), 9)
    x, df = HW.simulate(grid, 20_000, seed=3)
    for k in (8, 20, 40):
        se = df[:, k].std(ddof=1) / np.sqrt(df.shape[0])
        assert abs(df[:, k].mean() - CURVE.df(grid[k])) < 4 * se + 1e-12
    # E[D(0,t) P(t,T)] = P(0,T)
    pt = HW.bond(grid[20], 15.0, x[:, 20]) * df[:, 20]
    assert abs(pt.mean() - CURVE.df(15.0)) < 4 * pt.std(ddof=1) / np.sqrt(len(pt))


def test_par_swap_is_worth_zero():
    s = Swap("par", 1e8, 0.0, 0.0, 10.0, payer=True)
    s = Swap("par", 1e8, s.par_rate(CURVE), 0.0, 10.0, payer=True)
    assert s.price(CURVE) == pytest.approx(0.0, abs=1e-6)


def _ql_setup():
    ql = pytest.importorskip("QuantLib")
    today = ql.Date(15, ql.January, 2026)
    ql.Settings.instance().evaluationDate = today
    dc, cal = ql.SimpleDayCounter(), ql.NullCalendar()
    dates = [today] + [today + ql.Period(int(round(t * 12)), ql.Months) for t in NODES]
    zeros = [float(ZEROS[0])] + [float(z) for z in ZEROS]
    curve = ql.ZeroCurve(dates, zeros, dc, cal, ql.Linear(), ql.Continuous)
    return ql, today, dc, cal, ql.YieldTermStructureHandle(curve)


@pytest.mark.parametrize(
    ("start", "end", "payer", "rate"), [(0.0, 10.0, True, 0.035), (2.0, 7.0, False, 0.04)]
)
def test_swap_pricer_matches_quantlib(start, end, payer, rate):
    ql, today, dc, cal, h = _ql_setup()
    eff = today + ql.Period(int(start * 12), ql.Months)
    mat = today + ql.Period(int(end * 12), ql.Months)
    sched = ql.Schedule(
        eff,
        mat,
        ql.Period(6, ql.Months),
        cal,
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Forward,
        False,
    )
    index = ql.IborIndex(
        "X6M", ql.Period(6, ql.Months), 0, ql.USDCurrency(), cal, ql.Unadjusted, False, dc, h
    )
    typ = ql.Swap.Payer if payer else ql.Swap.Receiver
    sw = ql.VanillaSwap(typ, 1e8, sched, rate, dc, sched, index, 0.0, dc)
    sw.setPricingEngine(ql.DiscountingSwapEngine(h))
    ours = Swap("t", 1e8, rate, start, end, payer=payer).price(CURVE)
    assert ours == pytest.approx(sw.NPV(), abs=1e-8 * 1e8)  # 1e-8 per unit notional


def test_jamshidian_swaption_matches_quantlib():
    ql, today, dc, cal, h = _ql_setup()
    expiry, end, rate = 2.0, 7.0, 0.04
    eff = today + ql.Period(24, ql.Months)
    sched = ql.Schedule(
        eff,
        today + ql.Period(84, ql.Months),
        ql.Period(6, ql.Months),
        cal,
        ql.Unadjusted,
        ql.Unadjusted,
        ql.DateGeneration.Forward,
        False,
    )
    index = ql.IborIndex(
        "X6M", ql.Period(6, ql.Months), 0, ql.USDCurrency(), cal, ql.Unadjusted, False, dc, h
    )
    sw = ql.VanillaSwap(ql.Swap.Payer, 1.0, sched, rate, dc, sched, index, 0.0, dc)
    opt = ql.Swaption(sw, ql.EuropeanExercise(eff))
    opt.setPricingEngine(ql.JamshidianSwaptionEngine(ql.HullWhite(h, HW.a, HW.sigma)))
    s = Swap("u", 1.0, rate, expiry, end, payer=True)
    ours = HW.payer_swaption(expiry, s.pay_times, s.accruals, rate)
    assert ours == pytest.approx(opt.NPV(), abs=1e-8)


def test_mc_discounted_ee_matches_jamshidian_profile():
    s = Swap("s", 1.0, 0.04, 0.0, 10.0, payer=True)
    sim = exposure.simulate(HW, [s], n=20_000, seed=7, step=0.5)
    v = s.value_paths(HW, sim.grid, HW.simulate(sim.grid, 20_000, 7)[0])
    disc = sim.df * np.maximum(v, 0.0)
    for t in (1.0, 3.0, 5.0, 8.0):
        k = int(np.searchsorted(sim.grid, t))
        rest = s.pay_times[s.pay_times > t + 1e-9]
        analytic = HW.payer_swaption(t, rest, np.full(len(rest), 0.5), s.fixed_rate)
        se = disc[:, k].std(ddof=1) / np.sqrt(disc.shape[0])
        assert abs(disc[:, k].mean() - analytic) < 3.5 * se, (t, disc[:, k].mean(), analytic, se)


def test_value_at_zero_equals_pricer():
    s = Swap("s", 5e7, 0.038, 0.0, 5.0, payer=False)
    f = Swap("f", 5e7, 0.040, 2.0, 7.0, payer=True)
    sim = exposure.simulate(HW, [s, f], n=100, seed=1)
    assert sim.values["s"][:, 0] == pytest.approx(s.price(CURVE), rel=1e-12)
    assert sim.values["f"][:, 0] == pytest.approx(f.price(CURVE), rel=1e-12)


def test_netting_and_collateral_reduce_exposure():
    a = Swap("a", 1e8, 0.035, 0.0, 10.0, payer=True)
    b = Swap("b", 1e8, 0.040, 0.0, 5.0, payer=False)
    mpor = exposure.MPOR_DAYS / exposure.TRADING_DAYS
    sim = exposure.simulate(HW, [a, b], n=2000, seed=5, mpor=mpor)
    v = sim.netted()
    net = exposure.profile(sim, v[:, sim.report_idx])
    gross = exposure.profile(sim, exposure.no_netting(sim))
    csa = exposure.profile(sim, exposure.collateralised(sim, v, 0.0, mpor))
    loose = exposure.profile(sim, exposure.collateralised(sim, v, 1e15, mpor))
    assert np.all(net.ee <= gross.ee + 1e-6)
    assert csa.epe() < 0.5 * net.epe()
    assert loose.ee == pytest.approx(net.ee)
    assert net.eepe() >= net.epe()


def test_simulation_is_seeded():
    s = Swap("s", 1e8, 0.035, 0.0, 3.0, payer=True)
    a = exposure.simulate(HW, [s], n=200, seed=9).values["s"]
    b = exposure.simulate(HW, [s], n=200, seed=9).values["s"]
    assert np.array_equal(a, b)


def test_cva_flat_exposure_closed_form():
    t = np.linspace(0.0, 5.0, 501)
    dee = np.full_like(t, 1.0)
    s, lgd = 0.012, 0.6
    assert exposure.cva(t, dee, s, lgd) == pytest.approx(
        lgd * (1 - np.exp(-s / lgd * 5.0)), rel=1e-12
    )


def test_fit_historical_vol_recovers_parameters():
    rng = np.random.default_rng(0)
    a, sig = 0.08, 0.009
    load = (1 - np.exp(-a * NODES)) / (a * NODES)
    dx = rng.normal(0, sig / np.sqrt(252), 200_000)
    a_hat, s_hat = fit_historical_vol(dx[:, None] * load[None, :], NODES)
    assert a_hat == pytest.approx(a, rel=0.05)
    assert s_hat == pytest.approx(sig, rel=0.02)


def test_saccr_bcbs279_example_1():
    delta3 = saccr.option_delta("put", bought=True, underlying=0.06, strike=0.05, expiry=1.0)
    assert delta3 == pytest.approx(-0.27, abs=0.005)
    trades = [
        saccr.IrTrade(10_000, 0.0, 10.0, +1.0, 30.0, "USD"),
        saccr.IrTrade(10_000, 0.0, 4.0, -1.0, -20.0, "USD"),
        saccr.IrTrade(5_000, 1.0, 11.0, delta3, 50.0, "EUR", maturity=1.0),
    ]
    assert [round(t.adjusted_notional) for t in trades] == [78_694, 36_254, 37_428]
    r = saccr.ead(trades)
    assert r.rc == 60.0 and r.multiplier == 1.0
    assert r.effective_notional["USD"] == pytest.approx(59_270, abs=1)
    assert r.effective_notional["EUR"] == pytest.approx(10_083, abs=1)
    assert r.addon == pytest.approx(347, abs=0.5)
    assert r.ead == pytest.approx(569, abs=0.5)


def test_saccr_multiplier_and_margined_mf():
    assert saccr.multiplier(-1e12, 100.0) == pytest.approx(saccr.FLOOR)
    assert saccr.maturity_factor(10.0, margined=True, mpor_days=10) == pytest.approx(
        1.5 * np.sqrt(10 / 250)
    )
