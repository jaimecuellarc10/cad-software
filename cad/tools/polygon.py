import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import PolylineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT, SnapMode

PREVIEW_COLOR = QColor("#ffffff")
STATE_SIDES  = 0
STATE_CENTER = 1
STATE_RADIUS = 2


class PolygonTool(BaseTool):
    name = "polygon"

    def __init__(self):
        super().__init__()
        self._sides  = 6
        self._center: QPointF | None = None
        self._cursor: QPointF | None = None
        self._inscribed = True
        self._state = STATE_SIDES

    @property
    def is_idle(self): return self._state == STATE_SIDES

    @property
    def prompt(self):
        mode = "Inscribed" if self._inscribed else "Circumscribed"
        if self._state == STATE_SIDES:
            return f"POLYGON  Number of sides ({self._sides}):  [type + Enter]"
        if self._state == STATE_CENTER:
            return f"POLYGON  {self._sides} sides  Specify center:"
        r = (math.hypot(self._cursor.x()-self._center.x(),
                        self._cursor.y()-self._center.y()) / GRID_UNIT
             if self._cursor and self._center else 0)
        return f"POLYGON  {mode}  r={r:.2f}  [I=Inscribed  C=Circumscribed  type radius + Enter]"

    def snap_extras(self):
        if self._center: return [(self._center, SnapMode.CENTER)]
        return []

    def activate(self, view):
        super().activate(view)
        self._center = self._cursor = None
        self._state = STATE_SIDES

    def deactivate(self):
        self._center = self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_SIDES:
            try:
                n = int(cmd)
                if n >= 3:
                    self._sides = n
                    self._state = STATE_CENTER
                return True
            except ValueError:
                return False
        if self._state == STATE_RADIUS:
            up = cmd.strip().upper()
            if up in ("I", "INS", "INSCRIBED"):
                self._inscribed = True; return True
            if up in ("C", "CIR", "CIRCUMSCRIBED"):
                self._inscribed = False; return True
            try:
                r = float(cmd) * GRID_UNIT
                if r > 1: self._commit(r)
                return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self._state == STATE_CENTER:
            self._center = QPointF(snapped); self._state = STATE_RADIUS
        elif self._state == STATE_RADIUS and self._center:
            r = math.hypot(snapped.x()-self._center.x(), snapped.y()-self._center.y())
            if r > 1: self._commit(r)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._center = self._cursor = None; self._state = STATE_CENTER
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_RADIUS or self._center is None or self._cursor is None:
            return
        r = math.hypot(self._cursor.x()-self._center.x(),
                       self._cursor.y()-self._center.y())
        if r < 1: return
        verts = _polygon_verts(self._center, r, self._sides, self._inscribed,
                               start_angle=math.degrees(math.atan2(
                                   -(self._cursor.y()-self._center.y()),
                                   self._cursor.x()-self._center.x())))
        v = self.view
        pts = [v.mapFromScene(p) for p in verts]
        painter.setPen(QPen(PREVIEW_COLOR, 1.5, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(len(pts)):
            painter.drawLine(pts[i], pts[(i+1) % len(pts)])
        cp = v.mapFromScene(self._cursor)
        painter.setPen(QPen(PREVIEW_COLOR, 1))
        painter.drawText(cp.x()+8, cp.y()-8, f"{self._sides}-gon  r={r/GRID_UNIT:.2f}")

    def _commit(self, r: float):
        start = math.degrees(math.atan2(
            -(self._cursor.y()-self._center.y()),
            self._cursor.x()-self._center.x())) if self._cursor else 90.0
        verts = _polygon_verts(self._center, r, self._sides, self._inscribed, start)
        verts.append(QPointF(verts[0]))
        layer = self.view.layer_manager.current
        entity = PolylineEntity(verts, layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, entity))
        self._center = self._cursor = None; self._state = STATE_CENTER
        if self.view: self.view.viewport().update()


def _polygon_verts(center: QPointF, r: float, n: int,
                   inscribed: bool, start_angle: float = 90.0) -> list[QPointF]:
    actual_r = r if inscribed else r / math.cos(math.pi / n)
    verts = []
    for i in range(n):
        angle = math.radians(start_angle + 360.0 * i / n)
        verts.append(QPointF(center.x() + actual_r * math.cos(angle),
                             center.y() - actual_r * math.sin(angle)))
    return verts
