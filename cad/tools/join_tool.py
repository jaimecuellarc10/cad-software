import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import JoinCommand

WIN_FILL   = QColor(0,100,255,35);  WIN_BORDER = QColor(0,100,255,220)
CRS_FILL   = QColor(0,200,0,35);    CRS_BORDER = QColor(0,200,0,220)
DRAG_THRESHOLD = 6
JOIN_TOL = 2.0

STATE_SELECT = 0


class JoinTool(BaseTool):
    name = "join"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._press_vp: QPoint | None = None
        self._cur_vp:   QPoint | None = None
        self._dragging  = False

    @property
    def is_idle(self): return True

    @property
    def prompt(self):
        return f"JOIN  Select lines/polylines to join ({len(self._entities)}) [Space/Enter = join, Esc = cancel]"

    def activate(self, view):
        super().activate(view)
        self._entities = [e for e in view.cad_scene.selected_entities()
                          if isinstance(e, (LineEntity, PolylineEntity))]
        self._press_vp = self._cur_vp = None; self._dragging = False

    def deactivate(self):
        self._entities = []; self._press_vp = self._cur_vp = None
        super().deactivate()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._entities: self._apply()

    def finish(self):
        if self._entities: self._apply()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        self._press_vp = event.position().toPoint()
        self._cur_vp = self._press_vp; self._dragging = False

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._press_vp is not None:
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x()-self._press_vp.x())
            dy = abs(self._cur_vp.y()-self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        if self.view: self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(snapped, shift)
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._entities = []; self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None: return
        crossing = self._cur_vp.x() < self._press_vp.x()
        fill = CRS_FILL if crossing else WIN_FILL
        border = CRS_BORDER if crossing else WIN_BORDER
        style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border, 1, style)); painter.setBrush(QBrush(fill))
        painter.drawRect(QRect(min(self._press_vp.x(), self._cur_vp.x()),
                               min(self._press_vp.y(), self._cur_vp.y()),
                               abs(self._cur_vp.x()-self._press_vp.x()),
                               abs(self._cur_vp.y()-self._press_vp.y())))

    def _apply(self):
        if len(self._entities) < 2:
            self._entities = []; return
        chains = _find_chains(self._entities, JOIN_TOL)
        scene = self.view.cad_scene
        for chain_ents, verts in chains:
            if len(chain_ents) < 2 or len(verts) < 2: continue
            new_poly = PolylineEntity(verts, chain_ents[0].layer)
            self.view.undo_stack.push(JoinCommand(scene, chain_ents, new_poly))
        scene.clear_selection()
        self._entities = []
        if self.view: self.view.viewport().update()

    def _click_select(self, scene_pt: QPointF, shift: bool):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if isinstance(ent, (LineEntity, PolylineEntity)) and ent.hit_test(scene_pt, threshold):
                hit = ent; break
        if not shift: scene.clear_selection()
        if hit: hit.selected = False if (shift and hit.selected) else True
        self._entities = [e for e in scene.selected_entities()
                          if isinstance(e, (LineEntity, PolylineEntity))]

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        s = self.view.mapToScene(self._press_vp); e = self.view.mapToScene(vp_end)
        rect = QRectF(s, e).normalized()
        crossing = vp_end.x() < self._press_vp.x()
        scene.select_in_rect(rect, crossing, add=shift)
        self._entities = [e for e in scene.selected_entities()
                          if isinstance(e, (LineEntity, PolylineEntity))]


def _get_endpoints(ent) -> tuple[QPointF, QPointF]:
    if isinstance(ent, LineEntity):
        return ent.p1, ent.p2
    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        return verts[0], verts[-1]
    return None, None

def _get_all_verts(ent) -> list[QPointF]:
    if isinstance(ent, LineEntity): return [ent.p1, ent.p2]
    if isinstance(ent, PolylineEntity): return ent.vertices()
    return []

def _pts_close(a: QPointF, b: QPointF, tol: float) -> bool:
    return math.hypot(a.x()-b.x(), a.y()-b.y()) <= tol

def _find_chains(entities: list, tol: float) -> list[tuple[list, list[QPointF]]]:
    remaining = list(entities)
    chains = []
    while remaining:
        chain_ents = [remaining.pop(0)]
        chain_verts = _get_all_verts(chain_ents[0])
        changed = True
        while changed:
            changed = False
            for ent in list(remaining):
                s, e = _get_endpoints(ent)
                if s is None: continue
                verts = _get_all_verts(ent)
                if _pts_close(chain_verts[-1], s, tol):
                    chain_verts = chain_verts + verts[1:]
                    chain_ents.append(ent); remaining.remove(ent); changed = True
                elif _pts_close(chain_verts[-1], e, tol):
                    chain_verts = chain_verts + list(reversed(verts))[1:]
                    chain_ents.append(ent); remaining.remove(ent); changed = True
                elif _pts_close(chain_verts[0], e, tol):
                    chain_verts = verts[:-1] + chain_verts
                    chain_ents.append(ent); remaining.remove(ent); changed = True
                elif _pts_close(chain_verts[0], s, tol):
                    chain_verts = list(reversed(verts))[:-1] + chain_verts
                    chain_ents.append(ent); remaining.remove(ent); changed = True
        if len(chain_ents) >= 2:
            chains.append((chain_ents, chain_verts))
    return chains
