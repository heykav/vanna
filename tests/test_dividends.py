"""Continuous dividend yield (Merton) in pricing, the tree and the backtest."""
import math

import pytest

from vanna.backtest.attribution import attribute_pnl
from vanna.backtest.engine import run_backtest
from vanna.backtest.strategies import Leg
from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial
from vanna.pricing.implied_vol import implied_vol


@pytest.mark.parametrize("q", [0.0, 0.02, 0.06])
@pytest.mark.parametrize("K", [80.0, 100.0, 125.0])
def test_put_call_parity_with_dividend_yield(q, K):
    S, T, r, sigma = 100.0, 0.75, 0.04, 0.3
    c = bs.price(S, K, T, r, sigma, True, q)
    p = bs.price(S, K, T, r, sigma, False, q)
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=1e-10)


def test_european_tree_put_call_parity_with_dividend_yield():
    S, K, T, r, sigma, q, n = 100.0, 105.0, 1.0, 0.04, 0.25, 0.03, 600
    c = price_binomial(S, K, T, r, sigma, True, q, n, american=False)
    p = price_binomial(S, K, T, r, sigma, False, q, n, american=False)
    assert c - p == pytest.approx(S * math.exp(-q * T) - K * math.exp(-r * T), abs=2e-3)


@pytest.mark.parametrize("is_call", [True, False])
def test_european_tree_converges_to_black_scholes_merton(is_call):
    S, K, T, r, sigma, q = 100.0, 95.0, 0.5, 0.03, 0.25, 0.04
    tree = price_binomial(S, K, T, r, sigma, is_call, q, 800, american=False)
    assert tree == pytest.approx(bs.price(S, K, T, r, sigma, is_call, q), abs=5e-3)


def test_dividends_create_early_exercise_value_for_calls():
    S, K, T, r, sigma = 100.0, 90.0, 1.0, 0.03, 0.25
    am0 = price_binomial(S, K, T, r, sigma, True, 0.0, 400, True)
    eu0 = price_binomial(S, K, T, r, sigma, True, 0.0, 400, False)
    assert am0 == pytest.approx(eu0, abs=1e-9)  # no dividends: never exercise early
    am = price_binomial(S, K, T, r, sigma, True, 0.08, 400, True)
    eu = price_binomial(S, K, T, r, sigma, True, 0.08, 400, False)
    assert am > eu + 1e-3


def test_dividend_yield_lowers_calls_raises_puts_and_scales_delta():
    S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.03, 0.2, 0.05
    assert bs.price(S, K, T, r, sigma, True, q) < bs.price(S, K, T, r, sigma, True)
    assert bs.price(S, K, T, r, sigma, False, q) > bs.price(S, K, T, r, sigma, False)
    d0 = bs.greeks(S, K, T, r, sigma, True).delta
    dq = bs.greeks(S, K, T, r, sigma, True, q).delta
    assert dq < d0


def test_implied_vol_round_trip_with_dividends():
    S, K, T, r, sigma, q = 100.0, 110.0, 0.5, 0.03, 0.27, 0.04
    px = bs.price(S, K, T, r, sigma, True, q)
    assert implied_vol(px, S, K, T, r, True, q) == pytest.approx(sigma, abs=1e-8)


def test_tree_greeks_with_dividends_match_closed_form_in_european_limit():
    S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.03, 0.2, 0.04
    ref = bs.greeks(S, K, T, r, sigma, False, q)
    g = greeks_binomial(S, K, T, r, sigma, False, q, steps=800, american=False)
    assert g.delta == pytest.approx(ref.delta, abs=2e-3)


# ---- backtest -------------------------------------------------------------
KW = dict(s0=100.0, iv0=0.22, r=0.03, mu=0.05, entry_dte=30, exit_dte=10, n_trades=6, seed=7)


@pytest.mark.parametrize("strategy", ["iron_condor", "covered_call", "short_put", "long_straddle"])
def test_q_zero_reproduces_default_backtest_exactly(strategy):
    a = run_backtest(strategy, **KW)
    b = run_backtest(strategy, q=0.0, **KW)
    assert a.equity_curve == b.equity_curve
    assert [t.attribution for t in a.trades] == [t.attribution for t in b.trades]
    assert all(t.attribution.dividend_pnl == 0.0 for t in a.trades)


def test_dividend_yield_changes_option_backtest_and_stays_consistent():
    a = run_backtest("short_put", **KW)
    b = run_backtest("short_put", q=0.05, **KW)
    assert a.equity_curve != b.equity_curve
    for t in b.trades:
        assert t.attribution.total_pnl == pytest.approx(t.pnl, abs=1e-9)
        assert t.attribution.dividend_pnl == 0.0  # no stock leg


def test_covered_call_collects_dividends_on_the_stock_leg():
    q = 0.04
    a = run_backtest("covered_call", **KW)
    b = run_backtest("covered_call", q=q, **KW)
    for t in b.trades:
        att = t.attribution
        held_years = (t.exit_day - t.entry_day) / 252
        assert att.dividend_pnl > 0
        # ~ q * S * held time, with S within a few percent of entry spot
        assert att.dividend_pnl == pytest.approx(q * t.entry_spot * held_years, rel=0.15)
        assert att.total_pnl == pytest.approx(t.pnl, abs=1e-9)
        parts = (att.delta_pnl + att.gamma_pnl + att.theta_pnl + att.vega_pnl
                 + att.vanna_pnl + att.volga_pnl + att.dividend_pnl + att.residual)
        assert parts == pytest.approx(att.total_pnl, abs=1e-9)
    assert a.trades[0].attribution.dividend_pnl == 0.0


def test_attribute_pnl_pure_spot_move_with_yield_keeps_residual_small():
    legs = [Leg(True, 100.0, -1, 30)]
    r = attribute_pnl(legs, 0.03, 100.0, 0.25, 0, 100.5, 0.25, 0, q=0.05)
    assert abs(r.residual) < 1e-3


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_rejects_non_finite_yield(bad):
    with pytest.raises(ValueError, match="dividend"):
        run_backtest("iron_condor", q=bad, **KW)
