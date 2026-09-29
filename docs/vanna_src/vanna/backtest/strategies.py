"""Multi-leg strategy definitions.

A strategy is just a function that looks at today's spot/iv/rate and a
target DTE, and returns the legs to open. Fewer strategies than optopsy's
38 on purpose - these ten are implemented and tested properly rather than
stamped out from a template, which matters more for a library whose whole
pitch is "the numbers underneath are actually right."
"""
from __future__ import annotations

from dataclasses import dataclass

from vanna.backtest.chain import nearest_strike


@dataclass(frozen=True)
class Leg:
    is_call: bool
    strike: float
    quantity: int  # +1 = long one contract, -1 = short one contract
    dte_days: int  # DTE at entry, for this leg's expiry
    # A stock leg is one share of the underlying (delta exactly 1, no
    # gamma/theta/vega). `strike` holds the entry spot as a reference price
    # and `is_call`/`dte_days` are unused for pricing.
    is_stock: bool = False


def _k(spot, delta, dte, r, iv, is_call, q=0.0):
    return nearest_strike(spot, delta, dte, r, iv, is_call, q=q)


def long_call(spot, r, iv, dte_days, delta=0.35, q=0.0, **_):
    return [Leg(True, _k(spot, delta, dte_days, r, iv, True, q), +1, dte_days)]


def short_call(spot, r, iv, dte_days, delta=0.35, q=0.0, **_):
    return [Leg(True, _k(spot, delta, dte_days, r, iv, True, q), -1, dte_days)]


def long_put(spot, r, iv, dte_days, delta=0.35, q=0.0, **_):
    return [Leg(False, _k(spot, delta, dte_days, r, iv, False, q), +1, dte_days)]


def short_put(spot, r, iv, dte_days, delta=0.35, q=0.0, **_):
    return [Leg(False, _k(spot, delta, dte_days, r, iv, False, q), -1, dte_days)]


def long_straddle(spot, r, iv, dte_days, q=0.0, **_):
    k = round(spot)
    return [Leg(True, k, +1, dte_days), Leg(False, k, +1, dte_days)]


def short_straddle(spot, r, iv, dte_days, q=0.0, **_):
    k = round(spot)
    return [Leg(True, k, -1, dte_days), Leg(False, k, -1, dte_days)]


def long_call_spread(spot, r, iv, dte_days, long_delta=0.40, short_delta=0.20, q=0.0, **_):
    k_long = _k(spot, long_delta, dte_days, r, iv, True, q)
    k_short = _k(spot, short_delta, dte_days, r, iv, True, q)
    return [Leg(True, k_long, +1, dte_days), Leg(True, k_short, -1, dte_days)]


def short_call_spread(spot, r, iv, dte_days, long_delta=0.40, short_delta=0.20, q=0.0, **_):
    k_long = _k(spot, long_delta, dte_days, r, iv, True, q)
    k_short = _k(spot, short_delta, dte_days, r, iv, True, q)
    return [Leg(True, k_long, -1, dte_days), Leg(True, k_short, +1, dte_days)]


def iron_condor(spot, r, iv, dte_days, wing_delta=0.16, body_delta=0.30, q=0.0, **_):
    call_short = _k(spot, body_delta, dte_days, r, iv, True, q)
    call_long = _k(spot, wing_delta, dte_days, r, iv, True, q)
    put_short = _k(spot, body_delta, dte_days, r, iv, False, q)
    put_long = _k(spot, wing_delta, dte_days, r, iv, False, q)
    return [
        Leg(True, call_short, -1, dte_days),
        Leg(True, call_long, +1, dte_days),
        Leg(False, put_short, -1, dte_days),
        Leg(False, put_long, +1, dte_days),
    ]


def covered_call(spot, r, iv, dte_days, delta=0.30, q=0.0, **_):
    # Long one share of the underlying (a real stock leg, priced at spot
    # with delta 1) plus a short OTM call. Quantities are per-share, like
    # every other leg here, so the call is 1 option on 1 share.
    return [
        Leg(True, float(spot), +1, dte_days, is_stock=True),
        Leg(True, _k(spot, delta, dte_days, r, iv, True, q), -1, dte_days),
    ]


STRATEGIES = {
    "long_call": long_call,
    "short_call": short_call,
    "long_put": long_put,
    "short_put": short_put,
    "long_straddle": long_straddle,
    "short_straddle": short_straddle,
    "long_call_spread": long_call_spread,
    "short_call_spread": short_call_spread,
    "iron_condor": iron_condor,
    "covered_call": covered_call,
}
