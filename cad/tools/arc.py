import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath
from .base import BaseTool
from ..entities import ArcEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode


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

    def on_command(self, cmd: str) -> bool:
        coord = self._parse_coord(cmd)
        if coord is not None and not self._pts:
            self._pts.append(coord)
            if self.view:
                self.view.viewport().update()
            return True
        if not self._pts or self._cursor is None:
            return False
        try:
            value = float(cmd)
        except ValueError:
            return False
        if value <= 0:
            return True
        if len(self._pts) == 1:
            self._pts.append(_direction_pt(self._pts[0], self._cursor, value))
            if self.view:
                self.view.viewport().update()
            return True
        if len(self._pts) == 2:
            p3 = _end_for_radius(self._pts[0], self._pts[1], self._cursor, value * GRID_UNIT)
            if p3 is None:
                return True
            self._commit_points(self._pts[0], self._pts[1], p3)
            return True
        return False

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
            dist = math.hypot(self._cursor.x()-self._pts[0].x(),
                              self._cursor.y()-self._pts[0].y()) / GRID_UNIT
            cp = v.mapFromScene(self._cursor)
            painter.setPen(QPen(COLOR, 1))
            painter.drawText(cp.x()+8, cp.y()-8, f"{dist:.2f}u")

        elif len(self._pts) == 2:
            arc = _compute_arc(self._pts[0], self._pts[1], self._cursor)
            if arc is not None:
                center, radius, start, span = arc
                self._draw_preview_arc(painter, center, radius, start, span)
                cp = v.mapFromScene(self._cursor)
                arc_len = abs(math.radians(span) * radius) / GRID_UNIT
                painter.setPen(QPen(COLOR, 1))
                painter.drawText(cp.x()+8, cp.y()-8,
                                 f"r={radius/GRID_UNIT:.2f}  L={arc_len:.2f}")

    def _draw_preview_arc(self, painter: QPainter, center, radius, start, span):
        v     = self.view
        scale = v.transform().m11()
        cv    = v.mapFromScene(center)
        rvp   = radius * scale
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
        self._commit_points(p1, p2, p3)

    def _commit_points(self, p1: QPointF, p2: QPointF, p3: QPointF):
        arc = _compute_arc(p1, p2, p3)
        if arc is None:
            self._pts.clear()
            return
        center, radius, start, span = arc
        if radius < 1:
            self._pts.clear()
            return
        layer  = self.view.layer_manager.current
        entity = ArcEntity(center, radius, start, span, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._pts.clear()
        self._cursor = None
        if self.view:
            self.view.viewport().update()


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


def _compute_arc(p1: QPointF, p2: QPointF, p3: QPointF):
    ax, ay = p1.x(), p1.y()
    bx, by = p2.x(), p2.y()
    cx, cy = p3.x(), p3.y()
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-10:
        return None
    a2 = ax * ax + ay * ay
    b2 = bx * bx + by * by
    c2 = cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    center = QPointF(ux, uy)
    radius = math.hypot(ax - ux, ay - uy)
    start_angle = math.degrees(math.atan2(-(p1.y() - uy), p1.x() - ux)) % 360
    mid_angle = math.degrees(math.atan2(-(p2.y() - uy), p2.x() - ux)) % 360
    end_angle = math.degrees(math.atan2(-(p3.y() - uy), p3.x() - ux)) % 360
    span = (end_angle - start_angle) % 360
    mid_rel = (mid_angle - start_angle) % 360
    if mid_rel > span:
        span -= 360
    return center, radius, start_angle, span


def _end_for_radius(p1: QPointF, p2: QPointF, cursor: QPointF, radius: float) -> QPointF | None:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    chord = math.hypot(dx, dy)
    if chord < 1e-6 or radius < chord / 2:
        return None
    mx = (p1.x() + p2.x()) / 2
    my = (p1.y() + p2.y()) / 2
    h = math.sqrt(max(0.0, radius * radius - (chord / 2) * (chord / 2)))
    ux = -dy / chord
    uy = dx / chord
    centers = [QPointF(mx + ux * h, my + uy * h), QPointF(mx - ux * h, my - uy * h)]
    center = min(centers, key=lambda c: math.hypot(cursor.x() - c.x(), cursor.y() - c.y()))
    angle = math.atan2(cursor.y() - center.y(), cursor.x() - center.x())
    return QPointF(center.x() + radius * math.cos(angle),
                   center.y() + radius * math.sin(angle))
