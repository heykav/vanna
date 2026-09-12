"""Synthetic option chains and underlying paths.

vanna is model-driven, not historical-data-driven: rather than requiring a
paid market-data subscription (optopsy's data CLI needs an EODHD API key)
to have anything to backtest against, the default path simulates the
underlying with geometric Brownian motion and prices every option in the
chain directly from Black-Scholes at each snapshot. That's a deliberate,
disclosed scope choice, not a hidden limitation: it means every example,
test, and demo in this repo is exactly reproducible from a seed and needs
no external data or API key - and it means the "market" here is only ever
as realistic as GBM + constant/simple-skew implied vol actually is, which
is a real, known simplification (no smile dynamics, no vol clustering, no
jumps). A real historical-chain loader is a legitimate v2, not implemented
here yet.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vanna.pricing.black_scholes import price as bs_price, greeks as bs_greeks


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class ChainSnapshot:
    day: int
    spot: float
    iv: float  # flat implied vol used to price this snapshot's chain
    r: float


def simulate_gbm_path(s0: float, mu: float, sigma: float, days: int, seed: int) -> np.ndarray:
    """Daily-close underlying path under GBM, length `days + 1` (includes day 0)."""
    rng = np.random.default_rng(seed)
    dt = 1.0 / TRADING_DAYS_PER_YEAR
    shocks = rng.normal(loc=(mu - 0.5 * sigma ** 2) * dt, scale=sigma * np.sqrt(dt), size=days)
    log_path = np.concatenate(([0.0], np.cumsum(shocks)))
    return s0 * np.exp(log_path)


def simulate_iv_path(iv0: float, vol_of_vol: float, mean_reversion: float,
                      days: int, seed: int, floor: float = 0.03) -> np.ndarray:
    """A simple mean-reverting (Ornstein-Uhlenbeck-ish) daily IV path, so a
    backtest isn't stuck pricing every day off one frozen vol number. This
    is a stylized proxy for real vol dynamics, not a calibrated vol model -
    good enough to make vega/vanna/volga P&L attribution show something
    real to attribute, without pretending to forecast actual markets."""
    rng = np.random.default_rng(seed + 1)
    path = [iv0]
    for _ in range(days):
        prev = path[-1]
        shock = rng.normal(0, vol_of_vol)
        nxt = prev + mean_reversion * (iv0 - prev) + shock
        path.append(max(nxt, floor))
    return np.array(path)


def price_leg(spot: float, strike: float, dte_days: int, r: float, iv: float,
              is_call: bool) -> float:
    T = max(dte_days, 0) / TRADING_DAYS_PER_YEAR
    if T <= 0:
        return max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    return bs_price(spot, strike, T, r, iv, is_call)


def leg_greeks(spot: float, strike: float, dte_days: int, r: float, iv: float, is_call: bool):
    T = max(dte_days, 0) / TRADING_DAYS_PER_YEAR
    if T <= 0:
        return None  # at/past expiry, Greeks aren't defined the same way - caller uses intrinsic
    return bs_greeks(spot, strike, T, r, iv, is_call)


def nearest_strike(spot: float, target_delta: float, dte_days: int, r: float,
                    iv: float, is_call: bool, strike_step: float = 1.0) -> float:
    """Pick the strike whose Black-Scholes delta is closest to target_delta,
    scanning a reasonable range around spot at strike_step increments."""
    T = max(dte_days, 1) / TRADING_DAYS_PER_YEAR
    candidates = np.arange(spot * 0.5, spot * 1.5, strike_step)
    best_strike, best_diff = None, float("inf")
    for k in candidates:
        d = bs_greeks(spot, float(k), T, r, iv, is_call).delta
        diff = abs(abs(d) - abs(target_delta))
        if diff < best_diff:
            best_strike, best_diff = float(k), diff
    rounded = round(best_strike / strike_step) * strike_step
    # A long enough GBM path (low drift, many trading days) can wander the
    # underlying down under $1, and rounding to the nearest whole-dollar
    # strike then produces exactly 0.0 - a real, previously-latent bug,
    # only surfaced once price_leg started validating its inputs instead
    # of quietly accepting whatever nearest_strike handed it. A $0 strike
    # isn't a real strike at any price, so floor at one strike_step
    # instead of pretending sub-strike_step granularity exists here.
    return max(rounded, strike_step)
