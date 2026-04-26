from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush

from .base import BaseTool
from ._ghost import GHOST_PEN, draw_entities_ghost_mirrored
from ..undo import MirrorEntitiesCommand


PREVIEW_COLOR = QColor("#ffffff")
WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_SELECT = 0
STATE_P1     = 1
STATE_P2     = 2
STATE_KEEP   = 3


class MirrorTool(BaseTool):
    """Select entities, pick a mirror axis, then choose whether to keep originals."""

    name = "mirror"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._p1: QPointF | None = None
        self._p2: QPointF | None = None
        self._cursor: QPointF | None = None
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False

    @property
    def is_idle(self) -> bool:
        return False

    @property
    def prompt(self) -> str:
        if self._state == STATE_SELECT:
            return f"MIRROR  Select objects ({len(self._entities)})  [Space/Enter = confirm, Esc = cancel]"
        if self._state == STATE_P1:
            return f"MIRROR  {len(self._entities)} object(s)  Specify first mirror-line point:"
        if self._state == STATE_P2:
            return "MIRROR  Specify second mirror-line point:"
        return "MIRROR  Keep original? [Y]/N  (Enter = Yes)"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_P1 if self._entities else STATE_SELECT
        self._p1 = None
        self._p2 = None
        self._cursor = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False

    def deactivate(self):
        self.cancel()
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._state != STATE_KEEP:
            return False
        cmd = cmd.strip().upper()
        if cmd in ("Y", "YES"):
            self._commit(keep_original=True)
            return True
        if cmd in ("N", "NO"):
            self._commit(keep_original=False)
            return True
        return False

    def on_key(self, event):
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return
        if self._state == STATE_SELECT:
            self._confirm_selection()
        elif self._state == STATE_KEEP:
            self._commit(keep_original=True)

    def finish(self):
        if self._state == STATE_SELECT and self._entities:
            self._confirm_selection()
        elif self._state == STATE_KEEP:
            self._commit(keep_original=True)
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
        elif self._state == STATE_P1:
            self._p1 = QPointF(snapped)
            self._cursor = QPointF(snapped)
            self._state = STATE_P2
        elif self._state == STATE_P2:
            self._p2 = QPointF(snapped)
            self._cursor = QPointF(snapped)
            self._state = STATE_KEEP

        if self.view:
            self.view.viewport().update()

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
            self._toggle_entity_at(snapped)
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._state = STATE_SELECT
        self._entities = []
        self._p1 = None
        self._p2 = None
        self._cursor = None
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
        if self._p1 is None:
            return

        axis_end = self._p2 or self._cursor
        if axis_end is None:
            return

        v = self.view
        p1 = QPointF(v.mapFromScene(self._p1))
        p2 = QPointF(v.mapFromScene(axis_end))
        pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(p1, p2)

        painter.setPen(GHOST_PEN)
        draw_entities_ghost_mirrored(
            painter, v, self._entities,
            self._p1.x(), self._p1.y(), axis_end.x(), axis_end.y()
        )

    # ── State helpers ─────────────────────────────────────────────────────────

    def _confirm_selection(self):
        self._entities = self.view.cad_scene.selected_entities()
        if self._entities:
            self._state = STATE_P1
            self._press_vp = None
            self._cur_vp = None
            self._dragging = False
            if self.view:
                self.view.viewport().update()

    def _toggle_entity_at(self, scene_pt: QPointF):
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in self.view.cad_scene.all_entities():
            if ent.hit_test(scene_pt, threshold):
                hit = ent
                break
        if hit is None:
            return
        hit.selected = not hit.selected
        self._entities = self.view.cad_scene.selected_entities()

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        start = self._press_vp
        s_scene = self.view.mapToScene(start)
        e_scene = self.view.mapToScene(vp_end)
        rect = QRectF(s_scene, e_scene).normalized()
        crossing = vp_end.x() < start.x()
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
        painter.drawRect(_make_rect(self._press_vp, self._cur_vp))

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, keep_original: bool):
        if not self._entities or self._p1 is None or self._p2 is None:
            self.cancel()
            return

        self.view.undo_stack.push(
            MirrorEntitiesCommand(
                self.view.cad_scene, self._entities,
                self._p1.x(), self._p1.y(), self._p2.x(), self._p2.y(),
                keep_original
            )
        )
        if not keep_original:
            self.view.cad_scene.clear_selection()
        self._state = STATE_SELECT
        self._p1 = None
        self._p2 = None
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
