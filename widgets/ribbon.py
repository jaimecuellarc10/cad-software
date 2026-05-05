"""AutoCAD-style ribbon widget.

QTabWidget with RibbonPanel columns.  Double-click any tab to collapse/expand.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from theme import Colors

# ── sizing ──────────────────────────────────────────────────────────────────
_RH  = 118   # total ribbon height (px)
_LW  = 52    # large button width
_LH  = 62    # large button height
_LI  = 28    # large icon size
_SH  = 20    # small button height
_SI  = 16    # small icon size


def _mk_style(large: bool) -> str:
    pad = "2px 1px" if large else "1px 4px 1px 2px"
    align = "" if large else "text-align: left;"
    return f"""
        QToolButton {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 2px;
            color: {Colors.TEXT};
            font-size: 8pt;
            padding: {pad};
            {align}
        }}
        QToolButton:hover {{
            background: {Colors.BG_PANEL_ALT};
            border-color: {Colors.BORDER_LIGHT};
        }}
        QToolButton:pressed, QToolButton:checked {{
            background: {Colors.ACCENT_BG};
            border-color: {Colors.ACCENT};
        }}
    """


_LARGE_STYLE = _mk_style(True)
_SMALL_STYLE = _mk_style(False)


# ── RibbonPanel ─────────────────────────────────────────────────────────────

class RibbonPanel(QWidget):
    """One named group inside a ribbon tab.

    Structure (top → bottom):
        3px accent strip
        button area  (HBoxLayout — large buttons + small-button columns)
        20px footer  (panel title + dropdown launcher arrow)
    """

    launcher_clicked = Signal(str)

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        self._setup()

    def _setup(self) -> None:
        self.setStyleSheet(
            f"RibbonPanel {{ background: {Colors.BG_PANEL}; "
            f"border-right: 1px solid {Colors.BORDER}; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # — accent strip —
        strip = QWidget()
        strip.setFixedHeight(3)
        strip.setStyleSheet(f"background: {Colors.ACCENT};")
        outer.addWidget(strip)

        # — button area —
        self._btn_w = QWidget()
        self._btn_w.setStyleSheet("background: transparent;")
        self._btn_l = QHBoxLayout(self._btn_w)
        self._btn_l.setContentsMargins(4, 3, 4, 2)
        self._btn_l.setSpacing(2)
        self._btn_l.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        outer.addWidget(self._btn_w, 1)

        # — footer —
        footer = QWidget()
        footer.setFixedHeight(20)
        footer.setStyleSheet(f"background: {Colors.BG_HEADER};")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(6, 0, 2, 0)
        fl.setSpacing(0)

        lbl = QLabel(self._title)
        lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 8pt; background: transparent;"
        )
        fl.addWidget(lbl)
        fl.addStretch()

        launcher = QToolButton()
        launcher.setFixedSize(14, 14)
        launcher.setArrowType(Qt.ArrowType.DownArrow)
        launcher.setStyleSheet(
            f"QToolButton {{ border: none; background: transparent; "
            f"color: {Colors.TEXT_DIM}; }}"
            f"QToolButton:hover {{ color: {Colors.TEXT}; }}"
        )
        launcher.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        launcher.clicked.connect(lambda: self.launcher_clicked.emit(self._title))
        fl.addWidget(launcher)

        outer.addWidget(footer)

    # ── public API ───────────────────────────────────────────────────────────

    def add_large(
        self,
        icon: QIcon,
        label: str,
        callback=None,
        tooltip: str = "",
        checkable: bool = False,
    ) -> QToolButton:
        """Add a large button (32-px icon above label, 52×62 px)."""
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(_LI, _LI))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setFixedSize(_LW, _LH)
        btn.setAutoRaise(True)
        btn.setCheckable(checkable)
        btn.setText(label)
        btn.setStyleSheet(_LARGE_STYLE)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            btn.setToolTip(tooltip)
        if callback:
            btn.clicked.connect(callback)
        self._btn_l.addWidget(btn)
        return btn

    def add_small_column(self) -> QVBoxLayout:
        """Append a vertical column widget; return its layout for small buttons."""
        col = QWidget()
        col.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._btn_l.addWidget(col)
        return lay

    def add_small(
        self,
        icon: QIcon,
        label: str,
        callback=None,
        tooltip: str = "",
        checkable: bool = False,
        column: QVBoxLayout | None = None,
    ) -> QToolButton:
        """Add a small button (16-px icon + label beside, 20 px tall)."""
        btn = QToolButton()
        btn.setIcon(icon)
        btn.setIconSize(QSize(_SI, _SI))
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setFixedHeight(_SH)
        btn.setAutoRaise(True)
        btn.setCheckable(checkable)
        btn.setText(label)
        btn.setStyleSheet(_SMALL_STYLE)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            btn.setToolTip(tooltip)
        if callback:
            btn.clicked.connect(callback)
        if column is not None:
            column.addWidget(btn)
        else:
            self._btn_l.addWidget(btn)
        return btn

    def add_separator(self) -> None:
        """Add a vertical divider line between button groups."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {Colors.BORDER_LIGHT};")
        sep.setFixedWidth(1)
        self._btn_l.addWidget(sep)


# ── RibbonWidget ─────────────────────────────────────────────────────────────

class RibbonWidget(QTabWidget):
    """AutoCAD-style ribbon bar.

    Each tab holds a horizontal row of RibbonPanel widgets inside a scroll area.
    Double-click a tab label to collapse/expand the panel area.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._collapsed = False
        self.setDocumentMode(True)
        self.setFixedHeight(_RH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tabBarDoubleClicked.connect(self._on_tab_dbl)

    # ── collapse / expand ────────────────────────────────────────────────────

    def _on_tab_dbl(self, _index: int) -> None:
        if self._collapsed:
            self.setFixedHeight(_RH)
            self._collapsed = False
        else:
            self.setFixedHeight(self.tabBar().sizeHint().height() + 4)
            self._collapsed = True

    # ── tab / panel factory ──────────────────────────────────────────────────

    def add_tab_row(self, title: str) -> QHBoxLayout:
        """Create a named tab; return the inner HBoxLayout for adding panels."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {Colors.BG_PANEL};")

        inner = QWidget()
        inner.setStyleSheet(f"background: {Colors.BG_PANEL};")
        lay = QHBoxLayout(inner)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(0)
        lay.addStretch()   # panels are inserted before this trailing stretch

        scroll.setWidget(inner)
        self.addTab(scroll, title)
        return lay

    def insert_panel(self, row: QHBoxLayout, title: str) -> RibbonPanel:
        """Create a RibbonPanel and insert it before the trailing stretch."""
        panel = RibbonPanel(title)
        count = row.count()          # stretch is at count-1
        row.insertWidget(count - 1, panel)
        return panel
