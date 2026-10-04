"""Implied volatility: invert Black-Scholes to solve for sigma given a
market price.

The solver is a *safeguarded* Newton-Raphson iteration (in the spirit of
the classic "rtsafe" scheme): it keeps a bracket [lo, hi] in sigma that
always contains the root, takes a Newton step when that step lands
strictly inside the bracket, and bisects the bracket (geometrically, i.e.
in log-sigma) otherwise. Every iteration moves one end of the bracket to
the current iterate, so the method cannot diverge or oscillate the way
plain Newton does when vega is ~0 (deep ITM/OTM or very close to expiry).

Two details make the Newton steps good ones. An ITM price is first
converted by put-call parity into the price of the opposite OTM option,
which has the same implied vol and is pure time value. And below the
inflection point of price(sigma) Newton is run on ln(price) rather than on
price: there (the low-vega wings) the price behaves like exp(-c / sigma^2),
which plain Newton approaches in many tiny steps, while its logarithm is
much closer to linear in sigma. Above the inflection point the price is
concave and much closer to linear, and plain Newton on price is used.

Before iterating, the price is checked against the model-free
no-arbitrage bounds for a European option,

    call:  max(S e^{-qT} - K e^{-rT}, 0) <= C < S e^{-qT}
    put:   max(K e^{-rT} - S e^{-qT}, 0) <= P < K e^{-rT}

and a price outside them raises `ImpliedVolError` naming the bound it
violates, rather than a generic "no root found".

The default starting point is that inflection point, the Manaster-Koehler
(1982) seed sigma_0 = sqrt(2 |ln(F/K)| / T) (F = forward).
"""
from __future__ import annotations

import math

from vanna.pricing.black_scholes import price, greeks, validate_option_inputs


class ImpliedVolError(ValueError):
    pass


# Newton step size (in sigma) below which the iteration is declared
# converged. The price residual alone is not used because at low vega a
# tiny price error can still be a large error in sigma.
_STEP_TOL = 1e-9


def no_arbitrage_bounds(S: float, K: float, T: float, r: float, is_call: bool,
                        q: float = 0.0) -> tuple[float, float]:
    """(lower, upper) model-free no-arbitrage bounds on a European option
    price. Any price in ``[lower, upper)`` with ``lower < price`` has a
    unique Black-Scholes implied volatility."""
    fwd_S = S * math.exp(-q * T)
    fwd_K = K * math.exp(-r * T)
    if is_call:
        return max(fwd_S - fwd_K, 0.0), fwd_S
    return max(fwd_K - fwd_S, 0.0), fwd_K


