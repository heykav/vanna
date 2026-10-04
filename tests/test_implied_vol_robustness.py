"""Implied-vol solver: wide-grid round trips, no-arbitrage bound errors and
the solver's bracket guarantees."""
import itertools
import math

import pytest

from vanna.pricing import implied_vol as iv_mod
from vanna.pricing.black_scholes import greeks, price
from vanna.pricing.implied_vol import ImpliedVolError, implied_vol, no_arbitrage_bounds

S0 = 100.0
WIDE = list(itertools.product(
    [25.0, 70.0, 100.0, 130.0, 400.0],   # K
    [1 / 365, 30 / 365, 1.0, 5.0],       # T
    [0.01, 0.2, 1.0, 4.0],               # sigma
    [-0.02, 0.05],                       # r
    [0.0, 0.04],                         # q
    [True, False],
))


@pytest.mark.parametrize("K,T,sigma,r,q,is_call", WIDE)
def test_round_trip_price_to_vol_to_price(K, T, sigma, r, q, is_call):
    px = price(S0, K, T, r, sigma, is_call, q)
    lo, _ = no_arbitrage_bounds(S0, K, T, r, is_call, q)
    if px - lo < 1e-12 * S0:
        # No volatility information survives in double precision: the price
        # is its intrinsic floor to ~12 digits. The solver must say so or
        # return something that reprices to the same number.
        try:
            vol = implied_vol(px, S0, K, T, r, is_call, q)
        except ImpliedVolError:
            return
        assert price(S0, K, T, r, vol, is_call, q) == pytest.approx(px, abs=1e-12 * S0)
        return
    vol = implied_vol(px, S0, K, T, r, is_call, q)
    # The attainable accuracy in sigma is limited by the price's rounding
    # error divided by vega (the conditioning of the inverse problem).
    vega = greeks(S0, K, T, r, sigma, is_call, q).vega
    attainable = 4e-16 * px / vega
    assert abs(vol - sigma) <= max(1e-9, 10 * attainable)
    # and it reprices: to 1e-12 relative, or to what the (tiny) sigma error
    # implies through vega where the price is extremely sensitive to sigma
    reprice_tol = 1e-12 * px + 2 * vega * abs(vol - sigma)
    assert abs(price(S0, K, T, r, vol, is_call, q) - px) <= reprice_tol


def test_regression_old_solver_was_6e_6_off_for_a_one_day_deep_otm_call():
    # Old Newton-then-bisection: sigma error 6.7e-6 here, 5 orders of magnitude
    # above what the price's precision allows.
    S, K, T, r, sigma = 100.0, 400.0, 1 / 365, 0.0, 4.0
    px = price(S, K, T, r, sigma, True)
    assert implied_vol(px, S, K, T, r, True) == pytest.approx(sigma, abs=1e-9)


def test_zero_time_value_raises_instead_of_returning_an_arbitrary_vol():
    # The old solver returned 0.156 for a price of exactly 0.0.
    with pytest.raises(ImpliedVolError, match="no time value"):
        implied_vol(0.0, 100.0, 200.0, 30 / 365, 0.02, True)
    S, K, T, r = 100.0, 80.0, 0.5, 0.03
    floor, _ = no_arbitrage_bounds(S, K, T, r, True)
    with pytest.raises(ImpliedVolError, match="no time value"):
        implied_vol(floor, S, K, T, r, True)


@pytest.mark.parametrize("is_call", [True, False])
def test_price_at_or_above_the_cap_is_rejected_with_the_bound_named(is_call):
    S, K, T, r, q = 100.0, 100.0, 1.0, 0.05, 0.02
    _, cap = no_arbitrage_bounds(S, K, T, r, is_call, q)
    assert cap == pytest.approx(S * math.exp(-q * T) if is_call else K * math.exp(-r * T))
    with pytest.raises(ImpliedVolError, match="cap"):
        implied_vol(cap, S, K, T, r, is_call, q)
    with pytest.raises(ImpliedVolError, match="cap"):
        implied_vol(cap * 1.5, S, K, T, r, is_call, q)


def test_price_below_floor_is_rejected():
    with pytest.raises(ImpliedVolError, match="floor"):
        implied_vol(0.01, 100.0, 50.0, 1.0, 0.05, True)


def test_vol_outside_the_search_range_says_which_side():
    S, K, T, r = 100.0, 100.0, 1.0, 0.01
    with pytest.raises(ImpliedVolError, match="above the search range"):
        implied_vol(price(S, K, T, r, 3.0, True), S, K, T, r, True, bisection_bounds=(0.01, 2.0))
    with pytest.raises(ImpliedVolError, match="below the search range"):
        implied_vol(price(S, K, T, r, 0.05, True), S, K, T, r, True, bisection_bounds=(0.1, 2.0))


def test_rejects_invalid_bracket():
    with pytest.raises(ValueError, match="bisection_bounds"):
        implied_vol(10.0, 100.0, 100.0, 1.0, 0.01, True, bisection_bounds=(0.5, 0.1))


@pytest.mark.parametrize("guess", [1e-4 * 1.0001, 0.05, 0.3, 4.9, 50.0])
def test_any_starting_point_converges_to_the_same_root(guess):
    S, K, T, r, sigma = 100.0, 120.0, 0.25, 0.03, 0.35
    px = price(S, K, T, r, sigma, False)
    assert implied_vol(px, S, K, T, r, False, initial_guess=guess) == pytest.approx(sigma, abs=1e-10)


def test_iterates_never_leave_the_bracket(monkeypatch):
    seen = []
    real = iv_mod.greeks

    def spy(S, K, T, r, sigma, is_call, q):
        seen.append(sigma)
        return real(S, K, T, r, sigma, is_call, q)

    monkeypatch.setattr(iv_mod, "greeks", spy)
    lo, hi = 1e-4, 5.0
    for K, T, sigma in [(100.0, 1.0, 0.2), (300.0, 2 / 365, 0.5), (30.0, 0.1, 2.5)]:
        px = price(100.0, K, T, 0.02, sigma, True)
        implied_vol(px, 100.0, K, T, 0.02, True, initial_guess=0.3)
    assert seen and all(lo <= s <= hi for s in seen)


def test_well_conditioned_case_converges_in_few_iterations(monkeypatch):
    calls = []
    real = iv_mod.greeks
    monkeypatch.setattr(iv_mod, "greeks", lambda *a: calls.append(1) or real(*a))
    px = price(100.0, 105.0, 0.5, 0.03, 0.27, True)
    implied_vol(px, 100.0, 105.0, 0.5, 0.03, True)
    assert len(calls) <= 6
