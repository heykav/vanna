"""Dark, charcoal/electric-green theme, consistent with the same visual
identity used across the author's other projects rather than inventing a
new palette per app."""

BG = "#0d0e0c"
PANEL = "#161715"
BORDER = "#2a2c28"
TEXT = "#F4F5F2"
MUTED = "#9a9c96"
ACCENT = "#00FF66"
ACCENT_DIM = "#0b3d22"
RED = "#ff5c5c"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: -apple-system, "SF Pro Text", "Segoe UI", sans-serif;
    font-size: 13px;
}}
QMainWindow, QTabWidget::pane {{
    background: {BG};
    border: none;
}}
#controlPanel {{
    background: {PANEL};
    border-right: 1px solid {BORDER};
}}
QLabel#sectionHeader {{
    color: {ACCENT};
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding-top: 10px;
}}
QLabel {{
    color: {MUTED};
    font-size: 12px;
}}
QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 8px;
    color: {TEXT};
}}
QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border-color: {ACCENT};
}}
QPushButton {{
    background: {ACCENT};
    color: #06130a;
    border: none;
    border-radius: 4px;
    padding: 9px 16px;
    font-weight: 700;
}}
QPushButton:hover {{
    background: #33ff85;
}}
QPushButton:disabled {{
    background: {BORDER};
    color: {MUTED};
}}
QTabBar::tab {{
    background: {BG};
    color: {MUTED};
    padding: 8px 16px;
    border: 1px solid {BORDER};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    color: {ACCENT};
    background: {PANEL};
}}
QTableWidget {{
    background: {PANEL};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
}}
QHeaderView::section {{
    background: {BG};
    color: {MUTED};
    border: 1px solid {BORDER};
    padding: 4px;
}}
"""

MPL_STYLE = {
    "figure.facecolor": BG,
    "axes.facecolor": PANEL,
    "axes.edgecolor": BORDER,
    "axes.labelcolor": TEXT,
    "text.color": TEXT,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": BORDER,
    "grid.alpha": 0.6,
    "font.size": 10,
}
