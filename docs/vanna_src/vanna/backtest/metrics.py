"""Standard backtest performance metrics - the necessary baseline, not the
differentiator. Any competent backtesting library reports these; vanna's
actual pitch is the attribution layer in attribution.py and engine.py."""
from __future__ import annotations

from dataclasses import dataclass

from vanna.backtest.engine import BacktestResult


@dataclass(frozen=True)
class PerformanceSummary:
    n_trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    max_drawdown: float
    avg_pnl: float


def summarize(result: BacktestResult) -> PerformanceSummary:
    trades = result.trades
    n = len(trades)
    if n == 0:
        return PerformanceSummary(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    win_rate = len(wins) / n
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    equity = result.equity_curve
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        max_dd = max(max_dd, peak - v)

    total_pnl = result.total_pnl
    return PerformanceSummary(
        n_trades=n, win_rate=win_rate, profit_factor=profit_factor,
        total_pnl=total_pnl, max_drawdown=max_dd, avg_pnl=total_pnl / n,
    )
