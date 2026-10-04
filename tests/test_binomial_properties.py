"""Binomial trees: no-arbitrage properties (American and European),
convergence of CRR and Leisen-Reimer to closed forms and to a high-step
reference, and the LR lattice's Greeks."""
import itertools
import math

import pytest

from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial

CASES = list(itertools.product(
    [80.0, 100.0, 120.0],    # K
    [0.1, 1.0],              # T
    [0.15, 0.5],             # sigma
    [-0.01, 0.05],           # r
    [0.0, 0.04],             # q
))
METHODS = ["crr", "lr"]
N = 151


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("K,T,sigma,r,q", CASES)
def test_american_price_bounds_and_parity_inequality(method, K, T, sigma, r, q):
    S = 100.0
    c = price_binomial(S, K, T, r, sigma, True, q, N, True, method)
    p = price_binomial(S, K, T, r, sigma, False, q, N, True, method)
    ce = price_binomial(S, K, T, r, sigma, True, q, N, False, method)
    pe = price_binomial(S, K, T, r, sigma, False, q, N, False, method)
    eps = 1e-10
    # early-exercise right is worth >= 0; American >= intrinsic; <= S or K
    assert c >= ce - eps and p >= pe - eps
    assert c >= max(S - K, 0.0) - eps and p >= max(K - S, 0.0) - eps
    assert c <= S + eps and p <= K + eps
    # European tree satisfies put-call parity exactly (up to rounding)
    assert ce - pe == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-9)
    # American put-call parity inequality (holds for r >= 0 and q >= 0):
    #   S e^{-qT} - K <= C - P <= S - K e^{-rT}
    if r >= 0:
        assert S * math.exp(-q * T) - K - eps <= c - p <= S - K * math.exp(-r * T) + eps


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("is_call", [True, False])
def test_american_price_monotone_in_spot_and_vol_and_convex_in_strike(method, is_call):
    T, r, q, sigma = 0.5, 0.04, 0.02, 0.3
    spots = [80.0, 90.0, 100.0, 110.0, 120.0]
    by_spot = [price_binomial(s, 100.0, T, r, sigma, is_call, q, N, True, method) for s in spots]
    diffs = [b - a for a, b in zip(by_spot, by_spot[1:])]
    assert all(d > 0 for d in diffs) if is_call else all(d < 0 for d in diffs)

    by_vol = [price_binomial(100.0, 100.0, T, r, v, is_call, q, N, True, method)
              for v in (0.1, 0.2, 0.3, 0.5)]
    assert all(b > a for a, b in zip(by_vol, by_vol[1:]))

    strikes = [80.0, 90.0, 100.0, 110.0, 120.0]
    by_k = [price_binomial(100.0, k, T, r, sigma, is_call, q, N, True, method) for k in strikes]
    # convexity in strike: second difference >= 0 (butterflies cost >= 0)
    for a, b, c in zip(by_k, by_k[1:], by_k[2:]):
        assert a - 2 * b + c >= -1e-9


@pytest.mark.parametrize("K,T,sigma,r,q", CASES)
@pytest.mark.parametrize("is_call", [True, False])
def test_leisen_reimer_european_converges_much_faster_than_crr(K, T, sigma, r, q, is_call):
    S = 100.0
    exact = bs.price(S, K, T, r, sigma, is_call, q)
    err_lr = abs(price_binomial(S, K, T, r, sigma, is_call, q, 201, False, "lr") - exact)
    err_crr = abs(price_binomial(S, K, T, r, sigma, is_call, q, 201, False, "crr") - exact)
    assert err_lr < 2e-4
    assert err_lr <= err_crr + 1e-12


def test_leisen_reimer_error_falls_roughly_quadratically():
    S, K, T, r, sigma, q = 100.0, 110.0, 0.75, 0.03, 0.3, 0.01
    exact = bs.price(S, K, T, r, sigma, False, q)
    e1 = abs(price_binomial(S, K, T, r, sigma, False, q, 101, False, "lr") - exact)
    e2 = abs(price_binomial(S, K, T, r, sigma, False, q, 401, False, "lr") - exact)
    # 4x the steps -> ~16x smaller error for O(1/n^2); require at least 8x
    assert e2 < e1 / 8


def test_even_steps_round_up_to_odd_for_leisen_reimer():
    args = (100.0, 95.0, 0.5, 0.03, 0.25, False, 0.0)
    assert price_binomial(*args, 200, True, "lr") == price_binomial(*args, 201, True, "lr")


def test_american_call_without_dividends_equals_european_on_the_same_tree():
    for method in METHODS:
        for K in (80.0, 100.0, 120.0):
            am = price_binomial(100.0, K, 1.0, 0.05, 0.3, True, 0.0, N, True, method)
            eu = price_binomial(100.0, K, 1.0, 0.05, 0.3, True, 0.0, N, False, method)
            assert am == pytest.approx(eu, abs=1e-10)


@pytest.mark.parametrize("K", [90.0, 100.0, 110.0])
def test_american_put_crr_and_lr_agree_at_high_step_counts(K):
    # Independent lattices converge to the same American price.
    args = (100.0, K, 1.0, 0.05, 0.3, False, 0.0)
    lr = price_binomial(*args, 2001, True, "lr")
    crr = price_binomial(*args, 4000, True, "crr")
    assert lr == pytest.approx(crr, abs=2e-3)


@pytest.mark.parametrize("is_call", [True, False])
def test_leisen_reimer_tree_greeks_match_closed_form_for_european(is_call):
    S, K, T, r, sigma, q = 100.0, 105.0, 0.5, 0.03, 0.25, 0.02
    ref = bs.greeks(S, K, T, r, sigma, is_call, q)
    g = greeks_binomial(S, K, T, r, sigma, is_call, q, 401, False, "lr")
    assert g.price == pytest.approx(ref.price, abs=1e-5)
    assert g.delta == pytest.approx(ref.delta, abs=5e-4)   # measured ~1.3e-4
    assert g.gamma == pytest.approx(ref.gamma, rel=5e-3)   # measured ~1.1e-3
    # Theta needs the u*d != 1 correction in greeks_binomial: the middle
    # step-2 node of an LR tree is not at S. Uncorrected, this case is off by
    # 59% (call) and 90% (put); corrected, by ~4e-4 relative.
    assert g.theta == pytest.approx(ref.theta, rel=2e-3)


def test_unknown_method_is_rejected():
    with pytest.raises(ValueError, match="method"):
        price_binomial(100.0, 100.0, 1.0, 0.03, 0.2, True, method="jr")
