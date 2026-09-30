"""Binomial-tree convergence (CRR vs Leisen-Reimer), implied-vol solver
statistics and per-call timings. Needs only numpy (no QuantLib).

    python benchmarks/bench_trees.py                 # markdown tables
    python benchmarks/bench_trees.py --quick         # smaller grids
    python benchmarks/bench_trees.py --json out.json

Accuracy numbers are deterministic. Timings are medians of repeated
batches on whatever machine runs this; treat them as indicative only.
The references are:
  * European: the closed-form Black-Scholes-Merton price/Greeks.
  * American: a 4,001-step Leisen-Reimer tree. Its own error is estimated
    by comparing it with an 8,001-step LR tree (printed as the reference
    self-convergence gap); errors of that size are not resolved.
"""
from __future__ import annotations

import argparse
import itertools
import json
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vanna.backtest.engine import run_backtest  # noqa: E402
from vanna.pricing import black_scholes as bs  # noqa: E402
from vanna.pricing import implied_vol as iv_mod  # noqa: E402
from vanna.pricing.binomial import greeks_binomial, price_binomial  # noqa: E402

S = 100.0
EURO_GRID = list(itertools.product(
    [80.0, 90.0, 100.0, 110.0, 120.0], [0.1, 0.5, 1.0, 2.0], [0.15, 0.3, 0.6],
    [0.0, 0.05], [0.0, 0.03], [True, False]))
AM_GRID = list(itertools.product(
    [90.0, 100.0, 110.0], [0.25, 1.0], [0.2, 0.4], [0.02, 0.06],
    [(False, 0.0), (True, 0.04), (False, 0.04)]))  # (is_call, q)
STEPS = [25, 51, 101, 201, 401, 801]
IV_GRID = list(itertools.product(
    [25.0, 50.0, 70.0, 90.0, 100.0, 110.0, 130.0, 200.0, 400.0],
    [1 / 365, 7 / 365, 30 / 365, 0.25, 1.0, 5.0], [0.01, 0.05, 0.2, 0.5, 1.0, 2.0, 4.0],
    [-0.02, 0.0, 0.05], [0.0, 0.04], [True, False]))


def _stats(errs):
    return {"max": max(errs), "mean": statistics.fmean(errs), "n": len(errs)}


def european_convergence(grid, steps):
    out = {}
    for method in ("crr", "lr"):
        for n in steps:
            errs = [abs(price_binomial(S, K, T, r, s, c, q, n, False, method)
                        - bs.price(S, K, T, r, s, c, q)) for K, T, s, r, q, c in grid]
            out[(method, n)] = _stats(errs)
    return out


def european_greeks(grid, n):
    out = {}
    for method in ("crr", "lr"):
        e = {"delta": [], "gamma": [], "theta": []}
        for K, T, s, r, q, c in grid:
            ref = bs.greeks(S, K, T, r, s, c, q)
            g = greeks_binomial(S, K, T, r, s, c, q, n, False, method)
            e["delta"].append(abs(g.delta - ref.delta))
            e["gamma"].append(abs(g.gamma - ref.gamma) / ref.gamma)
            e["theta"].append(abs(g.theta - ref.theta) / abs(ref.theta))
        out[method] = {k: _stats(v) for k, v in e.items()}
    return out


def american_convergence(grid, steps, ref_steps=(4001, 8001)):
    refs, ref_gap = [], []
    for K, T, s, r, (c, q) in grid:
        lr_ref = price_binomial(S, K, T, r, s, c, q, ref_steps[0], True, "lr")
        finer = price_binomial(S, K, T, r, s, c, q, ref_steps[1], True, "lr")
        refs.append(lr_ref)
        ref_gap.append(abs(lr_ref - finer))
    out = {"reference_gap": _stats(ref_gap)}
    for method in ("crr", "lr"):
        for n in steps:
            errs = [abs(price_binomial(S, K, T, r, s, c, q, n, True, method) - ref)
                    for (K, T, s, r, (c, q)), ref in zip(grid, refs)]
            out[(method, n)] = _stats(errs)
    return out


def implied_vol_stats(grid):
    calls = [0]
    real = iv_mod.greeks

    def counting(*a):
        calls[0] += 1
        return real(*a)

    iv_mod.greeks = counting
    errs, excess, skipped, failures = [], 0, 0, 0
    solve_time = 0.0
    try:
        for K, T, s, r, q, c in grid:
            px = bs.price(S, K, T, r, s, c, q)
            lo, _ = iv_mod.no_arbitrage_bounds(S, K, T, r, c, q)
            if px - lo < 1e-12 * S:
                skipped += 1
                continue
            t0 = time.perf_counter()
            try:
                vol = iv_mod.implied_vol(px, S, K, T, r, c, q)
            except iv_mod.ImpliedVolError:
                failures += 1
                continue
            finally:
                solve_time += time.perf_counter() - t0
            err = abs(vol - s)
            attainable = 4e-16 * px / real(S, K, T, r, s, c, q).vega
            errs.append(err)
            excess += err > max(1e-9, 10 * attainable)
    finally:
        iv_mod.greeks = real
    return {"solved": len(errs), "skipped": skipped, "failures": failures,
            "max_abs_err": max(errs), "mean_abs_err": statistics.fmean(errs),
            "worse_than_10x_conditioning": excess,
            "mean_newton_evals": calls[0] / len(errs),
            "mean_us_per_solve (single pass, includes counting overhead)": 1e6 * solve_time / len(errs)}


