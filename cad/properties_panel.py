from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QPushButton,
    QDoubleSpinBox, QComboBox, QLineEdit, QFrame, QScrollArea,
    QColorDialog,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt, QTimer

from .constants import GRID_UNIT
from .entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity,
    XLineEntity, TextEntity, SplineEntity, PointEntity,
    DimLinearEntity, DimAngularEntity, HatchEntity,
)

_LINETYPES = [
    ("Solid",        Qt.PenStyle.SolidLine),
    ("Dashed",       Qt.PenStyle.DashLine),
    ("Dotted",       Qt.PenStyle.DotLine),
    ("Dash-Dot",     Qt.PenStyle.DashDotLine),
    ("Dash-Dot-Dot", Qt.PenStyle.DashDotDotLine),
]
_LT_LABELS = [lt[0] for lt in _LINETYPES]
_LT_STYLES = [lt[1] for lt in _LINETYPES]

# Entity types that carry their own linetype attribute
_HAS_LINETYPE = (LineEntity, PolylineEntity, CircleEntity, ArcEntity,
                 EllipseEntity, XLineEntity)
_HAS_LINEWEIGHT = (LineEntity, PolylineEntity, CircleEntity, ArcEntity,
                   EllipseEntity, XLineEntity, SplineEntity)


