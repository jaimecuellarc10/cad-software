import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath
from .base import BaseTool
from ..entities import ArcEntity, _circumscribed_circle
from ..undo import AddEntityCommand
from ..constants import SnapMode


class ArcTool(BaseTool):
    """
    3-point arc: click start → click a point on the arc → click end.
    The arc passes through all three clicked points.
    """

    name = "arc"

    def __init__(self):
        super().__init__()
        self._pts: list[QPointF] = []   # up to 3 points
        self._cursor: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return len(self._pts) == 0

    @property
    def prompt(self) -> str:
        n = len(self._pts)
        if n == 0: return "ARC  Specify start point:"
        if n == 1: return "ARC  Specify point on arc:"
        return "ARC  Specify end point:"

    def snap_extras(self):
        return [(p, SnapMode.ENDPOINT) for p in self._pts]

    def activate(self, view):
        super().activate(view)
        self._pts.clear()
        self._cursor = None

    def deactivate(self):
        self._pts.clear()
        self._cursor = None
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._pts.append(QPointF(snapped))
        if len(self._pts) == 3:
            self._commit()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cancel()

    def cancel(self):
        self._pts.clear()
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def finish(self):
        self.cancel()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if not self._pts or self._cursor is None:
            return

        v     = self.view
        COLOR = QColor("#ffffff")
        solid = QPen(COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Dot for each placed point
        dot = QPen(COLOR, 4)
        dot.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dot)
        for p in self._pts:
            painter.drawPoint(v.mapFromScene(p))

        if len(self._pts) == 1:
            painter.setPen(solid)
            painter.drawLine(v.mapFromScene(self._pts[0]),
                             v.mapFromScene(self._cursor))

        elif len(self._pts) == 2:
            self._draw_preview_arc(painter, self._pts[0], self._cursor, self._pts[1])

    def _draw_preview_arc(self, painter: QPainter, p1, p2, p3):
        center, radius = _circumscribed_circle(p1, p2, p3)
        if center is None:
            return
        v     = self.view
        scale = v.transform().m11()
        cv    = v.mapFromScene(center)
        rvp   = radius * scale
        start, span = _arc_angles(center, p1, p2, p3)
        from PySide6.QtCore import QRectF
        r = QRectF(cv.x()-rvp, cv.y()-rvp, rvp*2, rvp*2)
        path = QPainterPath()
        path.arcMoveTo(r, start)
        path.arcTo(r, start, span)
        painter.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.SolidLine))
        painter.drawPath(path)

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self):
        p1, p2, p3 = self._pts
        center, radius = _circumscribed_circle(p1, p2, p3)
        if center is None or radius < 1:
            self._pts.clear()
            return
        start, span = _arc_angles(center, p1, p2, p3)
        layer  = self.view.layer_manager.current
        entity = ArcEntity(center, radius, start, span, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._pts.clear()
        self._cursor = None
        if self.view:
            self.view.viewport().update()


def _qt_angle(center: QPointF, pt: QPointF) -> float:
    """Qt arc angle (degrees, CCW from 3-o'clock) for point pt on circle."""
    return math.degrees(math.atan2(-(pt.y()-center.y()), pt.x()-center.x()))


def _arc_angles(center: QPointF, p1: QPointF, p2: QPointF, p3: QPointF):
    """Return (start_angle, span_angle) so arc goes p1 → through p2 → p3."""
    a1 = _qt_angle(center, p1) % 360
    a2 = _qt_angle(center, p2) % 360
    a3 = _qt_angle(center, p3) % 360

    # CCW span from a1 to a3
    span_ccw = (a3 - a1) % 360
    # Is a2 within that CCW arc?
    a2_rel = (a2 - a1) % 360
    if a2_rel <= span_ccw:
        return a1, span_ccw          # CCW arc
    else:
        return a1, -(360 - span_ccw)  # CW arc (negative span)
