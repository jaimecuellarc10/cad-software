import math
from PySide6.QtCore import Qt, QPointF
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity, ArcEntity
from ..undo import FilletCommand
from ..constants import GRID_UNIT

STATE_RADIUS = 0
STATE_FIRST  = 1
STATE_SECOND = 2


class FilletTool(BaseTool):
    name = "fillet"

    def __init__(self):
        super().__init__()
        self._radius: float = 0.0
        self._state = STATE_RADIUS
        self._ent1 = None
        self._click1: QPointF | None = None

    @property
    def is_idle(self): return self._state == STATE_RADIUS

    @property
    def prompt(self):
        r = self._radius / GRID_UNIT
        if self._state == STATE_RADIUS:
            return f"FILLET  Specify fillet radius ({r:.2f}):  [type + Enter]"
        if self._state == STATE_FIRST:
            return f"FILLET  r={r:.2f}  Select first line:"
        return f"FILLET  r={r:.2f}  Select second line:"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_RADIUS; self._ent1 = None; self._click1 = None

    def deactivate(self):
        self._ent1 = None; self._click1 = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_RADIUS:
            try:
                self._radius = float(cmd) * GRID_UNIT
                self._state = STATE_FIRST
                return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        threshold = 8.0 / self.view.transform().m11()
        if self._state == STATE_FIRST:
            ent = self._pick_line(snapped, threshold)
            if ent:
                self._ent1 = ent; self._click1 = QPointF(snapped)
                self._state = STATE_SECOND
        elif self._state == STATE_SECOND:
            ent2 = self._pick_line(snapped, threshold, exclude=self._ent1)
            if ent2:
                self._apply_fillet(self._ent1, self._click1, ent2, snapped)
                self._ent1 = None; self._click1 = None
                self._state = STATE_FIRST

    def on_move(self, snapped, raw, event): pass
    def cancel(self):
        self._ent1 = None; self._click1 = None; self._state = STATE_FIRST
        if self.view: self.view.viewport().update()
    def draw_overlay(self, painter): pass

    def _pick_line(self, pt, threshold, exclude=None):
        for ent in self.view.cad_scene.all_entities():
            if ent is exclude: continue
            if isinstance(ent, (LineEntity, PolylineEntity)) and ent.hit_test(pt, threshold):
                return ent
        return None

    def _apply_fillet(self, ent1, click1: QPointF, ent2, click2: QPointF):
        segs1 = _entity_segments(ent1); segs2 = _entity_segments(ent2)
        best = None; best_dist = float('inf')
        for i, (a1, b1) in enumerate(segs1):
            for j, (a2, b2) in enumerate(segs2):
                pt = _line_line_isect(a1, b1, a2, b2)
                if pt is None: continue
                d = (math.hypot(pt.x()-click1.x(), pt.y()-click1.y()) +
                     math.hypot(pt.x()-click2.x(), pt.y()-click2.y()))
                if d < best_dist:
                    best_dist = d; best = (i, a1, b1, j, a2, b2, pt)
        if best is None: return
        i, a1, b1, j, a2, b2, P = best
        def far_end(a, b, click):
            da = math.hypot(click.x()-a.x(), click.y()-a.y())
            db = math.hypot(click.x()-b.x(), click.y()-b.y())
            return b if da < db else a
        far1 = far_end(a1, b1, click1)
        far2 = far_end(a2, b2, click2)
        d1 = _normalize(QPointF(far1.x()-P.x(), far1.y()-P.y()))
        d2 = _normalize(QPointF(far2.x()-P.x(), far2.y()-P.y()))
        dot = d1.x()*d2.x() + d1.y()*d2.y()
        dot = max(-1.0, min(1.0, dot))
        angle_between = math.acos(dot)
        half = angle_between / 2.0
        if math.sin(half) < 1e-6: return
        if self._radius < 1e-6:
            t1 = _rebuild_to_pt(ent1, i, P, far1 == b1)
            t2 = _rebuild_to_pt(ent2, j, P, far2 == b2)
            cmd = FilletCommand(self.view.cad_scene, ent1, ent2, t1, t2, None)
            self.view.undo_stack.push(cmd); return
        setback = self._radius / math.tan(half)
        T1 = QPointF(P.x() + d1.x()*setback, P.y() + d1.y()*setback)
        T2 = QPointF(P.x() + d2.x()*setback, P.y() + d2.y()*setback)
        bisector = _normalize(QPointF(d1.x()+d2.x(), d1.y()+d2.y()))
        center_dist = self._radius / math.sin(half)
        arc_center = QPointF(P.x()+bisector.x()*center_dist,
                             P.y()+bisector.y()*center_dist)
        ang1 = math.degrees(math.atan2(-(T1.y()-arc_center.y()), T1.x()-arc_center.x()))
        ang2 = math.degrees(math.atan2(-(T2.y()-arc_center.y()), T2.x()-arc_center.x()))
        span = (ang2 - ang1) % 360
        if span > 180: span -= 360
        layer = ent1.layer
        arc = ArcEntity(arc_center, self._radius, ang1, span, layer)
        t1 = _rebuild_to_pt(ent1, i, T1, far1 == b1)
        t2 = _rebuild_to_pt(ent2, j, T2, far2 == b2)
        cmd = FilletCommand(self.view.cad_scene, ent1, ent2, t1, t2, arc)
        self.view.undo_stack.push(cmd)
        if self.view: self.view.viewport().update()


def _entity_segments(ent):
    if isinstance(ent, LineEntity): return [(ent.p1, ent.p2)]
    if isinstance(ent, PolylineEntity): return ent.segments()
    return []


def _line_line_isect(a: QPointF, b: QPointF, c: QPointF, d: QPointF) -> QPointF | None:
    dx1=b.x()-a.x(); dy1=b.y()-a.y()
    dx2=d.x()-c.x(); dy2=d.y()-c.y()
    denom = dx1*dy2 - dy1*dx2
    if abs(denom) < 1e-10: return None
    t = ((c.x()-a.x())*dy2 - (c.y()-a.y())*dx2) / denom
    return QPointF(a.x()+t*dx1, a.y()+t*dy1)


def _normalize(v: QPointF) -> QPointF:
    l = math.hypot(v.x(), v.y())
    return QPointF(v.x()/l, v.y()/l) if l > 1e-9 else QPointF(1,0)


def _rebuild_to_pt(ent, seg_idx: int, new_end: QPointF, toward_b: bool):
    if isinstance(ent, LineEntity):
        if toward_b:
            p1, p2 = ent.p1, new_end
        else:
            p1, p2 = new_end, ent.p2
        if math.hypot(p2.x()-p1.x(), p2.y()-p1.y()) < 1: return None
        return LineEntity(p1, p2, ent.layer, ent.linetype, ent.lineweight)
    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        if toward_b:
            new_verts = verts[:seg_idx+1] + [new_end] + verts[seg_idx+2:]
        else:
            new_verts = verts[:seg_idx] + [new_end] + verts[seg_idx+1:]
        if len(new_verts) < 2: return None
        return PolylineEntity(new_verts, ent.layer, ent.linetype, ent.lineweight)
    return None
