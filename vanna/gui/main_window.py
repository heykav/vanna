from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QMessageBox,
)
from PySide6.QtCore import Qt

from vanna.backtest.engine import run_backtest
from vanna.backtest.metrics import summarize
from vanna.backtest.strategies import STRATEGIES
from vanna.gui.charts import EquityCurveChart, PayoffChart, AttributionChart


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("vanna — options pricing & Greek-attributed backtesting")
        self.resize(1280, 800)

        self.equity_chart = EquityCurveChart()
        self.payoff_chart = PayoffChart()
        self.attribution_chart = AttributionChart()
        self.summary_table = QTableWidget(6, 2)
        self.summary_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.horizontalHeader().setStretchLastSection(True)
        self.summary_table.setColumnWidth(0, 130)
        self.summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.summary_table.setSelectionMode(QTableWidget.NoSelection)
        self.summary_table.setShowGrid(False)
        row_h = self.summary_table.verticalHeader().defaultSectionSize()
        header_h = self.summary_table.horizontalHeader().height()
        self.summary_table.setFixedHeight(header_h + row_h * 6 + 4)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_control_panel(), 0)
        layout.addWidget(self._build_results_tabs(), 1)
        self.setCentralWidget(central)

    def _build_control_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("controlPanel")
        panel.setFixedWidth(300)
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(6)

        header = QLabel("BACKTEST PARAMETERS")
        header.setObjectName("sectionHeader")
        outer.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        self.strategy_box = QComboBox()
        self.strategy_box.addItems(sorted(STRATEGIES))
        self.strategy_box.setCurrentText("iron_condor")
        self.strategy_box.setToolTip("Which multi-leg strategy to simulate.")
        form.addRow("Strategy", self.strategy_box)

        self.spot_box = self._spin(50, 2000, 100, 1)
        self.spot_box.setToolTip("Starting underlying price for the simulated GBM path.")
        form.addRow("Spot ($)", self.spot_box)

        self.iv_box = self._spin(0.01, 3.0, 0.22, 0.01, decimals=2)
        self.iv_box.setToolTip("Starting implied volatility; it then follows a mean-reverting daily path.")
        form.addRow("Entry IV", self.iv_box)

        self.rate_box = self._spin(0.0, 0.2, 0.03, 0.005, decimals=3)
        self.rate_box.setToolTip("Continuously-compounded risk-free rate used for discounting.")
        form.addRow("Risk-free rate", self.rate_box)

        self.drift_box = self._spin(-0.5, 0.5, 0.05, 0.01, decimals=2)
        self.drift_box.setToolTip("Annualized drift (μ) of the simulated underlying path.")
        form.addRow("Underlying drift (μ)", self.drift_box)

        self.entry_dte_box = QSpinBox()
        self.entry_dte_box.setRange(2, 365)
        self.entry_dte_box.setValue(30)
        self.entry_dte_box.setToolTip("Days to expiration when each trade is opened.")
        form.addRow("Entry DTE", self.entry_dte_box)

        self.exit_dte_box = QSpinBox()
        self.exit_dte_box.setRange(0, 364)
        self.exit_dte_box.setValue(10)
        self.exit_dte_box.setToolTip("Days to expiration when each trade is closed (0 = hold to expiry). Must be less than Entry DTE.")
        form.addRow("Exit DTE", self.exit_dte_box)

        self.n_trades_box = QSpinBox()
        self.n_trades_box.setRange(1, 500)
        self.n_trades_box.setValue(20)
        self.n_trades_box.setToolTip("How many sequential (non-overlapping) trades to simulate.")
        form.addRow("Number of trades", self.n_trades_box)

        self.seed_box = QSpinBox()
        self.seed_box.setRange(0, 999999)
        self.seed_box.setValue(42)
        self.seed_box.setToolTip("Random seed - the same seed always reproduces the same simulated path.")
        form.addRow("Random seed", self.seed_box)

        outer.addLayout(form)

        self.run_btn = QPushButton("Run backtest")
        self.run_btn.setDefault(True)
        self.run_btn.setToolTip("Run (or press Enter)")
        self.run_btn.clicked.connect(self._on_run)
        outer.addSpacing(10)
        outer.addWidget(self.run_btn)

        pnl_note = QLabel("$ figures are per share - x100 for a standard equity option contract.")
        pnl_note.setWordWrap(True)
        pnl_note.setStyleSheet("font-size: 10px;")
        outer.addWidget(pnl_note)

        outer.addSpacing(16)
        summary_header = QLabel("SUMMARY")
        summary_header.setObjectName("sectionHeader")
        outer.addWidget(summary_header)
        outer.addWidget(self.summary_table)
        outer.addStretch(1)
        return panel

    @staticmethod
    def _spin(lo, hi, default, step, decimals=1):
        box = QDoubleSpinBox()
        box.setRange(lo, hi)
        box.setValue(default)
        box.setSingleStep(step)
        box.setDecimals(decimals)
        return box

    def _build_results_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self.equity_chart, "Equity Curve")
        tabs.addTab(self.payoff_chart, "Payoff Diagram")
        tabs.addTab(self.attribution_chart, "Greek Attribution")
        return tabs

    def _on_run(self):
        # A large entry_dte * n_trades combination can take several real
        # seconds (the day-by-day attribution walk in engine.py is the
        # cost) - without this, the whole window just freezes with no
        # feedback for that long, which reads as a hang, not a busy app.
        self.run_btn.setEnabled(False)
        self.run_btn.setText("Running…")
        self.setCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            result = run_backtest(
                strategy=self.strategy_box.currentText(),
                s0=self.spot_box.value(),
                iv0=self.iv_box.value(),
                r=self.rate_box.value(),
                mu=self.drift_box.value(),
                entry_dte=self.entry_dte_box.value(),
                exit_dte=self.exit_dte_box.value(),
                n_trades=self.n_trades_box.value(),
                seed=self.seed_box.value(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "Backtest error", str(e))
            return
        finally:
            self.run_btn.setEnabled(True)
            self.run_btn.setText("Run backtest")
            self.unsetCursor()

        if not result.trades:
            QMessageBox.information(self, "No trades",
                                     "The requested number of trades didn't fit in the "
                                     "simulated window - try fewer trades or a shorter entry DTE.")
            return

        self.equity_chart.plot(result.equity_curve)

        last_trade = result.trades[-1]
        self.payoff_chart.plot(last_trade.legs, self.rate_box.value(),
                                last_trade.entry_iv, last_trade.entry_spot)
        self.attribution_chart.plot(last_trade.attribution)

        summary = summarize(result)
        rows = [
            ("Trades", str(summary.n_trades)),
            ("Win rate", f"{summary.win_rate:.1%}"),
            ("Profit factor", f"{summary.profit_factor:.2f}"),
            ("Total P&L", f"${summary.total_pnl:,.2f}"),
            ("Max drawdown", f"${summary.max_drawdown:,.2f}"),
            ("Avg P&L / trade", f"${summary.avg_pnl:,.2f}"),
        ]
        for i, (label, value) in enumerate(rows):
            self.summary_table.setItem(i, 0, QTableWidgetItem(label))
            self.summary_table.setItem(i, 1, QTableWidgetItem(value))
