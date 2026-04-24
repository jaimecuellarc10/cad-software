from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..undo import MoveEntitiesCommand

PREVIEW_COLOR = QColor("#ffffff")


class MoveTool(BaseTool):
    """Select entities first, then M: pick base point → pick destination."""

    name = "move"

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
            return "MOVE  No objects selected.  Esc to cancel."
        if self._base is None:
            return f"MOVE  {len(self._entities)} object(s)  Specify base point:"
        return "MOVE  Specify destination point  [Esc = cancel]"

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

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._entities:
            return
        if self._base is None:
            self._base = QPointF(snapped)
        else:
            self._commit(snapped)

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
        p1 = v.mapFromScene(self._base)
        p2 = v.mapFromScene(self._cursor)
        painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
        painter.drawLine(p1, p2)

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, dest: QPointF):
        dx = dest.x() - self._base.x()
        dy = dest.y() - self._base.y()
        self.view.undo_stack.push(MoveEntitiesCommand(self._entities, dx, dy))
        self.view.cad_scene.clear_selection()
        self._base   = None
        self._cursor = None
        self._entities = []
        if self.view:
            self.view.viewport().update()
