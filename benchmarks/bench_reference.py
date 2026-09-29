"""Accuracy and speed benchmark of vanna against reference implementations.

Compares vanna's Black-Scholes(-Merton) price, Greeks, implied vol and the
binomial American price against QuantLib and py_vollib over a fixed grid.
Everything is computed locally; nothing here is hard-coded.

Run (from the repo root, in a venv with the optional deps):

    pip install -e . QuantLib py_vollib scipy
    python benchmarks/bench_reference.py            # prints markdown tables
    python benchmarks/bench_reference.py --json out.json

Conventions used to line the libraries up (see docs/benchmarks.md):
  * T = calendar days / 365 (QuantLib Actual365Fixed, no holidays).
  * vega per 1.00 of sigma; theta per year, d(V)/d(t) (calendar time);
    rho per 1.00 of r.  py_vollib output is rescaled to these units.
"""
from __future__ import annotations

import argparse
import itertools
import json
import platform
import statistics
import sys
import time
from importlib import metadata

import QuantLib as ql
from py_vollib.black_scholes_merton import black_scholes_merton as pv_price
from py_vollib.black_scholes_merton.greeks import analytical as pv_greeks
from py_vollib.black_scholes_merton.implied_volatility import implied_volatility as pv_iv

from vanna.pricing import black_scholes as bs
from vanna.pricing.binomial import greeks_binomial, price_binomial
from vanna.pricing.implied_vol import ImpliedVolError, implied_vol

# ----------------------------------------------------------------- the grid
SPOT = 100.0
STRIKES = [70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0]
VOLS = [0.10, 0.20, 0.40, 0.80]
RATES = [0.0, 0.02, 0.05]
DAYS = [7, 30, 90, 180, 365, 730]
DIVS = [0.0, 0.03]
EURO_GRID = list(itertools.product(STRIKES, VOLS, RATES, DAYS, DIVS, (True, False)))

AM_STRIKES = [90.0, 100.0, 110.0]
AM_VOLS = [0.20, 0.40]
AM_RATES = [0.02, 0.05]
AM_DAYS = [30, 180, 365]
AM_GRID = list(itertools.product(AM_STRIKES, AM_VOLS, AM_RATES, AM_DAYS, DIVS, (True, False)))
AM_STEPS = 200
AM_REF_STEPS = 2000

REL_FLOOR = 1e-4  # relative errors only where |reference| > this (see docs)

_TODAY = ql.Date(15, 1, 2024)
ql.Settings.instance().evaluationDate = _TODAY
_DC = ql.Actual365Fixed()
_CAL = ql.NullCalendar()


# ------------------------------------------------------------ QuantLib glue
class QLEuro:
    """European option with mutable quotes so the instrument is built once."""

    def __init__(self, K, days, is_call):
        self.s, self.r, self.q, self.v = (ql.SimpleQuote(1.0) for _ in range(4))
        rts = ql.YieldTermStructureHandle(ql.FlatForward(_TODAY, ql.QuoteHandle(self.r), _DC))
        qts = ql.YieldTermStructureHandle(ql.FlatForward(_TODAY, ql.QuoteHandle(self.q), _DC))
        vts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(_TODAY, _CAL, ql.QuoteHandle(self.v), _DC))
        self.process = ql.BlackScholesMertonProcess(ql.QuoteHandle(self.s), qts, rts, vts)
        payoff = ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, K)
        ex = ql.EuropeanExercise(_TODAY + days)
        self.opt = ql.EuropeanOption(payoff, ex)
        self.opt.setPricingEngine(ql.AnalyticEuropeanEngine(self.process))

    def set(self, S, r, q, sigma):
        self.s.setValue(S); self.r.setValue(r); self.q.setValue(q); self.v.setValue(sigma)
        return self

    def greeks(self):
        o = self.opt
        return dict(price=o.NPV(), delta=o.delta(), gamma=o.gamma(), vega=o.vega(),
                    theta=o.theta(), rho=o.rho())