def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                 is_call: bool, q: float = 0.0,
                 initial_guess: float | None = None,
                 newton_tol: float = 1e-8,
                 newton_max_iter: int = 50,
                 bisection_bounds: tuple[float, float] = (1e-4, 5.0),
                 bisection_tol: float = 1e-10,
                 bisection_max_iter: int = 100) -> float:
    """Solve for sigma such that ``price(S, K, T, r, sigma, is_call, q)``
    equals ``market_price``.

    ``bisection_bounds`` is the search bracket in sigma. The iteration stops
    when the Newton step is below 1e-9 in sigma (the step is then applied, so the
    returned error is of order the step squared) with a price residual below
    ``newton_tol``, or when the bracket is narrower than ``bisection_tol``;
    ``newton_max_iter + bisection_max_iter`` caps the total iteration count.
    ``initial_guess=None`` uses the Manaster-Koehler seed.
    """
    # Validate S/K/T/r *before* anything below tries a sigma, so a bad S or
    # K surfaces as a clear error pointing at the actual bad input instead
    # of a confusing solver failure.
    validate_option_inputs(S, K, T, sigma=1.0, r=r, q=q)
    if not math.isfinite(market_price) or market_price < 0:
        raise ImpliedVolError(f"market_price must be a non-negative finite number, got {market_price!r}")
    lo0, hi0 = lo, hi = bisection_bounds
    if not (0.0 < lo < hi and math.isfinite(hi)):
        raise ValueError(f"bisection_bounds must satisfy 0 < lo < hi < inf, got {bisection_bounds!r}")

    # The correct no-arbitrage floor for a *European* option discounts both
    # legs first - S - K undiscounted looks like a hard floor but isn't one;
    # with enough time value of money, a European put can trade well below
    # K - S and still be perfectly arbitrage-free. Using the undiscounted
    # intrinsic value here was a real bug, caught by testing against a real
    # deep-ITM long-dated case rather than only round-trip self-consistency.
    floor, cap = no_arbitrage_bounds(S, K, T, r, is_call, q)
    if market_price < floor - 1e-9:
        raise ImpliedVolError(
            f"price {market_price} is below the discounted no-arbitrage floor "
            f"{floor} - not a valid option price, no volatility can rationalize it"
        )
    if market_price <= floor:
        # Zero time value: the price is reproduced only in the limit
        # sigma -> 0 (or not at all), so there is no finite implied vol to
        # return. An earlier version returned an arbitrary sigma here.
        raise ImpliedVolError(
            f"price {market_price} has no time value over the discounted floor "
            f"{floor}: the implied vol is zero/undefined"
        )
    if market_price >= cap:
        raise ImpliedVolError(
            f"price {market_price} is at or above the no-arbitrage cap {cap} "
            f"({'S*exp(-qT)' if is_call else 'K*exp(-rT)'}) - an option is never "
            "worth that much, no volatility can rationalize it"
        )

    # Inflection point of price(sigma) (Manaster-Koehler): convex below,
    # concave above.
    log_moneyness = math.log(S / K) + (r - q) * T  # ln(F / K)
    sigma_inflect = math.sqrt(2.0 * abs(log_moneyness) / T)
    if initial_guess is None:
        initial_guess = sigma_inflect
    sigma = initial_guess if lo < initial_guess < hi else math.sqrt(lo * hi)

    # Iterate on the out-of-the-money (forward basis) option: by put-call
    # parity an ITM option's price minus its discounted intrinsic value is
    # exactly the price of the opposite OTM option at the same sigma. The
    # OTM price is pure time value and strictly positive, so ln(price) is
    # defined (see the module docstring for why that matters).
    otm_is_call = is_call if floor == 0.0 else not is_call
    target = market_price - floor
    log_target = math.log(target)

    for _ in range(newton_max_iter + bisection_max_iter):
        g = greeks(S, K, T, r, sigma, otm_is_call, q)
        diff = g.price - target
        if diff == 0.0:
            return sigma
        # The price is strictly increasing in sigma, so the sign of the
        # residual says which side of the root sigma is on.
        if diff > 0:
            hi = sigma
        else:
            lo = sigma
        newton = math.nan
        if g.vega > 0.0 and g.price > 0.0:
            price_step = diff / g.vega
            if abs(price_step) < _STEP_TOL and abs(diff) < newton_tol:
                newton = sigma - price_step  # converged on a real root
                return newton if lo <= newton <= hi else sigma
            if sigma < sigma_inflect:
                # Convex, exp(-c / sigma^2)-like region: Newton on ln(price),
                # d ln(price) / d sigma = vega / price.
                newton = sigma - (math.log(g.price) - log_target) * g.price / g.vega
            else:
                newton = sigma - price_step
        newton_inside = lo < newton < hi
        if hi - lo < bisection_tol:
            if newton_inside:
                return newton  # last Newton step, inside the (tiny) bracket
            break
        # Newton step if it stays strictly inside the bracket, else bisect
        # (geometrically: in log-sigma, since the bracket spans decades).
        sigma = newton if newton_inside else math.sqrt(lo * hi)

    # Stopped on bracket width (or the iteration cap). If one end of the
    # bracket never moved, the root may lie outside the search range:
    # check that end explicitly and say which side.
    if lo == lo0 and price(S, K, T, r, lo0, is_call, q) > market_price:
        raise ImpliedVolError(
            f"price {market_price} is below the model price at sigma={lo0}: the "
            f"implied vol, if any, is below the search range {bisection_bounds} "
            f"(S={S}, K={K}, T={T})"
        )
    if hi == hi0 and price(S, K, T, r, hi0, is_call, q) < market_price:
        raise ImpliedVolError(
            f"price {market_price} is above the model price at sigma={hi0}: the "
            f"implied vol is above the search range {bisection_bounds} "
            f"(S={S}, K={K}, T={T})"
        )
    return 0.5 * (lo + hi)
