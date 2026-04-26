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


class LineTool(BaseTool):
    name = "line"

    def __init__(self):
        super().__init__()
        self._start: QPointF | None = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return self._start is None

    @property
    def prompt(self) -> str:
        if self._start is None:
            return "LINE  Specify first point:"
        return "LINE  Specify next point  [type distance + Enter]  [Enter/Space = done]"

    def snap_extras(self):
        if self._start is not None:
            return [(self._start, SnapMode.ENDPOINT)]
        return []

    def activate(self, view):
        super().activate(view)
        self._start = None
        self._cursor = None

    def deactivate(self):
        self._start = None
        self._cursor = None
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
            self._commit(snapped)
            self._start = QPointF(snapped)   # chain

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cancel()

    def on_command(self, cmd: str) -> bool:
        if self._start is None or self._cursor is None:
            return False
        try:
            dist = float(cmd)
        except ValueError:
            return False
        end = _direction_pt(self._start, self._cursor, dist)
        self._commit(end)
        self._start = QPointF(end)
        return True

    def cancel(self):
        self._start = None
        self._cursor = None
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
        dx = self._cursor.x() - self._start.x()
        dy = self._cursor.y() - self._start.y()
        dist_units = math.hypot(dx, dy) / GRID_UNIT
        mid = v.mapFromScene(QPointF((self._start.x() + self._cursor.x()) / 2,
                                     (self._start.y() + self._cursor.y()) / 2))
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawText(mid.x() + 6, mid.y() - 6, f'{dist_units:.2f}')

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, end: QPointF):
        layer  = self.view.layer_manager.current
        entity = LineEntity(self._start, end, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        if self.view:
            self.view.viewport().update()
