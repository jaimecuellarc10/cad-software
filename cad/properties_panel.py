from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QObject, QEvent
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout

from .constants import GRID_UNIT
from .entities import (
    CADEntity, LineEntity, PolylineEntity, CircleEntity, ArcEntity,
    EllipseEntity, XLineEntity, TextEntity, DimLinearEntity, DimAngularEntity,
    HatchEntity, SplineEntity, PointEntity,
)
from widgets.properties_panel import PropertiesPanel as _NewPanel


_LT_LABEL_TO_STYLE = {
    "Solid":        Qt.PenStyle.SolidLine,
    "Dashed":       Qt.PenStyle.DashLine,
    "Dotted":       Qt.PenStyle.DotLine,
    "Dash-Dot":     Qt.PenStyle.DashDotLine,
    "Dash-Dot-Dot": Qt.PenStyle.DashDotDotLine,
}


class _TabFilter(QObject):
    """Catches Tab/Backtab in any panel widget and returns focus to the CAD view."""
    def __init__(self, view):
        super().__init__()
        self._view = view

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (
                Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._view.setFocus()
            self._view.keyPressEvent(event)
            return True
        return False


class PropertiesPanel(QWidget):
    def __init__(self, scene, view, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(300)
        self._scene      = scene
        self._view       = view
        self._tab_filter = _TabFilter(view)
        self._last_ids: list[int] = []
        self._selected:  list[CADEntity] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._panel = _NewPanel()
        self._panel.propertyChanged.connect(self._apply_property)
        layout.addWidget(self._panel)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(120)

    # ── Polling ───────────────────────────────────────────────────────────────

    def _poll(self):
        selected = self._scene.selected_entities()
        ids = [id(e) for e in selected]
        if ids == self._last_ids:
            return
        self._last_ids = ids
        self._selected = selected
        objects = [e.to_props_dict() for e in selected]
        self._panel.set_selection(objects)
        # Install tab filter on newly created editor widgets
        for w in self._panel.findChildren(QWidget):
            w.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            w.installEventFilter(self._tab_filter)

    # ── Property application ──────────────────────────────────────────────────

    def _apply_property(self, prop_name: str, value):
        for e in self._selected:
            self._apply_one(e, prop_name, value)

    def _apply_one(self, e: CADEntity, prop: str, val):
        if prop == "color":
            if isinstance(val, QColor):
                e.color_override = val
                e.update()

        elif prop == "lineweight" and hasattr(e, "lineweight"):
            e.lineweight = float(val)
            e.update()

        elif prop == "linetype" and hasattr(e, "linetype"):
            e.linetype = _LT_LABEL_TO_STYLE.get(val, Qt.PenStyle.SolidLine)
            e.update()

        # ── Line ──────────────────────────────────────────────────────────────
        elif prop == "start_x" and isinstance(e, LineEntity):
            e.prepareGeometryChange()
            e._p1 = QPointF(float(val), e._p1.y())
            e.update()
        elif prop == "start_y" and isinstance(e, LineEntity):
            e.prepareGeometryChange()
            e._p1 = QPointF(e._p1.x(), float(val))
            e.update()
        elif prop == "end_x" and isinstance(e, LineEntity):
            e.prepareGeometryChange()
            e._p2 = QPointF(float(val), e._p2.y())
            e.update()
        elif prop == "end_y" and isinstance(e, LineEntity):
            e.prepareGeometryChange()
            e._p2 = QPointF(e._p2.x(), float(val))
            e.update()

        # ── Circle / Arc / Ellipse center ─────────────────────────────────────
        elif prop == "center_x" and isinstance(e, (CircleEntity, ArcEntity, EllipseEntity)):
            e.prepareGeometryChange()
            e._center = QPointF(float(val), e._center.y())
            e.update()
        elif prop == "center_y" and isinstance(e, (CircleEntity, ArcEntity, EllipseEntity)):
            e.prepareGeometryChange()
            e._center = QPointF(e._center.x(), float(val))
            e.update()

        # ── Circle / Arc radius ───────────────────────────────────────────────
        elif prop == "radius" and isinstance(e, (CircleEntity, ArcEntity)):
            e.prepareGeometryChange()
            e._radius = float(val)
            e.update()

        # ── Ellipse ───────────────────────────────────────────────────────────
        elif prop == "radius_x" and isinstance(e, EllipseEntity):
            e.prepareGeometryChange()
            e._rx = float(val)
            e.update()
        elif prop == "radius_y" and isinstance(e, EllipseEntity):
            e.prepareGeometryChange()
            e._ry = float(val)
            e.update()

        # ── Arc angles ────────────────────────────────────────────────────────
        elif prop == "start_angle" and isinstance(e, ArcEntity):
            e.prepareGeometryChange()
            e._start_angle = float(val)
            e.update()
        elif prop == "span_angle" and isinstance(e, ArcEntity):
            e.prepareGeometryChange()
            e._span_angle = float(val)
            e.update()

        # ── XLine ─────────────────────────────────────────────────────────────
        elif prop == "pos_x" and isinstance(e, XLineEntity):
            e.prepareGeometryChange()
            e._point = QPointF(float(val), e._point.y())
            e.update()
        elif prop == "pos_y" and isinstance(e, XLineEntity):
            e.prepareGeometryChange()
            e._point = QPointF(e._point.x(), float(val))
            e.update()
        elif prop == "angle" and isinstance(e, XLineEntity):
            e.prepareGeometryChange()
            e._angle_deg = float(val)
            e.update()

        # ── Text / Point position ─────────────────────────────────────────────
        elif prop == "pos_x" and isinstance(e, (TextEntity, PointEntity)):
            e.prepareGeometryChange()
            e._pos = QPointF(float(val), e._pos.y())
            e.update()
        elif prop == "pos_y" and isinstance(e, (TextEntity, PointEntity)):
            e.prepareGeometryChange()
            e._pos = QPointF(e._pos.x(), float(val))
            e.update()

        # ── Rotation (Text and Ellipse share the key) ─────────────────────────
        elif prop == "rotation" and isinstance(e, (TextEntity, EllipseEntity)):
            e.prepareGeometryChange()
            e._angle_deg = float(val)
            e.update()

        # ── Text content / height ─────────────────────────────────────────────
        elif prop == "text_content" and isinstance(e, TextEntity):
            e.prepareGeometryChange()
            e._text = str(val)
            e.update()
        elif prop == "text_height" and isinstance(e, TextEntity):
            e.prepareGeometryChange()
            e._height = float(val)
            e.update()
        elif prop == "font_family" and isinstance(e, TextEntity):
            e.prepareGeometryChange()
            e._font_family = str(val)
            e.update()

        # ── Hatch ─────────────────────────────────────────────────────────────
        elif prop == "pattern" and isinstance(e, HatchEntity):
            e.prepareGeometryChange()
            e._pattern = str(val)
            e.update()
        elif prop == "hatch_scale" and isinstance(e, HatchEntity):
            e.prepareGeometryChange()
            e._scale = float(val)
            e.update()

        # ── Dimension (linear) ────────────────────────────────────────────────
        elif prop == "offset" and isinstance(e, DimLinearEntity):
            e.prepareGeometryChange()
            e._offset = float(val) * GRID_UNIT
            e.update()
        elif prop == "text_override" and isinstance(e, DimLinearEntity):
            e.prepareGeometryChange()
            e._text_override = str(val)
            e.update()

        # ── Dimension (angular) ───────────────────────────────────────────────
        elif prop == "arc_radius" and isinstance(e, DimAngularEntity):
            e.prepareGeometryChange()
            e._radius = float(val) * GRID_UNIT
            e.update()

        # ── Dimension (shared) ────────────────────────────────────────────────
        elif prop == "arrow_size" and isinstance(e, (DimLinearEntity, DimAngularEntity)):
            e.prepareGeometryChange()
            e.arrow_size = float(val)
            e.update()
        elif prop == "dim_text_height" and isinstance(e, (DimLinearEntity, DimAngularEntity)):
            e.prepareGeometryChange()
            e.text_height = float(val)
            e.update()
