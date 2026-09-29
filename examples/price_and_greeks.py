"""Price a European option and print every Greek vanna computes.

Run: python examples/price_and_greeks.py
"""
from vanna.pricing.black_scholes import greeks, price
from vanna.pricing.binomial import greeks_binomial, price_binomial

S, K, T, r, sigma = 100.0, 100.0, 0.25, 0.03, 0.22   # T in years

print(f"European call, S={S} K={K} T={T} r={r} sigma={sigma}")
print(f"  price            {price(S, K, T, r, sigma, is_call=True):.4f}")

g = greeks(S, K, T, r, sigma, is_call=True)
print(f"  delta            {g.delta:+.4f}")
print(f"  gamma            {g.gamma:+.4f}")
print(f"  vega  (per 1.00) {g.vega:+.4f}   -> per vol point: {g.vega / 100:+.4f}")
print(f"  theta (per year) {g.theta:+.4f}   -> per calendar day: {g.theta / 365:+.4f}")
print(f"  rho   (per 1.00) {g.rho:+.4f}")
print(f"  vanna            {g.vanna:+.4f}")
print(f"  volga            {g.volga:+.4f}")

# A deep in-the-money American put is worth more than its European twin.
Sp, Kp = 60.0, 100.0
am = price_binomial(Sp, Kp, 1.0, 0.08, 0.2, is_call=False, steps=400, american=True)
eu = price_binomial(Sp, Kp, 1.0, 0.08, 0.2, is_call=False, steps=400, american=False)
print(f"\nDeep ITM put (S={Sp}, K={Kp}): American {am:.4f} vs European {eu:.4f} "
      f"(early-exercise premium {am - eu:.4f})")

tg = greeks_binomial(100.0, 100.0, 0.5, 0.03, 0.25, is_call=False, steps=200)
print(f"American ATM put tree Greeks: price {tg.price:.4f} delta {tg.delta:+.4f} "
      f"gamma {tg.gamma:+.4f} theta/yr {tg.theta:+.4f}")
