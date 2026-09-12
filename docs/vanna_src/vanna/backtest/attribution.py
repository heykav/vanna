"""Greek-attributed P&L: the actual point of this library.

optopsy (and most backtesting tools) will tell you a trade made or lost
money. They generally won't tell you *why*, in the language a real
options desk uses to think about risk: how much of that P&L came from
the underlying moving (delta), from the rate of that move accelerating
(gamma), from time passing (theta), from implied vol changing (vega),
and from the cross-terms (vanna, volga) that dominate exactly the
situations - a vol crush after earnings, a gamma squeeze into expiry -
where "the P&L moved a lot and I'm not sure why" is the actual problem
people have.

The technique is a second-order Taylor expansion of option value in
(spot, vol, time), evaluated with the Greeks at the *start* of the
period:

    dV ~= Delta*dS + 0.5*Gamma*dS^2 + Theta*dt + Vega*dSigma
          + Vanna*dS*dSigma + 0.5*Volga*dSigma^2

This is exact only in the limit of an infinitesimal period; over a real
day (or several), it's an approximation, and the leftover
(actual dV minus the sum of the terms above) is reported honestly as
`residual` rather than folded into one of the named buckets - a real risk
manager would never let "vega P&L" silently absorb third-order effects
just to make the pie chart add up cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass

from vanna.backtest.chain import price_leg, leg_greeks, TRADING_DAYS_PER_YEAR
from vanna.backtest.strategies import Leg


@dataclass(frozen=True)
class AttributionResult:
    total_pnl: float
    delta_pnl: float
    gamma_pnl: float
    theta_pnl: float
    vega_pnl: float
    vanna_pnl: float
    volga_pnl: float
    residual: float


def position_value(legs: list[Leg], spot: float, r: float, iv: float, elapsed_days: int) -> float:
    total = 0.0
    for leg in legs:
        remaining = leg.dte_days - elapsed_days
        total += leg.quantity * price_leg(spot, leg.strike, remaining, r, iv, leg.is_call)
    return total


def attribute_pnl(legs: list[Leg], r: float,
                   s0: float, iv0: float, elapsed0: int,
                   s1: float, iv1: float, elapsed1: int) -> AttributionResult:
    ds = s1 - s0
    dsigma = iv1 - iv0
    dt = (elapsed1 - elapsed0) / TRADING_DAYS_PER_YEAR

    v0 = position_value(legs, s0, r, iv0, elapsed0)
    v1 = position_value(legs, s1, r, iv1, elapsed1)
    total_pnl = v1 - v0

    delta = gamma = theta = vega = vanna = volga = 0.0
    for leg in legs:
        remaining = leg.dte_days - elapsed0
        g = leg_greeks(s0, leg.strike, remaining, r, iv0, leg.is_call)
        if g is None:
            continue  # already at/past expiry at the start of this period
        delta += leg.quantity * g.delta
        gamma += leg.quantity * g.gamma
        theta += leg.quantity * g.theta
        vega += leg.quantity * g.vega
        vanna += leg.quantity * g.vanna
        volga += leg.quantity * g.volga

    delta_pnl = delta * ds
    gamma_pnl = 0.5 * gamma * ds ** 2
    theta_pnl = theta * dt
    vega_pnl = vega * dsigma
    vanna_pnl = vanna * ds * dsigma
    volga_pnl = 0.5 * volga * dsigma ** 2

    explained = delta_pnl + gamma_pnl + theta_pnl + vega_pnl + vanna_pnl + volga_pnl
    residual = total_pnl - explained

    return AttributionResult(
        total_pnl=total_pnl, delta_pnl=delta_pnl, gamma_pnl=gamma_pnl,
        theta_pnl=theta_pnl, vega_pnl=vega_pnl, vanna_pnl=vanna_pnl,
        volga_pnl=volga_pnl, residual=residual,
    )
