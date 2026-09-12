"""`vanna` CLI: run a backtest and print a summary, no GUI required."""
from __future__ import annotations

import argparse
import sys

from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize
from vanna.backtest.strategies import STRATEGIES


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vanna", description=__doc__)
    parser.add_argument("strategy", choices=sorted(STRATEGIES))
    parser.add_argument("--spot", type=float, default=100.0)
    parser.add_argument("--iv", type=float, default=0.22)
    parser.add_argument("--rate", type=float, default=0.03)
    parser.add_argument("--drift", type=float, default=0.0, help="underlying drift (mu)")
    parser.add_argument("--entry-dte", type=int, default=30)
    parser.add_argument("--exit-dte", type=int, default=10)
    parser.add_argument("--trades", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    result = run_backtest(
        strategy=args.strategy, s0=args.spot, iv0=args.iv, r=args.rate, mu=args.drift,
        entry_dte=args.entry_dte, exit_dte=args.exit_dte, n_trades=args.trades, seed=args.seed,
    )
    if not result.trades:
        print("No trades fit in the simulated window - try --trades lower or --entry-dte shorter.")
        return 1

    summary = summarize(result)
    print(f"Strategy:       {args.strategy}")
    print(f"Trades:         {summary.n_trades}")
    print(f"Win rate:       {summary.win_rate:.1%}")
    print(f"Profit factor:  {summary.profit_factor:.2f}")
    print(f"Total P&L:      {summary.total_pnl:+.2f} (per share; x100 for a standard equity option contract)")
    print(f"Max drawdown:   {summary.max_drawdown:.2f}")
    print(f"Avg P&L/trade:  {summary.avg_pnl:+.2f}")

    last = result.trades[-1]
    a = last.attribution
    print("\nGreek attribution of the most recent trade's P&L:")
    print(f"  delta {a.delta_pnl:+.3f}  gamma {a.gamma_pnl:+.3f}  theta {a.theta_pnl:+.3f}  "
          f"vega {a.vega_pnl:+.3f}  vanna {a.vanna_pnl:+.3f}  volga {a.volga_pnl:+.3f}  "
          f"residual {a.residual:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
