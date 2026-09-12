from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from vanna.gui.theme import ACCENT, BG, BORDER, MUTED, PANEL, RED, TEXT
from vanna.backtest.chain import price_leg


class _Canvas(FigureCanvasQTAgg):
    def __init__(self, width=6, height=4):
        fig = Figure(figsize=(width, height), tight_layout=True)
        super().__init__(fig)
        self.ax = fig.add_subplot(111)
        self._style()

    def _style(self):
        """Re-applies the dark theme to the figure/axes. ax.clear() resets
        any per-axes styling to matplotlib's default (white) look, so every
        plot() method here must call this again right after clearing -
        setting it once in __init__ isn't enough, and a chart that silently
        reverts to a stark white background on every redraw is exactly the
        kind of thing that's easy to miss without actually looking at a
        real screenshot rather than trusting the theme module exists."""
        self.figure.patch.set_facecolor(BG)
        self.ax.set_facecolor(PANEL)
        for spine in self.ax.spines.values():
            spine.set_color(BORDER)
        self.ax.tick_params(colors=MUTED)
        self.ax.xaxis.label.set_color(MUTED)
        self.ax.yaxis.label.set_color(MUTED)


class EquityCurveChart(_Canvas):
    def plot(self, equity_curve: list[float]):
        self.ax.clear()
        self._style()
        self.ax.plot(range(len(equity_curve)), equity_curve, color=ACCENT, linewidth=2)
        self.ax.axhline(0, color=MUTED, linewidth=0.8, linestyle="--")
        self.ax.fill_between(range(len(equity_curve)), equity_curve, 0,
                              color=ACCENT, alpha=0.12)
        self.ax.set_xlabel("Trade #")
        self.ax.set_ylabel("Cumulative P&L ($)")
        self.ax.set_title("Equity Curve", color=TEXT, fontsize=11, loc="left")
        self.ax.grid(True, alpha=0.3)
        self.draw()


class PayoffChart(_Canvas):
    def plot(self, legs, r: float, iv: float, entry_spot: float):
        self.ax.clear()
        self._style()
        entry_cost = sum(
            leg.quantity * price_leg(entry_spot, leg.strike, leg.dte_days, r, iv, leg.is_call)
            for leg in legs
        )
        lo, hi = entry_spot * 0.7, entry_spot * 1.3
        spots = np.linspace(lo, hi, 200)
        payoffs = []
        for s in spots:
            intrinsic = sum(
                leg.quantity * (max(s - leg.strike, 0.0) if leg.is_call else max(leg.strike - s, 0.0))
                for leg in legs
            )
            payoffs.append(intrinsic - entry_cost)

        payoffs = np.array(payoffs)
        self.ax.plot(spots, payoffs, color=ACCENT, linewidth=2)
        self.ax.axhline(0, color=MUTED, linewidth=0.8)
        self.ax.axvline(entry_spot, color=RED, linewidth=0.8, linestyle="--", label="Entry spot")
        self.ax.fill_between(spots, payoffs, 0, where=(payoffs >= 0), color=ACCENT, alpha=0.15)
        self.ax.fill_between(spots, payoffs, 0, where=(payoffs < 0), color=RED, alpha=0.12)
        self.ax.set_xlabel("Underlying price at expiration")
        self.ax.set_ylabel("P&L ($)")
        self.ax.set_title("Payoff at Expiration (most recent trade)", color=TEXT, fontsize=11, loc="left")
        self.ax.legend(facecolor="none", edgecolor="none", labelcolor=TEXT)
        self.ax.grid(True, alpha=0.3)
        self.draw()


class AttributionChart(_Canvas):
    LABELS = ["Delta", "Gamma", "Theta", "Vega", "Vanna", "Volga", "Residual"]
    COLORS = ["#00FF66", "#6fd94f", "#4fb8d9", "#d9b04f", "#c084fc", "#f472b6", "#5a5c58"]

    def plot(self, attribution):
        self.ax.clear()
        self._style()
        values = [attribution.delta_pnl, attribution.gamma_pnl, attribution.theta_pnl,
                  attribution.vega_pnl, attribution.vanna_pnl, attribution.volga_pnl,
                  attribution.residual]
        bars = self.ax.bar(self.LABELS, values, color=self.COLORS)
        self.ax.axhline(0, color=MUTED, linewidth=0.8)
        self.ax.set_ylabel("P&L contribution ($)")
        self.ax.set_title("Greek P&L Attribution (most recent trade)", color=TEXT, fontsize=11, loc="left")
        self.ax.tick_params(axis="x", rotation=20)
        self.ax.grid(True, axis="y", alpha=0.3)
        self.draw()
