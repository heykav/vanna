"""Continuous dividend yield (Merton): pricing, parity, and a covered call.

Run: python examples/dividend_yield.py
"""
import math

from vanna.backtest.engine import run_backtest
from vanna.pricing.binomial import price_binomial
from vanna.pricing.black_scholes import price

S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.03, 0.2, 0.04

c0, c = price(S, K, T, r, sigma, True), price(S, K, T, r, sigma, True, q=q)
p = price(S, K, T, r, sigma, False, q=q)
print(f"call without dividends {c0:.4f}, with q={q:.0%}: {c:.4f}")
parity = c - p - (S * math.exp(-q * T) - K * math.exp(-r * T))
print(f"put-call parity residual with q: {parity:.2e}")

# With a dividend yield an American call can be worth more than a European one.
am = price_binomial(S, 90.0, T, r, sigma, True, q=0.08, steps=400, american=True)
eu = price_binomial(S, 90.0, T, r, sigma, True, q=0.08, steps=400, american=False)
print(f"K=90 call, q=8%: American {am:.4f} vs European {eu:.4f}")

# Backtest: the stock leg of a covered call collects the yield.
for yld in (0.0, 0.04):
    res = run_backtest("covered_call", s0=100.0, iv0=0.22, r=0.03, mu=0.05, entry_dte=30,
                       exit_dte=10, n_trades=12, seed=42, q=yld)
    div = sum(t.attribution.dividend_pnl for t in res.trades)
    print(f"covered_call q={yld:.0%}: total P&L {res.total_pnl:+.3f}, dividend income {div:+.3f}")
