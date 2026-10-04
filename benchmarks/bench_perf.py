"""Before/after timing of the hot paths, using only APIs that exist both in
this version and in the parent commit (5a46a34), so the same script can be
run against either checkout:

    python benchmarks/bench_perf.py                        # this checkout
    git archive 5a46a34 vanna | tar -x -C /tmp/old && \
        PYTHONPATH=/tmp/old python benchmarks/bench_perf.py   # parent

Prints `name|median microseconds per call`. Timings depend on the machine
and its load; compare runs made back to back on the same machine only.
"""
from __future__ import annotations

import itertools
import statistics
import time

from vanna.backtest.engine import run_backtest
from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial
from vanna.pricing.implied_vol import implied_vol


def timeit(fn, reps, batches=15):
    samples = []
    for _ in range(batches):
        t = time.perf_counter()
        for _ in range(reps):
            fn()
        samples.append((time.perf_counter() - t) / reps)
    return statistics.median(samples) * 1e6


IV_GRID = list(itertools.product(
    [25.0, 50.0, 70.0, 90.0, 100.0, 110.0, 130.0, 200.0, 400.0],
    [1 / 365, 7 / 365, 30 / 365, 0.25, 1.0, 5.0], [0.01, 0.05, 0.2, 0.5, 1.0, 2.0, 4.0],
    [-0.02, 0.0, 0.05], [0.0, 0.04], [True, False]))


def iv_grid_cases():
    cases = []
    for K, T, s, r, q, c in IV_GRID:
        px = bs.price(100.0, K, T, r, s, c, q)
        fwd_s, fwd_k = 100.0 * 2.718281828459045 ** (-q * T), K * 2.718281828459045 ** (-r * T)
        floor = max(fwd_s - fwd_k, 0.0) if c else max(fwd_k - fwd_s, 0.0)
        if px - floor >= 1e-12 * 100.0:  # same well-posedness filter as bench_trees.py
            cases.append((px, 100.0, K, T, r, c, q))
    return cases


def iv_grid_mean(cases):
    def run():
        for args in cases:
            try:
                implied_vol(*args)
            except ValueError:
                pass
    return timeit(run, 1, batches=5) / len(cases)


def main():
    S, K, T, r, s, q = 100.0, 100.0, 0.5, 0.03, 0.25, 0.0
    atm = bs.price(S, K, T, r, s, True, q)
    otm = bs.price(S, 130.0, 7 / 365, r, 0.4, True, q)
    rows = [
        ("BS price", lambda: bs.price(S, K, T, r, s, True, q), 2000),
        ("BS greeks", lambda: bs.greeks(S, K, T, r, s, True, q), 2000),
        ("implied_vol ATM", lambda: implied_vol(atm, S, K, T, r, True, q), 500),
        ("implied_vol 1w 30% OTM", lambda: implied_vol(otm, S, 130.0, 7 / 365, r, True, q), 300),
        ("American put CRR 200", lambda: price_binomial(S, K, T, r, s, False, q, 200, True), 30),
        ("greeks_binomial CRR 200", lambda: greeks_binomial(S, K, T, r, s, False, q, 200, True), 30),
        ("run_backtest iron_condor 50 trades",
         lambda: run_backtest("iron_condor", 100.0, 0.22, 0.03, 0.0, 30, 10, 50, seed=1), 1),
    ]
    for name, fn, reps in rows:
        print(f"{name}|{timeit(fn, reps):.1f}")
    cases = iv_grid_cases()
    print(f"implied_vol mean over {len(cases)}-point grid|{iv_grid_mean(cases):.1f}")


if __name__ == "__main__":
    main()
