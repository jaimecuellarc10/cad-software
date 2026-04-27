import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import EllipseEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode

PREVIEW_COLOR = QColor("#ffffff")
STATE_CENTER = 0
STATE_AXIS1  = 1
STATE_AXIS2  = 2


def _direction_pt(anchor: QPointF, cursor: QPointF, dist_units: float) -> QPointF:
    dx = cursor.x() - anchor.x()
    dy = cursor.y() - anchor.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        dx, dy = 1.0, 0.0
    else:
        dx /= length
        dy /= length
    scene_dist = dist_units * GRID_UNIT
    return QPointF(anchor.x() + dx * scene_dist, anchor.y() + dy * scene_dist)


class EllipseTool(BaseTool):
    name = "ellipse"

    def __init__(self):
        super().__init__()
        self._center:  QPointF | None = None
        self._axis1:   QPointF | None = None
        self._cursor:  QPointF | None = None
        self._state = STATE_CENTER

    @property
    def is_idle(self): return self._state == STATE_CENTER

    @property
    def prompt(self):
        if self._state == STATE_CENTER:
            return "ELLIPSE  Specify center point:"
        if self._state == STATE_AXIS1:
            return "ELLIPSE  Specify endpoint of first axis:"
        rx = math.hypot(self._axis1.x()-self._center.x(),
                        self._axis1.y()-self._center.y()) / GRID_UNIT
        return f"ELLIPSE  Specify half-length of second axis  (axis1={rx:.2f})  [type + Enter]"

    def snap_extras(self):
        pts = []
        if self._center: pts.append((self._center, SnapMode.CENTER))
        if self._axis1:  pts.append((self._axis1,  SnapMode.ENDPOINT))
        return pts

    def activate(self, view):
        super().activate(view)
        self._center = self._axis1 = self._cursor = None
        self._state = STATE_CENTER

    def deactivate(self):
        self._center = self._axis1 = self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        coord = self._parse_coord(cmd)
        if coord is not None and self._state == STATE_CENTER:
            self._center = coord
            self._state = STATE_AXIS1
            if self.view:
                self.view.viewport().update()
            return True
        if self._state not in (STATE_AXIS1, STATE_AXIS2):
            return False
        try:
            units = float(cmd)
        except ValueError:
            return False
        if units <= 0:
            return True
        if self._state == STATE_AXIS1:
            cursor = self._cursor or QPointF(self._center.x() + GRID_UNIT, self._center.y())
            self._axis1 = _direction_pt(self._center, cursor, units)
            self._state = STATE_AXIS2
            if self.view:
                self.view.viewport().update()
            return True
        self._commit_with_ry(units * GRID_UNIT)
        return True

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._state != STATE_CENTER:
                self.cancel()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_CENTER:
            self._center = QPointF(snapped)
            self._state = STATE_AXIS1
        elif self._state == STATE_AXIS1:
            if math.hypot(snapped.x()-self._center.x(), snapped.y()-self._center.y()) < 1:
                return
            self._axis1 = QPointF(snapped)
            self._state = STATE_AXIS2
        elif self._state == STATE_AXIS2:
            ry = self._ry_from_cursor(snapped)
            if ry > 1:
                self._commit_with_ry(ry)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._center = self._axis1 = self._cursor = None
        self._state = STATE_CENTER
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._center is None or self._cursor is None:
            return
        v = self.view
        painter.setPen(QPen(PREVIEW_COLOR, 1.5, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self._state == STATE_AXIS1:
            dist = math.hypot(self._cursor.x()-self._center.x(),
                              self._cursor.y()-self._center.y()) / GRID_UNIT
            cp = v.mapFromScene(self._cursor)
            painter.setPen(QPen(PREVIEW_COLOR, 1.5, Qt.PenStyle.DashLine))
            painter.drawLine(v.mapFromScene(self._center), v.mapFromScene(self._cursor))
            painter.drawText(cp.x()+8, cp.y()-8, f"{dist:.2f}u")
            return

        if self._state == STATE_AXIS2 and self._axis1 is not None:
            rx = math.hypot(self._axis1.x()-self._center.x(),
                            self._axis1.y()-self._center.y())
            ry = self._ry_from_cursor(self._cursor)
            angle = math.degrees(math.atan2(-(self._axis1.y()-self._center.y()),
                                             self._axis1.x()-self._center.x()))
            if rx > 1 and ry > 1:
                scale = v.transform().m11()
                painter.save()
                painter.translate(QPointF(v.mapFromScene(self._center)))
                painter.rotate(-angle)
                painter.drawEllipse(QRectF(-rx*scale, -ry*scale, rx*scale*2, ry*scale*2))
                painter.restore()
            cp = v.mapFromScene(self._cursor)
            painter.setPen(QPen(PREVIEW_COLOR, 1))
            painter.drawText(cp.x()+8, cp.y()-8,
                             f"rx={rx/GRID_UNIT:.2f}  ry={ry/GRID_UNIT:.2f}")

    def _ry_from_cursor(self, cursor: QPointF) -> float:
        if self._center is None or self._axis1 is None:
            return 0.0
        ax = self._axis1.x()-self._center.x()
        ay = self._axis1.y()-self._center.y()
        rx = math.hypot(ax, ay)
        if rx < 1e-6:
            return 0.0
        ux, uy = ax/rx, ay/rx
        dx = cursor.x()-self._center.x()
        dy = cursor.y()-self._center.y()
        perp = abs(-dx*uy + dy*ux)
        return perp

    def _commit_with_ry(self, ry: float):
        rx = math.hypot(self._axis1.x()-self._center.x(),
                        self._axis1.y()-self._center.y())
        angle = math.degrees(math.atan2(-(self._axis1.y()-self._center.y()),
                                         self._axis1.x()-self._center.x()))
        layer = self.view.layer_manager.current
        entity = EllipseEntity(self._center, rx, ry, angle, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._center = self._axis1 = self._cursor = None
        self._state = STATE_CENTER
        if self.view:
            self.view.viewport().update()
