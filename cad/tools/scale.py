import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ._ghost import GHOST_PEN, draw_entities_ghost_scaled
from ..undo import ScaleEntitiesCommand
from ..constants import GRID_UNIT

PREVIEW_COLOR = QColor("#ffffff")
WIN_FILL   = QColor(0, 100, 255, 35);  WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL   = QColor(0, 200,   0, 35);  CRS_BORDER = QColor(0, 200,   0, 220)
DRAG_THRESHOLD = 6

STATE_SELECT = 0
STATE_BASE   = 1
STATE_FACTOR = 2


class ScaleTool(BaseTool):
    name = "scale"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._base:  QPointF | None = None
        self._cursor: QPointF | None = None
        self._ref_dist: float = 0.0
        self._press_vp: QPoint | None = None
        self._cur_vp:   QPoint | None = None
        self._dragging  = False

    @property
    def is_idle(self): return False

    @property
    def prompt(self):
        if self._state == STATE_SELECT:
            return f"SCALE  Select objects ({len(self._entities)}) [Space/Enter = confirm, Esc = cancel]"
        if self._state == STATE_BASE:
            return f"SCALE  {len(self._entities)} object(s)  Specify base point:"
        f = self._current_factor()
        return f"SCALE  Scale factor: {f:.3f}  [type factor + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_BASE if self._entities else STATE_SELECT
        if self._state == STATE_SELECT:
            view.cad_scene.clear_selection()
        self._base = self._cursor = None
        self._press_vp = self._cur_vp = None
        self._dragging = False

    def deactivate(self):
        self._entities = []; self._base = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_FACTOR and self._base is not None:
            try:
                factor = float(cmd)
                if factor > 0:
                    self._commit(factor)
                return True
            except ValueError:
                return False
        return False

    def on_key(self, event):
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            return
        if self._state == STATE_SELECT and self._entities:
            self._confirm_selection()

    def finish(self):
        if self._state == STATE_SELECT and self._entities:
            self._confirm_selection()
        elif self._state == STATE_FACTOR and self._base is not None:
            self._commit(self._current_factor())
        else:
            self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_SELECT:
            self._press_vp = event.position().toPoint()
            self._cur_vp = self._press_vp; self._dragging = False
        elif self._state == STATE_BASE:
            self._base = QPointF(snapped)
            self._cursor = QPointF(snapped)
            self._ref_dist = GRID_UNIT * 10
            self._state = STATE_FACTOR
        elif self._state == STATE_FACTOR:
            self._commit(self._current_factor())

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._state == STATE_SELECT and self._press_vp is not None:
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x()-self._press_vp.x())
            dy = abs(self._cur_vp.y()-self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        else:
            self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton or self._state != STATE_SELECT:
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(snapped, shift)
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._state = STATE_SELECT; self._entities = []
        self._base = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state == STATE_SELECT:
            self._draw_selection_box(painter)
            return
        if self._state != STATE_FACTOR or self._base is None or self._cursor is None:
            return
        v = self.view
        bp = v.mapFromScene(self._base)
        cp = v.mapFromScene(self._cursor)
        painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(bp, cp)
        f = self._current_factor()
        painter.setPen(QPen(PREVIEW_COLOR, 1))
        painter.drawText(cp.x()+8, cp.y()-8, f"x{f:.3f}")
        painter.setPen(GHOST_PEN)
        draw_entities_ghost_scaled(painter, v, self._entities,
                                   self._base.x(), self._base.y(), f)

    def _current_factor(self) -> float:
        if self._base is None or self._cursor is None:
            return 1.0
        d = math.hypot(self._cursor.x()-self._base.x(),
                       self._cursor.y()-self._base.y())
        return max(0.001, d / self._ref_dist) if self._ref_dist > 0 else 1.0

    def _commit(self, factor: float):
        if not self._entities or self._base is None:
            return
        self.view.undo_stack.push(
            ScaleEntitiesCommand(self._entities, self._base.x(), self._base.y(), factor))
        self.view.cad_scene.clear_selection()
        self._state = STATE_SELECT; self._entities = []
        self._base = self._cursor = None
        if self.view:
            self.view.viewport().update()

    def _confirm_selection(self):
        self._entities = self.view.cad_scene.selected_entities()
        if self._entities:
            self._state = STATE_BASE
            self._press_vp = self._cur_vp = None; self._dragging = False
            if self.view: self.view.viewport().update()

    def _click_select(self, scene_pt: QPointF, shift: bool):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if ent.hit_test(scene_pt, threshold):
                hit = ent; break
        if not shift: scene.clear_selection()
        if hit:
            hit.selected = False if (shift and hit.selected) else True
        self._entities = scene.selected_entities()

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        s = self.view.mapToScene(self._press_vp)
        e = self.view.mapToScene(vp_end)
        rect = QRectF(s, e).normalized()
        crossing = vp_end.x() < self._press_vp.x()
        scene.select_in_rect(rect, crossing, add=shift)
        self._entities = scene.selected_entities()

    def _draw_selection_box(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None:
            return
        crossing = self._cur_vp.x() < self._press_vp.x()
        fill = CRS_FILL if crossing else WIN_FILL
        border = CRS_BORDER if crossing else WIN_BORDER
        style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border, 1, style))
        painter.setBrush(QBrush(fill))
        r = QRect(min(self._press_vp.x(), self._cur_vp.x()),
                  min(self._press_vp.y(), self._cur_vp.y()),
                  abs(self._cur_vp.x()-self._press_vp.x()),
                  abs(self._cur_vp.y()-self._press_vp.y()))
        painter.drawRect(r)