def ql_american(S, K, days, r, q, sigma, is_call, steps):
    s, rq, qq, vq = (ql.SimpleQuote(x) for x in (S, r, q, sigma))
    rts = ql.YieldTermStructureHandle(ql.FlatForward(_TODAY, ql.QuoteHandle(rq), _DC))
    qts = ql.YieldTermStructureHandle(ql.FlatForward(_TODAY, ql.QuoteHandle(qq), _DC))
    vts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(_TODAY, _CAL, ql.QuoteHandle(vq), _DC))
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(s), qts, rts, vts)
    opt = ql.VanillaOption(
        ql.PlainVanillaPayoff(ql.Option.Call if is_call else ql.Option.Put, K),
        ql.AmericanExercise(_TODAY, _TODAY + days))
    opt.setPricingEngine(ql.BinomialVanillaEngine(proc, "crr", steps))
    return dict(price=opt.NPV(), delta=opt.delta(), gamma=opt.gamma(), theta=opt.theta())


def ql_iv(opt_helper: QLEuro, target, S, r, q, guess):
    opt_helper.set(S, r, q, guess)
    return opt_helper.opt.impliedVolatility(target, opt_helper.process, 1e-12, 200, 1e-4, 5.0)


# ---------------------------------------------------------------- stats
class Err:
    def __init__(self):
        self.abs, self.rel, self.worst = [], [], None

    def add(self, mine, ref, ctx):
        a = abs(mine - ref)
        self.abs.append(a)
        if abs(ref) > REL_FLOOR:
            self.rel.append(a / abs(ref))
        if self.worst is None or a > self.worst[0]:
            self.worst = (a, mine, ref, ctx)

    def row(self):
        return dict(n=len(self.abs), max_abs=max(self.abs), mean_abs=statistics.fmean(self.abs),
                    max_rel=max(self.rel) if self.rel else None,
                    mean_rel=statistics.fmean(self.rel) if self.rel else None,
                    n_rel=len(self.rel), worst=self.worst)


def timeit(fn, min_time=0.3):
    """Median per-call seconds over repeated batches (each batch >= ~10 ms)."""
    fn()
    n = 1
    while True:
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        dt = time.perf_counter() - t0
        if dt > 0.01:
            break
        n *= 4
    times, end = [], time.perf_counter() + min_time
    while time.perf_counter() < end or len(times) < 5:
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        times.append((time.perf_counter() - t0) / n)
    return statistics.median(times)


# ----------------------------------------------------------- accuracy runs
def european_accuracy():
    res = {}
    def e(name):
        return res.setdefault(name, Err())

    iv_fail = {"vanna": 0, "py_vollib": 0}
    iv_skipped = 0
    for K, sig, r, days, q, is_call in EURO_GRID:
        T = days / 365.0
        flag = "c" if is_call else "p"
        ctx = f"K={K} vol={sig} r={r} d={days} q={q} {'C' if is_call else 'P'}"
        qle = QLEuro(K, days, is_call).set(SPOT, r, q, sig)
        ref = qle.greeks()
        g = bs.greeks(SPOT, K, T, r, sig, is_call, q)
        px = bs.price(SPOT, K, T, r, sig, is_call, q)
        for k in ("price", "delta", "gamma", "vega", "theta", "rho"):
            mine = px if k == "price" else getattr(g, k)
            e(f"vanna vs QuantLib: {k}").add(mine, ref[k], ctx)
        # py_vollib (theta per day, vega/rho per 1%) rescaled to vanna units
        pv = dict(price=pv_price(flag, SPOT, K, T, r, sig, q),
                  delta=pv_greeks.delta(flag, SPOT, K, T, r, sig, q),
                  gamma=pv_greeks.gamma(flag, SPOT, K, T, r, sig, q),
                  vega=pv_greeks.vega(flag, SPOT, K, T, r, sig, q) * 100.0,
                  theta=pv_greeks.theta(flag, SPOT, K, T, r, sig, q) * 365.0,
                  rho=pv_greeks.rho(flag, SPOT, K, T, r, sig, q) * 100.0)
        for k in ("price", "delta", "gamma", "vega", "theta", "rho"):
            mine = px if k == "price" else getattr(g, k)
            e(f"vanna vs py_vollib: {k}").add(mine, pv[k], ctx)
            e(f"py_vollib vs QuantLib: {k}").add(pv[k], ref[k], ctx)

        # Implied vol round trip: feed the QuantLib price, recover sigma.
        target = ref["price"]
        floor = max(SPOT * pow(2.718281828459045, -q * T) - K * pow(2.718281828459045, -r * T), 0) \
            if is_call else max(K * pow(2.718281828459045, -r * T) - SPOT * pow(2.718281828459045, -q * T), 0)
        # Skip cases where the price carries no vol information at double
        # precision (time value < 1e-8): every solver is ill-posed there.
        if target - floor < 1e-8:
            iv_skipped += 1
            continue
        try:
            e("implied vol (vanna) vs true sigma").add(
                implied_vol(target, SPOT, K, T, r, is_call, q), sig, ctx)
        except ImpliedVolError:
            iv_fail["vanna"] += 1
        try:
            e("implied vol (py_vollib) vs true sigma").add(
                pv_iv(target, SPOT, K, T, r, q, flag), sig, ctx)
        except Exception:
            iv_fail["py_vollib"] += 1
        try:
            e("implied vol (QuantLib) vs true sigma").add(
                ql_iv(qle, target, SPOT, r, q, 0.3), sig, ctx)
        except RuntimeError:
            pass
    return res, iv_fail, iv_skipped


