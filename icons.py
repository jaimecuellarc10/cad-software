"""
Icon abstraction layer.

Currently backed by QtAwesome (Material Design Icons). When you build
custom SVGs later, only swap the implementation in IconProvider.icon() —
all call sites stay the same.

Usage:
    from icons import Icons
    button.setIcon(Icons.LINE)
    button.setIcon(Icons.get("rotate"))
"""

import qtawesome as qta
from PySide6.QtGui import QIcon

from theme import Colors


# Default icon color matches AutoCAD's two-tone style: light gray base.
# Active/hover variants are handled per-button via QtAwesome's animation API
# or by re-rendering with a different color.
_DEFAULT_COLOR = Colors.TEXT
_ACCENT_COLOR = Colors.ACCENT
_DISABLED_COLOR = Colors.TEXT_DISABLED


class IconProvider:
    """Single point of indirection between code and icon backend."""

    # Map of semantic name -> MDI icon id.
    # When swapping to custom SVGs, change this map's values to ":/icons/line.svg" etc.
    # and update icon() to use QIcon(path) instead.
    _MAP = {
        # Draw
        "line":         "mdi6.vector-line",
        "polyline":     "mdi6.vector-polyline",
        "circle":       "mdi6.circle-outline",
        "arc":          "mdi6.vector-radius",
        "rectangle":    "mdi6.rectangle-outline",
        "ellipse":      "mdi6.ellipse-outline",
        "hatch":        "mdi6.texture-box",

        # Modify
        "move":         "mdi6.cursor-move",
        "copy":         "mdi6.content-copy",
        "rotate":       "mdi6.rotate-left",
        "mirror":       "mdi6.flip-horizontal",
        "scale":        "mdi6.resize",
        "stretch":      "mdi6.arrow-expand-horizontal",
        "trim":         "mdi6.content-cut",
        "extend":       "mdi6.arrow-expand-right",
        "fillet":       "mdi6.vector-arrange-above",
        "chamfer":      "mdi6.vector-polygon",
        "array":        "mdi6.view-grid-outline",
        "offset":       "mdi6.vector-difference",
        "erase":        "mdi6.eraser",
        "explode":      "mdi6.scatter-plot",

        # File / app
        "new":          "mdi6.file-outline",
        "open":         "mdi6.folder-open-outline",
        "save":         "mdi6.content-save-outline",
        "export-pdf":   "mdi6.file-pdf-box",
        "export-dxf":   "mdi6.file-export-outline",
        "undo":         "mdi6.undo",
        "redo":         "mdi6.redo",

        # Properties panel
        "expand":       "mdi6.chevron-down",
        "collapse":     "mdi6.chevron-right",
        "color":        "mdi6.palette",
        "layer":        "mdi6.layers-outline",
        "linetype":     "mdi6.dots-horizontal",

        # Status bar
        "grid":         "mdi6.grid",
        "snap":         "mdi6.magnet",
        "ortho":        "mdi6.angle-right",
        "polar":        "mdi6.compass-outline",
    }

    @classmethod
    def get(cls, name: str, color: str | None = None) -> QIcon:
        """Get an icon by semantic name, optionally tinted."""
        mdi_id = cls._MAP.get(name)
        if mdi_id is None:
            # Fallback so missing icons don't crash UI
            return qta.icon("mdi6.help-circle-outline", color=Colors.ERROR)

        return qta.icon(
            mdi_id,
            color=color or _DEFAULT_COLOR,
            color_active=_ACCENT_COLOR,
            color_disabled=_DISABLED_COLOR,
        )


# Convenience attribute access: Icons.LINE is shorter than IconProvider.get("line")
class _IconsAccess:
    def __getattr__(self, name: str) -> QIcon:
        return IconProvider.get(name.lower().replace("_", "-"))

    def get(self, name: str, color: str | None = None) -> QIcon:
        return IconProvider.get(name, color)


Icons = _IconsAccess()
