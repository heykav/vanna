"""Sequential strategy backtest over a simulated underlying+IV path.

One trade is open at a time: enter at `entry_dte`, exit at `exit_dte`
calendar days later or at expiry, whichever comes first, then
immediately look to enter the next trade. Every trade's P&L is broken
down by Greek via `attribution.attribute_pnl`, summed day-by-day across
the trade's life (not just entry-to-exit in one shot), so a trade that
whipsaws - up then down - gets its P&L attributed correctly across each
leg of the move rather than one net number that hides the round trip.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from vanna.backtest.attribution import attribute_pnl, position_value, AttributionResult
from vanna.backtest.chain import simulate_gbm_path, simulate_iv_path
from vanna.backtest.strategies import STRATEGIES, Leg


@dataclass
class Trade:
    entry_day: int
    exit_day: int
    legs: list[Leg]
    entry_spot: float
    entry_iv: float
    entry_value: float
    exit_value: float
    pnl: float
    attribution: AttributionResult


@dataclass
class BacktestResult:
    equity_curve: list[float]
    trades: list[Trade] = field(default_factory=list)

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)


def run_backtest(strategy: str, s0: float, iv0: float, r: float, mu: float,
                  entry_dte: int, exit_dte: int, n_trades: int,
                  seed: int = 0, vol_of_vol: float = 0.01,
                  iv_mean_reversion: float = 0.05, **strategy_params) -> BacktestResult:
    # This is the facade every entry point (CLI, GUI, browser demo) calls
    # with raw, unvalidated user input. Without checks here, a bad value
    # doesn't fail here with a clear message - it fails several calls deep
    # (nearest_strike crashing on a non-positive spot, numpy refusing a
    # negative `size` for a negative day count, and so on), with an error
    # that points at the wrong place entirely.
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {sorted(STRATEGIES)}")
    if not math.isfinite(s0) or s0 <= 0:
        raise ValueError(f"s0 (spot) must be a positive finite number, got {s0!r}")
    if not math.isfinite(iv0) or iv0 <= 0:
        raise ValueError(f"iv0 (entry IV) must be a positive finite number, got {iv0!r}")
    if not math.isfinite(r):
        raise ValueError(f"r (risk-free rate) must be a finite number, got {r!r}")
    if not math.isfinite(mu):
        raise ValueError(f"mu (drift) must be a finite number, got {mu!r}")
    if entry_dte <= 0:
        raise ValueError(f"entry_dte must be a positive integer, got {entry_dte!r}")
    if exit_dte < 0:
        raise ValueError(f"exit_dte must be zero or a positive integer, got {exit_dte!r}")
    if exit_dte >= entry_dte:
        raise ValueError("exit_dte must be less than entry_dte (you hold until fewer days remain)")
    if n_trades <= 0:
        raise ValueError(f"n_trades must be a positive integer, got {n_trades!r}")

    strategy_fn = STRATEGIES[strategy]
    total_days = n_trades * entry_dte + 5
    spot_path = simulate_gbm_path(s0, mu, iv0, total_days, seed)
    iv_path = simulate_iv_path(iv0, vol_of_vol, iv_mean_reversion, total_days, seed)

    equity_curve = [0.0]
    trades: list[Trade] = []
    day = 0
    cumulative = 0.0

    for _ in range(n_trades):
        if day + entry_dte >= len(spot_path):
            break
        entry_spot, entry_iv = spot_path[day], iv_path[day]
        legs = strategy_fn(spot=entry_spot, r=r, iv=entry_iv, dte_days=entry_dte, **strategy_params)
        held_days = entry_dte - exit_dte
        entry_value = position_value(legs, entry_spot, r, entry_iv, elapsed_days=0)

        # Walk the trade day-by-day so attribution reflects the whole path,
        # not just start/end.
        agg = None
        for d in range(held_days):
            s_from, iv_from = spot_path[day + d], iv_path[day + d]
            s_to, iv_to = spot_path[day + d + 1], iv_path[day + d + 1]
            step = attribute_pnl(legs, r, s_from, iv_from, d, s_to, iv_to, d + 1)
            agg = step if agg is None else _add_attribution(agg, step)

        exit_day = day + held_days
        exit_spot, exit_iv = spot_path[exit_day], iv_path[exit_day]
        exit_value = position_value(legs, exit_spot, r, exit_iv, elapsed_days=held_days)
        pnl = exit_value - entry_value

        trades.append(Trade(entry_day=day, exit_day=exit_day, legs=legs,
                             entry_spot=float(entry_spot), entry_iv=float(entry_iv),
                             entry_value=entry_value, exit_value=exit_value,
                             pnl=pnl, attribution=agg))
        cumulative += pnl
        equity_curve.append(cumulative)
        day = exit_day

    return BacktestResult(equity_curve=equity_curve, trades=trades)


def _add_attribution(a: AttributionResult, b: AttributionResult) -> AttributionResult:
    return AttributionResult(
        total_pnl=a.total_pnl + b.total_pnl,
        delta_pnl=a.delta_pnl + b.delta_pnl,
        gamma_pnl=a.gamma_pnl + b.gamma_pnl,
        theta_pnl=a.theta_pnl + b.theta_pnl,
        vega_pnl=a.vega_pnl + b.vega_pnl,
        vanna_pnl=a.vanna_pnl + b.vanna_pnl,
        volga_pnl=a.volga_pnl + b.volga_pnl,
        residual=a.residual + b.residual,
    )
