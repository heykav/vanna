"""Cox-Ross-Rubinstein binomial tree pricing for American-style options.

Black-Scholes assumes European exercise (only at expiry). Real equity
options are American-style: the holder can exercise early, which matters
in practice for ITM puts (and for ITM calls on dividend-paying stock,
right before an ex-dividend date). A binomial tree prices that early-
exercise right explicitly, by checking at every node whether exercising
now is worth more than holding.

Greeks are read directly off the first two layers of the *same* tree
that produces the price (Hull's method): delta from the two nodes at
step 1, gamma from the three nodes at step 2, theta from the middle
step-2 node (which sits at the spot again) against the root. There is no
closed form once early exercise is in the mix. An earlier version bumped
spot and time and re-priced the tree; that was ~7x slower and, because a
tree price is a lattice function of spot, a bump much smaller than the
node spacing gave very noisy gamma and theta (see docs/benchmarks.md).

The backward induction is vectorised with numpy (one array operation per
time step instead of a Python loop over every node); the algorithm and
results are unchanged.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vanna.pricing.black_scholes import validate_option_inputs


@dataclass(frozen=True)
class BinomialGreeks:
    price: float
    delta: float
    gamma: float
    theta: float


def _tree(S, K, T, r, sigma, is_call, q, steps, american, keep_top=False):
    validate_option_inputs(S, K, T, sigma, r, q)
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
    sign = 1.0 if is_call else -1.0
    # Node i at layer n (i = number of down moves) has spot S * u**(n - 2i).
    idx = np.arange(steps + 1)
    values = np.maximum(sign * (S * u ** (steps - 2 * idx) - K), 0.0)
    top = {}
    for step in range(steps - 1, -1, -1):
        cont = disc * (p * values[:-1] + (1.0 - p) * values[1:])
        if american:
            spots = S * u ** (step - 2 * idx[: step + 1])
            cont = np.maximum(cont, np.maximum(sign * (spots - K), 0.0))
        values = cont
        if keep_top and step <= 2:
            top[step] = values
    return float(values[0]), top, (u, d, dt)


def price_binomial(S: float, K: float, T: float, r: float, sigma: float,
                    is_call: bool, q: float = 0.0, steps: int = 200,
                    american: bool = True) -> float:
    return _tree(S, K, T, r, sigma, is_call, q, steps, american)[0]


def greeks_binomial(S: float, K: float, T: float, r: float, sigma: float,
                     is_call: bool, q: float = 0.0, steps: int = 200,
                     american: bool = True) -> BinomialGreeks:
    """Price, delta, gamma and theta from one tree. Theta is per year of
    calendar time (same convention as `black_scholes.greeks`). Needs
    `steps >= 2` (gamma uses the step-2 layer)."""
    if steps < 2:
        raise ValueError("steps must be >= 2 to compute tree Greeks")
    base, top, (u, d, dt) = _tree(S, K, T, r, sigma, is_call, q, steps, american, keep_top=True)
    f1, f2 = top[1], top[2]  # index = number of down moves
    su, sd = S * u, S * d
    suu, sdd = S * u * u, S * d * d
    delta = (f1[0] - f1[1]) / (su - sd)
    gamma = (((f2[0] - f2[1]) / (suu - S) - (f2[1] - f2[2]) / (S - sdd))
             / (0.5 * (suu - sdd)))
    theta = (f2[1] - base) / (2.0 * dt)
    return BinomialGreeks(price=base, delta=float(delta), gamma=float(gamma), theta=float(theta))
