"""Binomial tree pricing for American-style options.

Black-Scholes assumes European exercise (only at expiry). Real equity
options are American-style: the holder can exercise early, which matters
in practice for ITM puts (and for ITM calls on dividend-paying stock,
right before an ex-dividend date). A binomial tree prices that early-
exercise right explicitly, by checking at every node whether exercising
now is worth more than holding.

Two lattices are available through ``method``:

* ``"crr"`` (default) - Cox-Ross-Rubinstein: u = exp(sigma sqrt(dt)),
  d = 1/u. Its error oscillates with the step count (the strike falls at a
  different place relative to the terminal nodes each time), so it
  converges at roughly O(1/n) with a saw-tooth on top.
* ``"lr"`` - Leisen-Reimer (1996), with the Peizer-Pratt "method 2"
  inversion. The up-probabilities are chosen so that the tree reproduces
  N(d1) and N(d2) of the Black-Scholes formula, which centres the tree on
  the strike and gives smooth, roughly O(1/n^2) convergence for European
  options. It is defined for an odd number of steps, so an even ``steps``
  is rounded up by one (as QuantLib does). docs/benchmarks.md has the
  measured error-per-step comparison of the two.

Greeks are read directly off the first two layers of the *same* tree
that produces the price (Hull's method): delta from the two nodes at
step 1, gamma from the three nodes at step 2, theta from the middle
step-2 node against the root. There is no closed form once early exercise
is in the mix. An earlier version bumped spot and time and re-priced the
tree; that was ~7x slower and, because a tree price is a lattice function
of spot, a bump much smaller than the node spacing gave very noisy gamma
and theta (see docs/benchmarks.md). For CRR the middle step-2 node sits
exactly at the spot; for LR it does not (u*d != 1), so theta is corrected
to first and second order in (S*u*d - S) with the step-2 delta and gamma.

The backward induction is vectorised with numpy (one array operation per
time step instead of a Python loop over every node).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from vanna.pricing.black_scholes import validate_option_inputs

METHODS = ("crr", "lr")


@dataclass(frozen=True)
class BinomialGreeks:
    price: float
    delta: float
    gamma: float
    theta: float


def _peizer_pratt_2(z: float, n: int) -> float:
    """Peizer-Pratt method-2 inversion: the binomial probability whose
    n-step binomial CDF approximates the normal CDF at z."""
    x = z / (n + 1.0 / 3.0 + 0.1 / (n + 1.0))
    return 0.5 + math.copysign(0.5, z) * math.sqrt(1.0 - math.exp(-x * x * (n + 1.0 / 6.0)))


def _lattice(S, K, T, r, sigma, q, steps, method):
    """Return (steps, u, d, p) for the requested lattice."""
    if method == "crr":
        dt = T / steps
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        p = (math.exp((r - q) * dt) - d) / (u - d)
        if not (0.0 < p < 1.0):
            raise ValueError(
                f"risk-neutral probability {p:.4f} out of (0,1) - steps too coarse "
                f"for these params (increase `steps`)"
            )
        return steps, u, d, p
    if method == "lr":
        if steps % 2 == 0:
            steps += 1
        dt = T / steps
        vol_sqrt_t = sigma * math.sqrt(T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / vol_sqrt_t
        d2 = d1 - vol_sqrt_t
        p = _peizer_pratt_2(d2, steps)
        p_star = _peizer_pratt_2(d1, steps)
        growth = math.exp((r - q) * dt)
        u = growth * p_star / p
        d = (growth - p * u) / (1.0 - p)
        if not (0.0 < p < 1.0 and d > 0.0):
            raise ValueError(
                f"Leisen-Reimer lattice degenerate for these params (p={p:.4g}, d={d:.4g}); "
                "increase `steps` or use method='crr'"
            )
        return steps, u, d, p
    raise ValueError(f"unknown method {method!r}; choose from {METHODS}")


def _tree(S, K, T, r, sigma, is_call, q, steps, american, method="crr", keep_top=False):
    validate_option_inputs(S, K, T, sigma, r, q)
    if steps < 1:
        raise ValueError("steps must be >= 1")
    steps, u, d, p = _lattice(S, K, T, r, sigma, q, steps, method)
    dt = T / steps
    disc = math.exp(-r * dt)
    pu, pd = disc * p, disc * (1.0 - p)
    sign = 1.0 if is_call else -1.0
    # Node i at layer n (i = number of down moves) has spot S * u**(n-i) * d**i.
    idx = np.arange(steps + 1)
    spots = S * np.exp((steps - idx) * math.log(u) + idx * math.log(d))
    values = np.maximum(sign * (spots - K), 0.0)
    inv_u = 1.0 / u
    top = {}
    for step in range(steps - 1, -1, -1):
        values = pu * values[:-1] + pd * values[1:]
        if american:
            # layer `step` node i = layer `step+1` node i moved one up-step back
            spots = spots[:-1] * inv_u
            np.maximum(values, sign * (spots - K), out=values)
        if keep_top and step <= 2:
            top[step] = values
    return float(values[0]), top, (u, d, dt)


def price_binomial(S: float, K: float, T: float, r: float, sigma: float,
                    is_call: bool, q: float = 0.0, steps: int = 200,
                    american: bool = True, method: str = "crr") -> float:
    return _tree(S, K, T, r, sigma, is_call, q, steps, american, method)[0]


def greeks_binomial(S: float, K: float, T: float, r: float, sigma: float,
                     is_call: bool, q: float = 0.0, steps: int = 200,
                     american: bool = True, method: str = "crr") -> BinomialGreeks:
    """Price, delta, gamma and theta from one tree. Theta is per year of
    calendar time (same convention as `black_scholes.greeks`). Needs
    `steps >= 2` (gamma uses the step-2 layer)."""
    if steps < 2:
        raise ValueError("steps must be >= 2 to compute tree Greeks")
    base, top, (u, d, dt) = _tree(S, K, T, r, sigma, is_call, q, steps, american, method,
                                  keep_top=True)
    f1, f2 = top[1], top[2]  # index = number of down moves
    su, sd = S * u, S * d
    suu, sud, sdd = S * u * u, S * u * d, S * d * d
    delta = (f1[0] - f1[1]) / (su - sd)
    d_up = (f2[0] - f2[1]) / (suu - sud)
    d_dn = (f2[1] - f2[2]) / (sud - sdd)
    gamma = (d_up - d_dn) / (0.5 * (suu - sdd))
    # V(S, t + 2dt) from the middle step-2 node, which sits at S*u*d (== S for
    # CRR, != S for LR): shift it back to S with the step-2 delta and gamma.
    shift = S - sud
    delta2 = (f2[0] - f2[2]) / (suu - sdd)
    v_2dt = f2[1] + delta2 * shift + 0.5 * gamma * shift * shift
    theta = (v_2dt - base) / (2.0 * dt)
    return BinomialGreeks(price=base, delta=float(delta), gamma=float(gamma), theta=float(theta))
