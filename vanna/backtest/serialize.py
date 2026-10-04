"""
JSON serialization helpers for vanna backtest output.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Union

from vanna.backtest.engine import BacktestResult, Trade
from vanna.backtest.metrics import PerformanceSummary, summarize
from vanna.backtest.attribution import AttributionResult


def _float_to_json(x: float) -> Union[float, None]:
    """
    Convert a float to JSON-compatible value.
    Non-finite values (inf, -inf, NaN) become null.
    """
    if math.isfinite(x):
        return x
    return None


def attribution_to_dict(attr: AttributionResult) -> Dict[str, Any]:
    """
    Convert AttributionResult to a dictionary for JSON serialization.
    """
    return {
        "total_pnl": _float_to_json(attr.total_pnl),
        "delta_pnl": _float_to_json(attr.delta_pnl),
        "gamma_pnl": _float_to_json(attr.gamma_pnl),
        "theta_pnl": _float_to_json(attr.theta_pnl),
        "vega_pnl": _float_to_json(attr.vega_pnl),
        "vanna_pnl": _float_to_json(attr.vanna_pnl),
        "volga_pnl": _float_to_json(attr.volga_pnl),
        "residual": _float_to_json(attr.residual),
        "dividend_pnl": _float_to_json(attr.dividend_pnl),
    }


def trade_to_dict(trade: Trade) -> Dict[str, Any]:
    """
    Convert Trade to a dictionary for JSON serialization.
    """
    return {
        "entry_day": trade.entry_day,
        "exit_day": trade.exit_day,
        "legs": [
            {
                "is_call": leg.is_call,
                "strike": _float_to_json(leg.strike),
                "quantity": _float_to_json(leg.quantity),
                "dte_days": leg.dte_days,
                "is_stock": leg.is_stock,
            }
            for leg in trade.legs
        ],
        "entry_spot": _float_to_json(trade.entry_spot),
        "entry_iv": _float_to_json(trade.entry_iv),
        "entry_value": _float_to_json(trade.entry_value),
        "exit_value": _float_to_json(trade.exit_value),
        "pnl": _float_to_json(trade.pnl),
        "attribution": attribution_to_dict(trade.attribution),
    }


def performance_summary_to_dict(summary: PerformanceSummary) -> Dict[str, Any]:
    """
    Convert PerformanceSummary to a dictionary for JSON serialization.
    """
    return {
        "n_trades": summary.n_trades,
        "win_rate": _float_to_json(summary.win_rate),
        "profit_factor": _float_to_json(summary.profit_factor),
        "total_pnl": _float_to_json(summary.total_pnl),
        "max_drawdown": _float_to_json(summary.max_drawdown),
        "avg_pnl": _float_to_json(summary.avg_pnl),
    }


def backtest_result_to_dict(
    result: BacktestResult,
    *,
    strategy: str,
    s0: float,
    iv0: float,
    r: float,
    q: float,
    mu: float,
    entry_dte: int,
    exit_dte: int,
    n_trades: int,
    seed: int,
) -> Dict[str, Any]:
    """
    Convert BacktestResult and input parameters to a dictionary for JSON serialization.
    Includes schema version and disclaimer.
    """
    return {
        "schema_version": "1.0.0",
        "disclaimer": "Simulated backtest for educational purposes only. Per-share prices, not live market data.",
        "parameters": {
            "strategy": strategy,
            "spot": _float_to_json(s0),
            "iv": _float_to_json(iv0),
            "rate": _float_to_json(r),
            "dividend_yield": _float_to_json(q),
            "drift": _float_to_json(mu),
            "entry_dte": entry_dte,
            "exit_dte": exit_dte,
            "requested_trades": n_trades,
            "seed": seed,
        },
        "summary": performance_summary_to_dict(summarize(result)),
        "equity_curve": [_float_to_json(x) for x in result.equity_curve],
        "nonfinite_values": "NaN and infinities are represented as null.",
        "trades": [trade_to_dict(t) for t in result.trades],
    }
