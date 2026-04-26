import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ._ghost import draw_entities_ghost_rotated
from ..undo import RotateEntitiesCommand

PREVIEW_COLOR = QColor("#ffffff")
WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_SELECT = 0
STATE_BASE = 1
STATE_DRAG = 2


class RotateTool(BaseTool):
    """Select entities, then RO: pick base point → drag or type angle → rotate."""

    name = "rotate"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._base:   QPointF | None = None
        self._cursor: QPointF | None = None
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False

    @property
    def is_idle(self) -> bool:
        return self._state != STATE_DRAG

    @property
    def prompt(self) -> str:
        if self._state == STATE_SELECT:
            return f"ROTATE  Select objects ({len(self._entities)}) [Space/Enter = confirm, Esc = cancel]"
        if self._state == STATE_BASE:
            return f"ROTATE  {len(self._entities)} object(s)  Specify base point:"
        ang = self._current_angle()
        return f"ROTATE  Angle: {ang:.1f}°  [type angle + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_BASE if self._entities else STATE_SELECT
        if self._state == STATE_SELECT:
            view.cad_scene.clear_selection()
        self._base   = None
        self._cursor = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False

    def deactivate(self):
        self._entities = []
        self._state = STATE_SELECT
        self._base   = None
        self._cursor = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        """Called by window when user types a value and presses Enter."""
        if self._state == STATE_DRAG and self._base is not None:
            try:
                angle = float(cmd)
                self._commit(angle)
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
        else:
            self.cancel()

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
            self._state = STATE_DRAG
        elif self._state == STATE_DRAG:
            self._commit(self._current_angle())

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
        self._base   = None
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
        if self._state == STATE_BASE:
            return
        if self._base is None or self._cursor is None:
            return
        v  = self.view
        bp = v.mapFromScene(self._base)
        cp = v.mapFromScene(self._cursor)
        pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(bp, cp)
        ang = self._current_angle()
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawText(cp.x() + 8, cp.y() - 8, f"{ang:.1f}°")
        draw_entities_ghost_rotated(
            painter, v, self._entities,
            self._base.x(), self._base.y(), ang
        )

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

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _current_angle(self) -> float:
        if self._base is None or self._cursor is None:
            return 0.0
        dx = self._cursor.x() - self._base.x()
        dy = self._cursor.y() - self._base.y()
        return math.degrees(math.atan2(-dy, dx))

    def _commit(self, angle_deg: float):
        cx = self._base.x()
        cy = self._base.y()
        self.view.undo_stack.push(
            RotateEntitiesCommand(self._entities, cx, cy, angle_deg)
        )
        self.view.cad_scene.clear_selection()
        self._state = STATE_SELECT
        self._base   = None
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
