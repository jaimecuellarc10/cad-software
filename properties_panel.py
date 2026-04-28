"""
AutoCAD-style properties panel.

Architecture:
    PropertiesPanel
      ├─ Selection combo at top  ("Line", "Multiple", "No selection")
      └─ Scroll area
            ├─ CategoryGroup ("General")
            │     └─ PropRow (label + editor) × N
            ├─ CategoryGroup ("Geometry")
            └─ ...

Public API:
    panel = PropertiesPanel()
    panel.set_selection(objects)   # list of dicts or your CAD entity objects
    panel.propertyChanged.connect(handler)  # (object_id, prop_name, new_value)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from icons import Icons
from theme import Colors, Metrics
from widgets.property_editors import (
    VARIES, ChoiceEditor, ColorEditor, NumericEditor, ReadOnlyEditor,
)


# ---------------------------------------------------------------------------
# Collapsible category group
# ---------------------------------------------------------------------------
class CategoryGroup(QWidget):
    """Header button + content frame that toggles visibility."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._expanded = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QPushButton(f"  ▼  {title}")
        self.header.setObjectName("CategoryHeader")
        self.header.setFixedHeight(Metrics.HEADER_HEIGHT)
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)

        self.content = QFrame()
        self.content.setStyleSheet(f"background-color: {Colors.BG_PANEL};")
        self.content_layout = QGridLayout(self.content)
        self.content_layout.setContentsMargins(0, 2, 0, 4)
        self.content_layout.setHorizontalSpacing(0)
        self.content_layout.setVerticalSpacing(0)
        self.content_layout.setColumnMinimumWidth(0, Metrics.LABEL_COL_WIDTH)
        self.content_layout.setColumnStretch(1, 1)
        layout.addWidget(self.content)

        self._row = 0

    def toggle(self):
        self._expanded = not self._expanded
        self.content.setVisible(self._expanded)
        title = self.header.text().lstrip(" ▼▶").strip()
        arrow = "▼" if self._expanded else "▶"
        self.header.setText(f"  {arrow}  {title}")

    def add_row(self, label: str, editor: QWidget):
        """Add a property row. editor is any QWidget with setValue()."""
        # Label
        lbl = QLabel(label)
        lbl.setObjectName("PropLabel")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setFixedHeight(Metrics.ROW_HEIGHT)

        # Editor wrapper for consistent height
        editor.setFixedHeight(Metrics.ROW_HEIGHT)

        self.content_layout.addWidget(lbl, self._row, 0)
        self.content_layout.addWidget(editor, self._row, 1)
        self._row += 1
        return editor

    def clear(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._row = 0


# ---------------------------------------------------------------------------
# Properties panel
# ---------------------------------------------------------------------------
class PropertiesPanel(QWidget):
    """The main properties panel — drop into a QDockWidget."""

    propertyChanged = Signal(str, object)  # property_name, new_value

    # Layers your CAD knows about — wire to your real layer manager later
    AVAILABLE_LAYERS = ["0", "Defpoints", "Walls", "Dimensions", "Hidden"]
    AVAILABLE_LINETYPES = ["ByLayer", "Continuous", "Hidden", "Dashed", "Center"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.set_selection([])

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top: selection combo
        self.selection_combo = QComboBox()
        self.selection_combo.setObjectName("SelectionCombo")
        self.selection_combo.setFixedHeight(28)
        root.addWidget(self.selection_combo)

        # Middle: scrollable category list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(scroll, 1)

        container = QWidget()
        self.categories_layout = QVBoxLayout(container)
        self.categories_layout.setContentsMargins(0, 0, 0, 0)
        self.categories_layout.setSpacing(0)
        self.categories_layout.addStretch(1)
        scroll.setWidget(container)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------
    def set_selection(self, objects: list[dict]):
        """
        objects: list of dicts representing selected CAD entities. Each dict
        should at minimum have a 'type' key. Adapt this to your real entity
        class — the only thing that matters is the property dictionary.
        """
        self._clear_categories()

        if not objects:
            self.selection_combo.clear()
            self.selection_combo.addItem("No selection")
            self._build_no_selection_view()
            return

        # Update selection combo
        self.selection_combo.clear()
        if len(objects) == 1:
            self.selection_combo.addItem(objects[0].get("type", "Unknown"))
        else:
            types = {o.get("type", "Unknown") for o in objects}
            if len(types) == 1:
                self.selection_combo.addItem(f"{next(iter(types))} ({len(objects)})")
            else:
                self.selection_combo.addItem(f"All ({len(objects)})")
                for t in sorted(types):
                    count = sum(1 for o in objects if o.get("type") == t)
                    self.selection_combo.addItem(f"{t} ({count})")

        # Merge properties — VARIES sentinel for differing values
        merged = self._merge_properties(objects)
        self._build_categories(merged)

    # -----------------------------------------------------------------------
    # View builders
    # -----------------------------------------------------------------------
    def _clear_categories(self):
        # remove everything except the trailing stretch
        while self.categories_layout.count() > 1:
            item = self.categories_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_no_selection_view(self):
        general = CategoryGroup("General")
        general.add_row("Color",    ColorEditor("ByLayer"))
        general.add_row("Layer",    ChoiceEditor(self.AVAILABLE_LAYERS, "0"))
        general.add_row("Linetype", ChoiceEditor(self.AVAILABLE_LINETYPES, "ByLayer"))
        general.add_row("Lineweight", ChoiceEditor(
            ["ByLayer", "0.00 mm", "0.05 mm", "0.09 mm", "0.13 mm", "0.25 mm"],
            "ByLayer",
        ))
        self.categories_layout.insertWidget(0, general)

        view = CategoryGroup("View")
        view.add_row("Center X", NumericEditor(0.0))
        view.add_row("Center Y", NumericEditor(0.0))
        view.add_row("Height",   NumericEditor(100.0))
        self.categories_layout.insertWidget(1, view)

    def _build_categories(self, props: dict):
        """Build category groups from a merged properties dict."""
        general = CategoryGroup("General")
        if "color" in props:
            ed = ColorEditor(props["color"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("color", v))
            general.add_row("Color", ed)
        if "layer" in props:
            ed = ChoiceEditor(self.AVAILABLE_LAYERS, props["layer"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("layer", v))
            general.add_row("Layer", ed)
        if "linetype" in props:
            ed = ChoiceEditor(self.AVAILABLE_LINETYPES, props["linetype"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("linetype", v))
            general.add_row("Linetype", ed)
        self.categories_layout.insertWidget(0, general)

        # Geometry — only for relevant types
        geom_keys = ["start_x", "start_y", "end_x", "end_y",
                     "center_x", "center_y", "radius", "length"]
        if any(k in props for k in geom_keys):
            geom = CategoryGroup("Geometry")
            for key, label in [
                ("start_x", "Start X"), ("start_y", "Start Y"),
                ("end_x", "End X"),     ("end_y", "End Y"),
                ("center_x", "Center X"), ("center_y", "Center Y"),
                ("radius", "Radius"),
            ]:
                if key in props:
                    ed = NumericEditor(props[key])
                    ed.valueChanged.connect(
                        lambda v, k=key: self.propertyChanged.emit(k, v)
                    )
                    geom.add_row(label, ed)
            if "length" in props:
                geom.add_row("Length", ReadOnlyEditor(props["length"]))
            self.categories_layout.insertWidget(1, geom)

    # -----------------------------------------------------------------------
    # Property merging across multi-selection
    # -----------------------------------------------------------------------
    @staticmethod
    def _merge_properties(objects: list[dict]) -> dict:
        """Combine all object property dicts. Differing values become VARIES."""
        if not objects:
            return {}

        # Use union of keys; only common props if you prefer AutoCAD's stricter mode
        all_keys: set[str] = set()
        for o in objects:
            all_keys.update(o.get("properties", {}).keys())

        merged: dict = {}
        for key in all_keys:
            values = [o.get("properties", {}).get(key) for o in objects]
            values = [v for v in values if v is not None]
            if not values:
                continue
            first = values[0]
            if all(_eq(v, first) for v in values[1:]):
                merged[key] = first
            else:
                merged[key] = VARIES
        return merged


def _eq(a, b):
    """Equality that handles QColor (which doesn't compare cleanly via ==)."""
    if isinstance(a, QColor) and isinstance(b, QColor):
        return a.rgba() == b.rgba()
    return a == b
