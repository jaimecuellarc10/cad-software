from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtGui import QFont, QColor, QPalette, QKeyEvent
from PySide6.QtCore import Qt, Signal, QEvent


class CommandBar(QWidget):
    """
    AutoCAD-style command bar.

    The view routes raw keystrokes here via feed_char() / feed_backspace().
    When the user presses Enter the submitted() signal fires with the typed text.
    Escape clears the current input without submitting.
    """

    submitted = Signal(str)   # emitted with uppercased command text on Enter

    _BG       = "#111111"
    _HIST_FG  = "#888888"
    _INPUT_FG = "#ffffff"
    _PROMPT_FG = "#aaddff"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(66)
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(self._BG))
        self.setPalette(p)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(0)

        mono = QFont("Courier New", 9)

        # ── History line (last command echo) ──────────────────────────────────
        self._hist_label = QLabel("")
        self._hist_label.setFont(mono)
        self._hist_label.setStyleSheet(f"color: {self._HIST_FG};")
        layout.addWidget(self._hist_label)

        # ── Active input row ──────────────────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 2, 0, 0)
        input_row.setSpacing(6)

        self._prompt_label = QLabel("Command:")
        self._prompt_label.setFont(QFont("Courier New", 10))
        self._prompt_label.setStyleSheet(f"color: {self._PROMPT_FG};")
        self._prompt_label.setFixedWidth(240)
        input_row.addWidget(self._prompt_label)

        self._input_label = QLabel("")
        self._input_label.setFont(QFont("Courier New", 10))
        self._input_label.setStyleSheet(f"color: {self._INPUT_FG};")
        input_row.addWidget(self._input_label, 1)

        layout.addLayout(input_row)

        self._buffer = ""
        self._view_ref = None   # set by window so Escape can refocus view

    # ── Public API ────────────────────────────────────────────────────────────

    def set_prompt(self, text: str):
        self._prompt_label.setText(text)

    def feed_char(self, ch: str):
        self._buffer += ch.upper()
        self._refresh_input()

    def feed_backspace(self):
        if self._buffer:
            self._buffer = self._buffer[:-1]
            self._refresh_input()

    def clear_input(self):
        self._buffer = ""
        self._refresh_input()
        if self._view_ref:
            self._view_ref.setFocus()

    def has_input(self) -> bool:
        return bool(self._buffer)

    def submit(self):
        cmd = self._buffer.strip()
        if cmd:
            self._hist_label.setText(f"> {cmd}")
            self.clear_input()
            self.submitted.emit(cmd)
        else:
            self.submitted.emit("")   # Enter with empty input = repeat last

    # ── Internal ──────────────────────────────────────────────────────────────

    def _refresh_input(self):
        cursor = "|" if self._buffer else ""
        self._input_label.setText(self._buffer + cursor)
