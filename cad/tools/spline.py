from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import SplineEntity, _catmull_rom_points
from ..undo import AddEntityCommand
from ..constants import SnapMode

PREVIEW_COLOR = QColor("#ffffff")


class SplineTool(BaseTool):
    name = "spline"

    def __init__(self):
        super().__init__()
        self._points: list[QPointF] = []
        self._cursor: QPointF | None = None

    @property
    def is_idle(self):
        return len(self._points) == 0

    @property
    def prompt(self):
        return f"SPLINE  Specify control point ({len(self._points)})  [C = close, Enter/Space = done]"

    def activate(self, view):
        super().activate(view)
        self._points = []
        self._cursor = None

    def deactivate(self):
        self._points = []
        self._cursor = None
        super().deactivate()

    def snap_extras(self):
        return [(p, SnapMode.ENDPOINT) for p in self._points]

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._points.append(QPointF(snapped))
        elif event.button() == Qt.MouseButton.RightButton:
            self._finish()
        if self.view:
            self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_key(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._finish()
        elif key == Qt.Key.Key_C:
            self._finish(close=True)

    def on_command(self, cmd: str) -> bool:
        if cmd.strip().upper() == "C":
            self._finish(close=True)
            return True
        return False

    def finish(self):
        self._finish()

    def cancel(self):
        self._points = []
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        pts = list(self._points)
        if self._cursor is not None:
            pts.append(QPointF(self._cursor))
        if not pts:
            return
        v = self.view
        painter.setPen(QPen(PREVIEW_COLOR, 1.5))
        curve = _catmull_rom_points(pts, False)
        for a, b in zip(curve, curve[1:]):
            painter.drawLine(v.mapFromScene(a), v.mapFromScene(b))
        if self._points and self._cursor is not None:
            painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
            painter.drawLine(v.mapFromScene(self._points[-1]), v.mapFromScene(self._cursor))
        painter.setPen(QPen(PREVIEW_COLOR, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for p in self._points:
            painter.drawPoint(v.mapFromScene(p))

    def _finish(self, close: bool = False):
        pts = list(self._points)
        self._points = []
        self._cursor = None
        if len(pts) >= 2:
            ent = SplineEntity(pts, close, self.view.layer_manager.current)
            self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        if self.view:
            self.view.viewport().update()
