import pytest

from vanna.backtest.chain import nearest_strike, price_leg, leg_greeks


def test_nearest_strike_never_returns_zero_or_negative_for_a_low_spot():
    # Regression test: a long enough GBM path can wander the underlying
    # under $1, and rounding to the nearest whole-dollar strike used to
    # produce exactly 0.0 here - which then crashed Black-Scholes pricing
    # several calls away with a confusing "K must be positive" error, not
    # a message pointing at nearest_strike. Found via run_backtest(entry_dte=365,
    # n_trades=500, seed=1), not invented.
    for spot in (0.05, 0.1, 0.3, 0.49, 0.5, 0.9):
        k = nearest_strike(spot, target_delta=0.3, dte_days=30, r=0.03, iv=0.22, is_call=True)
        assert k > 0, f"nearest_strike({spot}) returned {k}"


def test_nearest_strike_stays_reasonable_for_a_normal_spot():
    k = nearest_strike(100, target_delta=0.3, dte_days=30, r=0.03, iv=0.22, is_call=True)
    assert 50 < k < 150


def test_price_leg_returns_intrinsic_at_zero_dte():
    assert price_leg(spot=110, strike=100, dte_days=0, r=0.03, iv=0.2, is_call=True) == pytest.approx(10.0)
    assert price_leg(spot=90, strike=100, dte_days=0, r=0.03, iv=0.2, is_call=True) == pytest.approx(0.0)
    assert price_leg(spot=90, strike=100, dte_days=0, r=0.03, iv=0.2, is_call=False) == pytest.approx(10.0)


def test_leg_greeks_is_none_at_zero_dte():
    assert leg_greeks(spot=100, strike=100, dte_days=0, r=0.03, iv=0.2, is_call=True) is None


def test_leg_greeks_returns_real_greeks_before_expiry():
    g = leg_greeks(spot=100, strike=100, dte_days=30, r=0.03, iv=0.2, is_call=True)
    assert g is not None
    assert 0 < g.delta < 1
