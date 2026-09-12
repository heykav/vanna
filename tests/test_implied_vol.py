import pytest

from vanna.pricing.black_scholes import price
from vanna.pricing.implied_vol import implied_vol, ImpliedVolError


@pytest.mark.parametrize("true_sigma,S,K,T,r,is_call", [
    (0.20, 100, 100, 1.0, 0.05, True),
    (0.45, 100, 80, 0.1, 0.02, True),   # short-dated, ITM: low vega, forces the bisection fallback
    (0.15, 100, 120, 2.0, 0.03, False),
    (0.60, 50, 50, 0.05, 0.01, True),   # very short-dated ATM: also low-vega-ish
])
def test_recovers_the_volatility_that_generated_the_price(true_sigma, S, K, T, r, is_call):
    market_price = price(S, K, T, r, true_sigma, is_call)
    recovered = implied_vol(market_price, S, K, T, r, is_call)
    assert recovered == pytest.approx(true_sigma, abs=1e-4)


def test_falls_back_to_bisection_when_vega_is_near_zero():
    # Deep OTM, very short-dated: vega is essentially zero, so Newton
    # must bail out and bisection must still find the right answer.
    S, K, T, r, true_sigma = 100, 200, 0.02, 0.02, 0.3
    market_price = price(S, K, T, r, true_sigma, is_call=True)
    recovered = implied_vol(market_price, S, K, T, r, is_call=True)
    assert recovered == pytest.approx(true_sigma, abs=1e-3)


def test_rejects_price_below_intrinsic_value():
    with pytest.raises(ImpliedVolError):
        implied_vol(market_price=0.01, S=100, K=50, T=1.0, r=0.05, is_call=True)


def test_rejects_price_no_volatility_can_produce():
    with pytest.raises(ImpliedVolError):
        implied_vol(market_price=1_000_000, S=100, K=100, T=1.0, r=0.05, is_call=True)
