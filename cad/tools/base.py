import re
from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter


class BaseTool:
    name = "base"

    def __init__(self):
        self.view = None  # set by activate()

    def activate(self, view):
        self.view = view

    def deactivate(self):
        self.cancel()
        self.view = None

    @property
    def is_idle(self) -> bool:
        """True when the tool has no in-progress operation."""
        return True

    @property
    def prompt(self) -> str:
        """Status text shown in the command bar."""
        return "Command:"

    def snap_extras(self) -> list[tuple]:
        """Extra (QPointF, SnapMode) pairs from in-progress geometry."""
        return []

    def _parse_coord(self, cmd: str) -> QPointF | None:
        cmd = cmd.strip().replace(' ', ',')
        parts = [p for p in cmd.split(',') if p]
        if len(parts) == 2:
            try:
                x, y = float(parts[0]), float(parts[1])
                from ..constants import GRID_UNIT
                return QPointF(x * GRID_UNIT, -y * GRID_UNIT)
            except ValueError:
                return None
        return None

    def on_press(self, snapped: QPointF, event): pass
    def on_move(self, snapped: QPointF, raw: QPointF, event): pass
    def on_release(self, snapped: QPointF, event): pass
    def on_key(self, event): pass
    def cancel(self): pass

    def finish(self):
        """Commit any pending work then reset — called by spacebar.
        Default is same as cancel (override in tools that have uncommitted state)."""
        self.cancel()

    def draw_overlay(self, painter: QPainter):
        """Draw tool UI in viewport (screen) coordinates."""
        pass
