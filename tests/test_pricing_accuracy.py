"""Regression tests for accuracy issues found by benchmarks/bench_reference.py."""
import pytest

from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial
from vanna.pricing.implied_vol import implied_vol


@pytest.mark.parametrize("is_call", [True, False])
def test_implied_vol_is_precise_when_vega_is_tiny(is_call):
    # Deep OTM/ITM, one week, 40% vol: vega ~ 1e-4. The old solver stopped on a
    # 1e-6 *price* residual and returned a vol ~0.009 off.
    S, K, T, r, sigma = 100.0, 130.0, 7 / 365.0, 0.05, 0.4
    px = bs.price(S, K, T, r, sigma, is_call)
    assert implied_vol(px, S, K, T, r, is_call) == pytest.approx(sigma, abs=1e-6)


@pytest.mark.parametrize("is_call", [True, False])
def test_european_tree_greeks_converge_to_closed_form(is_call):
    S, K, T, r, sigma, q = 100.0, 100.0, 0.5, 0.03, 0.25, 0.02
    ref = bs.greeks(S, K, T, r, sigma, is_call, q)
    g = greeks_binomial(S, K, T, r, sigma, is_call, q, steps=800, american=False)
    assert g.price == pytest.approx(ref.price, abs=5e-3)
    assert g.delta == pytest.approx(ref.delta, abs=2e-3)
    assert g.gamma == pytest.approx(ref.gamma, rel=0.02)
    assert g.theta == pytest.approx(ref.theta, rel=0.05)


def test_tree_greeks_need_two_steps():
    with pytest.raises(ValueError):
        greeks_binomial(100, 100, 1.0, 0.03, 0.2, True, steps=1)
