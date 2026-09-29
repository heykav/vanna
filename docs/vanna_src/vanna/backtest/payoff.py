"""Pure payoff-at-expiration helper (no Qt/matplotlib), used by the GUI."""
from __future__ import annotations

import numpy as np

from vanna.backtest.chain import price_leg


def payoff_curve(legs, r: float, iv: float, entry_spot: float, spots):
    """P&L at expiration for each spot in `spots` (pure, no Qt needed).

    Stock legs pay quantity * (S - entry_spot); option legs pay intrinsic
    value less the premium paid/received at entry.
    """
    entry_cost = sum(
        leg.quantity * (entry_spot if leg.is_stock
                        else price_leg(entry_spot, leg.strike, leg.dte_days, r, iv, leg.is_call))
        for leg in legs
    )
    payoffs = []
    for s in spots:
        intrinsic = sum(
            leg.quantity * (s if leg.is_stock
                            else max(s - leg.strike, 0.0) if leg.is_call
                            else max(leg.strike - s, 0.0))
            for leg in legs
        )
        payoffs.append(intrinsic - entry_cost)
    return np.array(payoffs)
