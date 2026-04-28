"""
Property editor widgets used in the right column of the properties panel.

Each editor has the same interface:
    - constructor takes initial value (may be a sentinel VARIES)
    - .valueChanged signal emits when user commits a change
    - .setValue(v) updates display without emitting signal

Add new editor types by following the same pattern.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QHBoxLayout, QLineEdit,
    QPushButton, QWidget,
)

from theme import Colors


# Sentinel value indicating selection has differing values for this property
class _Varies:
    def __repr__(self): return "*VARIES*"
VARIES = _Varies()


# ---------------------------------------------------------------------------
# Numeric editor (lengths, angles, counts)
# ---------------------------------------------------------------------------
class NumericEditor(QLineEdit):
    valueChanged = Signal(object)  # float, or None on parse fail

    def __init__(self, value: float | _Varies = 0.0, suffix: str = "", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        self.setValue(value)
        self.editingFinished.connect(self._commit)

    def setValue(self, v):
        if v is VARIES:
            self.setPlaceholderText("*VARIES*")
            self.setText("")
        else:
            self.setText(f"{v:g}{self._suffix}")

    def _commit(self):
        text = self.text().strip().rstrip(self._suffix).strip()
        try:
            self.valueChanged.emit(float(text))
        except ValueError:
            pass  # silently ignore bad input; AutoCAD does the same


# ---------------------------------------------------------------------------
# String editor (text content, text override)
# ---------------------------------------------------------------------------
class StringEditor(QLineEdit):
    valueChanged = Signal(object)  # str

    def __init__(self, value: str | _Varies = "", parent=None):
        super().__init__(parent)
        self.setValue(value)
        self.editingFinished.connect(lambda: self.valueChanged.emit(self.text()))

    def setValue(self, v):
        if v is VARIES:
            self.setPlaceholderText("*VARIES*")
            self.setText("")
        else:
            self.setText(str(v))


# ---------------------------------------------------------------------------
# Color editor — swatch + name, opens picker on click
# ---------------------------------------------------------------------------
class ColorEditor(QPushButton):
    valueChanged = Signal(object)  # QColor or "ByLayer"/"ByBlock"

    def __init__(self, value="ByLayer", parent=None):
        super().__init__(parent)
        self._value = value
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def setValue(self, v):
        self._value = v
        self._refresh()

    def _refresh(self):
        if self._value is VARIES:
            self.setText("  *VARIES*")
        elif isinstance(self._value, str):
            self.setText(f"  {self._value}")
        else:
            self.setText(f"  {self._value.name().upper()}")
        self.update()

    def _pick(self):
        initial = self._value if isinstance(self._value, QColor) else QColor("white")
        c = QColorDialog.getColor(initial, self, "Select Color")
        if c.isValid():
            self._value = c
            self._refresh()
            self.valueChanged.emit(c)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Draw color swatch on left
        rect = self.rect().adjusted(4, 4, 0, -4)
        rect.setWidth(rect.height())
        if isinstance(self._value, QColor):
            p.fillRect(rect, self._value)
        else:
            p.fillRect(rect, QColor(Colors.BG_INPUT))
        p.setPen(QColor(Colors.BORDER))
        p.drawRect(rect)


# ---------------------------------------------------------------------------
# Choice editor — generic dropdown (layers, linetypes, booleans)
# ---------------------------------------------------------------------------
class ChoiceEditor(QComboBox):
    valueChanged = Signal(object)

    def __init__(self, choices: list[str], value=None, parent=None):
        super().__init__(parent)
        self.addItems(choices)
        if value is VARIES:
            self.insertItem(0, "*VARIES*")
            self.setCurrentIndex(0)
        elif value is not None and value in choices:
            self.setCurrentText(value)
        self.currentTextChanged.connect(self._commit)

    def setValue(self, v):
        if v is VARIES:
            if self.itemText(0) != "*VARIES*":
                self.insertItem(0, "*VARIES*")
            self.setCurrentIndex(0)
        else:
            # remove varies sentinel if present
            if self.itemText(0) == "*VARIES*":
                self.removeItem(0)
            self.setCurrentText(str(v))

    def _commit(self, text: str):
        if text == "*VARIES*":
            return
        # remove sentinel after user commits to a real value
        if self.itemText(0) == "*VARIES*":
            self.removeItem(0)
        self.valueChanged.emit(text)


# ---------------------------------------------------------------------------
# Read-only display (for derived values like Length on a Line)
# ---------------------------------------------------------------------------
class ReadOnlyEditor(QLineEdit):
    def __init__(self, value="", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setValue(value)

    def setValue(self, v):
        self.setText("*VARIES*" if v is VARIES else str(v))
