from PySide6.QtCore import Qt, QPointF
from .base import BaseTool
from ..entities import PointEntity
from ..undo import AddEntityCommand


class PointTool(BaseTool):
    name = "point"

    @property
    def prompt(self):
        return "POINT  Click or type x,y to place a point"

    def on_press(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._exit_to_select()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._place(snapped)

    def on_command(self, cmd: str) -> bool:
        pt = self._parse_coord(cmd)
        if pt is None:
            return False
        self._place(pt)
        return True

    def cancel(self):
        if self.view:
            self.view.viewport().update()

    def _exit_to_select(self):
        view = self.view
        self.cancel()
        if view and view._select_tool:
            view.set_tool(view._select_tool)
            view._notify_tool_change("select")

    def _place(self, pt: QPointF):
        layer = self.view.layer_manager.current
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, PointEntity(pt, layer)))
        if self.view:
            self.view.viewport().update()
