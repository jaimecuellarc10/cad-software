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
    panel.set_selection(objects)   # list of dicts: [{'type': str, 'properties': dict}, ...]
    panel.propertyChanged.connect(handler)  # (prop_name, new_value)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QLabel,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from theme import Colors, Metrics
from .property_editors import (
    VARIES, ChoiceEditor, ColorEditor, NumericEditor, ReadOnlyEditor, StringEditor,
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
        lbl = QLabel(label)
        lbl.setObjectName("PropLabel")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl.setFixedHeight(Metrics.ROW_HEIGHT)

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

    AVAILABLE_LAYERS    = ["0"]
    AVAILABLE_LINETYPES = ["Solid", "Dashed", "Dotted", "Dash-Dot", "Dash-Dot-Dot"]
    AVAILABLE_PATTERNS  = ["ANSI31", "SOLID", "HORIZONTAL", "VERTICAL", "CROSS", "NET45", "NET"]

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
        objects: list of dicts from entity.to_props_dict():
            [{'type': 'Line', 'properties': {...}}, ...]
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
        general.add_row("Layer",    ChoiceEditor(self.AVAILABLE_LAYERS, self.AVAILABLE_LAYERS[0]))
        general.add_row("Linetype", ChoiceEditor(self.AVAILABLE_LINETYPES, self.AVAILABLE_LINETYPES[0]))
        self.categories_layout.insertWidget(0, general)

    def _build_categories(self, props: dict):
        """Build category groups from the merged properties dict."""
        idx = 0

        # ── General ──────────────────────────────────────────────────────────
        general = CategoryGroup("General")
        general_added = False
        if "color" in props:
            ed = ColorEditor(props["color"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("color", v))
            general.add_row("Color", ed)
            general_added = True
        if "layer" in props:
            ed = ChoiceEditor(self.AVAILABLE_LAYERS, props["layer"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("layer", v))
            general.add_row("Layer", ed)
            general_added = True
        if "linetype" in props:
            ed = ChoiceEditor(self.AVAILABLE_LINETYPES, props["linetype"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("linetype", v))
            general.add_row("Linetype", ed)
            general_added = True
        if "lineweight" in props:
            ed = NumericEditor(props["lineweight"])
            ed.valueChanged.connect(lambda v: self.propertyChanged.emit("lineweight", v))
            general.add_row("Lineweight", ed)
            general_added = True
        if general_added:
            self.categories_layout.insertWidget(idx, general)
            idx += 1

        # ── Geometry ─────────────────────────────────────────────────────────
        geom_editable = [
            ("start_x",    "Start X"),
            ("start_y",    "Start Y"),
            ("end_x",      "End X"),
            ("end_y",      "End Y"),
            ("center_x",   "Center X"),
            ("center_y",   "Center Y"),
            ("pos_x",      "Pos X"),
            ("pos_y",      "Pos Y"),
            ("radius",     "Radius"),
            ("radius_x",   "Radius X"),
            ("radius_y",   "Radius Y"),
            ("start_angle","Start Angle°"),
            ("span_angle", "Span Angle°"),
            ("angle",      "Angle°"),
            ("rotation",   "Rotation°"),
        ]
        geom_readonly = [
            ("length",       "Length"),
            ("vertex_count", "Vertices"),
            ("point_count",  "Points"),
            ("closed",       "Closed"),
        ]
        geom_present = any(k in props for k, _ in geom_editable + geom_readonly)
        if geom_present:
            geom = CategoryGroup("Geometry")
            for key, label in geom_editable:
                if key in props:
                    ed = NumericEditor(props[key])
                    ed.valueChanged.connect(lambda v, k=key: self.propertyChanged.emit(k, v))
                    geom.add_row(label, ed)
            for key, label in geom_readonly:
                if key in props:
                    geom.add_row(label, ReadOnlyEditor(props[key]))
            self.categories_layout.insertWidget(idx, geom)
            idx += 1

        # ── Text ─────────────────────────────────────────────────────────────
        text_present = "text_content" in props or "text_height" in props
        if text_present:
            text_grp = CategoryGroup("Text")
            if "text_content" in props:
                ed = StringEditor(props["text_content"])
                ed.valueChanged.connect(lambda v: self.propertyChanged.emit("text_content", v))
                text_grp.add_row("Content", ed)
            if "text_height" in props:
                ed = NumericEditor(props["text_height"])
                ed.valueChanged.connect(lambda v: self.propertyChanged.emit("text_height", v))
                text_grp.add_row("Height", ed)
            self.categories_layout.insertWidget(idx, text_grp)
            idx += 1

        # ── Hatch ────────────────────────────────────────────────────────────
        hatch_present = "pattern" in props or "hatch_scale" in props
        if hatch_present:
            hatch_grp = CategoryGroup("Hatch")
            if "pattern" in props:
                ed = ChoiceEditor(self.AVAILABLE_PATTERNS, props["pattern"])
                ed.valueChanged.connect(lambda v: self.propertyChanged.emit("pattern", v))
                hatch_grp.add_row("Pattern", ed)
            if "hatch_scale" in props:
                ed = NumericEditor(props["hatch_scale"])
                ed.valueChanged.connect(lambda v: self.propertyChanged.emit("hatch_scale", v))
                hatch_grp.add_row("Scale", ed)
            self.categories_layout.insertWidget(idx, hatch_grp)
            idx += 1

        # ── Dimension ────────────────────────────────────────────────────────
        dim_numeric = [
            ("offset",         "Offset"),
            ("arc_radius",     "Arc Radius"),
            ("arrow_size",     "Arrow Size"),
            ("dim_text_height","Text Height"),
        ]
        dim_string = [("text_override", "Text Override")]
        dim_present = any(k in props for k, _ in dim_numeric + dim_string)
        if dim_present:
            dim_grp = CategoryGroup("Dimension")
            for key, label in dim_numeric:
                if key in props:
                    ed = NumericEditor(props[key])
                    ed.valueChanged.connect(lambda v, k=key: self.propertyChanged.emit(k, v))
                    dim_grp.add_row(label, ed)
            for key, label in dim_string:
                if key in props:
                    ed = StringEditor(props[key])
                    ed.valueChanged.connect(lambda v, k=key: self.propertyChanged.emit(k, v))
                    dim_grp.add_row(label, ed)
            self.categories_layout.insertWidget(idx, dim_grp)
            idx += 1

    # -----------------------------------------------------------------------
    # Property merging across multi-selection
    # -----------------------------------------------------------------------
    @staticmethod
    def _merge_properties(objects: list[dict]) -> dict:
        """Combine all object property dicts. Differing values become VARIES."""
        if not objects:
            return {}

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