def american_accuracy():
    res = {}
    def e(name):
        return res.setdefault(name, Err())
    for K, sig, r, days, q, is_call in AM_GRID:
        T = days / 365.0
        ctx = f"K={K} vol={sig} r={r} d={days} q={q} {'C' if is_call else 'P'}"
        ref200 = ql_american(SPOT, K, days, r, q, sig, is_call, AM_STEPS)
        ref_hi = ql_american(SPOT, K, days, r, q, sig, is_call, AM_REF_STEPS)
        px = price_binomial(SPOT, K, T, r, sig, is_call, q, AM_STEPS, True)
        g = greeks_binomial(SPOT, K, T, r, sig, is_call, q, AM_STEPS, True)
        mine = dict(price=px, delta=g.delta, gamma=g.gamma, theta=g.theta)
        for k in mine:
            e(f"vanna({AM_STEPS}) vs QuantLib CRR({AM_STEPS}): {k}").add(mine[k], ref200[k], ctx)
            e(f"vanna({AM_STEPS}) vs QuantLib CRR({AM_REF_STEPS}): {k}").add(mine[k], ref_hi[k], ctx)
            if k == "price":
                e(f"QuantLib CRR({AM_STEPS}) vs QuantLib CRR({AM_REF_STEPS}): {k}").add(
                    ref200[k], ref_hi[k], ctx)
        # Theta against a time-difference of the high-step QuantLib price.
        # QuantLib's own tree theta is the Black-Scholes PDE identity, which
        # is not meaningful inside the early-exercise region, so it is not a
        # trustworthy reference for theta there (see docs/benchmarks.md).
        h = 2  # days
        fd_theta = -(ql_american(SPOT, K, days + h, r, q, sig, is_call, AM_REF_STEPS)["price"]
                     - ql_american(SPOT, K, days - h, r, q, sig, is_call, AM_REF_STEPS)["price"]) \
            / (2 * h / 365.0)
        e(f"vanna({AM_STEPS}) theta vs time-difference of QuantLib CRR({AM_REF_STEPS}) price").add(
            g.theta, fd_theta, ctx)
        # European limit of the tree vs closed form
        eu = price_binomial(SPOT, K, T, r, sig, is_call, q, AM_STEPS, False)
        e(f"vanna binomial(european, {AM_STEPS}) vs vanna closed form: price").add(
            eu, bs.price(SPOT, K, T, r, sig, is_call, q), ctx)
    return res


