import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import LineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode

PREVIEW_COLOR = QColor("#ffffff")


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


class LineTool(BaseTool):
    name = "line"

    def __init__(self):
        super().__init__()
        self._start: QPointF | None = None
        self._cursor: QPointF | None = None
        self._angle_locked = False
        self._locked_angle = 0.0

    @property
    def is_idle(self) -> bool:
        return self._start is None

    @property
    def prompt(self) -> str:
        if self._start is None:
            return "LINE  Specify first point:"
        if self._cursor is not None:
            dx = self._cursor.x() - self._start.x()
            dy = self._cursor.y() - self._start.y()
            dist = math.hypot(dx, dy) / GRID_UNIT
            angle = math.degrees(math.atan2(-dy, dx)) % 360
            if self._angle_locked:
                return f"LINE  {self._locked_angle:.1f}° 🔒  type dist or Tab to unlock"
            return f"LINE  {dist:.2f}u  {angle:.1f}°  [type dist, A<deg> to lock angle, Tab to lock current]"
        return "LINE  type dist, A<deg> to lock angle, Tab to lock current"

    def snap_extras(self):
        if self._start is not None:
            return [(self._start, SnapMode.ENDPOINT)]
        return []

    def activate(self, view):
        super().activate(view)
        self._start = None
        self._cursor = None
        self._angle_locked = False
        self._locked_angle = 0.0

    def deactivate(self):
        self._start = None
        self._cursor = None
        self._angle_locked = False
        self._locked_angle = 0.0
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.RightButton:
            if self._start is not None:
                self.finish()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._start is None:
            self._start = QPointF(snapped)
        else:
            end = self._cursor if self._angle_locked and self._cursor is not None else snapped
            self._commit(end)
            self._start = QPointF(end)   # chain

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._angle_locked and self._start is not None:
            rad = math.radians(self._locked_angle)
            dir_x = math.cos(rad)
            dir_y = -math.sin(rad)
            dx = raw.x() - self._start.x()
            dy = raw.y() - self._start.y()
            t = dx * dir_x + dy * dir_y
            self._cursor = QPointF(self._start.x() + dir_x * t,
                                   self._start.y() + dir_y * t)
        else:
            self._cursor = QPointF(snapped)
        if self.view:
            self.view._update_prompt()
            self.view.viewport().update()

    def on_key(self, event):
        if event.key() == Qt.Key.Key_Tab:
            if self._angle_locked:
                self._angle_locked = False
            elif self._start is not None and self._cursor is not None:
                dx = self._cursor.x() - self._start.x()
                dy = self._cursor.y() - self._start.y()
                self._locked_angle = math.degrees(math.atan2(-dy, dx)) % 360
                self._angle_locked = True
            if self.view:
                self.view.viewport().update()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cancel()

    def on_command(self, cmd: str) -> bool:
        if self._start is None or self._cursor is None:
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
            end = _angle_pt(self._start, self._locked_angle, dist)
        else:
            end = _direction_pt(self._start, self._cursor, dist)
        self._commit(end)
        self._start = QPointF(end)
        return True

    def cancel(self):
        self._start = None
        self._cursor = None
        self._angle_locked = False
        self._locked_angle = 0.0
        if self.view:
            self.view.viewport().update()

    def finish(self):
        self.cancel()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._start is None or self._cursor is None:
            return
        v  = self.view
        p1 = v.mapFromScene(self._start)
        p2 = v.mapFromScene(self._cursor)
        pen = QPen(PREVIEW_COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        if self._angle_locked:
            rad = math.radians(self._locked_angle)
            dir_x = math.cos(rad)
            dir_y = -math.sin(rad)
            a = v.mapFromScene(QPointF(self._start.x() - dir_x * 45000,
                                       self._start.y() - dir_y * 45000))
            b = v.mapFromScene(QPointF(self._start.x() + dir_x * 45000,
                                       self._start.y() + dir_y * 45000))
            locked_pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
            locked_pen.setCosmetic(True)
            painter.setPen(locked_pen)
            painter.drawLine(a, b)
        dx = self._cursor.x() - self._start.x()
        dy = self._cursor.y() - self._start.y()
        dist_units = math.hypot(dx, dy) / GRID_UNIT
        angle = math.degrees(math.atan2(-dy, dx)) % 360
        mid = v.mapFromScene(QPointF((self._start.x() + self._cursor.x()) / 2,
                                     (self._start.y() + self._cursor.y()) / 2))
        painter.setPen(QPen(QColor('#ffffff'), 1))
        suffix = " 🔒" if self._angle_locked else ""
        painter.drawText(mid.x() + 6, mid.y() - 6, f'{dist_units:.2f}u  {angle:.1f}°{suffix}')

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, end: QPointF):
        layer  = self.view.layer_manager.current
        entity = LineEntity(self._start, end, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        if self.view:
            self.view.viewport().update()
