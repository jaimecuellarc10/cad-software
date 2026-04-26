import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import DimLinearEntity, DimAngularEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT

PREVIEW_COLOR = QColor("#ffffff")

STATE_P1 = 0
STATE_P2 = 1
STATE_OFFSET = 2

STATE_CENTER = 0
STATE_AP1 = 1
STATE_AP2 = 2


class DimLinearTool(BaseTool):
    name = "dimlinear"

    def __init__(self):
        super().__init__()
        self._state = STATE_P1
        self._p1: QPointF | None = None
        self._p2: QPointF | None = None
        self._cursor: QPointF | None = None
        self._offset = 0.0

    @property
    def is_idle(self):
        return self._state == STATE_P1

    @property
    def prompt(self):
        if self._state == STATE_P1:
            return "DIMLINEAR  Specify first extension line origin:"
        if self._state == STATE_P2:
            return "DIMLINEAR  Specify second extension line origin:"
        return f"DIMLINEAR  Offset {self._offset/GRID_UNIT:.3f}  [type offset + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_P1:
            self._p1 = QPointF(snapped)
            self._state = STATE_P2
        elif self._state == STATE_P2:
            self._p2 = QPointF(snapped)
            self._state = STATE_OFFSET
        elif self._state == STATE_OFFSET:
            self._commit()
        if self.view:
            self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self._state == STATE_OFFSET and self._p1 and self._p2:
            self._offset = _signed_offset(self._p1, self._p2, snapped)
        if self.view:
            self.view.viewport().update()

    def on_command(self, cmd: str) -> bool:
        if self._state != STATE_OFFSET:
            return False
        try:
            self._offset = float(cmd) * GRID_UNIT
        except ValueError:
            return False
        self._commit()
        return True

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_OFFSET or self._p1 is None or self._p2 is None:
            return
        ent = DimLinearEntity(self._p1, self._p2, self._offset,
                              layer=self.view.layer_manager.current)
        painter.save()
        painter.setPen(QPen(PREVIEW_COLOR, 0))
        ent.paint(painter, None)
        painter.restore()

    def cancel(self):
        self._state = STATE_P1
        self._p1 = None
        self._p2 = None
        self._cursor = None
        self._offset = 0.0
        if self.view:
            self.view.viewport().update()

    def _commit(self):
        if self._p1 is None or self._p2 is None:
            return
        ent = DimLinearEntity(self._p1, self._p2, self._offset,
                              layer=self.view.layer_manager.current)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self.cancel()


class DimAngularTool(BaseTool):
    name = "dimangular"

    def __init__(self):
        super().__init__()
        self._state = STATE_CENTER
        self._center: QPointF | None = None
        self._p1: QPointF | None = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self):
        return self._state == STATE_CENTER

    @property
    def prompt(self):
        if self._state == STATE_CENTER:
            return "DIMANGULAR  Specify angle vertex:"
        if self._state == STATE_AP1:
            return "DIMANGULAR  Specify first angle endpoint:"
        return "DIMANGULAR  Specify second angle endpoint:"

    def activate(self, view):
        super().activate(view)
        self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_CENTER:
            self._center = QPointF(snapped)
            self._state = STATE_AP1
        elif self._state == STATE_AP1:
            self._p1 = QPointF(snapped)
            self._state = STATE_AP2
        elif self._state == STATE_AP2:
            self._commit(snapped)
        if self.view:
            self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_AP2 or self._center is None or self._p1 is None or self._cursor is None:
            return
        r = math.hypot(self._cursor.x()-self._center.x(), self._cursor.y()-self._center.y())
        if r < 1:
            return
        ent = DimAngularEntity(self._center, self._p1, self._cursor, r,
                               layer=self.view.layer_manager.current)
        painter.save()
        painter.setPen(QPen(PREVIEW_COLOR, 0))
        ent.paint(painter, None)
        painter.restore()

    def cancel(self):
        self._state = STATE_CENTER
        self._center = None
        self._p1 = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def _commit(self, p2: QPointF):
        if self._center is None or self._p1 is None:
            return
        r = math.hypot(p2.x()-self._center.x(), p2.y()-self._center.y())
        ent = DimAngularEntity(self._center, self._p1, p2, r,
                               layer=self.view.layer_manager.current)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self.cancel()


def _signed_offset(p1: QPointF, p2: QPointF, pt: QPointF) -> float:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0
    nx = -dy / length
    ny = dx / length
    return (pt.x() - p1.x()) * nx + (pt.y() - p1.y()) * ny
