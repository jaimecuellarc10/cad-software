from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..undo import MirrorEntitiesCommand

PREVIEW_COLOR = QColor("#ffffff")


class MirrorTool(BaseTool):
    """Select entities, then MI: pick 2 points defining the mirror line.
    Type 'Y' + Enter to keep the original (mirror-copy). Default = no copy."""

    name = "mirror"

    def __init__(self):
        super().__init__()
        self._entities:    list = []
        self._p1:   QPointF | None = None
        self._cursor: QPointF | None = None
        self._keep_original: bool = False

    @property
    def is_idle(self) -> bool:
        return self._p1 is None

    @property
    def prompt(self) -> str:
        if not self._entities:
            return "MIRROR  No objects selected.  Esc to cancel."
        if self._p1 is None:
            return f"MIRROR  {len(self._entities)} object(s)  Specify first mirror-line point:"
        return "MIRROR  Specify second mirror-line point  [Y+Enter = keep original]"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._p1     = None
        self._cursor = None
        self._keep_original = False

    def deactivate(self):
        self._entities = []
        self._p1     = None
        self._cursor = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        if self._p1 is not None and cmd in ("Y", "YES"):
            self._keep_original = True
            return True
        if self._p1 is not None and cmd in ("N", "NO"):
            self._keep_original = False
            return True
        return False

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not self._entities:
            return
        if self._p1 is None:
            self._p1 = QPointF(snapped)
        else:
            self._commit(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._p1     = None
        self._cursor = None
        self._entities = []
        self._keep_original = False
        if self.view:
            self.view.viewport().update()

    # ── Overlay ───────────────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._p1 is None or self._cursor is None:
            return
        v  = self.view
        p1 = v.mapFromScene(self._p1)
        p2 = v.mapFromScene(self._cursor)
        pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(p1, p2)

    # ── Commit ────────────────────────────────────────────────────────────────

    def _commit(self, p2: QPointF):
        ax, ay = self._p1.x(), self._p1.y()
        bx, by = p2.x(), p2.y()
        self.view.undo_stack.push(
            MirrorEntitiesCommand(self.view.cad_scene, self._entities,
                                  ax, ay, bx, by, self._keep_original)
        )
        if not self._keep_original:
            self.view.cad_scene.clear_selection()
        self._p1     = None
        self._cursor = None
        self._entities = []
        self._keep_original = False
        if self.view:
            self.view.viewport().update()
