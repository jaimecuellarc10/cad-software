import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import CircleEntity
from ..undo import AddEntityCommand
from ..constants import SnapMode


class CircleTool(BaseTool):
    """Click centre → click/drag radius point to commit."""

    name = "circle"

    def __init__(self):
        super().__init__()
        self._center: QPointF | None = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return self._center is None

    @property
    def prompt(self) -> str:
        if self._center is None:
            return "CIRCLE  Specify center point:"
        return "CIRCLE  Specify radius point  [Esc = cancel]"

    def snap_extras(self):
        if self._center is not None:
            return [(self._center, SnapMode.CENTER)]
        return []

    def activate(self, view):
        super().activate(view)
        self._center = None
        self._cursor = None

    def deactivate(self):
        self._center = None
        self._cursor = None
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._center is None:
            self._center = QPointF(snapped)
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
        self._center = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def finish(self):
        self.cancel()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._center is None or self._cursor is None:
            return
        radius_scene = math.hypot(self._cursor.x() - self._center.x(),
                                  self._cursor.y() - self._center.y())
        if radius_scene < 0.5:
            return

        v           = self.view
        scale       = v.transform().m11()
        center_vp   = v.mapFromScene(self._center)
        radius_vp   = radius_scene * scale
        COLOR       = QColor("#ffffff")

        # Circle outline — solid
        pen = QPen(COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(center_vp), radius_vp, radius_vp)

        # Centre crosshair — solid
        s = 5
        painter.setPen(QPen(COLOR, 1))
        painter.drawLine(center_vp.x()-s, center_vp.y(), center_vp.x()+s, center_vp.y())
        painter.drawLine(center_vp.x(), center_vp.y()-s, center_vp.x(), center_vp.y()+s)

        # Radius line — dashed (projection helper)
        cursor_vp = v.mapFromScene(self._cursor)
        painter.setPen(QPen(COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(center_vp, cursor_vp)

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, radius_pt: QPointF):
        radius = math.hypot(radius_pt.x() - self._center.x(),
                            radius_pt.y() - self._center.y())
        if radius < 1:
            self.cancel()
            return
        layer  = self.view.layer_manager.current
        entity = CircleEntity(self._center, radius, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._center = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()
