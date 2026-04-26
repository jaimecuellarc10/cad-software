import math, re
from PySide6.QtCore import Qt, QPointF
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ChamferCommand
from ..constants import GRID_UNIT

STATE_DIST   = 0
STATE_FIRST  = 1
STATE_SECOND = 2


class ChamferTool(BaseTool):
    name = "chamfer"

    def __init__(self):
        super().__init__()
        self._d1: float = 0.0
        self._d2: float = 0.0
        self._state = STATE_DIST
        self._ent1 = None
        self._click1: QPointF | None = None

    @property
    def is_idle(self): return self._state == STATE_DIST

    @property
    def prompt(self):
        d1 = self._d1/GRID_UNIT; d2 = self._d2/GRID_UNIT
        if self._state == STATE_DIST:
            return f"CHAMFER  Specify distances ({d1:.2f},{d2:.2f}):  [type D or D1,D2 + Enter]"
        if self._state == STATE_FIRST:
            return f"CHAMFER  d1={d1:.2f} d2={d2:.2f}  Select first line:"
        return f"CHAMFER  d1={d1:.2f} d2={d2:.2f}  Select second line:"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_DIST; self._ent1 = None; self._click1 = None

    def deactivate(self):
        self._ent1 = None; self._click1 = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_DIST:
            parts = re.split(r'[,\s]+', cmd.strip())
            try:
                if len(parts) >= 2:
                    self._d1 = float(parts[0]) * GRID_UNIT
                    self._d2 = float(parts[1]) * GRID_UNIT
                else:
                    self._d1 = self._d2 = float(parts[0]) * GRID_UNIT
                self._state = STATE_FIRST
                return True
            except ValueError:
                return False
        return False

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        threshold = 8.0 / self.view.transform().m11()
        if self._state == STATE_FIRST:
            ent = self._pick_line(snapped, threshold)
            if ent:
                self._ent1 = ent; self._click1 = QPointF(snapped)
                self._state = STATE_SECOND
        elif self._state == STATE_SECOND:
            ent2 = self._pick_line(snapped, threshold, exclude=self._ent1)
            if ent2:
                self._apply_chamfer(self._ent1, self._click1, ent2, snapped)
                self._ent1 = None; self._click1 = None; self._state = STATE_FIRST

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

    def _apply_chamfer(self, ent1, click1, ent2, click2):
        from .fillet import _entity_segments, _line_line_isect, _normalize, _rebuild_to_pt
        segs1 = _entity_segments(ent1); segs2 = _entity_segments(ent2)
        best = None; best_dist = float('inf')
        for i,(a1,b1) in enumerate(segs1):
            for j,(a2,b2) in enumerate(segs2):
                pt = _line_line_isect(a1,b1,a2,b2)
                if pt is None: continue
                d = (math.hypot(pt.x()-click1.x(), pt.y()-click1.y()) +
                     math.hypot(pt.x()-click2.x(), pt.y()-click2.y()))
                if d < best_dist:
                    best_dist = d; best = (i,a1,b1,j,a2,b2,pt)
        if best is None: return
        i,a1,b1,j,a2,b2,P = best
        def far_end(a,b,click):
            da=math.hypot(click.x()-a.x(),click.y()-a.y())
            db=math.hypot(click.x()-b.x(),click.y()-b.y())
            return b if da < db else a
        far1 = far_end(a1,b1,click1); far2 = far_end(a2,b2,click2)
        d1_dir = _normalize(QPointF(far1.x()-P.x(), far1.y()-P.y()))
        d2_dir = _normalize(QPointF(far2.x()-P.x(), far2.y()-P.y()))
        C1 = QPointF(P.x()+d1_dir.x()*self._d1, P.y()+d1_dir.y()*self._d1)
        C2 = QPointF(P.x()+d2_dir.x()*self._d2, P.y()+d2_dir.y()*self._d2)
        t1 = _rebuild_to_pt(ent1, i, C1, far1==b1)
        t2 = _rebuild_to_pt(ent2, j, C2, far2==b2)
        if math.hypot(C2.x()-C1.x(), C2.y()-C1.y()) < 1:
            chamfer_line = None
        else:
            chamfer_line = LineEntity(C1, C2, ent1.layer)
        cmd = ChamferCommand(self.view.cad_scene, ent1, ent2, t1, t2, chamfer_line)
        self.view.undo_stack.push(cmd)
        if self.view: self.view.viewport().update()
