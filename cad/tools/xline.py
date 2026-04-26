import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import XLineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode

PREVIEW_COLOR = QColor("#ffffff")
STATE_POINT = 0
STATE_DIR   = 1


class XLineTool(BaseTool):
    name = "xline"

    def __init__(self):
        super().__init__()
        self._point:  QPointF | None = None
        self._cursor: QPointF | None = None
        self._state = STATE_POINT

    @property
    def is_idle(self): return self._state == STATE_POINT

    @property
    def prompt(self):
        if self._state == STATE_POINT:
            return "XLINE  Specify point on construction line:  [H=horizontal  V=vertical]"
        ang = self._current_angle()
        return f"XLINE  Specify direction  [{ang:.1f}°]  [type angle + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._point = self._cursor = None; self._state = STATE_POINT

    def deactivate(self):
        self._point = self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_POINT:
            up = cmd.strip().upper()
            if up == "H":
                self._pending_angle = 0.0; return True
            if up == "V":
                self._pending_angle = 90.0; return True
        if self._state == STATE_DIR:
            try:
                angle = float(cmd)
                self._commit(angle)
                return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self._state == STATE_POINT:
            self._point = QPointF(snapped)
            self._state = STATE_DIR
            if hasattr(self, '_pending_angle'):
                self._commit(self._pending_angle)
                del self._pending_angle
        elif self._state == STATE_DIR:
            self._commit(self._current_angle())
            self._state = STATE_POINT; self._point = None

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._point = self._cursor = None; self._state = STATE_POINT
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_DIR or self._point is None or self._cursor is None:
            return
        v = self.view
        ang = self._current_angle()
        rad = math.radians(ang)
        HALF = 45000.0
        dx = math.cos(rad) * HALF; dy = math.sin(rad) * HALF
        p1 = v.mapFromScene(QPointF(self._point.x()-dx, self._point.y()+dy))
        p2 = v.mapFromScene(QPointF(self._point.x()+dx, self._point.y()-dy))
        painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashDotLine))
        painter.drawLine(p1, p2)
        cp = v.mapFromScene(self._cursor)
        painter.setPen(QPen(PREVIEW_COLOR, 1))
        painter.drawText(cp.x()+8, cp.y()-8, f"{ang:.1f}°")

    def _current_angle(self) -> float:
        if self._point is None or self._cursor is None: return 0.0
        return math.degrees(math.atan2(-(self._cursor.y()-self._point.y()),
                                        self._cursor.x()-self._point.x())) % 180

    def _commit(self, angle_deg: float):
        if self._point is None: return
        layer = self.view.layer_manager.current
        entity = XLineEntity(self._point, angle_deg % 180, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._state = STATE_POINT; self._point = None
        if self.view: self.view.viewport().update()
