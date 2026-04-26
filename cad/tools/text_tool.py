from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import TextEntity
from ..undo import AddEntityCommand

STATE_POS = 0
STATE_INPUT = 1


class TextTool(BaseTool):
    name = "text"

    def __init__(self):
        super().__init__()
        self._state = STATE_POS
        self._pos: QPointF | None = None
        self._buffer = ""

    @property
    def is_idle(self):
        return self._state == STATE_POS

    @property
    def prompt(self):
        if self._state == STATE_POS:
            return "TEXT  Click insertion point"
        return "TEXT  Type text content, Enter to place"

    def activate(self, view):
        super().activate(view)
        self._state = STATE_POS
        self._pos = None
        self._buffer = ""

    def deactivate(self):
        self._state = STATE_POS
        self._pos = None
        self._buffer = ""
        super().deactivate()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_POS:
            self._pos = QPointF(snapped)
            self._buffer = ""
            self._state = STATE_INPUT
            if self.view:
                self.view.viewport().update()

    def on_key(self, event):
        if self._state != STATE_INPUT:
            return
        key = event.key()
        if key == Qt.Key.Key_Backspace:
            self._buffer = self._buffer[:-1]
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._commit(self._buffer)
        elif key == Qt.Key.Key_Escape:
            self.cancel()
        else:
            text = event.text()
            if text and text.isprintable():
                self._buffer += text
        if self.view:
            self.view.viewport().update()

    def on_command(self, cmd: str) -> bool:
        if self._state == STATE_INPUT and self._pos is not None:
            self._commit(cmd)
            return True
        return False

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_INPUT or self._pos is None:
            return
        v = self.view
        p = v.mapFromScene(self._pos)
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawLine(p.x()-5, p.y(), p.x()+5, p.y())
        painter.drawLine(p.x(), p.y()-5, p.x(), p.y()+5)
        if self._buffer:
            painter.drawText(p.x()+8, p.y()-8, self._buffer)

    def snap_extras(self):
        return []

    def cancel(self):
        self._state = STATE_POS
        self._pos = None
        self._buffer = ""
        if self.view:
            self.view.viewport().update()

    def _commit(self, text: str):
        if self._pos is None or not text:
            return
        layer = self.view.layer_manager.current
        ent = TextEntity(self._pos, text, height=2.5, layer=layer)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self._state = STATE_POS
        self._pos = None
        self._buffer = ""
        if self.view:
            self.view.viewport().update()
