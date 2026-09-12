"""Web-only glue between the real `vanna` package and the browser demo.

Deliberately kept out of the `vanna` package itself: this is JSON-shaping
for the JS/Chart.js frontend, not part of the library. Everything it
calls into (run_backtest, summarize, price_leg) is the exact same code
the desktop GUI and the test suite use - the browser demo runs the real
engine, not a reimplementation of it.
"""
import json

from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize
from vanna.backtest.chain import price_leg


def run_web_backtest(strategy, s0, iv0, r, mu, entry_dte, exit_dte, n_trades, seed):
    try:
        result = run_backtest(strategy=strategy, s0=s0, iv0=iv0, r=r, mu=mu,
                               entry_dte=entry_dte, exit_dte=exit_dte,
                               n_trades=n_trades, seed=seed)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if not result.trades:
        return json.dumps({
            "error": "No trades fit in the simulated window - try fewer "
                     "trades or a shorter entry DTE."
        })

    summary = summarize(result)
    last = result.trades[-1]

    entry_cost = sum(
        leg.quantity * price_leg(last.entry_spot, leg.strike, leg.dte_days,
                                  r, last.entry_iv, leg.is_call)
        for leg in last.legs
    )
    lo, hi = last.entry_spot * 0.7, last.entry_spot * 1.3
    n = 120
    payoff_x = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    payoff_y = []
    for s in payoff_x:
        intrinsic = sum(
            leg.quantity * (max(s - leg.strike, 0.0) if leg.is_call else max(leg.strike - s, 0.0))
            for leg in last.legs
        )
        payoff_y.append(intrinsic - entry_cost)

    a = last.attribution
    pf = summary.profit_factor
    return json.dumps({
        "equity_curve": result.equity_curve,
        "payoff_x": payoff_x,
        "payoff_y": payoff_y,
        "entry_spot": last.entry_spot,
        "legs": [{"is_call": leg.is_call, "strike": leg.strike, "quantity": leg.quantity}
                 for leg in last.legs],
        "attribution": {
            "Delta": a.delta_pnl, "Gamma": a.gamma_pnl, "Theta": a.theta_pnl,
            "Vega": a.vega_pnl, "Vanna": a.vanna_pnl, "Volga": a.volga_pnl,
            "Residual": a.residual,
        },
        "summary": {
            "n_trades": summary.n_trades,
            "win_rate": summary.win_rate,
            "profit_factor": None if pf == float("inf") else pf,
            "total_pnl": summary.total_pnl,
            "max_drawdown": summary.max_drawdown,
            "avg_pnl": summary.avg_pnl,
        },
    })
