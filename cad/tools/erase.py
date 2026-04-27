from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..undo import DeleteEntitiesCommand

WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_SELECT = 0


class EraseTool(BaseTool):
    name = "erase"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False

    @property
    def is_idle(self) -> bool:
        return False

    @property
    def prompt(self) -> str:
        return f"ERASE  Select objects ({len(self._entities)}) [Enter/Space = delete, Esc = cancel]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_SELECT
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False

    def deactivate(self):
        self._entities = []
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        super().deactivate()

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.finish()

    def finish(self):
        if self._entities:
            self.view.undo_stack.push(DeleteEntitiesCommand(self.view.cad_scene, self._entities))
        self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_vp = event.position().toPoint()
        self._cur_vp = self._press_vp
        self._dragging = False

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._press_vp is None:
            return
        self._cur_vp = event.position().toPoint()
        dx = abs(self._cur_vp.x() - self._press_vp.x())
        dy = abs(self._cur_vp.y() - self._press_vp.y())
        if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
            self._dragging = True
        if self.view:
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
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
        if self.view:
            self.view.cad_scene.clear_selection()
        self._state = STATE_SELECT
        self._entities = []
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None:
            return
        crossing = self._cur_vp.x() < self._press_vp.x()
        fill = CRS_FILL if crossing else WIN_FILL
        border = CRS_BORDER if crossing else WIN_BORDER
        style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border, 1, style))
        painter.setBrush(QBrush(fill))
        painter.drawRect(_make_rect(self._press_vp, self._cur_vp))

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


def _make_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                 abs(b.x() - a.x()), abs(b.y() - a.y()))
