import pytest

from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize


def test_backtest_is_deterministic_given_a_seed():
    r1 = run_backtest("iron_condor", s0=100, iv0=0.20, r=0.03, mu=0.05,
                       entry_dte=30, exit_dte=10, n_trades=5, seed=42)
    r2 = run_backtest("iron_condor", s0=100, iv0=0.20, r=0.03, mu=0.05,
                       entry_dte=30, exit_dte=10, n_trades=5, seed=42)
    assert [t.pnl for t in r1.trades] == [t.pnl for t in r2.trades]


def test_different_seeds_give_different_paths():
    r1 = run_backtest("long_call", s0=100, iv0=0.20, r=0.03, mu=0.05,
                       entry_dte=30, exit_dte=10, n_trades=5, seed=1)
    r2 = run_backtest("long_call", s0=100, iv0=0.20, r=0.03, mu=0.05,
                       entry_dte=30, exit_dte=10, n_trades=5, seed=2)
    assert [t.pnl for t in r1.trades] != [t.pnl for t in r2.trades]


def test_produces_requested_number_of_trades():
    result = run_backtest("short_straddle", s0=100, iv0=0.25, r=0.02, mu=0.0,
                           entry_dte=21, exit_dte=7, n_trades=8, seed=7)
    assert len(result.trades) == 8
    assert len(result.equity_curve) == 9  # starting 0.0 plus one point per trade


def test_equity_curve_matches_cumulative_trade_pnl():
    result = run_backtest("iron_condor", s0=100, iv0=0.22, r=0.03, mu=0.03,
                           entry_dte=45, exit_dte=21, n_trades=6, seed=3)
    running = 0.0
    for i, t in enumerate(result.trades):
        running += t.pnl
        assert result.equity_curve[i + 1] == pytest.approx(running)


def test_trade_attribution_sums_to_trade_pnl():
    # Each trade's day-by-day attribution should still sum (modulo the
    # small per-day residuals) to something close to the trade's actual
    # entry-to-exit P&L - a real end-to-end check that engine.py wires
    # attribution.py together correctly across multiple days.
    result = run_backtest("long_put", s0=100, iv0=0.30, r=0.01, mu=-0.02,
                           entry_dte=30, exit_dte=15, n_trades=4, seed=11)
    for t in result.trades:
        explained = (t.attribution.delta_pnl + t.attribution.gamma_pnl +
                     t.attribution.theta_pnl + t.attribution.vega_pnl +
                     t.attribution.vanna_pnl + t.attribution.volga_pnl +
                     t.attribution.residual)
        assert explained == pytest.approx(t.attribution.total_pnl, abs=1e-6)
        assert t.pnl == pytest.approx(t.attribution.total_pnl, abs=1e-6)


def test_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        run_backtest("not_a_real_strategy", s0=100, iv0=0.2, r=0.03, mu=0.0,
                      entry_dte=30, exit_dte=10, n_trades=1, seed=0)


def test_rejects_exit_dte_not_less_than_entry_dte():
    with pytest.raises(ValueError):
        run_backtest("long_call", s0=100, iv0=0.2, r=0.03, mu=0.0,
                      entry_dte=10, exit_dte=10, n_trades=1, seed=0)


def test_summarize_matches_manual_win_rate_and_profit_factor():
    result = run_backtest("iron_condor", s0=100, iv0=0.20, r=0.02, mu=0.0,
                           entry_dte=30, exit_dte=7, n_trades=20, seed=5)
    summary = summarize(result)
    pnls = [t.pnl for t in result.trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    assert summary.n_trades == len(pnls)
    assert summary.win_rate == pytest.approx(len(wins) / len(pnls))
    assert summary.total_pnl == pytest.approx(sum(pnls))
    if losses:
        expected_pf = sum(wins) / abs(sum(losses))
        assert summary.profit_factor == pytest.approx(expected_pf)


def test_max_drawdown_is_nonnegative_and_correct_on_a_known_curve():
    # Build a backtest, then check drawdown against a hand-computed value
    # from the actual equity curve it produced, rather than trusting the
    # implementation's own arithmetic.
    result = run_backtest("short_call_spread", s0=100, iv0=0.25, r=0.02, mu=0.0,
                           entry_dte=30, exit_dte=10, n_trades=15, seed=9)
    summary = summarize(result)
    equity = result.equity_curve
    peak = equity[0]
    expected_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        expected_dd = max(expected_dd, peak - v)
    assert summary.max_drawdown == pytest.approx(expected_dd)
    assert summary.max_drawdown >= 0
