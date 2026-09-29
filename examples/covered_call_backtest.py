"""Backtest a covered call on a simulated path and attribute P&L to Greeks.

The path is geometric Brownian motion with a mean-reverting IV path, fully
determined by the seed (no market data). Run: python examples/covered_call_backtest.py
"""
from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize

result = run_backtest("covered_call", s0=100.0, iv0=0.22, r=0.03, mu=0.05,
                      entry_dte=30, exit_dte=10, n_trades=12, seed=42)
summary = summarize(result)
print(f"trades {summary.n_trades}  win rate {summary.win_rate:.0%}  "
      f"total P&L {summary.total_pnl:+.2f} (per share)  max drawdown {summary.max_drawdown:.2f}")

names = ("delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl", "vanna_pnl", "volga_pnl", "residual")
totals = {n: sum(getattr(t.attribution, n) for t in result.trades) for n in names}
print("\nGreek attribution summed over all trades:")
for n, v in totals.items():
    print(f"  {n:<10} {v:+9.3f}")
print(f"  {'total':<10} {sum(totals.values()):+9.3f}   (equals total P&L above)")

t = result.trades[-1]
print(f"\nLast trade: legs {[(l.quantity, 'stock' if l.is_stock else l.strike) for l in t.legs]} "
      f"P&L {t.pnl:+.3f}")
