"""Small regression check against QuantLib (skipped when it is not installed).

The full grid, timings and py_vollib comparison live in
benchmarks/bench_reference.py; this keeps a fast subset in the test suite.
Tolerances are far looser than the measured agreement (~1e-13) so that a
different QuantLib build cannot make CI flaky, but tight enough to catch a
wrong sign, unit or day-count convention.
"""
import itertools

import pytest

from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial
from vanna.pricing.implied_vol import implied_vol

ql = pytest.importorskip("QuantLib")

TODAY = ql.Date(15, 1, 2024)
DC = ql.Actual365Fixed()


def _process(S, r, q, sigma):
    ql.Settings.instance().evaluationDate = TODAY
    flat = lambda x: ql.YieldTermStructureHandle(ql.FlatForward(TODAY, x, DC))
    vol = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(TODAY, ql.NullCalendar(), sigma, DC))
    return ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), flat(q), flat(r), vol)


def _european(S, K, days, r, q, sigma, is_call):
    opt = ql.EuropeanOption(
        ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, K),
        ql.EuropeanExercise(TODAY + days))
    opt.setPricingEngine(ql.AnalyticEuropeanEngine(_process(S, r, q, sigma)))
    return opt


GRID = list(itertools.product([85.0, 100.0, 115.0], [0.15, 0.5], [0.0, 0.04],
                              [30, 365], [0.0, 0.03], [True, False]))


@pytest.mark.parametrize("K,sigma,r,days,q,is_call", GRID)
def test_black_scholes_matches_quantlib(K, sigma, r, days, q, is_call):
    S, T = 100.0, days / 365.0
    ref = _european(S, K, days, r, q, sigma, is_call)
    g = bs.greeks(S, K, T, r, sigma, is_call, q)
    assert g.price == pytest.approx(ref.NPV(), abs=1e-9)
    assert g.delta == pytest.approx(ref.delta(), abs=1e-9)
    assert g.gamma == pytest.approx(ref.gamma(), abs=1e-9)
    assert g.vega == pytest.approx(ref.vega(), abs=1e-8)
    assert g.theta == pytest.approx(ref.theta(), abs=1e-8)  # per year, calendar time
    assert g.rho == pytest.approx(ref.rho(), abs=1e-8)


@pytest.mark.parametrize("K,sigma,r,days,q,is_call", GRID[::3])
def test_implied_vol_recovers_sigma_from_quantlib_price(K, sigma, r, days, q, is_call):
    S = 100.0
    target = _european(S, K, days, r, q, sigma, is_call).NPV()
    assert implied_vol(target, S, K, days / 365.0, r, is_call, q) == pytest.approx(sigma, abs=1e-6)


@pytest.mark.parametrize("K,sigma,r,days,q,is_call",
                         [(90.0, 0.3, 0.04, 180, 0.0, False), (100.0, 0.3, 0.04, 365, 0.03, True),
                          (110.0, 0.2, 0.04, 90, 0.0, False)])
def test_american_binomial_matches_quantlib_crr(K, sigma, r, days, q, is_call):
    S, steps = 100.0, 200
    opt = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, K),
        ql.AmericanExercise(TODAY, TODAY + days))
    opt.setPricingEngine(ql.BinomialVanillaEngine(_process(S, r, q, sigma), "crr", steps))
    g = greeks_binomial(S, K, days / 365.0, r, sigma, is_call, q, steps)
    assert g.price == pytest.approx(opt.NPV(), abs=2e-3)
    assert g.delta == pytest.approx(opt.delta(), abs=1e-3)
    assert g.gamma == pytest.approx(opt.gamma(), abs=1e-3)
    assert price_binomial(S, K, days / 365.0, r, sigma, is_call, q, steps) == pytest.approx(g.price)


@pytest.mark.parametrize("K,sigma,r,days,q,is_call",
                         [(90.0, 0.3, 0.04, 180, 0.0, False), (100.0, 0.3, 0.04, 365, 0.03, True),
                          (110.0, 0.2, 0.04, 90, 0.0, False), (100.0, 0.4, 0.05, 180, 0.0, True)])
@pytest.mark.parametrize("american", [True, False])
def test_leisen_reimer_matches_quantlib_lr(K, sigma, r, days, q, is_call, american):
    # 1001 steps: measured agreement ~2e-10 over a 288-point grid. (At some
    # other step counts QuantLib 1.43's *American* LR price differs by up to
    # 0.06 and can fall below its own European price for a no-dividend call,
    # which is not arbitrage-free, so those are not used as a reference.)
    S, steps = 100.0, 1001
    exercise = (ql.AmericanExercise(TODAY, TODAY + days) if american
                else ql.EuropeanExercise(TODAY + days))
    opt = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, K), exercise)
    opt.setPricingEngine(ql.BinomialVanillaEngine(_process(S, r, q, sigma), "lr", steps))
    g = greeks_binomial(S, K, days / 365.0, r, sigma, is_call, q, steps, american, "lr")
    assert g.price == pytest.approx(opt.NPV(), abs=1e-8)
    assert g.delta == pytest.approx(opt.delta(), abs=1e-9)
    assert g.gamma == pytest.approx(opt.gamma(), abs=1e-9)
