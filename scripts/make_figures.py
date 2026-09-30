"""Regenerate every figure under docs/img/ from the real library.

    pip install -e . matplotlib
    python scripts/make_figures.py

Deterministic: fixed seed, no network, no market data. Nothing is drawn by
hand; every number comes from one of
  * vanna.backtest.engine.run_backtest (attribution waterfall, payoff),
  * vanna.pricing.black_scholes.price (hero curves),
  * the tables in docs/benchmarks.md (accuracy and tree convergence;
    parsed, not retyped), which were measured by benchmarks/bench_reference.py
    against QuantLib and py_vollib and by benchmarks/bench_trees.py. QuantLib and py_vollib are NOT needed to run this script.
matplotlib is a figure-only dependency (already in the `gui` extra); the
library itself depends only on numpy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "img"

from vanna.backtest.engine import run_backtest  # noqa: E402
from vanna.backtest.payoff import payoff_curve  # noqa: E402
from vanna.pricing.black_scholes import price  # noqa: E402

# ---- one palette, two themes ------------------------------------------------
THEMES = {
    "dark": dict(bg="#0d0e0c", panel="#141513", text="#e8ebe4", muted="#8d9389",
                 grid="#262824", pos="#00e676", neg="#ff6b6b", ref="#6aa8ff",
                 amber="#f5b642", total="#e8ebe4"),
    "light": dict(bg="#ffffff", panel="#f6f7f4", text="#1a1c18", muted="#5d635a",
                  grid="#dfe2da", pos="#0a8f45", neg="#c62d2d", ref="#2a62c9",
                  amber="#a86a00", total="#1a1c18"),
}
FONT = ["DejaVu Sans"]  # bundled with matplotlib -> identical output everywhere

# The example run from examples/covered_call_backtest.py, plus q=1% so the
# dividend term is non-zero. Trade index 2 is the third trade of that run.
RUN = dict(strategy="covered_call", s0=100.0, iv0=0.22, r=0.03, mu=0.05,
           entry_dte=30, exit_dte=10, n_trades=12, seed=42, q=0.01)
TRADE_IDX = 2


def style(t):
    plt.rcParams.update({
        "font.family": FONT, "font.size": 10.5, "text.color": t["text"],
        "axes.labelcolor": t["text"], "axes.edgecolor": t["grid"],
        "xtick.color": t["muted"], "ytick.color": t["muted"],
        "axes.facecolor": t["panel"], "figure.facecolor": t["bg"],
        "savefig.facecolor": t["bg"], "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": True, "grid.color": t["grid"],
        "grid.linewidth": 0.8, "axes.axisbelow": True, "legend.frameon": False,
    })


def get_trade():
    res = run_backtest(**RUN)
    return res.trades[TRADE_IDX]


def waterfall(ax, t, tr, compact=False):
    a = tr.attribution
    items = [("Delta", a.delta_pnl), ("Gamma", a.gamma_pnl), ("Theta", a.theta_pnl),
             ("Vega", a.vega_pnl), ("Vanna", a.vanna_pnl), ("Volga", a.volga_pnl),
             ("Dividend", a.dividend_pnl), ("Residual", a.residual)]
    total = sum(v for _, v in items)
    assert abs(total - tr.pnl) < 1e-9, (total, tr.pnl)  # attribution sums to P&L
    run, xs = 0.0, range(len(items) + 1)
    for i, (name, v) in enumerate(items):
        ax.bar(i, v, bottom=run, width=0.62, color=t["pos"] if v >= 0 else t["neg"], zorder=3)
        if i < len(items):
            ax.plot([i + 0.31, i + 0.69], [run + v] * 2, color=t["muted"], lw=0.8, zorder=2)
        run += v
        ax.annotate(f"{v:+.2f}", (i, max(run, run - v)), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=8.5 if compact else 9.5, color=t["text"])
    n = len(items)
    ax.bar(n, total, width=0.62, color=t["total"], zorder=3)
    ax.annotate(f"{total:+.2f}", (n, max(total, 0)), xytext=(0, 3), textcoords="offset points",
                ha="center", va="bottom", fontsize=8.5 if compact else 9.5,
                color=t["text"], fontweight="bold")
    ax.axhline(0, color=t["muted"], lw=1, zorder=4)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n_ for n_, _ in items] + ["Total P&L"],
                       rotation=30 if compact else 0, ha="right" if compact else "center",
                       fontsize=8.5 if compact else 10)
    ax.grid(axis="x", visible=False)
    levels = np.concatenate([[0.0], np.cumsum([v for _, v in items])])
    span = levels.max() - min(levels.min(), 0)
    ax.set_ylim(min(levels.min(), 0) - 0.06 * span, levels.max() + 0.16 * span)
    return total


def fig_attribution(theme, tr):
    t = THEMES[theme]; style(t)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=200)
    waterfall(ax, t, tr)
    ax.set_ylabel("P&L per share ($)")
    strike = [l.strike for l in tr.legs if not l.is_stock][0]
    fig.suptitle("Where one covered-call trade's P&L came from", x=0.06, ha="left",
                 fontsize=13.5, fontweight="bold", y=0.985)
    ax.set_title(f"Long stock + short {strike:.0f} call, entry spot {tr.entry_spot:.2f}, "
                 f"IV {tr.entry_iv:.1%}, held {tr.exit_day - tr.entry_day} days; "
                 f"synthetic GBM path (seed {RUN['seed']}, trade #{TRADE_IDX + 1})",
                 loc="left", fontsize=9, color=t["muted"], pad=8)
    fig.text(0.06, 0.012, "Source: vanna.backtest.engine.run_backtest; Taylor terms use start-of-period "
             "Greeks, residual is reported, not hidden.", fontsize=7.8, color=t["muted"], ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(OUT / f"attribution-{theme}.png"); plt.close(fig)


def fig_payoff(theme, tr):
    t = THEMES[theme]; style(t)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=200)
    K = [l.strike for l in tr.legs if not l.is_stock][0]
    s = np.linspace(tr.entry_spot * 0.8, tr.entry_spot * 1.2, 401)
    pay = payoff_curve(tr.legs, RUN["r"], tr.entry_iv, tr.entry_spot, s, q=RUN["q"])
    hold = s - tr.entry_spot
    ax.plot(s, hold, color=t["muted"], lw=1.6, ls="--", label="Stock alone", zorder=2)
    ax.plot(s, pay, color=t["pos"], lw=2.6, label="Covered call at expiration", zorder=3)
    ax.fill_between(s, 0, pay, where=pay >= 0, color=t["pos"], alpha=0.14, zorder=1)
    ax.fill_between(s, 0, pay, where=pay < 0, color=t["neg"], alpha=0.14, zorder=1)
    ax.axhline(0, color=t["muted"], lw=1)
    ax.axvline(K, color=t["ref"], lw=1.2, ls=":")
    ax.axvline(tr.entry_spot, color=t["amber"], lw=1.2, ls=":")
    ymax = pay.max()
    ax.annotate(f"Strike {K:.0f}", (K, ax.get_ylim()[0]), xytext=(5, 6), textcoords="offset points",
                color=t["ref"], fontsize=9.5)
    ax.annotate(f"Entry spot {tr.entry_spot:.2f}", (tr.entry_spot, ax.get_ylim()[0]),
                xytext=(-5, 6), textcoords="offset points", ha="right", color=t["amber"], fontsize=9.5)
    ax.annotate(f"Max gain {ymax:+.2f}\n(capped above the strike)", (s[-1], ymax),
                xytext=(-8, 8), textcoords="offset points", ha="right", va="bottom", color=t["pos"], fontsize=9.5)
    ax.set_xlabel("Underlying price at expiration ($)")
    ax.set_ylabel("P&L per share ($)")
    ax.legend(loc="upper left", fontsize=9.5)
    fig.suptitle("Covered-call payoff at expiration", x=0.06, ha="left", fontsize=13.5,
                 fontweight="bold", y=0.985)
    ax.set_title(f"Long 1 share + short 1 call (strike {K:.0f}); premium from Black-Scholes at "
                 f"IV {tr.entry_iv:.1%}, r=3%, q=1%", loc="left", fontsize=9, color=t["muted"], pad=8)
    fig.text(0.06, 0.012, "Source: vanna.backtest.payoff.payoff_curve. Per share, not per contract "
             "(x100); dividends not included.", fontsize=7.8, color=t["muted"], ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    fig.savefig(OUT / f"payoff-{theme}.png"); plt.close(fig)


def parse_benchmarks():
    """Read `max abs` from the tables in docs/benchmarks.md (not retyped here)."""
    rows = {}
    pat = re.compile(r"^\| (.+?) \| (\d+) \| ([\d.]+e[+-]\d+) \|")
    for line in (ROOT / "docs" / "benchmarks.md").read_text().splitlines():
        m = pat.match(line)
        if m:
            rows[m.group(1)] = float(m.group(3))
    return rows


def fig_accuracy(theme):
    t = THEMES[theme]; style(t)
    b = parse_benchmarks()
    qs = ["price", "delta", "gamma", "vega", "theta", "rho"]
    vq = [b[f"vanna vs QuantLib: {q}"] for q in qs]
    vp = [b[f"vanna vs py_vollib: {q}"] for q in qs]
    iv = [b["implied vol (vanna) vs true sigma"], b["implied vol (py_vollib) vs true sigma"],
          b["implied vol (QuantLib) vs true sigma"]]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.6), dpi=200,
                                 gridspec_kw=dict(width_ratios=[2.4, 1], wspace=0.3))
    x = np.arange(len(qs)); w = 0.38
    a1.bar(x - w / 2, vq, w, color=t["pos"], label="vanna vs QuantLib", zorder=3)
    a1.bar(x + w / 2, vp, w, color=t["ref"], label="vanna vs py_vollib", zorder=3)
    a1.set_yscale("log"); a1.set_ylim(1e-17, 1e-10)
    a1.set_xticks(x); a1.set_xticklabels(qs)
    a1.set_ylabel("Max absolute difference (log scale)")
    a1.set_title("Black-Scholes-Merton, 2,016-point grid", loc="left", fontsize=10.5, pad=8)
    a1.legend(loc="upper right", fontsize=9, ncol=1)
    a1.grid(axis="x", visible=False)
    x2 = np.arange(3)
    a2.bar(x2, iv, 0.6, color=[t["pos"], t["ref"], t["amber"]], zorder=3)
    a2.set_yscale("log"); a2.set_ylim(1e-11, 1e-8)
    a2.set_xticks(x2); a2.set_xticklabels(["vanna", "py_vollib", "QuantLib"], fontsize=9)
    a2.set_ylabel("Max |recovered - true| sigma")
    a2.set_title("Implied vol, 1,812 points", loc="left", fontsize=10.5, pad=8)
    a2.grid(axis="x", visible=False)
    for xi, v in zip(x2, iv):
        a2.annotate(f"{v:.1e}", (xi, v), xytext=(0, 3), textcoords="offset points",
                    ha="center", fontsize=8.5)
    fig.suptitle("Numerical agreement with QuantLib and py_vollib", x=0.06, ha="left",
                 fontsize=13.5, fontweight="bold", y=0.985)
    fig.text(0.06, 0.012, "Source: docs/benchmarks.md (one run: QuantLib 1.43, py_vollib 1.0.12; "
             "European options, incl. dividend yield). Shows the formulas match, not that BSM fits markets.",
             fontsize=7.8, color=t["muted"], ha="left")
    fig.subplots_adjust(left=0.09, right=0.98, top=0.83, bottom=0.11)
    fig.savefig(OUT / f"accuracy-{theme}.png"); plt.close(fig)


# Two-series palette for the convergence chart, validated per theme with the
# dataviz palette checker (lightness band, CVD separation, contrast).
SERIES = {"dark": {"crr": "#c4861c", "lr": "#5a90e0"},
          "light": {"crr": "#a86a00", "lr": "#2a62c9"}}


def parse_convergence(title_prefix):
    """Rows `| steps | CRR max | CRR mean | LR max | LR mean |` of the table
    under the heading starting with `title_prefix` in docs/benchmarks.md."""
    lines = (ROOT / "docs" / "benchmarks.md").read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("#### " + title_prefix))
    rows, pat = [], re.compile(r"^\| (\d+) \| ([\d.e+-]+) \| ([\d.e+-]+) \| ([\d.e+-]+) \| ([\d.e+-]+) \|$")
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        m = pat.match(line)
        if m:
            rows.append([float(g) for g in m.groups()])
    assert rows, title_prefix
    return np.array(rows)


def fig_convergence(theme):
    t = THEMES[theme]; style(t); c = SERIES[theme]
    eu = parse_convergence("European price error")
    am = parse_convergence("American price error")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), dpi=200, gridspec_kw=dict(wspace=0.28))
    for ax, data, title in ((axes[0], eu, "European (vs closed form), 480 points"),
                            (axes[1], am, "American (vs 4,001-step LR), 72 points")):
        n = data[:, 0]
        ax.plot(n, data[:, 1], color=c["crr"], lw=2, ls="--", marker="o", ms=5, label="CRR", zorder=3)
        ax.plot(n, data[:, 3], color=c["lr"], lw=2, marker="s", ms=5, label="Leisen-Reimer", zorder=3)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xticks(n); ax.set_xticklabels([f"{int(v)}" for v in n])
        ax.minorticks_off()
        ax.set_xlabel("Tree steps")
        ax.set_title(title, loc="left", fontsize=10.5, pad=8)
        ax.set_xlim(n[0] / 1.25, n[-1] * 2.1)  # room for the end labels
        for col in (1, 3):
            ax.annotate(f"{data[-1, col]:.1e}", (n[-1], data[-1, col]), xytext=(7, 0),
                        textcoords="offset points", ha="left", va="center", fontsize=8.5,
                        color=t["text"])
    axes[0].set_ylabel("Max absolute price error (log scale)")
    axes[0].legend(loc="lower left", fontsize=9)
    fig.suptitle("Binomial tree error vs step count", x=0.06, ha="left",
                 fontsize=13.5, fontweight="bold", y=0.985)
    fig.text(0.06, 0.012, "Source: docs/benchmarks.md, measured by benchmarks/bench_trees.py "
             "(S=100, grids listed there). Max over the grid; lower is better.",
             fontsize=7.8, color=t["muted"], ha="left")
    fig.subplots_adjust(left=0.09, right=0.98, top=0.83, bottom=0.14)
    fig.savefig(OUT / f"convergence-{theme}.png"); plt.close(fig)


def hero_svg(theme):
    t = THEMES[theme]
    accent = "#00ff66" if theme == "dark" else "#0a8f45"
    W, H = 1280, 320
    # Real Black-Scholes call value vs spot at four expiries (K=100, 22% vol).
    curves = []
    x0, x1, y0, y1 = 700, 1230, 285, 40
    spots = np.linspace(70, 130, 121)
    ymax = price(130, 100, 0.5, 0.03, 0.22, True) 
    for T, op in ((0.02, 1.0), (0.1, 0.7), (0.25, 0.45), (0.5, 0.25)):
        pts = " ".join(f"{x0 + (s - 70) / 60 * (x1 - x0):.1f},"
                        f"{y0 - price(s, 100, T, 0.03, 0.22, True) / ymax * (y0 - y1):.1f}"
                        for s in spots)
        curves.append(f'<polyline points="{pts}" fill="none" stroke="{accent}" stroke-width="2.4" '
                      f'stroke-opacity="{op}" stroke-linejoin="round"/>')
    grid = "".join(f'<line x1="{x0}" x2="{x1}" y1="{y}" y2="{y}" stroke="{t["grid"]}"/>'
                   for y in np.linspace(y1, y0, 5))
    grid += "".join(f'<line y1="{y1}" y2="{y0}" x1="{x}" x2="{x}" stroke="{t["grid"]}"/>'
                    for x in np.linspace(x0, x1, 7))
    sans = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
    mono = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">vanna</title>
<desc id="d">vanna: options pricing, Greeks and Greek-attributed backtesting. Background shows Black-Scholes call value against spot at four expiries.</desc>
<rect width="{W}" height="{H}" rx="14" fill="{t["bg"]}"/>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{t["grid"]}"/>
{grid}
{"".join(curves)}
<text x="700" y="304" font-family="{mono}" font-size="12" fill="{t["muted"]}">spot 70</text>
<text x="1230" y="304" font-family="{mono}" font-size="12" fill="{t["muted"]}" text-anchor="end">130</text>
<text x="1230" y="30" font-family="{mono}" font-size="12" fill="{t["muted"]}" text-anchor="end">call value, K=100, vol 22%: 1w / 5w / 13w / 26w to expiry</text>
<text x="64" y="132" font-family="{sans}" font-size="88" font-weight="700" fill="{t["text"]}" letter-spacing="-2">vanna</text>
<rect x="64" y="150" width="72" height="5" rx="2.5" fill="{accent}"/>
<text x="64" y="196" font-family="{sans}" font-size="24" fill="{t["text"]}">Options pricing, Greeks and backtesting</text>
<text x="64" y="228" font-family="{sans}" font-size="24" fill="{t["text"]}">with every trade's P&amp;L attributed to its Greeks.</text>
<text x="64" y="272" font-family="{mono}" font-size="15" fill="{t["muted"]}">dV = Δ·dS + ½Γ·dS² + Θ·dt + Vega·dσ + Vanna·dS·dσ + ½Volga·dσ² + residual</text>
</svg>
'''


def fig_social(tr):
    t = THEMES["dark"]; style(t)
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)
    fig.text(0.05, 0.80, "vanna", fontsize=76, fontweight="bold", color=t["text"], va="center")
    fig.add_artist(plt.Rectangle((0.052, 0.665), 0.06, 0.012, color="#00ff66", transform=fig.transFigure))
    fig.text(0.05, 0.575, "Options pricing, Greeks and backtesting", fontsize=17, color=t["text"])
    fig.text(0.05, 0.515, "with every trade's P&L attributed to its Greeks.", fontsize=17, color=t["text"])
    fig.text(0.05, 0.44, "Black-Scholes-Merton  |  CRR and Leisen-Reimer trees (American)\nImplied vol  |  ten option strategies\n"
             "Checked against QuantLib and py_vollib", fontsize=13.5, color=t["muted"], linespacing=1.7, va="top")
    fig.text(0.05, 0.075, "github.com/heykav/vanna", fontsize=14, color=t["muted"], family="DejaVu Sans Mono")
    ax = fig.add_axes([0.56, 0.20, 0.41, 0.60])
    waterfall(ax, t, tr, compact=True)
    ax.set_ylabel("P&L per share ($)", fontsize=9)
    ax.set_title("Greek attribution of one covered-call trade", loc="left", fontsize=11.5, pad=10)
    fig.savefig(OUT / "social-preview.png"); plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tr = get_trade()
    for theme in THEMES:
        (OUT / f"hero-{theme}.svg").write_text(hero_svg(theme), encoding="utf-8")
        fig_attribution(theme, tr)
        fig_payoff(theme, tr)
        fig_accuracy(theme)
        fig_convergence(theme)
    fig_social(tr)
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