def timeit(fn, min_time=0.3):
    n, t0 = 0, time.perf_counter()
    while time.perf_counter() - t0 < 0.05:
        fn()
        n += 1
    samples = []
    t_end = time.perf_counter() + min_time
    while time.perf_counter() < t_end or len(samples) < 5:
        t = time.perf_counter()
        for _ in range(n):
            fn()
        samples.append((time.perf_counter() - t) / n)
    return statistics.median(samples)


def timings():
    K, T, r, s, q = 100.0, 0.5, 0.03, 0.25, 0.0
    atm = bs.price(S, K, T, r, s, True, q)
    return {
        "BS price": timeit(lambda: bs.price(S, K, T, r, s, True, q)),
        "BS greeks()": timeit(lambda: bs.greeks(S, K, T, r, s, True, q)),
        "implied_vol, ATM": timeit(lambda: iv_mod.implied_vol(atm, S, K, T, r, True, q)),
        "American put, CRR 201 steps": timeit(lambda: price_binomial(S, K, T, r, s, False, q, 201, True, "crr")),
        "American put, LR 201 steps": timeit(lambda: price_binomial(S, K, T, r, s, False, q, 201, True, "lr")),
        "greeks_binomial, CRR 201 steps": timeit(lambda: greeks_binomial(S, K, T, r, s, False, q, 201, True, "crr")),
        "run_backtest iron_condor, 50 trades": timeit(
            lambda: run_backtest("iron_condor", 100.0, 0.22, 0.03, 0.0, 30, 10, 50, seed=1), 1.0),
    }


def fmt(x):
    return f"{x:.2e}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--json")
    args = ap.parse_args(argv)
    euro_grid = EURO_GRID[::7] if args.quick else EURO_GRID
    am_grid = AM_GRID[::6] if args.quick else AM_GRID
    iv_grid = IV_GRID[::11] if args.quick else IV_GRID

    print("### Environment\n")
    print(f"- python {platform.python_version()}, {platform.platform()}, "
          f"processor: {platform.processor() or 'n/a'}")
    import numpy
    print(f"- numpy {numpy.__version__}\n")

    eu = european_convergence(euro_grid, STEPS)
    print(f"### European price error vs closed form ({len(euro_grid)} points)\n")
    print("| steps | CRR max | CRR mean | LR max | LR mean |\n|---:|---:|---:|---:|---:|")
    for n in STEPS:
        c, lr = eu[("crr", n)], eu[("lr", n)]
        print(f"| {n} | {fmt(c['max'])} | {fmt(c['mean'])} | {fmt(lr['max'])} | {fmt(lr['mean'])} |")

    gk = european_greeks(euro_grid, 201)
    print(f"\n### European tree Greeks vs closed form, 201 steps ({len(euro_grid)} points)\n")
    print("| Greek | error | CRR max | CRR mean | LR max | LR mean |\n|---|---|---:|---:|---:|---:|")
    for name, kind in (("delta", "abs"), ("gamma", "rel"), ("theta", "rel")):
        c, lr = gk["crr"][name], gk["lr"][name]
        print(f"| {name} | {kind} | {fmt(c['max'])} | {fmt(c['mean'])} | {fmt(lr['max'])} | {fmt(lr['mean'])} |")

    am = american_convergence(am_grid, STEPS)
    gap = am["reference_gap"]
    print(f"\n### American price error vs 4,001-step LR reference ({len(am_grid)} points)\n")
    print(f"Reference self-convergence gap (|LR 4001 - LR 8001|): max {fmt(gap['max'])}, mean {fmt(gap['mean'])}.\n")
    print("| steps | CRR max | CRR mean | LR max | LR mean |\n|---:|---:|---:|---:|---:|")
    for n in STEPS:
        c, lr = am[("crr", n)], am[("lr", n)]
        print(f"| {n} | {fmt(c['max'])} | {fmt(c['mean'])} | {fmt(lr['max'])} | {fmt(lr['mean'])} |")

    ivs = implied_vol_stats(iv_grid)
    print(f"\n### Implied vol round trip ({len(iv_grid)} grid points)\n")
    for k, v in ivs.items():
        print(f"- {k}: {fmt(v) if isinstance(v, float) else v}")

    tm = timings()
    print("\n### Timing (median per call, this machine)\n")
    print("| operation | time |\n|---|---:|")
    for k, v in tm.items():
        print(f"| {k} | {v * 1e6:,.1f} us |")

    if args.json:
        blob = {"european": {f"{m}_{n}": v for (m, n), v in eu.items()},
                "european_greeks_201": gk,
                "american": {(k if isinstance(k, str) else f"{k[0]}_{k[1]}"): v for k, v in am.items()},
                "implied_vol": ivs, "timings_s": tm}
        Path(args.json).write_text(json.dumps(blob, indent=2))


if __name__ == "__main__":
    main()
