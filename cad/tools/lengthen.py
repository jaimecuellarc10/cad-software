import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ReplaceEntityCommand
from ..constants import GRID_UNIT

STATE_DELTA = 0
STATE_PICK = 1


class LengthenTool(BaseTool):
    name = "lengthen"

    def __init__(self):
        super().__init__()
        self._state = STATE_DELTA
        self._delta = 0.0
        self._cursor: QPointF | None = None
        self._target = None

    @property
    def is_idle(self):
        return self._state == STATE_DELTA

    @property
    def prompt(self):
        if self._state == STATE_DELTA:
            return "LENGTHEN  Type delta length (+ to extend, - to shorten) + Enter, or DE/DY/PE/T for mode"
        return f"LENGTHEN  Delta: {self._delta:.3f}  Click near end of line to lengthen"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_DELTA
        self._delta = 0.0
        self._cursor = None
        self._target = None

    def on_command(self, cmd: str) -> bool:
        if self._state != STATE_DELTA:
            return False
        try:
            self._delta = float(cmd)
        except ValueError:
            return False
        self._state = STATE_PICK
        if self.view:
            self.view.viewport().update()
        return True

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        self._target = self._nearest_target(snapped) if self._state == STATE_PICK else None
        if self.view:
            self.view.viewport().update()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton or self._state != STATE_PICK:
            return
        target = self._nearest_target(snapped)
        if target is None:
            return
        ent, which = target
        new_ent = _lengthened(ent, which, self._delta * GRID_UNIT)
        if new_ent:
            self.view.undo_stack.push(ReplaceEntityCommand(self.view.cad_scene, ent, new_ent))
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_PICK or self._target is None:
            return
        ent, which = self._target
        pt = _endpoint(ent, which)
        if pt is None:
            return
        vp = self.view.mapFromScene(pt)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(vp, 6, 6)

    def cancel(self):
        self._state = STATE_DELTA
        self._cursor = None
        self._target = None
        if self.view:
            self.view.viewport().update()

    def _nearest_target(self, pt: QPointF):
        threshold = 8.0 / self.view.transform().m11()
        best = None
        best_d = threshold
        for ent in self.view.cad_scene.all_entities():
            if not isinstance(ent, (LineEntity, PolylineEntity)):
                continue
            for which in ("first", "last"):
                ep = _endpoint(ent, which)
                if ep is None:
                    continue
                d = math.hypot(pt.x()-ep.x(), pt.y()-ep.y())
                if d <= best_d:
                    best = (ent, which)
                    best_d = d
        return best


def _endpoint(ent, which: str):
    if isinstance(ent, LineEntity):
        return ent.p1 if which == "first" else ent.p2
    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        if not verts:
            return None
        return verts[0] if which == "first" else verts[-1]
    return None


def _lengthened(ent, which: str, delta: float):
    if isinstance(ent, LineEntity):
        p1, p2 = ent.p1, ent.p2
        length = math.hypot(p2.x()-p1.x(), p2.y()-p1.y())
        if length < 1e-6:
            return None
        ux = (p2.x()-p1.x()) / length
        uy = (p2.y()-p1.y()) / length
        if which == "first":
            p1 = QPointF(p1.x()-ux*delta, p1.y()-uy*delta)
        else:
            p2 = QPointF(p2.x()+ux*delta, p2.y()+uy*delta)
        return LineEntity(p1, p2, ent.layer, ent.linetype, ent.lineweight)

    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        if len(verts) < 2:
            return None
        if which == "first":
            a, b = verts[0], verts[1]
            length = math.hypot(b.x()-a.x(), b.y()-a.y())
            if length < 1e-6:
                return None
            ux = (b.x()-a.x()) / length
            uy = (b.y()-a.y()) / length
            verts[0] = QPointF(a.x()-ux*delta, a.y()-uy*delta)
        else:
            a, b = verts[-2], verts[-1]
            length = math.hypot(b.x()-a.x(), b.y()-a.y())
            if length < 1e-6:
                return None
            ux = (b.x()-a.x()) / length
            uy = (b.y()-a.y()) / length
            verts[-1] = QPointF(b.x()+ux*delta, b.y()+uy*delta)
        return PolylineEntity(verts, ent.layer, ent.linetype, ent.lineweight)

    return None
