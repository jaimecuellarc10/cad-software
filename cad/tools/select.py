from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from .base import BaseTool

# Window select (L→R): blue
WIN_FILL   = QColor(0,   100, 255,  35)
WIN_BORDER = QColor(0,   100, 255, 220)

# Crossing select (R→L): green
CRS_FILL   = QColor(0,   200,   0,  35)
CRS_BORDER = QColor(0,   200,   0, 220)

DRAG_THRESHOLD = 6   # px before we commit to a drag


class SelectTool(BaseTool):
    name = "select"

    def __init__(self):
        super().__init__()
        self._press_vp: QPoint | None = None   # viewport px where LMB went down
        self._cur_vp:   QPoint | None = None   # current mouse position (viewport)
        self._dragging  = False

    @property
    def is_idle(self) -> bool:
        return not self._dragging

    @property
    def prompt(self) -> str:
        return "Command:"

    def activate(self, view):
        super().activate(view)
        self._reset()

    def deactivate(self):
        self._reset()
        super().deactivate()

    def cancel(self):
        self._reset()
        if self.view:
            self.view.viewport().update()

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_vp = event.position().toPoint()
        self._cur_vp   = self._press_vp
        self._dragging = False

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._press_vp is None:
            return
        self._cur_vp = event.position().toPoint()
        dx = abs(self._cur_vp.x() - self._press_vp.x())
        dy = abs(self._cur_vp.y() - self._press_vp.y())
        if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
            self._dragging = True
        if self._dragging:
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(event.position().toPoint(), shift)

        self._reset()
        self.view.viewport().update()

    # ── Selection logic ───────────────────────────────────────────────────────

    def _click_select(self, vp: QPoint, shift: bool):
        scene     = self.view.cad_scene
        scene_pt  = self.view.mapToScene(vp)
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

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene  = self.view.cad_scene
        start  = self._press_vp

        # Convert viewport corners to scene
        s_scene = self.view.mapToScene(start)
        e_scene = self.view.mapToScene(vp_end)
        rect    = QRectF(s_scene, e_scene).normalized()

        # Drag direction determines mode
        crossing = vp_end.x() < start.x()
        scene.select_in_rect(rect, crossing, add=shift)

    # ── Overlay (selection box) ───────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if not self._dragging or self._press_vp is None:
            return

        crossing = self._cur_vp.x() < self._press_vp.x()
        fill     = CRS_FILL   if crossing else WIN_FILL
        border   = CRS_BORDER if crossing else WIN_BORDER
        style    = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine

        pen = QPen(border, 1, style)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRect(_make_rect(self._press_vp, self._cur_vp))

    # ── helpers ───────────────────────────────────────────────────────────────

    def _reset(self):
        self._press_vp = None
        self._cur_vp   = None
        self._dragging = False


def _make_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                 abs(b.x() - a.x()), abs(b.y() - a.y()))
