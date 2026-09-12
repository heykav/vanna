import pytest

from vanna.backtest.attribution import attribute_pnl
from vanna.backtest.strategies import Leg


def test_attribution_terms_plus_residual_equals_total_pnl():
    # This is an algebraic identity by construction - if it doesn't hold
    # exactly, something in the bookkeeping is broken, not just imprecise.
    legs = [Leg(is_call=True, strike=100, quantity=1, dte_days=30)]
    r = attribute_pnl(legs, r=0.03, s0=100, iv0=0.25, elapsed0=0, s1=103, iv1=0.28, elapsed1=3)
    explained = r.delta_pnl + r.gamma_pnl + r.theta_pnl + r.vega_pnl + r.vanna_pnl + r.volga_pnl
    assert r.total_pnl == pytest.approx(explained + r.residual, abs=1e-9)


def test_pure_spot_move_isolates_delta_and_gamma():
    # Only the underlying moves; iv and elapsed time are unchanged, so
    # theta/vega/vanna/volga terms must be exactly zero (their dt/dsigma
    # factor is zero), and delta+gamma should explain nearly all of the
    # P&L for a modest move.
    legs = [Leg(is_call=True, strike=100, quantity=1, dte_days=30)]
    r = attribute_pnl(legs, r=0.03, s0=100, iv0=0.25, elapsed0=5, s1=102, iv1=0.25, elapsed1=5)
    assert r.theta_pnl == 0.0
    assert r.vega_pnl == 0.0
    assert r.vanna_pnl == 0.0
    assert r.volga_pnl == 0.0
    explained = r.delta_pnl + r.gamma_pnl
    assert abs(r.residual) < 0.05 * abs(explained)


def test_pure_time_decay_isolates_theta():
    legs = [Leg(is_call=True, strike=100, quantity=-1, dte_days=30)]  # short call, decays in our favor
    r = attribute_pnl(legs, r=0.03, s0=100, iv0=0.25, elapsed0=0, s1=100, iv1=0.25, elapsed1=1)
    assert r.delta_pnl == 0.0
    assert r.gamma_pnl == 0.0
    assert r.vega_pnl == 0.0
    assert r.theta_pnl != 0.0
    assert abs(r.residual) < 0.1 * abs(r.theta_pnl)


def test_pure_vol_move_isolates_vega_and_volga():
    legs = [Leg(is_call=True, strike=100, quantity=1, dte_days=45)]
    r = attribute_pnl(legs, r=0.03, s0=100, iv0=0.20, elapsed0=0, s1=100, iv1=0.23, elapsed1=0)
    assert r.delta_pnl == 0.0
    assert r.gamma_pnl == 0.0
    assert r.theta_pnl == 0.0
    explained = r.vega_pnl + r.volga_pnl
    assert abs(r.residual) < 0.05 * abs(explained)


def test_residual_shrinks_faster_than_second_order_terms_as_move_shrinks():
    # The Taylor expansion is accurate to O(move^3). Halving a combined
    # spot+vol move should shrink the residual by roughly 2^3 = 8x if the
    # decomposition is actually doing what a second-order expansion should.
    legs = [Leg(is_call=True, strike=100, quantity=1, dte_days=30)]

    big = attribute_pnl(legs, r=0.03, s0=100, iv0=0.25, elapsed0=0, s1=108, iv1=0.33, elapsed1=0)
    small = attribute_pnl(legs, r=0.03, s0=100, iv0=0.25, elapsed0=0, s1=104, iv1=0.29, elapsed1=0)

    assert abs(small.residual) < abs(big.residual) / 4  # generously below the ~8x theoretical ratio


def test_multi_leg_iron_condor_attribution_sums_correctly():
    legs = [
        Leg(is_call=True, strike=110, quantity=-1, dte_days=30),
        Leg(is_call=True, strike=115, quantity=+1, dte_days=30),
        Leg(is_call=False, strike=90, quantity=-1, dte_days=30),
        Leg(is_call=False, strike=85, quantity=+1, dte_days=30),
    ]
    r = attribute_pnl(legs, r=0.03, s0=100, iv0=0.22, elapsed0=0, s1=101, iv1=0.20, elapsed1=5)
    explained = r.delta_pnl + r.gamma_pnl + r.theta_pnl + r.vega_pnl + r.vanna_pnl + r.volga_pnl
    assert r.total_pnl == pytest.approx(explained + r.residual, abs=1e-9)
