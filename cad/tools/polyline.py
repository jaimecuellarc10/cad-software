import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import PolylineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode


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


class PolylineTool(BaseTool):
    """
    Click to place vertices one by one.
    Right-click or Enter to commit the polyline.
    Escape cancels the whole thing.
    """

    name = "polyline"

    def __init__(self):
        super().__init__()
        self._verts: list[QPointF] = []
        self._cursor_pt: QPointF | None = None   # current snap position

    @property
    def is_idle(self) -> bool:
        return len(self._verts) == 0

    def snap_extras(self):
        extras = []
        for i, v in enumerate(self._verts):
            extras.append((v, SnapMode.ENDPOINT))
            if i < len(self._verts) - 1:
                mid = QPointF((v.x() + self._verts[i+1].x()) / 2,
                              (v.y() + self._verts[i+1].y()) / 2)
                extras.append((mid, SnapMode.MIDPOINT))
        return extras

    @property
    def prompt(self) -> str:
        n = len(self._verts)
        if n == 0:
            return "PLINE  Specify start point:"
        if n == 1:
            return "PLINE  Specify next point  [type distance + Enter]  [Enter/Space = done  Esc = cancel]"
        return f"PLINE  Specify next point  [{n} pts]  [type distance + Enter]  [C = Close  Enter/Space = done]"

    def activate(self, view):
        super().activate(view)
        self._verts.clear()
        self._cursor_pt = None

    def deactivate(self):
        self._verts.clear()
        self._cursor_pt = None
        super().deactivate()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Don't add duplicate point if double-click
            if self._verts and _same(snapped, self._verts[-1]):
                self._finish()
                return
            self._verts.append(QPointF(snapped))
            if self.view:
                self.view.viewport().update()

        elif event.button() == Qt.MouseButton.RightButton:
            self._finish()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor_pt = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_key(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._finish()
        elif key == Qt.Key.Key_C and len(self._verts) >= 2:
            self._finish(close=True)

    def on_command(self, cmd: str) -> bool:
        if not self._verts or self._cursor_pt is None:
            return False
        try:
            dist = float(cmd)
        except ValueError:
            return False
        end = _direction_pt(self._verts[-1], self._cursor_pt, dist)
        self._verts.append(end)
        if self.view:
            self.view.viewport().update()
        return True

    def finish(self):
        self._finish()

    def cancel(self):
        self._verts.clear()
        self._cursor_pt = None
        if self.view:
            self.view.viewport().update()

    # ── Drawing overlay ───────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if not self._verts:
            return

        v = self.view
        COLOR = QColor("#ffffff")

        # Already-placed segments (solid)
        solid_pen = QPen(COLOR, 1.5, Qt.PenStyle.SolidLine)
        painter.setPen(solid_pen)
        for i in range(len(self._verts) - 1):
            p1 = v.mapFromScene(self._verts[i])
            p2 = v.mapFromScene(self._verts[i + 1])
            painter.drawLine(p1, p2)

        # Rubber-band to cursor (solid)
        if self._cursor_pt is not None:
            painter.setPen(QPen(COLOR, 1.5, Qt.PenStyle.SolidLine))
            p1 = v.mapFromScene(self._verts[-1])
            p2 = v.mapFromScene(self._cursor_pt)
            painter.drawLine(p1, p2)
            dx = self._cursor_pt.x() - self._verts[-1].x()
            dy = self._cursor_pt.y() - self._verts[-1].y()
            dist_units = math.hypot(dx, dy) / GRID_UNIT
            mid = v.mapFromScene(QPointF((self._verts[-1].x() + self._cursor_pt.x()) / 2,
                                         (self._verts[-1].y() + self._cursor_pt.y()) / 2))
            painter.setPen(QPen(QColor('#ffffff'), 1))
            painter.drawText(mid.x() + 6, mid.y() - 6, f'{dist_units:.2f}')

        # Small dot at each placed vertex
        dot_pen = QPen(COLOR, 4)
        dot_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(dot_pen)
        for pt in self._verts:
            vp = v.mapFromScene(pt)
            painter.drawPoint(vp)

    # ── Internals ─────────────────────────────────────────────────────────────

    def _finish(self, close: bool = False):
        verts = list(self._verts)
        if close and len(verts) >= 3:
            verts.append(QPointF(verts[0]))   # connect last to first

        self._verts.clear()
        self._cursor_pt = None

        if len(verts) < 2:
            if self.view:
                self.view.viewport().update()
            return

        layer  = self.view.layer_manager.current
        entity = PolylineEntity(verts, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        if self.view:
            self.view.viewport().update()


def _same(a: QPointF, b: QPointF, tol: float = 0.001) -> bool:
    return abs(a.x() - b.x()) < tol and abs(a.y() - b.y()) < tol
