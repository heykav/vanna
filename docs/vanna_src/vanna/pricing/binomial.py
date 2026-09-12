"""Cox-Ross-Rubinstein binomial tree pricing for American-style options.

Black-Scholes assumes European exercise (only at expiry). Real equity
options are American-style: the holder can exercise early, which matters
in practice for ITM puts (and for ITM calls on dividend-paying stock,
right before an ex-dividend date). A binomial tree prices that early-
exercise right explicitly, by checking at every node whether exercising
now is worth more than holding.

Greeks here come from bumping the tree (finite difference on price), not
from a closed form - there isn't a clean closed form once early exercise
is in the mix. That's a real, disclosed trade-off, not an oversight: it
costs a few extra tree evaluations per Greek, which is fine at this scale
(a few thousand nodes), and would only start to matter if this were
re-pricing a whole chain per millisecond.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class BinomialGreeks:
    price: float
    delta: float
    gamma: float
    theta: float


def price_binomial(S: float, K: float, T: float, r: float, sigma: float,
                    is_call: bool, q: float = 0.0, steps: int = 200,
                    american: bool = True) -> float:
    if steps < 1:
        raise ValueError("steps must be >= 1")
    dt = T / steps
    u = math.exp(sigma * math.sqrt(dt))
    d = 1.0 / u
    disc = math.exp(-r * dt)
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not (0.0 < p < 1.0):
        raise ValueError(
            f"risk-neutral probability {p:.4f} out of (0,1) - steps too coarse "
            f"for these params (increase `steps`)"
        )

    # Terminal payoffs across the final layer of the tree.
    values = []
    for i in range(steps + 1):
        s_t = S * (u ** (steps - i)) * (d ** i)
        payoff = max(s_t - K, 0.0) if is_call else max(K - s_t, 0.0)
        values.append(payoff)

    # Walk back through the tree; at each node, compare the discounted
    # continuation value against immediate exercise (American only).
    for step in range(steps - 1, -1, -1):
        next_values = []
        for i in range(step + 1):
            continuation = disc * (p * values[i] + (1 - p) * values[i + 1])
            if american:
                s_t = S * (u ** (step - i)) * (d ** i)
                intrinsic = max(s_t - K, 0.0) if is_call else max(K - s_t, 0.0)
                next_values.append(max(continuation, intrinsic))
            else:
                next_values.append(continuation)
        values = next_values

    return values[0]


def greeks_binomial(S: float, K: float, T: float, r: float, sigma: float,
                     is_call: bool, q: float = 0.0, steps: int = 200,
                     american: bool = True) -> BinomialGreeks:
    def px(spot, tenor):
        return price_binomial(spot, K, tenor, r, sigma, is_call, q, steps, american)

    base = px(S, T)
    h_s = 1e-3 * S
    delta = (px(S + h_s, T) - px(S - h_s, T)) / (2 * h_s)
    gamma = (px(S + h_s, T) - 2 * base + px(S - h_s, T)) / (h_s ** 2)

    h_t = min(1e-4, T * 0.01) if T > 1e-3 else T * 0.1
    theta = -(px(S, T + h_t) - px(S, T - h_t)) / (2 * h_t)

    return BinomialGreeks(price=base, delta=delta, gamma=gamma, theta=theta)
