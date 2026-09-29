import numpy as np
import pytest

from vanna.backtest.attribution import attribute_pnl, position_value
from vanna.backtest.engine import run_backtest
from vanna.backtest.strategies import STRATEGIES
from vanna.backtest.payoff import payoff_curve

SPOT, R, IV, DTE = 100.0, 0.03, 0.22, 30


def test_covered_call_has_stock_leg_and_short_otm_call():
    legs = STRATEGIES["covered_call"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    stock = [l for l in legs if l.is_stock]
    calls = [l for l in legs if not l.is_stock]
    assert len(stock) == 1 and stock[0].quantity == 1
    assert len(calls) == 1 and calls[0].is_call and calls[0].quantity == -1
    assert calls[0].strike > SPOT


def test_stock_leg_priced_at_spot():
    legs = STRATEGIES["covered_call"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    call_only = [l for l in legs if not l.is_stock]
    diff = position_value(legs, 105.0, R, IV, 3) - position_value(call_only, 105.0, R, IV, 3)
    assert diff == pytest.approx(105.0)


def test_covered_call_pnl_differs_from_short_call():
    args = (100, 0.22, 0.03, 0.0, 30, 10, 20)
    cc = run_backtest("covered_call", *args, seed=42)
    sc = run_backtest("short_call", *args, seed=42)
    assert cc.total_pnl != pytest.approx(sc.total_pnl, abs=0.5)


def test_delta_attribution_is_stock_move_plus_call_delta():
    legs = STRATEGIES["covered_call"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    call_only = [l for l in legs if not l.is_stock]
    s1 = 101.0
    full = attribute_pnl(legs, R, SPOT, IV, 0, s1, IV, 1)
    opt = attribute_pnl(call_only, R, SPOT, IV, 0, s1, IV, 1)
    assert full.delta_pnl == pytest.approx((s1 - SPOT) + opt.delta_pnl, abs=1e-9)
    # stock contributes nothing to any other bucket
    for f in ("gamma_pnl", "theta_pnl", "vega_pnl", "vanna_pnl", "volga_pnl"):
        assert getattr(full, f) == pytest.approx(getattr(opt, f), abs=1e-12)
    assert abs(full.residual) < 0.05
    assert full.total_pnl == pytest.approx(opt.total_pnl + (s1 - SPOT), abs=1e-9)


def test_backtest_attribution_residual_small():
    res = run_backtest("covered_call", 100, 0.22, 0.03, 0.0, 30, 10, 20, seed=42)
    for t in res.trades:
        assert abs(t.attribution.residual) < 0.25 * max(1.0, abs(t.pnl))
        assert t.attribution.total_pnl == pytest.approx(t.pnl, abs=1e-6)


def test_payoff_curve_handles_stock_leg():
    legs = STRATEGIES["covered_call"](spot=SPOT, r=R, iv=IV, dte_days=DTE)
    strike = next(l.strike for l in legs if not l.is_stock)
    spots = np.array([80.0, 100.0, strike, strike + 20])
    pay = payoff_curve(legs, R, IV, SPOT, spots)
    call_only = [l for l in legs if not l.is_stock]
    opt = payoff_curve(call_only, R, IV, SPOT, spots)
    assert pay == pytest.approx(opt + (spots - SPOT))
    # capped upside above the short strike
    assert pay[3] == pytest.approx(pay[2])
    stock_only = [l for l in legs if l.is_stock]
    assert payoff_curve(stock_only, R, IV, SPOT, spots) == pytest.approx(spots - SPOT)
