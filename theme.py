"""
AutoCAD-style dark theme for PySide6.

Single source of truth for colors, spacing, and typography.
Call apply_theme(app) once in main.py after creating QApplication.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Color palette (matches AutoCAD 2024 dark theme closely)
# ---------------------------------------------------------------------------
class Colors:
    # Backgrounds (darker -> lighter, layered)
    BG_WINDOW       = "#2B2B2B"   # main window
    BG_PANEL        = "#373737"   # dock panels, ribbon
    BG_PANEL_ALT    = "#3F3F3F"   # hover rows, alternating
    BG_HEADER       = "#454545"   # category headers, panel titles
    BG_INPUT        = "#252525"   # recessed input fields
    BG_CANVAS       = "#1F1F1F"   # drawing area (very dark)

    # Borders
    BORDER          = "#1E1E1E"   # darker than bg = AutoCAD trick
    BORDER_LIGHT    = "#505050"   # lighter dividers inside panels

    # Text
    TEXT            = "#E8E8E8"
    TEXT_DIM        = "#A0A0A0"   # property labels
    TEXT_DISABLED   = "#6E6E6E"
    TEXT_VARIES     = "#C9A227"   # "*VARIES*" yellow for multi-select

    # Accent (selection, focus, hover highlight)
    ACCENT          = "#5B9BD5"   # AutoCAD blue
    ACCENT_HOVER    = "#4A7FB0"
    ACCENT_BG       = "#2D4661"   # subtle blue tint for selected rows

    # Status colors
    SUCCESS         = "#7BC242"
    WARNING         = "#E8A33D"
    ERROR           = "#D9534F"


# ---------------------------------------------------------------------------
# Spacing & sizing (4px grid)
# ---------------------------------------------------------------------------
class Metrics:
    UNIT            = 4
    PADDING_SM      = 4
    PADDING_MD      = 8
    PADDING_LG      = 12

    ROW_HEIGHT      = 22          # property rows, list items
    HEADER_HEIGHT   = 24          # category headers
    BUTTON_SM       = 22
    BUTTON_LG       = 48          # large ribbon buttons

    LABEL_COL_WIDTH = 110         # properties panel left column
    BORDER_RADIUS   = 2           # AutoCAD uses very subtle rounding


# ---------------------------------------------------------------------------
# QSS template
# ---------------------------------------------------------------------------
def build_qss() -> str:
    c = Colors
    m = Metrics
    return f"""
    /* ============ Global ============ */
    QWidget {{
        background-color: {c.BG_WINDOW};
        color: {c.TEXT};
        font-family: "Segoe UI", "Inter", sans-serif;
        font-size: 9pt;
        outline: none;
    }}

    QMainWindow, QDialog {{
        background-color: {c.BG_WINDOW};
    }}

    /* ============ Tooltips ============ */
    QToolTip {{
        background-color: {c.BG_HEADER};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        padding: 4px 6px;
        border-radius: {m.BORDER_RADIUS}px;
    }}

    /* ============ Dock widgets (properties, palettes) ============ */
    QDockWidget {{
        background-color: {c.BG_PANEL};
        color: {c.TEXT};
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}
    QDockWidget::title {{
        background-color: {c.BG_HEADER};
        padding: 4px 8px;
        border-bottom: 1px solid {c.BORDER};
        text-align: left;
    }}

    /* ============ Buttons ============ */
    QPushButton {{
        background-color: {c.BG_PANEL_ALT};
        color: {c.TEXT};
        border: 1px solid {c.BORDER_LIGHT};
        border-radius: {m.BORDER_RADIUS}px;
        padding: 4px 10px;
        min-height: 18px;
    }}
    QPushButton:hover {{
        background-color: {c.BG_HEADER};
        border-color: {c.ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {c.ACCENT_BG};
    }}
    QPushButton:disabled {{
        color: {c.TEXT_DISABLED};
        border-color: {c.BORDER};
    }}
    QPushButton:checked {{
        background-color: {c.ACCENT_BG};
        border-color: {c.ACCENT};
    }}

    /* Flat buttons (used for category headers) */
    QPushButton[flat="true"] {{
        background: transparent;
        border: none;
        text-align: left;
        padding: 4px 6px;
    }}
    QPushButton[flat="true"]:hover {{
        background-color: {c.BG_PANEL_ALT};
    }}

    /* ============ Inputs ============ */
    QLineEdit, QSpinBox, QDoubleSpinBox {{
        background-color: {c.BG_INPUT};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        border-radius: {m.BORDER_RADIUS}px;
        padding: 2px 4px;
        selection-background-color: {c.ACCENT};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {c.ACCENT};
    }}
    QLineEdit:read-only {{
        background-color: transparent;
        border-color: transparent;
        color: {c.TEXT_DIM};
    }}

    /* ============ Combo boxes ============ */
    QComboBox {{
        background-color: {c.BG_INPUT};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        border-radius: {m.BORDER_RADIUS}px;
        padding: 2px 6px;
        min-height: 18px;
    }}
    QComboBox:hover {{
        border-color: {c.ACCENT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 16px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 3px solid transparent;
        border-right: 3px solid transparent;
        border-top: 4px solid {c.TEXT_DIM};
        margin-right: 4px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c.BG_PANEL};
        color: {c.TEXT};
        border: 1px solid {c.BORDER};
        selection-background-color: {c.ACCENT_BG};
        selection-color: {c.TEXT};
        outline: none;
    }}

    /* ============ Scroll areas ============ */
    QScrollArea {{
        background-color: {c.BG_PANEL};
        border: none;
    }}
    QScrollBar:vertical {{
        background: {c.BG_PANEL};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {c.BORDER_LIGHT};
        min-height: 20px;
        border-radius: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c.TEXT_DIM};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}

    /* ============ Tab widget (used for ribbon tabs later) ============ */
    QTabWidget::pane {{
        background-color: {c.BG_PANEL};
        border-top: 1px solid {c.BORDER};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c.TEXT_DIM};
        padding: 6px 14px;
        border: none;
    }}
    QTabBar::tab:hover {{
        color: {c.TEXT};
    }}
    QTabBar::tab:selected {{
        color: {c.TEXT};
        border-bottom: 2px solid {c.ACCENT};
    }}

    /* ============ Menu bar / context menus ============ */
    QMenuBar {{
        background-color: {c.BG_PANEL};
        border-bottom: 1px solid {c.BORDER};
    }}
    QMenuBar::item:selected {{
        background-color: {c.ACCENT_BG};
    }}
    QMenu {{
        background-color: {c.BG_PANEL};
        border: 1px solid {c.BORDER};
        padding: 4px 0;
    }}
    QMenu::item {{
        padding: 4px 24px;
    }}
    QMenu::item:selected {{
        background-color: {c.ACCENT_BG};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c.BORDER_LIGHT};
        margin: 4px 8px;
    }}

    /* ============ Status bar ============ */
    QStatusBar {{
        background-color: {c.BG_PANEL};
        border-top: 1px solid {c.BORDER};
        color: {c.TEXT_DIM};
    }}

    /* ============ Properties panel custom widgets ============ */
    /* Selection combo at top */
    QComboBox#SelectionCombo {{
        background-color: {c.BG_HEADER};
        font-weight: 500;
        padding: 4px 8px;
    }}

    /* Category header button */
    QPushButton#CategoryHeader {{
        background-color: {c.BG_HEADER};
        border: none;
        border-bottom: 1px solid {c.BORDER};
        text-align: left;
        padding: 4px 8px;
        font-weight: 500;
    }}
    QPushButton#CategoryHeader:hover {{
        background-color: {c.BG_PANEL_ALT};
    }}

    /* Property row label */
    QLabel#PropLabel {{
        color: {c.TEXT_DIM};
        background: transparent;
        padding: 2px 6px 2px 12px;
    }}
    QLabel#PropLabel[active="true"] {{
        color: {c.ACCENT};
    }}

    /* Property row container (for hover effect) */
    QWidget#PropRow:hover {{
        background-color: {c.BG_PANEL_ALT};
    }}
    """


def apply_theme(app: QApplication) -> None:
    """Apply theme to the entire application."""
    app.setFont(QFont("Segoe UI", 9))
    app.setStyleSheet(build_qss())
