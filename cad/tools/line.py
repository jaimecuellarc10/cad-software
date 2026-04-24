from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import LineEntity
from ..undo import AddEntityCommand
from ..constants import SnapMode

PREVIEW_COLOR = QColor("#ffffff")


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
        return "LINE  Specify next point  [Enter/Space = done  Esc = cancel]"

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

    def cancel(self):
        self._start = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

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

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, end: QPointF):
        layer  = self.view.layer_manager.current
        entity = LineEntity(self._start, end, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        if self.view:
            self.view.viewport().update()
