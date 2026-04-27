import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import PolylineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode


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
        return "RECTANGLE  Pick corner [W,H=size]"

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

    def on_command(self, cmd: str) -> bool:
        coord = self._parse_coord(cmd)
        if coord is not None and self._corner is None:
            self._corner = coord
            if self.view:
                self.view.viewport().update()
            return True
        if self._corner is None:
            return False
        import re
        parts = re.split(r'[,\s]+', cmd.strip())
        try:
            if len(parts) >= 2:
                w = float(parts[0]) * GRID_UNIT
                h = float(parts[1]) * GRID_UNIT
            else:
                w = h = float(parts[0]) * GRID_UNIT
        except ValueError:
            return False
        if w < 1 or h < 1:
            return True
        cursor = self._cursor or QPointF(self._corner.x() + w, self._corner.y() + h)
        sx = 1 if cursor.x() >= self._corner.x() else -1
        sy = 1 if cursor.y() >= self._corner.y() else -1
        opp = QPointF(self._corner.x() + sx * w, self._corner.y() + sy * h)
        self._commit(opp)
        return True

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
        dx = abs(self._cursor.x() - self._corner.x()) / GRID_UNIT
        dy = abs(self._cursor.y() - self._corner.y()) / GRID_UNIT
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawText(c2.x() + 6, c2.y() - 6, f'{dx:.2f} × {dy:.2f}')

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
