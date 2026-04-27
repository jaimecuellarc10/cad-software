from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ExplodeCommand

WIN_FILL   = QColor(0,100,255,35);  WIN_BORDER = QColor(0,100,255,220)
CRS_FILL   = QColor(0,200,0,35);    CRS_BORDER = QColor(0,200,0,220)
DRAG_THRESHOLD = 6

STATE_SELECT  = 0
STATE_CONFIRM = 1


class ExplodeTool(BaseTool):
    name = "explode"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._press_vp: QPoint | None = None
        self._cur_vp:   QPoint | None = None
        self._dragging  = False

    @property
    def is_idle(self): return False

    @property
    def prompt(self):
        polys = sum(1 for e in self._entities if isinstance(e, PolylineEntity))
        if self._state == STATE_SELECT:
            return f"EXPLODE  Select polylines ({polys}) [Space/Enter = confirm, Esc = cancel]"
        return f"EXPLODE  {polys} polyline(s) ready  [Space/Enter = explode, Esc = cancel]"

    def activate(self, view):
        super().activate(view)
        self._entities = [e for e in view.cad_scene.selected_entities()
                          if isinstance(e, PolylineEntity)]
        self._state = STATE_CONFIRM if self._entities else STATE_SELECT
        self._press_vp = self._cur_vp = None; self._dragging = False

    def deactivate(self):
        self._entities = []; self._press_vp = self._cur_vp = None
        super().deactivate()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._state == STATE_SELECT and self._entities:
                self._state = STATE_CONFIRM
            elif self._state == STATE_CONFIRM:
                self._apply()

    def finish(self):
        if self._state == STATE_CONFIRM:
            self._apply()
        elif self._state == STATE_SELECT and self._entities:
            self._state = STATE_CONFIRM

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self._state == STATE_SELECT:
            self._press_vp = event.position().toPoint()
            self._cur_vp = self._press_vp; self._dragging = False

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._state == STATE_SELECT and self._press_vp is not None:
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x()-self._press_vp.x())
            dy = abs(self._cur_vp.y()-self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        if self.view: self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton or self._state != STATE_SELECT:
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(snapped, shift)
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._entities = []; self._state = STATE_SELECT
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None:
            return
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
        scene = self.view.cad_scene
        for ent in self._entities:
            if not isinstance(ent, PolylineEntity): continue
            lines = [LineEntity(a, b, ent.layer, ent.linetype, ent.lineweight)
                     for a, b in ent.segments()
                     if (a.x()-b.x())**2 + (a.y()-b.y())**2 > 1]
            if lines:
                self.view.undo_stack.push(ExplodeCommand(scene, ent, lines))
        self._entities = []; self._state = STATE_SELECT
        if self.view: self.view.viewport().update()

    def _click_select(self, scene_pt: QPointF, shift: bool):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if isinstance(ent, PolylineEntity) and ent.hit_test(scene_pt, threshold):
                hit = ent; break
        if not shift: scene.clear_selection()
        if hit: hit.selected = False if (shift and hit.selected) else True
        self._entities = [e for e in scene.selected_entities()
                          if isinstance(e, PolylineEntity)]

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        s = self.view.mapToScene(self._press_vp); e = self.view.mapToScene(vp_end)
        rect = QRectF(s, e).normalized()
        crossing = vp_end.x() < self._press_vp.x()
        scene.select_in_rect(rect, crossing, add=shift)
        self._entities = [e for e in scene.selected_entities()
                          if isinstance(e, PolylineEntity)]
