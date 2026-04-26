import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ._ghost import GHOST_PEN, draw_entities_ghost_translated
from ..undo import MoveEntitiesCommand
from ..constants import GRID_UNIT

PREVIEW_COLOR = QColor("#ffffff")
WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_SELECT = 0
STATE_BASE = 1
STATE_DEST = 2


def _direction_pt(anchor: QPointF, cursor: QPointF, dist_units: float) -> QPointF:
    dx = cursor.x() - anchor.x()
    dy = cursor.y() - anchor.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        dx, dy = 1.0, 0.0
    else:
        dx /= length
        dy /= length
    scene_dist = dist_units * GRID_UNIT
    return QPointF(anchor.x() + dx * scene_dist, anchor.y() + dy * scene_dist)


class MoveTool(BaseTool):
    """Select entities first, then M: pick base point → pick destination."""

    name = "move"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._base: QPointF | None = None
        self._cursor: QPointF | None = None
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False

    @property
    def is_idle(self) -> bool:
        return self._state == STATE_BASE and self._base is None

    @property
    def prompt(self) -> str:
        if self._state == STATE_SELECT:
            return f"MOVE  Select objects ({len(self._entities)}) [Space/Enter = confirm, Esc = cancel]"
        if self._state == STATE_BASE:
            return f"MOVE  {len(self._entities)} object(s)  Specify base point:"
        return "MOVE  Specify destination  [type distance + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_BASE if self._entities else STATE_SELECT
        if self._state == STATE_SELECT:
            view.cad_scene.clear_selection()
        self._base = None
        self._cursor = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False

    def deactivate(self):
        self._entities = []
        self._state = STATE_SELECT
        self._base = None
        self._cursor = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        super().deactivate()

    def on_key(self, event):
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            return
        if self._state == STATE_SELECT and self._entities:
            self._confirm_selection()

    def finish(self):
        if self._state == STATE_SELECT and self._entities:
            self._confirm_selection()
        else:
            self.cancel()

    def on_command(self, cmd: str) -> bool:
        if self._state != STATE_DEST or self._base is None or self._cursor is None:
            return False
        try:
            dist = float(cmd)
        except ValueError:
            return False
        dest = _direction_pt(self._base, self._cursor, dist)
        self._commit(dest)
        return True

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_SELECT:
            self._press_vp = event.position().toPoint()
            self._cur_vp = self._press_vp
            self._dragging = False
        elif self._state == STATE_BASE:
            self._base = QPointF(snapped)
            self._cursor = QPointF(snapped)
            self._state = STATE_DEST
        elif self._state == STATE_DEST:
            self._commit(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._state == STATE_SELECT:
            if self._press_vp is None:
                return
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x() - self._press_vp.x())
            dy = abs(self._cur_vp.y() - self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        else:
            self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state != STATE_SELECT:
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(snapped, shift)
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._state = STATE_SELECT
        self._base = None
        self._cursor = None
        self._entities = []
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._state == STATE_SELECT:
            self._draw_selection_box(painter)
            return
        if self._state != STATE_DEST or self._base is None or self._cursor is None:
            return
        v = self.view
        p1 = v.mapFromScene(self._base)
        p2 = v.mapFromScene(self._cursor)
        painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(p1, p2)
        dx = self._cursor.x() - self._base.x()
        dy = self._cursor.y() - self._base.y()
        dist_units = math.hypot(dx, dy) / GRID_UNIT
        cp = v.mapFromScene(self._cursor)
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawText(cp.x() + 8, cp.y() - 8, f'{dist_units:.2f}')
        painter.setPen(GHOST_PEN)
        draw_entities_ghost_translated(painter, v, self._entities, dx, dy)

    def _draw_selection_box(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None:
            return
        crossing = self._cur_vp.x() < self._press_vp.x()
        fill = CRS_FILL if crossing else WIN_FILL
        border = CRS_BORDER if crossing else WIN_BORDER
        style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border, 1, style))
        painter.setBrush(QBrush(fill))
        painter.drawRect(_make_rect(self._press_vp, self._cur_vp))

    # ── Selection logic ───────────────────────────────────────────────────────

    def _confirm_selection(self):
        self._entities = self.view.cad_scene.selected_entities()
        if self._entities:
            self._state = STATE_BASE
            self._press_vp = None
            self._cur_vp = None
            self._dragging = False
            if self.view:
                self.view.viewport().update()

    def _click_select(self, scene_pt: QPointF, shift: bool):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if ent.hit_test(scene_pt, threshold):
                hit = ent
                break
        if not shift:
            scene.clear_selection()
        if hit:
            if shift and hit.selected:
                hit.selected = False
            else:
                hit.selected = True
        self._entities = scene.selected_entities()

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        start = self._press_vp
        s_scene = self.view.mapToScene(start)
        e_scene = self.view.mapToScene(vp_end)
        rect = QRectF(s_scene, e_scene).normalized()
        crossing = vp_end.x() < start.x()
        scene.select_in_rect(rect, crossing, add=shift)
        self._entities = scene.selected_entities()

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, dest: QPointF):
        dx = dest.x() - self._base.x()
        dy = dest.y() - self._base.y()
        self.view.undo_stack.push(MoveEntitiesCommand(self._entities, dx, dy))
        self.view.cad_scene.clear_selection()
        self._state = STATE_SELECT
        self._base = None
        self._cursor = None
        self._entities = []
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()


def _make_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                 abs(b.x() - a.x()), abs(b.y() - a.y()))