# ----------------------------------------------------------------- timing
def timings():
    S, K, T, r, sig, q = 100.0, 100.0, 0.5, 0.03, 0.25, 0.0
    days = 183
    T = days / 365.0
    out = {}
    out["BS price"] = {
        "vanna": timeit(lambda: bs.price(S, K, T, r, sig, True, q)),
        "py_vollib": timeit(lambda: pv_price("c", S, K, T, r, sig, q)),
    }
    qe = QLEuro(K, days, True)
    def ql_reuse():
        qe.set(S, r, q, sig); return qe.opt.NPV()
    def ql_fresh():
        return QLEuro(K, days, True).set(S, r, q, sig).opt.NPV()
    out["BS price"]["QuantLib (reused instrument)"] = timeit(ql_reuse)
    out["BS price"]["QuantLib (build instrument per call)"] = timeit(ql_fresh)

    out["all Greeks (delta,gamma,vega,theta,rho)"] = {
        "vanna (greeks(), also gives vanna+volga)": timeit(lambda: bs.greeks(S, K, T, r, sig, True, q)),
        "py_vollib (5 separate calls)": timeit(lambda: (
            pv_greeks.delta("c", S, K, T, r, sig, q), pv_greeks.gamma("c", S, K, T, r, sig, q),
            pv_greeks.vega("c", S, K, T, r, sig, q), pv_greeks.theta("c", S, K, T, r, sig, q),
            pv_greeks.rho("c", S, K, T, r, sig, q))),
        "QuantLib (reused instrument)": timeit(lambda: (qe.set(S, r, q, sig), qe.greeks())),
    }
    target = bs.price(S, K, T, r, sig, True, q)
    qe2 = QLEuro(K, days, True)
    out["implied vol (ATM, well-conditioned)"] = {
        "vanna": timeit(lambda: implied_vol(target, S, K, T, r, True, q)),
        "py_vollib (lets_be_rational)": timeit(lambda: pv_iv(target, S, K, T, r, q, "c")),
        "QuantLib": timeit(lambda: ql_iv(qe2, target, S, r, q, 0.3)),
    }
    out[f"American price, CRR {AM_STEPS} steps"] = {
        "vanna (numpy-vectorised tree)": timeit(lambda: price_binomial(S, K, T, r, sig, False, q, AM_STEPS, True), 0.5),
        "QuantLib (incl. building option)": timeit(lambda: ql_american(S, K, days, r, q, sig, False, AM_STEPS), 0.5),
    }
    out[f"American delta/gamma/theta, {AM_STEPS} steps"] = {
        "vanna (greeks_binomial: one tree, price+delta+gamma+theta)": timeit(lambda: greeks_binomial(S, K, T, r, sig, False, q, AM_STEPS, True), 0.5),
        "QuantLib (tree-native)": timeit(lambda: ql_american(S, K, days, r, q, sig, False, AM_STEPS), 0.5),
    }
    return out


# ------------------------------------------------------------------ output
def fmt(x):
    return "n/a" if x is None else f"{x:.2e}"


def markdown(acc_e, iv_fail, iv_skipped, acc_a, tim):
    L = []
    def table(title, res):
        L.append(f"### {title}\n")
        L.append("| comparison | n | max abs | mean abs | max rel | mean rel | worst case |")
        L.append("|---|---:|---:|---:|---:|---:|---|")
        for name, er in res.items():
            r = er.row()
            L.append(f"| {name} | {r['n']} | {fmt(r['max_abs'])} | {fmt(r['mean_abs'])} | "
                     f"{fmt(r['max_rel'])} | {fmt(r['mean_rel'])} | {r['worst'][3]} |")
        L.append("")
    table("European: Black-Scholes-Merton", acc_e)
    L.append(f"Implied-vol failures (no root returned): {iv_fail}; "
             f"grid points skipped as ill-posed (time value < 1e-8): {iv_skipped}\n")
    table("American: binomial", acc_a)
    L.append("### Timing (median seconds per call, single thread)\n")
    L.append("| operation | implementation | time per call |")
    L.append("|---|---|---:|")
    for op, d in tim.items():
        for impl, t in d.items():
            L.append(f"| {op} | {impl} | {t * 1e6:,.1f} us |")
    return "\n".join(L)


def env_info():
    def v(p):
        try:
            return metadata.version(p)
        except metadata.PackageNotFoundError:
            return "n/a"
    cpu = "unknown"
    try:
        with open("/proc/cpuinfo") as f:
            cpu = next(l.split(":", 1)[1].strip() for l in f if l.startswith("model name"))
    except Exception:
        cpu = platform.processor() or "unknown"
    return dict(python=sys.version.split()[0], platform=platform.platform(), cpu=cpu,
                vanna=v("vanna") if v("vanna") != "n/a" else v("vanna-greeks"),
                QuantLib=v("QuantLib"), py_vollib=v("py_vollib"),
                lets_be_rational=v("lets_be_rational"), numpy=v("numpy"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="also write raw results to this path")
    ap.add_argument("--skip-timing", action="store_true")
    a = ap.parse_args(argv)
    env = env_info()
    acc_e, iv_fail, iv_skipped = european_accuracy()
    acc_a = american_accuracy()
    tim = {} if a.skip_timing else timings()
    print("## Environment\n")
    for k, v in env.items():
        print(f"- {k}: {v}")
    print(f"\nEuropean grid: {len(EURO_GRID)} points; American grid: {len(AM_GRID)} points\n")
    print(markdown(acc_e, iv_fail, iv_skipped, acc_a, tim))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(env=env, european={k: v.row() for k, v in acc_e.items()},
                           american={k: v.row() for k, v in acc_a.items()},
                           iv_fail=iv_fail, timing=tim), f, indent=1, default=str)


if __name__ == "__main__":
    main()
