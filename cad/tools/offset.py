import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity, CircleEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT

PREVIEW_COLOR = QColor("#ffffff")

STATE_DISTANCE = 0
STATE_PICK = 1
STATE_SIDE = 2


class OffsetTool(BaseTool):
    name = "offset"

    def __init__(self):
        super().__init__()
        self._dist: float = 0.0
        self._state = STATE_DISTANCE
        self._picked: object = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self):
        return self._state == STATE_DISTANCE

    @property
    def prompt(self):
        if self._state == STATE_DISTANCE:
            d = self._dist / GRID_UNIT if self._dist else 0
            return f"OFFSET  Specify offset distance ({d:.2f}):  [type + Enter]"
        if self._state == STATE_PICK:
            return "OFFSET  Select object to offset:"
        return "OFFSET  Specify side to offset toward:"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_DISTANCE
        self._picked = None
        self._cursor = None

    def deactivate(self):
        self._picked = None
        self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_DISTANCE:
            try:
                d = float(cmd)
                if d <= 0:
                    return True
                self._dist = d * GRID_UNIT
                self._state = STATE_PICK
                return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_PICK:
            self._pick_entity(snapped)
        elif self._state == STATE_SIDE:
            self._commit_offset(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._state = STATE_DISTANCE
        self._picked = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_SIDE or self._picked is None or self._cursor is None:
            return
        side = _which_side(self._picked, self._cursor)
        preview = _make_offset(self._picked, self._dist, side)
        if preview is None:
            return
        v = self.view
        scale = v.transform().m11()
        painter.setPen(QPen(PREVIEW_COLOR, 1.5, Qt.PenStyle.SolidLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if isinstance(preview, list):
            vps = [QPointF(v.mapFromScene(p)) for p in preview]
            for a, b in zip(vps, vps[1:]):
                painter.drawLine(a, b)
        elif isinstance(preview, tuple) and len(preview) == 2:
            painter.drawLine(v.mapFromScene(preview[0]), v.mapFromScene(preview[1]))
        elif isinstance(preview, tuple) and len(preview) == 3:
            c = QPointF(v.mapFromScene(preview[0]))
            r = preview[1] * scale
            painter.drawEllipse(c, r, r)

    def _pick_entity(self, pt: QPointF):
        threshold = 8.0 / self.view.transform().m11()
        for ent in self.view.cad_scene.all_entities():
            if ent.hit_test(pt, threshold):
                self._picked = ent
                self._state = STATE_SIDE
                if self.view:
                    self.view.viewport().update()
                return

    def _commit_offset(self, side_pt: QPointF):
        if self._picked is None:
            return
        side = _which_side(self._picked, side_pt)
        preview = _make_offset(self._picked, self._dist, side)
        if preview is None:
            self._state = STATE_PICK
            self._picked = None
            return
        layer = self.view.layer_manager.current
        ent = None
        if isinstance(preview, list):
            ent = PolylineEntity(preview, layer)
        elif isinstance(preview, tuple) and len(preview) == 2:
            ent = LineEntity(preview[0], preview[1], layer)
        elif isinstance(preview, tuple) and len(preview) == 3:
            ent = CircleEntity(preview[0], preview[1], layer)
        if ent is not None:
            self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self._state = STATE_PICK
        self._picked = None
        if self.view:
            self.view.viewport().update()


def _which_side(ent, cursor: QPointF) -> float:
    if isinstance(ent, LineEntity):
        dx = ent.p2.x()-ent.p1.x()
        dy = ent.p2.y()-ent.p1.y()
        cx = cursor.x()-ent.p1.x()
        cy = cursor.y()-ent.p1.y()
        cross = dx*cy - dy*cx
        return 1.0 if cross >= 0 else -1.0
    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        if len(verts) >= 2:
            dx = verts[1].x()-verts[0].x()
            dy = verts[1].y()-verts[0].y()
            cx = cursor.x()-verts[0].x()
            cy = cursor.y()-verts[0].y()
            cross = dx*cy - dy*cx
            return 1.0 if cross >= 0 else -1.0
    if isinstance(ent, CircleEntity):
        dist = math.hypot(cursor.x()-ent.center.x(), cursor.y()-ent.center.y())
        return 1.0 if dist > ent.radius else -1.0
    return 1.0


def _offset_pt(pt: QPointF, nx: float, ny: float, dist: float, side: float) -> QPointF:
    return QPointF(pt.x() + nx*dist*side, pt.y() + ny*dist*side)


def _seg_normal(a: QPointF, b: QPointF):
    dx = b.x()-a.x()
    dy = b.y()-a.y()
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 1.0
    return -dy/length, dx/length


def _make_offset(ent, dist: float, side: float):
    if isinstance(ent, LineEntity):
        nx, ny = _seg_normal(ent.p1, ent.p2)
        p1 = _offset_pt(ent.p1, nx, ny, dist, side)
        p2 = _offset_pt(ent.p2, nx, ny, dist, side)
        return p1, p2
    if isinstance(ent, CircleEntity):
        r = ent.radius + dist*side
        if r <= 0:
            return None
        return QPointF(ent.center), r, 0
    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        if len(verts) < 2:
            return None
        offset_segs = []
        for i in range(len(verts)-1):
            nx, ny = _seg_normal(verts[i], verts[i+1])
            a = _offset_pt(verts[i], nx, ny, dist, side)
            b = _offset_pt(verts[i+1], nx, ny, dist, side)
            offset_segs.append((a, b))
        if not offset_segs:
            return None
        result = [offset_segs[0][0]]
        for i in range(len(offset_segs)-1):
            a1, b1 = offset_segs[i]
            a2, b2 = offset_segs[i+1]
            pt = _line_line_isect(a1, b1, a2, b2)
            result.append(pt if pt else b1)
        result.append(offset_segs[-1][1])
        return result
    return None


def _line_line_isect(a: QPointF, b: QPointF, c: QPointF, d: QPointF) -> QPointF | None:
    dx1 = b.x()-a.x()
    dy1 = b.y()-a.y()
    dx2 = d.x()-c.x()
    dy2 = d.y()-c.y()
    denom = dx1*dy2 - dy1*dx2
    if abs(denom) < 1e-10:
        return None
    t = ((c.x()-a.x())*dy2 - (c.y()-a.y())*dx2) / denom
    return QPointF(a.x()+t*dx1, a.y()+t*dy1)
