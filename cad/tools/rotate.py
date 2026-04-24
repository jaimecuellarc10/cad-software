import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..undo import RotateEntitiesCommand

PREVIEW_COLOR = QColor("#ffffff")


class RotateTool(BaseTool):
    """Select entities, then RO: pick base point → drag or type angle → rotate."""

    name = "rotate"

    def __init__(self):
        super().__init__()
        self._entities: list = []
        self._base:   QPointF | None = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return self._base is None

    @property
    def prompt(self) -> str:
        if not self._entities:
            return "ROTATE  No objects selected.  Esc to cancel."
        if self._base is None:
            return f"ROTATE  {len(self._entities)} object(s)  Specify base point:"
        ang = self._current_angle()
        return f"ROTATE  Specify rotation angle: {ang:.1f}°  [type angle + Enter, or click]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._base   = None
        self._cursor = None

    def deactivate(self):
        self._entities = []
        self._base   = None
        self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        """Called by window when user types a value and presses Enter."""
        if self._base is not None:
            try:
                angle = float(cmd)
                self._commit(angle)
                return True
            except ValueError:
                return False
        return False

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._entities:
            return
        if self._base is None:
            self._base = QPointF(snapped)
        else:
            self._commit(self._current_angle())

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._base   = None
        self._cursor = None
        self._entities = []
        if self.view:
            self.view.viewport().update()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._base is None or self._cursor is None:
            return
        v  = self.view
        bp = v.mapFromScene(self._base)
        cp = v.mapFromScene(self._cursor)
        pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(bp, cp)
        ang = self._current_angle()
        painter.drawText(cp.x() + 8, cp.y() - 8, f"{ang:.1f}°")

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
        self._base   = None
        self._cursor = None
        self._entities = []
        if self.view:
            self.view.viewport().update()
