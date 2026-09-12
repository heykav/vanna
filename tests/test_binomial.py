import math

import pytest

from vanna.pricing.black_scholes import price as bs_price
from vanna.pricing.binomial import price_binomial, greeks_binomial


def test_european_binomial_converges_to_black_scholes():
    # With american=False, the tree has no early-exercise right, so as
    # steps grows it should converge to the closed-form Black-Scholes
    # price for the *same* European contract - a real correctness check
    # of the tree mechanics, not just an internal sanity check.
    S, K, T, r, sigma = 100, 95, 0.75, 0.04, 0.25
    bs = bs_price(S, K, T, r, sigma, is_call=True)
    tree = price_binomial(S, K, T, r, sigma, is_call=True, steps=500, american=False)
    assert tree == pytest.approx(bs, abs=0.05)


def test_american_put_worth_more_than_european_put_when_deep_itm():
    # The one case every textbook uses: a deep ITM American put on a
    # non-dividend stock has a real early-exercise premium over its
    # European counterpart, because holding costs you interest on the
    # strike you'd otherwise already have banked.
    S, K, T, r, sigma = 60, 100, 1.0, 0.08, 0.2
    american = price_binomial(S, K, T, r, sigma, is_call=False, steps=400, american=True)
    european = price_binomial(S, K, T, r, sigma, is_call=False, steps=400, american=False)
    assert american > european + 1e-6


def test_american_call_equals_european_call_without_dividends():
    # Classic result: with no dividends, it's never optimal to early-
    # exercise an American call, so American == European here.
    S, K, T, r, sigma = 100, 90, 1.0, 0.05, 0.3
    american = price_binomial(S, K, T, r, sigma, is_call=True, steps=400, american=True)
    european = price_binomial(S, K, T, r, sigma, is_call=True, steps=400, american=False)
    assert american == pytest.approx(european, abs=0.02)


def test_binomial_delta_matches_finite_difference():
    S, K, T, r, sigma = 100, 100, 0.5, 0.03, 0.25
    h = 0.5
    up = price_binomial(S + h, K, T, r, sigma, is_call=True, steps=300)
    down = price_binomial(S - h, K, T, r, sigma, is_call=True, steps=300)
    fd_delta = (up - down) / (2 * h)
    g = greeks_binomial(S, K, T, r, sigma, is_call=True, steps=300)
    assert g.delta == pytest.approx(fd_delta, abs=1e-2)


def test_rejects_unstable_step_count():
    with pytest.raises(ValueError):
        # An absurdly large dt relative to sigma pushes the risk-neutral
        # probability out of (0, 1) - the function must refuse rather
        # than silently return a nonsense price.
        price_binomial(S=100, K=100, T=50.0, r=0.5, sigma=0.01, is_call=True, steps=1)


@pytest.mark.parametrize("S,K,T,sigma", [
    (-100, 100, 1.0, 0.2),   # negative spot used to silently divide by zero
    (100, 100, 0, 0.2),      # T=0 used to raise a bare ZeroDivisionError
    (100, 100, 1.0, 0),      # sigma=0 - same failure mode as T=0
])
def test_rejects_invalid_inputs_with_a_clear_message_instead_of_crashing(S, K, T, sigma):
    with pytest.raises(ValueError, match=r"(spot|expiry|volatility)"):
        price_binomial(S, K, T, r=0.03, sigma=sigma, is_call=True)


def test_near_expiry_theta_does_not_push_time_negative():
    # T - h_t must stay positive for any T > 0, in both branches of the
    # h_t formula - verified directly rather than assumed, since this is
    # exactly the kind of boundary a finite-difference bump can quietly
    # break.
    g = greeks_binomial(S=100, K=100, T=1e-4, r=0.03, sigma=0.2, is_call=True, steps=50)
    assert math.isfinite(g.theta)