class PropertiesPanel(QWidget):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(210)
        self.setMaximumWidth(270)
        self._scene    = scene
        self._updating = False
        self._last_ids: list[int] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QLabel("  Properties")
        hdr.setStyleSheet(
            "background:#2a2a2a; color:#cccccc; font-weight:bold; padding:6px 8px;")
        outer.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        self._body = QWidget()
        scroll.setWidget(self._body)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 8, 8, 8)
        self._body_layout.setSpacing(4)

        self._show_empty()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(120)

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self):
        selected = self._scene.selected_entities()
        ids = [id(e) for e in selected]
        if ids != self._last_ids:
            self._last_ids = ids
            self._rebuild(selected)

    # ── Layout helpers ────────────────────────────────────────────────────────

    def _clear(self):
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                _clear_layout(item.layout())

    def _show_empty(self):
        self._clear()
        lbl = QLabel("No selection")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#555; margin-top:16px;")
        self._body_layout.addWidget(lbl)
        self._body_layout.addStretch()

    def _rebuild(self, selected: list):
        self._updating = True
        try:
            self._clear()
            if not selected:
                self._show_empty()
                return
            self._build_form(selected)
            self._body_layout.addStretch()
        finally:
            self._updating = False

    # ── Form construction ─────────────────────────────────────────────────────

    def _build_form(self, selected: list):
        multi = len(selected) > 1
        ent   = selected[0]

        # Type label
        if multi:
            type_lbl = f"{len(selected)} objects"
        else:
            type_lbl = type(ent).__name__.replace("Entity", "")
        lbl = QLabel(type_lbl)
        lbl.setStyleSheet("color:#999; font-size:10px; padding-bottom:2px;")
        self._body_layout.addWidget(lbl)

        # ── Appearance ────────────────────────────────────────────────────────
        self._body_layout.addWidget(_section_label("Appearance"))
        form = _form()

        # Layer (read-only)
        layer_names = set(e.layer.name for e in selected if e.layer)
        layer_text = list(layer_names)[0] if len(layer_names) == 1 else "—"
        form.addRow("Layer:", _ro_label(layer_text))

        # Color
        color = ent.color_override or ent.layer.color
        self._color_btn = QPushButton()
        self._color_btn.setFixedHeight(22)
        _apply_color_style(self._color_btn, color)
        self._color_btn.clicked.connect(lambda: self._pick_color(selected))
        form.addRow("Color:", self._color_btn)

        # Line weight
        if any(isinstance(e, _HAS_LINEWEIGHT) for e in selected):
            lw = (ent.lineweight if hasattr(ent, 'lineweight') and ent.lineweight is not None
                  else ent.layer.lineweight)
            self._weight_spin = _spin(0.1, 10.0, 0.1, 1, lw)
            self._weight_spin.valueChanged.connect(
                lambda v: self._apply(selected, '_set_weight', v))
            form.addRow("Weight:", self._weight_spin)

        # Line type
        if any(isinstance(e, _HAS_LINETYPE) for e in selected):
            lt = ent.linetype if hasattr(ent, 'linetype') else Qt.PenStyle.SolidLine
            idx = _LT_STYLES.index(lt) if lt in _LT_STYLES else 0
            self._lt_combo = QComboBox()
            self._lt_combo.addItems(_LT_LABELS)
            self._lt_combo.setCurrentIndex(idx)
            self._lt_combo.currentIndexChanged.connect(
                lambda i: self._apply(selected, '_set_linetype', _LT_STYLES[i]))
            form.addRow("Line type:", self._lt_combo)

        self._body_layout.addLayout(form)

        # ── Entity-specific (single selection only) ───────────────────────────
        if not multi:
            self._build_specific(ent)

    def _build_specific(self, ent):
        if isinstance(ent, DimLinearEntity):
            self._body_layout.addWidget(_section_label("Dimension"))
            form = _form()

            off = _spin(-9999, 9999, 1.0, 2, ent._offset / GRID_UNIT)
            off.valueChanged.connect(
                lambda v: self._dim_attr(ent, '_offset', v * GRID_UNIT))
            form.addRow("Offset:", off)

            arr = _spin(1.0, 100.0, 0.5, 1, ent.arrow_size)
            arr.valueChanged.connect(lambda v: self._dim_attr(ent, 'arrow_size', v))
            form.addRow("Arrow size:", arr)

            txh = _spin(0.5, 50.0, 0.5, 1, ent.text_height)
            txh.valueChanged.connect(lambda v: self._dim_attr(ent, 'text_height', v))
            form.addRow("Text height:", txh)

            ovr = QLineEdit(ent._text_override)
            ovr.setPlaceholderText("auto")
            ovr.textChanged.connect(lambda t: self._dim_attr(ent, '_text_override', t))
            form.addRow("Text override:", ovr)

            self._body_layout.addLayout(form)

        elif isinstance(ent, DimAngularEntity):
            self._body_layout.addWidget(_section_label("Dimension"))
            form = _form()

            rad = _spin(1.0, 9999.0, 1.0, 2, ent._radius / GRID_UNIT)
            rad.valueChanged.connect(
                lambda v: self._dim_attr(ent, '_radius', v * GRID_UNIT))
            form.addRow("Arc radius:", rad)

            arr = _spin(1.0, 100.0, 0.5, 1, ent.arrow_size)
            arr.valueChanged.connect(lambda v: self._dim_attr(ent, 'arrow_size', v))
            form.addRow("Arrow size:", arr)

            txh = _spin(0.5, 50.0, 0.5, 1, ent.text_height)
            txh.valueChanged.connect(lambda v: self._dim_attr(ent, 'text_height', v))
            form.addRow("Text height:", txh)

            self._body_layout.addLayout(form)

        elif isinstance(ent, TextEntity):
            self._body_layout.addWidget(_section_label("Text"))
            form = _form()

            content = QLineEdit(ent._text)
            content.textChanged.connect(lambda t: self._text_attr(ent, '_text', t))
            form.addRow("Content:", content)

            h = _spin(0.1, 100.0, 0.5, 1, ent._height)
            h.valueChanged.connect(lambda v: self._text_attr(ent, '_height', v))
            form.addRow("Height:", h)

            rot = _spin(-360.0, 360.0, 5.0, 1, ent._angle_deg)
            rot.valueChanged.connect(lambda v: self._text_attr(ent, '_angle_deg', v))
            form.addRow("Rotation°:", rot)

            self._body_layout.addLayout(form)

    # ── Property changers ─────────────────────────────────────────────────────

    def _pick_color(self, selected):
        first   = selected[0]
        current = first.color_override or first.layer.color
        color   = QColorDialog.getColor(current, self, "Pick Color")
        if not color.isValid():
            return
        for e in selected:
            e.color_override = color
            e.update()
        _apply_color_style(self._color_btn, color)

    def _apply(self, selected, method, value):
        if self._updating:
            return
        getattr(self, method)(selected, value)

    def _set_weight(self, selected, value):
        for e in selected:
            if hasattr(e, 'lineweight'):
                e.lineweight = value
                e.update()

    def _set_linetype(self, selected, style):
        for e in selected:
            if hasattr(e, 'linetype'):
                e.linetype = style
                e.update()

    def _dim_attr(self, ent, attr, value):
        if self._updating:
            return
        ent.prepareGeometryChange()
        setattr(ent, attr, value)
        ent.update()

    def _text_attr(self, ent, attr, value):
        if self._updating:
            return
        ent.prepareGeometryChange()
        setattr(ent, attr, value)
        ent.update()


# ── Widget helpers ─────────────────────────────────────────────────────────────

def _section_label(title: str) -> QLabel:
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(
        "color:#777; font-size:9px; font-weight:bold;"
        "border-top:1px solid #333; margin-top:6px; padding-top:5px;")
    return lbl


def _ro_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#888;")
    return lbl


def _form() -> QFormLayout:
    f = QFormLayout()
    f.setSpacing(5)
    f.setContentsMargins(0, 2, 0, 2)
    f.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    return f


def _spin(lo: float, hi: float, step: float, decimals: int, value: float) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    return s


def _apply_color_style(btn: QPushButton, color: QColor):
    r, g, b = color.red(), color.green(), color.blue()
    fg = "#000" if (r * 299 + g * 587 + b * 114) > 128000 else "#fff"
    btn.setStyleSheet(
        f"background:{color.name()}; color:{fg}; border:1px solid #555; padding:2px;")
    btn.setText(color.name().upper())


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
