import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import CircleEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode


class CircleTool(BaseTool):
    """Click centre → click/drag radius point to commit."""

    name = "circle"

    def __init__(self):
        super().__init__()
        self._center: QPointF | None = None
        self._cursor: QPointF | None = None
        self._diameter_mode = False

    @property
    def is_idle(self) -> bool:
        return self._center is None

    @property
    def prompt(self) -> str:
        if self._center is None:
            return "CIRCLE  Specify center point:"
        if self._diameter_mode:
            return "CIRCLE  Specify diameter:"
        radius = 0.0
        if self._cursor is not None:
            radius = math.hypot(self._cursor.x() - self._center.x(),
                                self._cursor.y() - self._center.y()) / GRID_UNIT
        return f"CIRCLE  r={radius:.2f}  [R=radius  D=diam]"

    def snap_extras(self):
        if self._center is not None:
            return [(self._center, SnapMode.CENTER)]
        return []

    def activate(self, view):
        super().activate(view)
        self._center = None
        self._cursor = None
        self._diameter_mode = False

    def deactivate(self):
        self._center = None
        self._cursor = None
        self._diameter_mode = False
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

    def on_command(self, cmd: str) -> bool:
        coord = self._parse_coord(cmd)
        if coord is not None and self._center is None:
            self._center = coord
            if self.view:
                self.view.viewport().update()
            return True
        if self._center is None:
            return False
        text = cmd.strip()
        diameter_mode = self._diameter_mode
        if text.upper() == "D":
            self._diameter_mode = True
            if self.view:
                self.view.viewport().update()
            return True
        if text.upper().startswith("D"):
            diameter_mode = True
            text = text[1:].strip()
            if not text:
                self._diameter_mode = True
                if self.view:
                    self.view.viewport().update()
                return True
        try:
            value = float(text)
        except ValueError:
            return False
        if diameter_mode:
            value /= 2.0
        r = value * GRID_UNIT
        if r < 1:
            return True
        layer = self.view.layer_manager.current
        from ..entities import CircleEntity
        from ..undo import AddEntityCommand
        entity = CircleEntity(self._center, r, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._center = None
        self._cursor = None
        self._diameter_mode = False
        if self.view:
            self.view.viewport().update()
        return True

    def cancel(self):
        self._center = None
        self._cursor = None
        self._diameter_mode = False
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
        radius_units = radius_scene / GRID_UNIT
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawText(cursor_vp.x() + 8, cursor_vp.y() - 8, f'r={radius_units:.2f}')

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
        self._diameter_mode = False
        if self.view:
            self.view.viewport().update()
