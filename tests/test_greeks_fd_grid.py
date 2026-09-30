"""Every closed-form Greek against a central finite difference of the pricer,
over a grid that includes the edge cases where transcription errors and
floating-point problems usually hide: two-day expiries, deep ITM/OTM
strikes, 3% and 150% vol, negative rates and a non-zero dividend yield.

First-order Greeks are differenced from `price()` and second-order Greeks
from `price()` too (gamma and volga as second differences, vanna as a mixed
difference), so no Greek is checked only against another Greek. Steps are
scaled to the natural width of each variable (e.g. S * sigma * sqrt(T) for
spot), and Richardson extrapolation of two step sizes removes the O(h^2)
truncation error, so the tolerance can be tight.
"""
import itertools
import math

import pytest

from vanna.pricing.black_scholes import greeks, price

S0 = 100.0
GRID = list(itertools.product(
    [60.0, 95.0, 100.0, 105.0, 150.0],   # K: deep ITM/OTM and near the money
    [2 / 365, 0.25, 3.0],                # T
    [0.03, 0.25, 1.5],                   # sigma
    [-0.01, 0.04],                       # r (negative rates included)
    [0.0, 0.03],                         # q
    [True, False],
))


def _central(f, x, h):
    return (f(x + h) - f(x - h)) / (2 * h)


def _second(f, x, h):
    return (f(x + h) - 2 * f(x) + f(x - h)) / (h * h)


def _richardson(rule, f, x, h):
    # Both rules are O(h^2): combine h and h/2 to cancel the leading term.
    return (4 * rule(f, x, h / 2) - rule(f, x, h)) / 3


def _fd_greeks(K, T, sigma, r, q, is_call):
    def px(S=S0, T_=T, sig=sigma, r_=r):
        return price(S, K, T_, r_, sig, is_call, q)

    # Steps are a small fraction of each variable's natural scale, shrunk
    # further in the tails (large |d1|), where the price curves faster.
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma ** 2) * T) / vol_sqrt_t
    shrink = 1.0 + abs(d1)
    hs = 0.05 * S0 * vol_sqrt_t / shrink
    hv = 0.05 * sigma / shrink
    ht = 0.05 * T / shrink
    hr = 1e-3
    fd = {
        "delta": _richardson(_central, lambda s: px(S=s), S0, hs),
        "gamma": _richardson(_second, lambda s: px(S=s), S0, hs),
        "vega": _richardson(_central, lambda v: px(sig=v), sigma, hv),
        "volga": _richardson(_second, lambda v: px(sig=v), sigma, hv),
        "theta": -_richardson(_central, lambda t: px(T_=t), T, ht),
        "rho": _richardson(_central, lambda x: px(r_=x), r, hr),
        "vanna": _richardson(
            _central,
            lambda v: _richardson(_central, lambda s: px(S=s, sig=v), S0, hs),
            sigma, hv),
    }
    # Error scale for each Greek: the size of the price change the Greek
    # explains over one step, divided back out, plus a relative term.
    scale = {
        "delta": 1.0, "gamma": 1.0 / hs, "vega": S0 * math.sqrt(T),
        "volga": S0 * math.sqrt(T) / sigma, "theta": S0 / T, "rho": S0 * T,
        "vanna": math.sqrt(T) / sigma,
    }
    return fd, scale


@pytest.mark.parametrize("K,T,sigma,r,q,is_call", GRID)
def test_every_greek_matches_finite_difference_of_price(K, T, sigma, r, q, is_call):
    g = greeks(S0, K, T, r, sigma, is_call, q)
    fd, scale = _fd_greeks(K, T, sigma, r, q, is_call)
    for name, ref in fd.items():
        analytic = getattr(g, name)
        tol = 1e-4 * abs(ref) + 1e-7 * scale[name]
        assert abs(analytic - ref) <= tol, (name, analytic, ref, tol)
