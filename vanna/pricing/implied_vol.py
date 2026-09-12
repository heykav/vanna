"""Implied volatility: invert Black-Scholes to solve for sigma given a
market price.

Newton-Raphson (using vega as the derivative) converges in a handful of
iterations when it converges at all - but vega goes to ~0 for deep
ITM/OTM options and for options very close to expiry, and Newton with a
near-zero derivative either diverges or oscillates. Rather than paper
over that with a maximum-iteration cutoff and hope, this falls back to
bisection - slower, but it can't diverge, because it only ever needs the
price function to be monotonic in sigma (which it is) and a bracket that
contains the root (which a wide-enough [1e-4, 5.0] vol range reliably
does for any real market price between intrinsic value and infinity).
"""
from __future__ import annotations

import math

from vanna.pricing.black_scholes import price, greeks


class ImpliedVolError(ValueError):
    pass


def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                 is_call: bool, q: float = 0.0,
                 initial_guess: float = 0.3,
                 newton_tol: float = 1e-8,
                 newton_max_iter: int = 50,
                 bisection_bounds: tuple[float, float] = (1e-4, 5.0),
                 bisection_tol: float = 1e-6,
                 bisection_max_iter: int = 100) -> float:
    # The correct no-arbitrage floor for a *European* option discounts both
    # legs first - S - K undiscounted looks like a hard floor but isn't one;
    # with enough time value of money, a European put can trade well below
    # K - S and still be perfectly arbitrage-free. Using the undiscounted
    # intrinsic value here was a real bug, caught by testing against a real
    # deep-ITM long-dated case rather than only round-trip self-consistency.
    fwd_S = S * math.exp(-q * T)
    fwd_K = K * math.exp(-r * T)
    floor = max(fwd_S - fwd_K, 0.0) if is_call else max(fwd_K - fwd_S, 0.0)
    if market_price < floor - 1e-9:
        raise ImpliedVolError(
            f"price {market_price} is below the discounted no-arbitrage floor "
            f"{floor} - not a valid option price, no volatility can rationalize it"
        )

    sigma = initial_guess
    for _ in range(newton_max_iter):
        try:
            g = greeks(S, K, T, r, sigma, is_call, q)
        except ValueError:
            break
        diff = g.price - market_price
        if abs(diff) < newton_tol:
            return sigma
        vega = g.vega
        if vega < 1e-8:
            break  # flat derivative - Newton isn't reliable here, fall back
        sigma -= diff / vega
        if sigma <= 0 or sigma > bisection_bounds[1]:
            break  # stepped outside a sane range - fall back rather than chase it

    return _bisection(market_price, S, K, T, r, is_call, q,
                       bisection_bounds, bisection_tol, bisection_max_iter)


def _bisection(market_price, S, K, T, r, is_call, q, bounds, tol, max_iter):
    lo, hi = bounds
    f_lo = price(S, K, T, r, lo, is_call, q) - market_price
    f_hi = price(S, K, T, r, hi, is_call, q) - market_price
    if f_lo * f_hi > 0:
        raise ImpliedVolError(
            f"no root bracketed in sigma in {bounds} for price={market_price} "
            f"(S={S}, K={K}, T={T}) - price is outside what any volatility "
            "in this range can produce"
        )
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = price(S, K, T, r, mid, is_call, q) - market_price
        if abs(f_mid) < tol or (hi - lo) < tol:
            return mid
        if f_lo * f_mid <= 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
