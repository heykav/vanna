"""Closed-form Black-Scholes-Merton pricing and Greeks for European options.

Conventions: S = spot, K = strike, T = time to expiry in years, r = risk-free
rate (continuously compounded), q = continuous dividend/borrow yield,
sigma = annualized volatility. `is_call=True` for calls, False for puts.

First-order Greeks (delta, gamma, theta, vega, rho) use the standard
closed-form results and are the ones every quant library gets from a
textbook. The second-order Greeks (vanna, volga) are also implemented in
closed form here - but the thing that actually makes them trustworthy is
`tests/test_black_scholes.py`, which cross-checks every one of them
against a centered finite difference of the first-order Greeks. A wrong
sign or a transposed d1/d2 in a second-order Greek formula is an easy,
quiet way to ship something subtly broken, so the analytic formula is
never treated as correct just because it was transcribed carefully - it's
correct because the finite-difference check agrees with it to 1e-6.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _phi(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via erf (no scipy dependency for the core)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def validate_option_inputs(S: float, K: float, T: float, sigma: float,
                            r: float | None = None, q: float | None = None) -> None:
    """Raises a specific, actionable ValueError for the first bad input,
    rather than letting a negative/zero S or K fall through to a bare
    `math domain error` from log() or a ZeroDivisionError three calls deep.
    This matters more than it looks: every one of S, K, sigma reaches this
    code from raw user-typed numbers in the CLI, the GUI, and the browser
    demo - none of them are ever validated upstream of here."""
    for name, value in (("S (spot)", S), ("K (strike)", K), ("T (time to expiry)", T)):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number, got {value!r}")
        if value <= 0:
            raise ValueError(f"{name} must be positive, got {value!r}")
    if not math.isfinite(sigma):
        raise ValueError(f"sigma (volatility) must be a finite number, got {sigma!r}")
    if sigma <= 0:
        raise ValueError(f"sigma (volatility) must be positive, got {sigma!r}")
    if r is not None and not math.isfinite(r):
        raise ValueError(f"r (risk-free rate) must be a finite number, got {r!r}")
    if q is not None and not math.isfinite(q):
        raise ValueError(f"q (dividend yield) must be a finite number, got {q!r}")


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    validate_option_inputs(S, K, T, sigma, r, q)
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


@dataclass(frozen=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float  # per 1.00 (100 vol points) of sigma, i.e. divide by 100 for "per 1 vol point"
    theta: float  # per year; divide by 365 for per-calendar-day
    rho: float  # per 1.00 (100%) of r
    vanna: float  # d(delta)/d(sigma) == d(vega)/d(S)
    volga: float  # d(vega)/d(sigma), a.k.a. vomma


def price(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0) -> float:
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    if is_call:
        return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def greeks(S: float, K: float, T: float, r: float, sigma: float, is_call: bool, q: float = 0.0) -> Greeks:
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    pdf_d1 = _phi(d1)
    sqrt_t = math.sqrt(T)

    if is_call:
        px = S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)
        delta = disc_q * _norm_cdf(d1)
        theta = (
            -S * disc_q * pdf_d1 * sigma / (2 * sqrt_t)
            - r * K * disc_r * _norm_cdf(d2)
            + q * S * disc_q * _norm_cdf(d1)
        )
        rho = K * T * disc_r * _norm_cdf(d2)
    else:
        px = K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)
        delta = disc_q * (_norm_cdf(d1) - 1.0)
        theta = (
            -S * disc_q * pdf_d1 * sigma / (2 * sqrt_t)
            + r * K * disc_r * _norm_cdf(-d2)
            - q * S * disc_q * _norm_cdf(-d1)
        )
        rho = -K * T * disc_r * _norm_cdf(-d2)

    gamma = disc_q * pdf_d1 / (S * sigma * sqrt_t)
    vega = S * disc_q * pdf_d1 * sqrt_t
    vanna = -disc_q * pdf_d1 * d2 / sigma
    volga = vega * d1 * d2 / sigma

    return Greeks(price=px, delta=delta, gamma=gamma, vega=vega, theta=theta,
                  rho=rho, vanna=vanna, volga=volga)
