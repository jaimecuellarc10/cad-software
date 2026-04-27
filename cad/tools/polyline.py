import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import PolylineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode


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


def _angle_pt(anchor: QPointF, angle: float, dist_units: float) -> QPointF:
    rad = math.radians(angle)
    dx = math.cos(rad)
    dy = -math.sin(rad)
    scene_dist = dist_units * GRID_UNIT
    return QPointF(anchor.x() + dx * scene_dist, anchor.y() + dy * scene_dist)


class PolylineTool(BaseTool):
    """
    Click to place vertices one by one.
    Right-click or Enter to commit the polyline.
    Escape cancels the whole thing.
    """

    name = "polyline"

    def __init__(self):
        super().__init__()
        self._verts: list[QPointF] = []
        self._cursor_pt: QPointF | None = None   # current snap position
        self._angle_locked = False
        self._locked_angle = 0.0

    @property
    def is_idle(self) -> bool:
        return len(self._verts) == 0

    def snap_extras(self):
        extras = []
        for i, v in enumerate(self._verts):
            extras.append((v, SnapMode.ENDPOINT))
            if i < len(self._verts) - 1:
                mid = QPointF((v.x() + self._verts[i+1].x()) / 2,
                              (v.y() + self._verts[i+1].y()) / 2)
                extras.append((mid, SnapMode.MIDPOINT))
        return extras

    @property
    def prompt(self) -> str:
        n = len(self._verts)
        if n == 0:
            return "PLINE  Specify start point:"
        if self._cursor_pt is not None:
            dx = self._cursor_pt.x() - self._verts[-1].x()
            dy = self._cursor_pt.y() - self._verts[-1].y()
            dist = math.hypot(dx, dy) / GRID_UNIT
            angle = math.degrees(math.atan2(-dy, dx)) % 360
            if self._angle_locked:
                return f"PLINE  {self._locked_angle:.1f}° 🔒  type dist or Tab to unlock"
            return f"PLINE  {dist:.2f}u  {angle:.1f}°  [type dist, A<deg> to lock angle, Tab to lock current]"
        if n == 1:
            return "PLINE  type dist, A<deg> to lock angle, Tab to lock current"
        return f"PLINE  Specify next point  [{n} pts]  [type dist, A<deg> to lock angle, Tab to lock current]"

    def activate(self, view):
        super().activate(view)
        self._verts.clear()
        self._cursor_pt = None
        self._angle_locked = False
        self._locked_angle = 0.0

    def deactivate(self):
        self._verts.clear()
        self._cursor_pt = None
        self._angle_locked = False
        self._locked_angle = 0.0
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pt = self._cursor_pt if self._angle_locked and self._cursor_pt is not None else snapped
            # Don't add duplicate point if double-click
            if self._verts and _same(pt, self._verts[-1]):
                self._finish()
                return
            self._verts.append(QPointF(pt))
            if self.view:
                self.view.viewport().update()

        elif event.button() == Qt.MouseButton.RightButton:
            self._finish()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._angle_locked and self._verts:
            anchor = self._verts[-1]
            rad = math.radians(self._locked_angle)
            dir_x = math.cos(rad)
            dir_y = -math.sin(rad)
            dx = raw.x() - anchor.x()
            dy = raw.y() - anchor.y()
            t = dx * dir_x + dy * dir_y
            self._cursor_pt = QPointF(anchor.x() + dir_x * t,
                                      anchor.y() + dir_y * t)
        else:
            self._cursor_pt = QPointF(snapped)
        if self.view:
            self.view._update_prompt()
            self.view.viewport().update()

    def on_key(self, event):
        key = event.key()
        if key == Qt.Key.Key_Tab:
            if self._angle_locked:
                self._angle_locked = False
            elif self._verts and self._cursor_pt is not None:
                dx = self._cursor_pt.x() - self._verts[-1].x()
                dy = self._cursor_pt.y() - self._verts[-1].y()
                self._locked_angle = math.degrees(math.atan2(-dy, dx)) % 360
                self._angle_locked = True
            if self.view:
                self.view.viewport().update()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish()
        elif key == Qt.Key.Key_C and len(self._verts) >= 2:
            self._finish(close=True)

    def on_command(self, cmd: str) -> bool:
        if not self._verts or self._cursor_pt is None:
            return False
        stripped = cmd.strip()
        if stripped.upper().startswith(("A", "@")):
            try:
                self._locked_angle = float(stripped[1:])
            except ValueError:
                return False
            self._angle_locked = True
            if self.view:
                self.view._update_prompt()
                self.view.viewport().update()
            return True
        try:
            dist = float(stripped)
        except ValueError:
            return False
        if self._angle_locked:
            end = _angle_pt(self._verts[-1], self._locked_angle, dist)
        else:
            end = _direction_pt(self._verts[-1], self._cursor_pt, dist)
        self._verts.append(end)
        if self.view:
            self.view.viewport().update()
        return True

    def finish(self):
        self._finish()

    def cancel(self):
        self._verts.clear()
        self._cursor_pt = None
        self._angle_locked = False
        self._locked_angle = 0.0
        if self.view:
            self.view.viewport().update()

    # ── Drawing overlay ───────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if not self._verts:
            return

        v = self.view
        COLOR = QColor("#ffffff")

        # Already-placed segments (solid)
        solid_pen = QPen(COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(solid_pen)
        for i in range(len(self._verts) - 1):
            p1 = v.mapFromScene(self._verts[i])
            p2 = v.mapFromScene(self._verts[i + 1])
            painter.drawLine(p1, p2)

        # Rubber-band to cursor (solid)
        if self._cursor_pt is not None:
            painter.setPen(QPen(COLOR, 1.5, Qt.PenStyle.SolidLine))
            p1 = v.mapFromScene(self._verts[-1])
            p2 = v.mapFromScene(self._cursor_pt)
            painter.drawLine(p1, p2)
            if self._angle_locked:
                rad = math.radians(self._locked_angle)
                dir_x = math.cos(rad)
                dir_y = -math.sin(rad)
                anchor = self._verts[-1]
                a = v.mapFromScene(QPointF(anchor.x() - dir_x * 45000,
                                           anchor.y() - dir_y * 45000))
                b = v.mapFromScene(QPointF(anchor.x() + dir_x * 45000,
                                           anchor.y() + dir_y * 45000))
                locked_pen = QPen(COLOR, 1, Qt.PenStyle.DashLine)
                locked_pen.setCosmetic(True)
                painter.setPen(locked_pen)
                painter.drawLine(a, b)
            dx = self._cursor_pt.x() - self._verts[-1].x()
            dy = self._cursor_pt.y() - self._verts[-1].y()
            dist_units = math.hypot(dx, dy) / GRID_UNIT
            angle = math.degrees(math.atan2(-dy, dx)) % 360
            mid = v.mapFromScene(QPointF((self._verts[-1].x() + self._cursor_pt.x()) / 2,
                                         (self._verts[-1].y() + self._cursor_pt.y()) / 2))
            painter.setPen(QPen(QColor('#ffffff'), 1))
            suffix = " 🔒" if self._angle_locked else ""
            painter.drawText(mid.x() + 6, mid.y() - 6, f'{dist_units:.2f}u  {angle:.1f}°{suffix}')

        # Small dot at each placed vertex
        dot_pen = QPen(COLOR, 4)
        dot_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dot_pen)
        for pt in self._verts:
            vp = v.mapFromScene(pt)
            painter.drawPoint(vp)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _finish(self, close: bool = False):
        verts = list(self._verts)
        if close and len(verts) >= 3:
            verts.append(QPointF(verts[0]))   # connect last to first

        self._verts.clear()
        self._cursor_pt = None
        self._angle_locked = False
        self._locked_angle = 0.0

        if len(verts) < 2:
            if self.view:
                self.view.viewport().update()
            return

        layer  = self.view.layer_manager.current
        entity = PolylineEntity(verts, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        if self.view:
            self.view.viewport().update()


def _same(a: QPointF, b: QPointF, tol: float = 0.001) -> bool:
    return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol
