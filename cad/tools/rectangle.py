from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import PolylineEntity
from ..undo import AddEntityCommand
from ..constants import SnapMode


class RectangleTool(BaseTool):
    """Click two opposite corners to create a closed rectangular polyline."""

    name = "rectangle"

    def __init__(self):
        super().__init__()
        self._corner: QPointF | None = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return self._corner is None

    @property
    def prompt(self) -> str:
        if self._corner is None:
            return "RECTANGLE  Specify first corner:"
        return "RECTANGLE  Specify opposite corner  [Esc = cancel]"

    def snap_extras(self):
        if self._corner is not None:
            return [(self._corner, SnapMode.ENDPOINT)]
        return []

    def activate(self, view):
        super().activate(view)
        self._corner = None
        self._cursor = None

    def deactivate(self):
        self._corner = None
        self._cursor = None
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._corner is None:
            self._corner = QPointF(snapped)
        else:
            self._commit(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cancel()

    def cancel(self):
        self._corner = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def finish(self):
        self.cancel()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._corner is None or self._cursor is None:
            return
        v  = self.view
        c1 = v.mapFromScene(self._corner)
        c2 = v.mapFromScene(self._cursor)

        painter.setPen(QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        from PySide6.QtCore import QRect
        painter.drawRect(QRect(
            min(c1.x(), c2.x()), min(c1.y(), c2.y()),
            abs(c2.x()-c1.x()), abs(c2.y()-c1.y())
        ))

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, opp: QPointF):
        x1, y1 = self._corner.x(), self._corner.y()
        x2, y2 = opp.x(), opp.y()
        if abs(x2-x1) < 1 or abs(y2-y1) < 1:
            self.cancel()
            return
        verts = [
            QPointF(x1, y1), QPointF(x2, y1),
            QPointF(x2, y2), QPointF(x1, y2),
            QPointF(x1, y1),   # closed
        ]
        layer  = self.view.layer_manager.current
        entity = PolylineEntity(verts, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._corner = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()
