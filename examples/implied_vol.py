"""Recover implied volatility from an option price.

Run: python examples/implied_vol.py
"""
from vanna.pricing.black_scholes import price
from vanna.pricing.implied_vol import ImpliedVolError, implied_vol

S, K, T, r = 100.0, 105.0, 0.5, 0.03
true_sigma = 0.27

market_price = price(S, K, T, r, true_sigma, is_call=True)
iv = implied_vol(market_price, S, K, T, r, is_call=True)
print(f"price {market_price:.4f} -> implied vol {iv:.6f} (input vol was {true_sigma})")

# Low-vega case (deep out of the money, one week): plain Newton on price is
# unreliable here; the solver keeps a bracket and steps on ln(price).
far = price(100.0, 130.0, 7 / 365, 0.03, 0.40, is_call=True)
print(f"deep OTM call price {far:.2e} -> implied vol "
      f"{implied_vol(far, 100.0, 130.0, 7 / 365, 0.03, is_call=True):.6f} (input 0.4)")

# A price below the discounted no-arbitrage floor has no implied vol.
try:
    implied_vol(0.01, 100.0, 50.0, 1.0, 0.05, is_call=True)
except ImpliedVolError as e:
    print(f"rejected as expected: {e}")
