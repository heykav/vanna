"""Floating-point regressions in the Black-Scholes core.

The reference values below were computed with mpmath at 60 significant
digits from the same closed-form formulas (not from vanna), e.g.

    mp.mp.dps = 60; d1 = (mp.log(S/K) + (r + s*s/2)*T) / (s*mp.sqrt(T)); ...

Before the fix, `_norm_cdf` was 0.5 * (1 + erf(x / sqrt 2)), which returns
exactly 0.0 for x below about -8.3 and loses relative precision well
before that; the put delta was computed as N(d1) - 1, which cancels.
"""
import math

import pytest

from vanna.pricing.black_scholes import _norm_cdf, delta, greeks, price
from vanna.pricing.implied_vol import implied_vol


def test_norm_cdf_left_tail_keeps_relative_precision():
    # mpmath: ncdf(-10) = 7.61985302416052606597e-24 (erf form returned 0.0)
    assert _norm_cdf(-10.0) == pytest.approx(7.61985302416052606597e-24, rel=1e-13)
    # mpmath: ncdf(-30) = 4.906713927148187e-198
    assert _norm_cdf(-30.0) == pytest.approx(4.906713927148187e-198, rel=1e-12)
    assert _norm_cdf(0.0) == 0.5
    assert _norm_cdf(40.0) == 1.0


@pytest.mark.parametrize("K,is_call,ref_price,ref_delta", [
    # 30-day, 2x out-of-the-money call and 0.5x put: both used to price as 0.0
    (200.0, True, 5.6859460424939083e-34, 1.2149022548946812e-33),
    (50.0, False, 1.4083275641841337e-34, -3.0089574964886271e-34),
])
def test_deep_out_of_the_money_prices_do_not_underflow_to_zero(K, is_call, ref_price, ref_delta):
    S, T, r, sigma = 100.0, 30 / 365, 0.02, 0.2
    assert price(S, K, T, r, sigma, is_call) == pytest.approx(ref_price, rel=1e-10)
    assert greeks(S, K, T, r, sigma, is_call).delta == pytest.approx(ref_delta, rel=1e-10)


def test_deep_otm_put_price_and_delta_keep_relative_precision():
    # 1% vol ATM-forward-ish put: the erf form was off by 1.4e-8 (price) and
    # 2.5e-10 (delta) in relative terms.
    S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.05, 0.01, 0.0
    g = greeks(S, K, T, r, sigma, False, q)
    assert g.price == pytest.approx(5.2141072075915258e-08, rel=1e-11)
    assert g.delta == pytest.approx(-2.7931015515582383e-07, rel=1e-12)


@pytest.mark.parametrize("K,is_call", [(200.0, True), (50.0, False)])
def test_implied_vol_recovered_from_a_deep_otm_price(K, is_call):
    # Only possible once the price no longer underflows to zero.
    S, T, r, sigma = 100.0, 30 / 365, 0.02, 0.2
    px = price(S, K, T, r, sigma, is_call)
    assert px > 0.0
    assert implied_vol(px, S, K, T, r, is_call) == pytest.approx(sigma, abs=1e-9)


@pytest.mark.parametrize("K", [50.0, 100.0, 150.0])
@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("q", [0.0, 0.03])
def test_delta_function_is_identical_to_greeks_delta(K, is_call, q):
    args = (100.0, K, 0.4, 0.02, 0.3, is_call, q)
    assert delta(*args) == greeks(*args).delta


def test_put_call_delta_parity_holds_to_rounding():
    for K in (50.0, 100.0, 150.0):
        c = greeks(100.0, K, 0.5, 0.03, 0.25, True, 0.02).delta
        p = greeks(100.0, K, 0.5, 0.03, 0.25, False, 0.02).delta
        assert c - p == pytest.approx(math.exp(-0.02 * 0.5), abs=1e-15)
