import math
from PySide6.QtCore import Qt, QPointF
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import BreakEntityCommand

STATE_FIRST  = 0
STATE_SECOND = 1


class BreakTool(BaseTool):
    name = "break"

    def __init__(self):
        super().__init__()
        self._state = STATE_FIRST
        self._ent = None
        self._pt1: QPointF | None = None

    @property
    def is_idle(self): return self._state == STATE_FIRST

    @property
    def prompt(self):
        if self._state == STATE_FIRST:
            return "BREAK  Click entity at first break point:"
        return "BREAK  Click second break point:"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_FIRST; self._ent = None; self._pt1 = None

    def deactivate(self):
        self._ent = None; self._pt1 = None
        super().deactivate()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        threshold = 8.0 / self.view.transform().m11()
        if self._state == STATE_FIRST:
            for ent in self.view.cad_scene.all_entities():
                if isinstance(ent, (LineEntity, PolylineEntity)) and ent.hit_test(snapped, threshold):
                    self._ent = ent
                    self._pt1 = _closest_point_on_entity(ent, snapped)
                    self._state = STATE_SECOND
                    break
        elif self._state == STATE_SECOND:
            pt2 = _closest_point_on_entity(self._ent, snapped)
            self._apply_break(pt2)
            self._ent = None; self._pt1 = None; self._state = STATE_FIRST

    def on_move(self, snapped, raw, event): pass
    def cancel(self):
        self._ent = None; self._pt1 = None; self._state = STATE_FIRST
        if self.view: self.view.viewport().update()
    def draw_overlay(self, painter): pass

    def _apply_break(self, pt2: QPointF):
        if self._ent is None or self._pt1 is None: return
        part1, part2 = _break_entity(self._ent, self._pt1, pt2)
        self.view.undo_stack.push(BreakEntityCommand(
            self.view.cad_scene, self._ent, part1, part2))
        if self.view: self.view.viewport().update()


def _param_on_entity(ent, pt: QPointF) -> tuple[int, float]:
    segs = _entity_segs(ent)
    best_seg, best_t, best_d = 0, 0.0, float('inf')
    for i, (a, b) in enumerate(segs):
        dx=b.x()-a.x(); dy=b.y()-a.y(); l2=dx*dx+dy*dy
        if l2 < 1e-12:
            t=0.0
        else:
            t = max(0.0,min(1.0,((pt.x()-a.x())*dx+(pt.y()-a.y())*dy)/l2))
        px=a.x()+t*dx; py=a.y()+t*dy
        d=math.hypot(pt.x()-px, pt.y()-py)
        if d < best_d:
            best_d=d; best_seg=i; best_t=t
    return best_seg, best_t


def _closest_point_on_entity(ent, pt: QPointF) -> QPointF:
    segs = _entity_segs(ent)
    best_pt, best_d = pt, float('inf')
    for a,b in segs:
        dx=b.x()-a.x(); dy=b.y()-a.y(); l2=dx*dx+dy*dy
        if l2<1e-12:
            t=0.0
        else:
            t=max(0.0,min(1.0,((pt.x()-a.x())*dx+(pt.y()-a.y())*dy)/l2))
        p=QPointF(a.x()+t*dx,a.y()+t*dy)
        d=math.hypot(pt.x()-p.x(),pt.y()-p.y())
        if d<best_d: best_d=d; best_pt=p
    return best_pt


def _entity_segs(ent):
    if isinstance(ent, LineEntity): return [(ent.p1, ent.p2)]
    if isinstance(ent, PolylineEntity): return ent.segments()
    return []


def _break_entity(ent, pt1: QPointF, pt2: QPointF):
    s1, t1 = _param_on_entity(ent, pt1)
    s2, t2 = _param_on_entity(ent, pt2)
    idx1 = s1 + t1; idx2 = s2 + t2
    if idx1 > idx2:
        pt1, pt2 = pt2, pt1; s1, t1, s2, t2 = s2, t2, s1, t1

    if isinstance(ent, LineEntity):
        p1 = QPointF(ent.p1.x()+t1*(ent.p2.x()-ent.p1.x()),
                     ent.p1.y()+t1*(ent.p2.y()-ent.p1.y()))
        p2 = QPointF(ent.p1.x()+t2*(ent.p2.x()-ent.p1.x()),
                     ent.p1.y()+t2*(ent.p2.y()-ent.p1.y()))
        def _ml(a,b):
            if math.hypot(b.x()-a.x(),b.y()-a.y())<1: return None
            return LineEntity(a,b,ent.layer,ent.linetype,ent.lineweight)
        return _ml(ent.p1, p1), _ml(p2, ent.p2)

    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        segs = ent.segments()
        a1,b1 = segs[s1]; brk1 = QPointF(a1.x()+t1*(b1.x()-a1.x()),a1.y()+t1*(b1.y()-a1.y()))
        a2,b2 = segs[s2]; brk2 = QPointF(a2.x()+t2*(b2.x()-a2.x()),a2.y()+t2*(b2.y()-a2.y()))
        part1_v = verts[:s1+1] + [brk1]
        part2_v = [brk2] + verts[s2+1:]
        def _mp(vs):
            if len(vs)<2: return None
            return PolylineEntity(vs,ent.layer,ent.linetype,ent.lineweight)
        return _mp(part1_v), _mp(part2_v)

    return None, None
