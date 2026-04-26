import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import StretchCommand
from ..constants import GRID_UNIT
from ._ghost import GHOST_PEN

PREVIEW_COLOR = QColor("#ffffff")
CRS_FILL   = QColor(0,200,0,35);    CRS_BORDER = QColor(0,200,0,220)
DRAG_THRESHOLD = 6

STATE_WINDOW = 0
STATE_BASE   = 1
STATE_DEST   = 2


class StretchTool(BaseTool):
    name = "stretch"

    def __init__(self):
        super().__init__()
        self._state = STATE_WINDOW
        self._window: QRectF | None = None
        self._base:   QPointF | None = None
        self._cursor: QPointF | None = None
        self._press_vp: QPoint | None = None
        self._cur_vp:   QPoint | None = None
        self._dragging  = False

    @property
    def is_idle(self): return self._state == STATE_WINDOW

    @property
    def prompt(self):
        if self._state == STATE_WINDOW:
            return "STRETCH  Drag a crossing window (right-to-left) over vertices to stretch:"
        if self._state == STATE_BASE:
            return "STRETCH  Specify base point:"
        dx = dy = dist = 0.0
        if self._base and self._cursor:
            dx = (self._cursor.x()-self._base.x())/GRID_UNIT
            dy = -(self._cursor.y()-self._base.y())/GRID_UNIT
            dist = math.hypot(dx, dy)
        return f"STRETCH  Specify destination  Δ={dist:.2f}  [type distance + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_WINDOW; self._window = None
        self._base = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False

    def deactivate(self):
        self._window = self._base = self._cursor = None
        self._press_vp = self._cur_vp = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_DEST and self._base and self._cursor:
            try:
                dist = float(cmd) * GRID_UNIT
                dx_raw = self._cursor.x()-self._base.x()
                dy_raw = self._cursor.y()-self._base.y()
                length = math.hypot(dx_raw, dy_raw)
                if length < 1e-6: dx_raw, dy_raw = dist, 0.0
                else: dx_raw = dx_raw/length*dist; dy_raw = dy_raw/length*dist
                self._apply(dx_raw, dy_raw); return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self._state == STATE_WINDOW:
            self._press_vp = event.position().toPoint()
            self._cur_vp = self._press_vp; self._dragging = False
        elif self._state == STATE_BASE:
            self._base = QPointF(snapped); self._state = STATE_DEST
        elif self._state == STATE_DEST and self._base:
            self._apply(snapped.x()-self._base.x(), snapped.y()-self._base.y())

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self._state == STATE_WINDOW and self._press_vp is not None:
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x()-self._press_vp.x())
            dy = abs(self._cur_vp.y()-self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        if self.view: self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton or self._state != STATE_WINDOW:
            return
        if self._dragging and self._press_vp and self._cur_vp:
            s = self.view.mapToScene(self._press_vp)
            e = self.view.mapToScene(self._cur_vp)
            self._window = QRectF(s, e).normalized()
            self._state = STATE_BASE
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._state = STATE_WINDOW; self._window = self._base = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state == STATE_WINDOW and self._dragging and self._press_vp and self._cur_vp:
            painter.setPen(QPen(CRS_BORDER, 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(CRS_FILL))
            painter.drawRect(QRect(min(self._press_vp.x(), self._cur_vp.x()),
                                   min(self._press_vp.y(), self._cur_vp.y()),
                                   abs(self._cur_vp.x()-self._press_vp.x()),
                                   abs(self._cur_vp.y()-self._press_vp.y())))
        if self._state == STATE_DEST and self._base and self._cursor:
            v = self.view
            bp = v.mapFromScene(self._base); cp = v.mapFromScene(self._cursor)
            dx = self._cursor.x()-self._base.x(); dy = self._cursor.y()-self._base.y()
            dist = math.hypot(dx, dy)/GRID_UNIT
            painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
            painter.drawLine(bp, cp)
            painter.setPen(QPen(PREVIEW_COLOR, 1))
            painter.drawText(cp.x()+8, cp.y()-8, f"Δ{dist:.2f}")

    def _apply(self, sdx: float, sdy: float):
        if self._window is None: return
        scene = self.view.cad_scene
        old_ents, new_ents = [], []
        for ent in scene.all_entities():
            new_ent = _stretch_entity(ent, self._window, sdx, sdy)
            if new_ent is not None:
                old_ents.append(ent); new_ents.append(new_ent)
        if old_ents:
            self.view.undo_stack.push(StretchCommand(scene, old_ents, new_ents))
        self._state = STATE_WINDOW; self._window = self._base = self._cursor = None
        if self.view: self.view.viewport().update()


def _stretch_entity(ent, rect: QRectF, sdx: float, sdy: float):
    def mv(pt: QPointF) -> QPointF:
        return QPointF(pt.x()+sdx, pt.y()+sdy) if rect.contains(pt) else pt

    if isinstance(ent, LineEntity):
        np1 = mv(ent.p1); np2 = mv(ent.p2)
        if np1.x() == ent.p1.x() and np1.y() == ent.p1.y() and            np2.x() == ent.p2.x() and np2.y() == ent.p2.y():
            return None
        return LineEntity(np1, np2, ent.layer, ent.linetype, ent.lineweight)

    if isinstance(ent, PolylineEntity):
        new_verts = [mv(v) for v in ent.vertices()]
        changed = any(nv.x() != ov.x() or nv.y() != ov.y()
                      for nv, ov in zip(new_verts, ent.vertices()))
        if not changed: return None
        return PolylineEntity(new_verts, ent.layer, ent.linetype, ent.lineweight)

    return None
