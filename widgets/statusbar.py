"""AutoCAD-style status bar widget.

Row of checkable snap-toggle buttons on the left, a transient message label
in the centre, Courier-font coordinate display and unit combo on the right.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QWidget,
)

from theme import Colors


class CADStatusBar(QWidget):
    """Replacement for QStatusBar with snap toggle buttons."""

    def __init__(self, snap_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._snap = snap_manager

        # Temporary-message timer (mimics QStatusBar.showMessage timeout)
        self._msg_timer = QTimer(self)
        self._msg_timer.setSingleShot(True)
        self._msg_timer.timeout.connect(self._clear_msg)

        # Button-sync timer — reads snap_manager every 100 ms
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_buttons)
        self._sync_timer.start(100)

        self._setup()

    # ── Layout ───────────────────────────────────────────────────────────────

    def _setup(self) -> None:
        self.setFixedHeight(26)
        self.setStyleSheet(
            f"CADStatusBar {{ background: {Colors.BG_PANEL}; "
            f"border-top: 1px solid {Colors.BORDER}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 6, 1)
        lay.setSpacing(1)

        from icons import Icons

        def _btn(icon_name: str, label: str, tip: str = "") -> QPushButton:
            b = QPushButton()
            b.setIcon(Icons.get(icon_name))
            b.setIconSize(QSize(14, 14))
            b.setText(label)
            b.setCheckable(True)
            b.setObjectName("StatusBtn")
            b.setFixedHeight(22)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if tip:
                b.setToolTip(tip)
            lay.addWidget(b)
            return b

        self._btn_grid  = _btn("grid",     "Grid",  "Toggle grid display  [F7]")
        self._btn_snap  = _btn("snap",     "Snap",  "Toggle grid snap  [F9]")
        self._btn_ortho = _btn("ortho",    "Ortho", "Toggle ortho mode  [F8]")
        self._btn_polar = _btn("polar",    "Polar", "Polar tracking  [F10]  (not yet implemented)")
        self._btn_osnap = _btn("snap",     "OSnap", "Toggle object snap  [F3]  (right-click for modes)")
        self._btn_dynin = _btn("dyninput", "DynIn", "Dynamic input  [F12]  (not yet implemented)")

        # Placeholders — no back-end yet
        self._btn_polar.setEnabled(False)
        self._btn_dynin.setEnabled(False)

        # Wire toggled → snap_manager
        self._btn_grid.toggled.connect(
            lambda on: (setattr(self._snap, 'grid_visible', on),
                        self._request_view_update()))
        self._btn_snap.toggled.connect(
            lambda on: setattr(self._snap, 'grid_snap_enabled', on))
        self._btn_ortho.toggled.connect(
            lambda on: (setattr(self._snap, 'ortho_enabled', on),
                        self._request_view_update()))
        self._btn_osnap.toggled.connect(
            lambda on: setattr(self._snap, 'osnap_enabled', on))

        # Right-click on OSnap → individual snap mode menu
        self._btn_osnap.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn_osnap.customContextMenuRequested.connect(self._show_osnap_menu)

        # — vertical separator —
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {Colors.BORDER_LIGHT};")
        sep.setFixedWidth(1)
        sep.setContentsMargins(2, 2, 2, 2)
        lay.addWidget(sep)

        # Transient message (center, flexible)
        self._msg_lbl = QLabel()
        self._msg_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 8pt;")
        self._msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Preferred)
        lay.addWidget(self._msg_lbl)

        # Coordinate display (right, fixed width, monospace)
        self._coord_lbl = QLabel("X:   0.000   Y:   0.000")
        self._coord_lbl.setFont(QFont("Courier New", 9))
        self._coord_lbl.setMinimumWidth(240)
        self._coord_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._coord_lbl.setStyleSheet(f"color: {Colors.TEXT};")
        lay.addWidget(self._coord_lbl)

        # Unit combo
        from cad.constants import DrawingUnit
        self.unit_combo = QComboBox()
        for u in DrawingUnit:
            self.unit_combo.addItem(u.label, userData=u)
        self.unit_combo.setCurrentText(DrawingUnit.MM.label)
        self.unit_combo.setFixedWidth(60)
        self.unit_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.unit_combo)

        self._sync_buttons()

    # ── Public API ────────────────────────────────────────────────────────────

    def update_coords(self, x: float, y: float,
                      unit_label: str, mode_str: str = "") -> None:
        """Called by CADView on every mouse-move to refresh the coordinate readout."""
        self._coord_lbl.setText(
            f"X: {x:>9.3f}   Y: {y:>9.3f}  {unit_label}{mode_str}"
        )

    def showMessage(self, msg: str, timeout: int = 0) -> None:
        """QStatusBar-compatible: display a temporary or permanent message."""
        self._msg_lbl.setText(msg)
        if timeout > 0:
            self._msg_timer.start(timeout)
        else:
            self._msg_timer.stop()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _clear_msg(self) -> None:
        self._msg_lbl.setText("")

    def _sync_buttons(self) -> None:
        """Sync button checked state with snap_manager (called every 100 ms)."""
        pairs = [
            (self._btn_grid,  'grid_visible',       True),
            (self._btn_snap,  'grid_snap_enabled',  True),
            (self._btn_ortho, 'ortho_enabled',       False),
            (self._btn_osnap, 'osnap_enabled',       True),
        ]
        for btn, attr, default in pairs:
            val = getattr(self._snap, attr, default)
            if btn.isChecked() != val:
                btn.blockSignals(True)
                btn.setChecked(val)
                btn.blockSignals(False)

    def _request_view_update(self) -> None:
        """Ask the view to repaint (grid visibility may have changed)."""
        if self._view_ref is not None:
            self._view_ref.viewport().update()

    # ── OSnap right-click menu ────────────────────────────────────────────────

    def _show_osnap_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        from cad.constants import SnapMode

        _LABELS = [
            (SnapMode.ENDPOINT,      "Endpoint"),
            (SnapMode.MIDPOINT,      "Midpoint"),
            (SnapMode.CENTER,        "Center"),
            (SnapMode.INTERSECTION,  "Intersection"),
            (SnapMode.PERPENDICULAR, "Perpendicular"),
            (SnapMode.TANGENT,       "Tangent"),
            (SnapMode.NEAREST,       "Nearest"),
            (SnapMode.PARALLEL,      "Parallel"),
        ]

        menu = QMenu(self)
        for mode, label in _LABELS:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(mode in self._snap.active_modes)
            act.toggled.connect(lambda on, m=mode: self._toggle_snap_mode(m, on))

        menu.addSeparator()
        menu.addAction("Select All").triggered.connect(self._osnap_select_all)
        menu.addAction("Clear All").triggered.connect(self._osnap_clear_all)

        menu.exec(self._btn_osnap.mapToGlobal(pos))

    def _toggle_snap_mode(self, mode, on: bool) -> None:
        if on:
            self._snap.active_modes.add(mode)
        else:
            self._snap.active_modes.discard(mode)

    def _osnap_select_all(self) -> None:
        from cad.constants import SnapMode
        for m in SnapMode:
            if m not in (SnapMode.NONE, SnapMode.GRID):
                self._snap.active_modes.add(m)

    def _osnap_clear_all(self) -> None:
        self._snap.active_modes.clear()

    # Set by MainWindow after view is created.
    _view_ref = None
