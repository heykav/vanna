"""Backtest bookkeeping: no lookahead, period boundaries, time units, and
the attribution residual being reported rather than absorbed."""
import numpy as np
import pytest

import vanna.backtest.engine as engine
from vanna.backtest.attribution import attribute_pnl, position_value
from vanna.backtest.chain import TRADING_DAYS_PER_YEAR, leg_greeks, simulate_gbm_path
from vanna.backtest.strategies import Leg

PARAMS = dict(strategy="iron_condor", s0=100.0, iv0=0.22, r=0.03, mu=0.02,
              entry_dte=30, exit_dte=10, n_trades=6, seed=5)


def test_trades_do_not_see_the_future(monkeypatch):
    """Perturb the simulated path after day D: every trade that has already
    closed by D must be bit-for-bit unchanged, and the trade open at D must
    have the same legs and entry value (they were chosen on its entry day)."""
    base = engine.run_backtest(**PARAMS)
    real_path = engine.simulate_gbm_path
    cutoff = base.trades[3].entry_day + 5  # inside the 4th trade

    def perturbed(s0, mu, sigma, days, seed):
        path = real_path(s0, mu, sigma, days, seed).copy()
        path[cutoff + 1:] *= 1.37
        return path

    monkeypatch.setattr(engine, "simulate_gbm_path", perturbed)
    alt = engine.run_backtest(**PARAMS)
    for a, b in zip(base.trades[:3], alt.trades[:3]):
        assert a.exit_day <= cutoff
        assert (a.pnl, a.legs, a.entry_value, a.exit_value) == (b.pnl, b.legs, b.entry_value, b.exit_value)
    open_trade_base, open_trade_alt = base.trades[3], alt.trades[3]
    assert open_trade_base.legs == open_trade_alt.legs
    assert open_trade_base.entry_value == open_trade_alt.entry_value
    assert open_trade_base.pnl != open_trade_alt.pnl  # the perturbation did bite


def test_trade_periods_are_contiguous_and_the_right_length():
    res = engine.run_backtest(**PARAMS)
    held = PARAMS["entry_dte"] - PARAMS["exit_dte"]
    path = simulate_gbm_path(PARAMS["s0"], PARAMS["mu"], PARAMS["iv0"],
                             PARAMS["n_trades"] * PARAMS["entry_dte"] + 5, PARAMS["seed"])
    for prev, t in zip([None] + res.trades[:-1], res.trades):
        assert t.exit_day - t.entry_day == held
        if prev is not None:
            assert t.entry_day == prev.exit_day
        assert t.entry_spot == path[t.entry_day]
        # entry value is marked at the entry-day spot with all DTE remaining
        assert t.entry_value == pytest.approx(
            position_value(t.legs, path[t.entry_day], 0.03, t.entry_iv, 0), abs=1e-12)


def test_hold_to_expiry_settles_at_intrinsic_value():
    params = dict(PARAMS, strategy="long_call", exit_dte=0, n_trades=3)
    res = engine.run_backtest(**params)
    path = simulate_gbm_path(params["s0"], params["mu"], params["iv0"],
                             params["n_trades"] * params["entry_dte"] + 5, params["seed"])
    for t in res.trades:
        (leg,) = t.legs
        assert t.exit_value == pytest.approx(max(path[t.exit_day] - leg.strike, 0.0), abs=1e-12)


def test_theta_pnl_uses_trading_day_year_fraction():
    # One day of pure time decay: theta P&L is theta (per year) * 1/252,
    # the same year fraction the option is priced with.
    legs = [Leg(is_call=True, strike=100.0, quantity=1, dte_days=30)]
    res = attribute_pnl(legs, r=0.03, s0=100.0, iv0=0.25, elapsed0=4,
                        s1=100.0, iv1=0.25, elapsed1=5)
    g = leg_greeks(100.0, 100.0, 26, 0.03, 0.25, True)
    assert res.theta_pnl == pytest.approx(g.theta / TRADING_DAYS_PER_YEAR, rel=1e-15)
    # ... and it explains the actual one-day decay to within ~1%
    assert abs(res.residual) < 0.01 * abs(res.total_pnl)


def test_residual_is_reported_not_absorbed_for_a_large_move():
    # A 15% gap and a 10-vol-point jump: second order cannot explain this,
    # and the leftover must appear in `residual`, not in a named bucket.
    legs = [Leg(is_call=False, strike=95.0, quantity=-1, dte_days=20)]
    r = attribute_pnl(legs, r=0.02, s0=100.0, iv0=0.2, elapsed0=0, s1=85.0, iv1=0.3, elapsed1=1)
    named = r.delta_pnl + r.gamma_pnl + r.theta_pnl + r.vega_pnl + r.vanna_pnl + r.volga_pnl
    assert r.total_pnl == pytest.approx(named + r.residual + r.dividend_pnl, abs=1e-12)
    assert abs(r.residual) > 0.01 * abs(r.total_pnl)


def test_daily_attribution_residual_is_small_relative_to_pnl_over_a_backtest():
    # Summed day-by-day, the residual stays a small share of gross P&L on a
    # realistic path; this is a measured property, not a bookkeeping identity.
    res = engine.run_backtest(**dict(PARAMS, n_trades=10))
    gross = sum(abs(t.pnl) for t in res.trades)
    resid = sum(abs(t.attribution.residual) for t in res.trades)
    assert resid < 0.05 * gross


def test_max_drawdown_is_measured_on_closed_trade_equity():
    from vanna.backtest.metrics import summarize
    res = engine.run_backtest(**PARAMS)
    eq = np.array(res.equity_curve)
    assert summarize(res).max_drawdown == pytest.approx(float(np.max(np.maximum.accumulate(eq) - eq)))
