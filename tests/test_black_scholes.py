import math

import pytest

from vanna.pricing.black_scholes import price, greeks


def test_hull_textbook_call_price():
    # Hull, "Options, Futures, and Other Derivatives": S=42, K=40, T=0.5,
    # r=10%, sigma=20%, no dividend -> call = 4.76 (a well-known checkable
    # reference value, not just internal self-consistency).
    c = price(S=42, K=40, T=0.5, r=0.10, sigma=0.20, is_call=True)
    assert c == pytest.approx(4.76, abs=0.01)


@pytest.mark.parametrize("S,K,T,r,q,sigma", [
    (100, 100, 1.0, 0.05, 0.0, 0.2),
    (100, 90, 0.25, 0.03, 0.01, 0.35),
    (50, 60, 2.0, 0.01, 0.0, 0.5),
    (42, 40, 0.5, 0.10, 0.0, 0.2),
])
def test_put_call_parity(S, K, T, r, q, sigma):
    c = price(S, K, T, r, sigma, is_call=True, q=q)
    p = price(S, K, T, r, sigma, is_call=False, q=q)
    lhs = c - p
    rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
    assert lhs == pytest.approx(rhs, abs=1e-8)


PARAM_GRID = [
    (100, 100, 1.0, 0.05, 0.0, 0.2, True),
    (100, 100, 1.0, 0.05, 0.0, 0.2, False),
    (100, 90, 0.25, 0.03, 0.01, 0.35, True),
    (100, 110, 0.25, 0.03, 0.01, 0.35, False),
    (50, 60, 2.0, 0.01, 0.0, 0.5, True),
    (42, 40, 0.5, 0.10, 0.0, 0.2, True),
]


def _fd_derivative(f, x, h):
    return (f(x + h) - f(x - h)) / (2 * h)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_delta_matches_finite_difference(S, K, T, r, q, sigma, is_call):
    h = 1e-4 * S
    fd = _fd_derivative(lambda s: price(s, K, T, r, sigma, is_call, q), S, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).delta
    assert analytic == pytest.approx(fd, abs=1e-5)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_gamma_matches_finite_difference_of_delta(S, K, T, r, q, sigma, is_call):
    h = 1e-3 * S
    fd = _fd_derivative(lambda s: greeks(s, K, T, r, sigma, is_call, q).delta, S, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).gamma
    assert analytic == pytest.approx(fd, abs=1e-4)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_vega_matches_finite_difference(S, K, T, r, q, sigma, is_call):
    h = 1e-4
    fd = _fd_derivative(lambda v: price(S, K, T, r, v, is_call, q), sigma, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).vega
    assert analytic == pytest.approx(fd, abs=1e-5)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_rho_matches_finite_difference(S, K, T, r, q, sigma, is_call):
    h = 1e-5
    fd = _fd_derivative(lambda rate: price(S, K, T, rate, sigma, is_call, q), r, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).rho
    assert analytic == pytest.approx(fd, abs=1e-4)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_theta_matches_finite_difference(S, K, T, r, q, sigma, is_call):
    # Theta is dPrice/dt where t is calendar time, i.e. -dPrice/dT.
    h = 1e-5
    fd = -_fd_derivative(lambda t: price(S, K, t, r, sigma, is_call, q), T, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).theta
    assert analytic == pytest.approx(fd, abs=1e-3)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_vanna_matches_finite_difference_of_delta_wrt_vol(S, K, T, r, q, sigma, is_call):
    h = 1e-4
    fd = _fd_derivative(lambda v: greeks(S, K, T, r, v, is_call, q).delta, sigma, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).vanna
    assert analytic == pytest.approx(fd, abs=1e-4)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_vanna_matches_finite_difference_of_vega_wrt_spot(S, K, T, r, q, sigma, is_call):
    # vanna is a mixed partial: d(delta)/d(sigma) == d(vega)/d(S). Checking
    # it both ways catches a formula that's merely self-consistent with one
    # side but not actually the real mixed partial.
    h = 1e-4 * S
    fd = _fd_derivative(lambda s: greeks(s, K, T, r, sigma, is_call, q).vega, S, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).vanna
    assert analytic == pytest.approx(fd, abs=1e-3)


@pytest.mark.parametrize("S,K,T,r,q,sigma,is_call", PARAM_GRID)
def test_volga_matches_finite_difference_of_vega_wrt_vol(S, K, T, r, q, sigma, is_call):
    h = 1e-4
    fd = _fd_derivative(lambda v: greeks(S, K, T, r, v, is_call, q).vega, sigma, h)
    analytic = greeks(S, K, T, r, sigma, is_call, q).volga
    assert analytic == pytest.approx(fd, abs=1e-3)


def test_deep_itm_call_delta_approaches_one():
    g = greeks(S=1000, K=10, T=0.1, r=0.02, sigma=0.2, is_call=True)
    assert g.delta == pytest.approx(1.0, abs=1e-6)


def test_deep_otm_put_delta_approaches_zero():
    g = greeks(S=1000, K=10, T=0.1, r=0.02, sigma=0.2, is_call=False)
    assert g.delta == pytest.approx(0.0, abs=1e-6)
