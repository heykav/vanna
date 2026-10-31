"""Backtest an iron condor on REAL daily BTC prices and the real DVOL index.

Data: Deribit public API (no key). By default this reads the committed
snapshot in tests/data so it runs offline and reproducibly; pass --live to
download the latest ~400 days instead.

What is real: the daily closes of the BTC perpetual future and Deribit's
DVOL 30-day implied volatility index. What is NOT real: the option prices.
Each trade is priced by vanna's Black-Scholes model at that day's DVOL (one
flat vol for every strike), not from historical option quotes, so skew,
bid/ask spreads and fees are all ignored. Treat the numbers as a model
exercise on a real path, not as what trading these options would have paid.
Run: python examples/real_price_backtest.py [--live]
"""
import sys
from pathlib import Path

from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize
from vanna.marketdata import fetch_history, load_history_snapshot

if "--live" in sys.argv:
    hist = fetch_history("BTC", days=400)
else:
    hist = load_history_snapshot(Path(__file__).resolve().parent.parent
                                 / "tests" / "data" / "deribit_btc_daily_history.json")

print(f"REAL DATA: {hist.currency}-PERPETUAL daily close + DVOL, {hist.dates[0]} to {hist.dates[-1]} "
      f"({len(hist.dates)} days), source: Deribit public API")
result = run_backtest("iron_condor", s0=hist.closes[0], iv0=hist.iv[0], r=0.0, mu=0.0,
                      entry_dte=30, exit_dte=10, n_trades=1000,
                      spot_path=list(hist.closes), iv_path=list(hist.iv))
summary = summarize(result)
print(f"trades {summary.n_trades}  win rate {summary.win_rate:.0%}  "
      f"total P&L {summary.total_pnl:+,.0f} USD per 1 BTC notional  max drawdown {summary.max_drawdown:,.0f}")

names = ("delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl", "vanna_pnl", "volga_pnl", "residual")
totals = {n: sum(getattr(t.attribution, n) for t in result.trades) for n in names}
print("\nGreek attribution summed over all trades (model-priced, real path):")
for n, v in totals.items():
    print(f"  {n:<10} {v:+12,.1f}")
print(f"  {'total':<10} {sum(totals.values()):+12,.1f}   (equals total P&L above)")
print("\nCaveat: option prices are model prices at the DVOL index, not historical quotes.")
