import os

from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QLabel, QWidget, QVBoxLayout,
    QFileDialog, QMessageBox, QDockWidget,
)
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtCore import Qt

from cad.export import export_dxf, export_pdf, HAS_EZDXF
from cad.properties_panel import PropertiesPanel

from cad.scene import CADScene
from cad.view import CADView
from cad.snap import SnapManager
from cad.constants import SnapMode
from cad.undo import UndoStack
from cad.layers import LayerManager
from cad.command_bar import CommandBar
from cad.tools.select import SelectTool
from cad.tools.line import LineTool
from cad.tools.polyline import PolylineTool
from cad.tools.circle import CircleTool
from cad.tools.arc import ArcTool
from cad.tools.rectangle import RectangleTool
from cad.tools.move import MoveTool
from cad.tools.copy_tool import CopyTool
from cad.tools.rotate import RotateTool
from cad.tools.mirror import MirrorTool
from cad.tools.trim import TrimTool
from cad.tools.extend import ExtendTool
from cad.tools.offset import OffsetTool
from cad.tools.ellipse import EllipseTool
from cad.tools.scale import ScaleTool
from cad.tools.fillet import FilletTool
from cad.tools.chamfer import ChamferTool
from cad.tools.break_tool import BreakTool
from cad.tools.polygon   import PolygonTool
from cad.tools.xline     import XLineTool
from cad.tools.explode   import ExplodeTool
from cad.tools.join_tool import JoinTool
from cad.tools.array     import ArrayTool
from cad.tools.stretch   import StretchTool
from cad.tools.text_tool import TextTool
from cad.tools.dimension import DimLinearTool, DimAngularTool
from cad.tools.hatch     import HatchTool
from cad.tools.spline    import SplineTool
from cad.tools.lengthen  import LengthenTool
from cad.tools.erase     import EraseTool
from cad.tools.point_tool import PointTool

# ── AutoCAD command aliases ───────────────────────────────────────────────────
COMMANDS: dict[str, str] = {
    # Line
    "L": "line", "LI": "line", "LIN": "line", "LINE": "line",
    # Polyline
    "PL": "polyline", "PLI": "polyline", "PLIN": "polyline",
    "PLINE": "polyline", "POLYLINE": "polyline",
    # Circle
    "C": "circle", "CI": "circle", "CIR": "circle",
    "CIRC": "circle", "CIRCLE": "circle",
    # Arc
    "A": "arc", "ARC": "arc",
    # Rectangle
    "REC": "rectangle", "RECT": "rectangle",
    "RECTANGLE": "rectangle", "RECTANG": "rectangle",
    # Ellipse
    "EL": "ellipse", "ELLIPSE": "ellipse",
    # Move
    "M": "move", "MO": "move", "MOV": "move", "MOVE": "move",
    # Scale
    "SC": "scale", "SCALE": "scale",
    # Copy
    "CO": "copy", "CP": "copy", "COPY": "copy",
    # Rotate
    "RO": "rotate", "ROT": "rotate", "ROTATE": "rotate",
    # Mirror
    "MI": "mirror", "MIR": "mirror", "MIRROR": "mirror",
    # Offset
    "O": "offset", "OF": "offset", "OFFSET": "offset",
    # Fillet
    "F": "fillet", "FI": "fillet", "FILLET": "fillet",
    # Chamfer
    "CHA": "chamfer", "CHAMFER": "chamfer",
    # Break
    "BR": "break", "BREAK": "break",
    "POL": "polygon", "POLYGON": "polygon",
    "XLINE": "xline", "XL": "xline", "RAY": "xline",
    "X": "explode", "EXPLODE": "explode",
    "J": "join", "JOIN": "join",
    "AR": "array", "ARRAY": "array",
    "S": "stretch", "STRETCH": "stretch",
    "T": "text", "TEXT": "text", "MT": "text", "MTEXT": "text",
    "DIM": "dimlinear", "DIMLINEAR": "dimlinear", "DLI": "dimlinear",
    "DIMANGULAR": "dimangular", "DAN": "dimangular",
    "H": "hatch", "HATCH": "hatch", "BH": "hatch",
    "SPL": "spline", "SPLINE": "spline",
    "LEN": "lengthen", "LENGTHEN": "lengthen",
    "E": "erase", "ERASE": "erase", "DEL": "erase",
    "PO": "point", "POINT": "point",
    # Trim
    "TR": "trim", "TRIM": "trim",
    # Extend
    "EX": "extend", "EXT": "extend", "EXTEND": "extend",
    # Zoom extents
    "ZE": "zoom_extents", "EXTENTS": "zoom_extents", "ZOOM": "zoom_extents",
}

# Tool options (sub-commands while a tool is active)
TOOL_OPTIONS: dict[str, dict[str, str]] = {
    "polyline":  {"C": "close", "CLOSE": "close"},
    "mirror":    {"Y": "keep_original", "YES": "keep_original",
                  "N": "no_copy",       "NO":  "no_copy"},
    "line":      {},
    "circle":    {},
    "arc":       {},
    "rectangle": {},
    "ellipse":   {},
    "move":      {},
    "scale":     {},
    "copy":      {},
    "rotate":    {},
    "trim":      {},
    "extend":    {},
    "offset":    {},
    "fillet":    {},
    "chamfer":   {},
    "break":     {},
    "polygon":   {},
    "xline":     {},
    "explode":   {},
    "join":      {},
    "array":     {},
    "stretch":   {},
    "text":      {},
    "dimlinear": {},
    "dimangular": {},
    "hatch":     {},
    "spline":    {},
    "lengthen":  {},
    "erase":     {},
    "point":     {},
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CAD")
        self.resize(1440, 900)

        # ── Core systems ──────────────────────────────────────────────────────
        self.layer_manager = LayerManager()
        self.undo_stack    = UndoStack()
        self.snap_manager  = SnapManager()
        self.scene         = CADScene()

        # ── Status bar ────────────────────────────────────────────────────────
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        coord_label = QLabel("X: 0.000   Y: 0.000")
        coord_label.setFont(QFont("Courier New", 10))
        coord_label.setMinimumWidth(260)
        self.status.addPermanentWidget(coord_label)

        # ── View ──────────────────────────────────────────────────────────────
        self.view = CADView(
            self.scene, self.undo_stack,
            self.snap_manager, self.layer_manager,
            self.status,
        )

        # ── Command bar ───────────────────────────────────────────────────────
        self._cmd_bar = CommandBar()
        self._cmd_bar.submitted.connect(self._on_command)
        self._cmd_bar._view_ref = self.view
        self.view._command_bar  = self._cmd_bar

        # ── Central widget: view + command bar stacked ─────────────────────
        central = QWidget()
        vlay    = QVBoxLayout(central)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)
        vlay.addWidget(self.view)
        vlay.addWidget(self._cmd_bar)
        self.setCentralWidget(central)

        # ── Tools ─────────────────────────────────────────────────────────────
        self._select_tool    = SelectTool()
        self._line_tool      = LineTool()
        self._polyline_tool  = PolylineTool()
        self._circle_tool    = CircleTool()
        self._arc_tool       = ArcTool()
        self._rectangle_tool = RectangleTool()
        self._move_tool      = MoveTool()
        self._copy_tool      = CopyTool()
        self._rotate_tool    = RotateTool()
        self._mirror_tool    = MirrorTool()
        self._trim_tool      = TrimTool()
        self._extend_tool    = ExtendTool()
        self._offset_tool    = OffsetTool()
        self._ellipse_tool   = EllipseTool()
        self._scale_tool     = ScaleTool()
        self._fillet_tool    = FilletTool()
        self._chamfer_tool   = ChamferTool()
        self._break_tool     = BreakTool()
        self._polygon_tool   = PolygonTool()
        self._xline_tool     = XLineTool()
        self._explode_tool   = ExplodeTool()
        self._join_tool      = JoinTool()
        self._array_tool     = ArrayTool()
        self._stretch_tool   = StretchTool()
        self._text_tool      = TextTool()
        self._dimlinear_tool = DimLinearTool()
        self._dimangular_tool = DimAngularTool()
        self._hatch_tool     = HatchTool()
        self._spline_tool    = SplineTool()
        self._lengthen_tool  = LengthenTool()
        self._erase_tool     = EraseTool()
        self._point_tool     = PointTool()

        self._last_draw_tool: str | None = None
        self._current_file:   str | None = None
        self._save_idx:       int        = -1   # undo._idx at last save

        self.view._select_tool     = self._select_tool
        self.view._text_tool       = self._text_tool
        self.view._on_tool_change  = self._sync_tool_buttons
        self.view._on_space_recall = self._recall_last_tool
        self.view._on_tool_done    = lambda: self._activate_tool("select")

        # ── UI ────────────────────────────────────────────────────────────────
        self._build_draw_toolbar()
        self._build_snap_bar()
        self._build_properties_dock()
        self._build_menu()

        self._activate_tool("select")

    # ── Draw toolbar (left) ───────────────────────────────────────────────────

    def _build_draw_toolbar(self):
        tb = QToolBar("Draw")
        tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb)

        self._tool_actions: dict[str, QAction] = {}

        def add(name, label, tip=None):
            a = QAction(label, self)
            a.setCheckable(True)
            if tip:
                a.setToolTip(tip)
            a.triggered.connect(lambda _c, n=name: self._activate_tool(n))
            tb.addAction(a)
            self._tool_actions[name] = a

        add("select",    "Select",
            "Select / modify  [click or drag]")
        tb.addSeparator()
        add("line",      "Line",
            "Line  [L]\nClick start → click end, chains\nSpace/Enter = done  Esc = cancel")
        add("polyline",  "Polyline",
            "Polyline  [PL]\nClick vertices  Space/Enter = done\nC+Enter = close  Esc = cancel")
        add("circle",    "Circle",
            "Circle  [C]\nClick centre → click radius point")
        add("arc",       "Arc",
            "Arc 3-pt  [A]\nClick start → point on arc → end point")
        add("rectangle", "Rectangle",
            "Rectangle  [REC]\nClick corner → click opposite corner")
        add("ellipse",  "Ellipse",
            "Ellipse  [EL]\nClick center -> axis1 endpoint -> axis2 half-length")
        add("polygon", "Polygon", "Polygon  [POL]\nType sides, pick center, pick/type radius")
        add("xline",   "XLine",   "XLine  [XLINE]\nInfinite construction line")
        add("point",   "Point",   "Point  [PO]\nPlace points")
        add("text",    "Text",    "Text  [T]\nPick insertion point, then type text")
        add("spline",  "Spline",  "Spline  [SPL]\nClick control points, Enter/Space = done")
        add("hatch",   "Hatch",   "Hatch  [H]\nClick inside a closed region")
        add("dimlinear", "Dim Lin", "Linear dimension  [DLI]\nPick two points, then offset")
        add("dimangular", "Dim Ang", "Angular dimension  [DAN]\nPick vertex and two rays")
        tb.addSeparator()
        add("move",      "Move",
            "Move  [M]\nSelect objects first, then pick base point → destination")
        add("copy",      "Copy",
            "Copy  [CO]\nSelect objects first, then pick base point → destination")
        add("rotate",    "Rotate",
            "Rotate  [RO]\nSelect objects first, then pick base point → drag or type angle")
        add("mirror",    "Mirror",
            "Mirror  [MI]\nSelect objects first, then pick 2 mirror-line points\nY+Enter = keep original")
        add("offset",    "Offset",
            "Offset  [O]\nSpecify distance, pick object, click side")
        add("scale",    "Scale",
            "Scale  [SC]\nSelect, pick base, drag or type factor")
        add("fillet",   "Fillet",
            "Fillet  [F]\nType radius, click two lines")
        add("chamfer",  "Chamfer",
            "Chamfer  [CHA]\nType distances, click two lines")
        add("break",    "Break",
            "Break  [BR]\nClick entity at first break point, then second")
        add("array",   "Array",   "Array  [AR]\nSelect → [R]ect rows,cols,dx,dy or [P]olar count,angle")
        add("stretch", "Stretch", "Stretch  [S]\nDrag crossing window over vertices, then base→dest")
        add("explode", "Explode", "Explode  [X]\nBreak polyline into individual line segments")
        add("join",    "Join",    "Join  [J]\nMerge touching lines/polylines into one polyline")
        add("lengthen", "Lengthen", "Lengthen  [LEN]\nType delta, then click an endpoint")
        add("erase",    "Erase", "Erase  [E]\nSelect objects, Enter/Space = delete")
        tb.addSeparator()
        add("trim",      "Trim",
            "Trim  [TR]\nClick the part of a line to trim (needs intersecting geometry)")
        add("extend",    "Extend",
            "Extend  [EX]\nClick near the end of a line to extend it to another entity")

    # ── Snap toggle bar (bottom) ──────────────────────────────────────────────

    def _build_snap_bar(self):
        sb = QToolBar("Object Snap")
        sb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, sb)

        lbl = QLabel("  OSNAP: ")
        lbl.setFont(QFont("Courier New", 9))
        sb.addWidget(lbl)

        grid = QAction("Grid", self)
        grid.setCheckable(True)
        grid.setChecked(self.snap_manager.grid_snap_enabled)
        grid.setToolTip("GRID snap  [F9]")
        grid.toggled.connect(self._toggle_grid_snap)
        sb.addAction(grid)

        ortho = QAction("Ortho", self)
        ortho.setCheckable(True)
        ortho.setChecked(self.snap_manager.ortho_enabled)
        ortho.setToolTip("ORTHO  [F8]")
        ortho.toggled.connect(self._toggle_ortho)
        sb.addAction(ortho)

        snap_defs = [
            (SnapMode.ENDPOINT,     "Endpoint",     "ENDpoint  —  yellow square"),
            (SnapMode.MIDPOINT,     "Midpoint",     "MIDpoint  —  yellow triangle"),
            (SnapMode.CENTER,       "Center",       "CENTER  —  yellow circle"),
            (SnapMode.INTERSECTION, "Intersection", "INTersection  —  yellow X"),
        ]

        self._snap_actions: dict[SnapMode, QAction] = {}
        for mode, label, tip in snap_defs:
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(mode in self.snap_manager.active_modes)
            a.setToolTip(tip)
            a.toggled.connect(lambda checked, m=mode: self._toggle_snap(m, checked))
            sb.addAction(a)
            self._snap_actions[mode] = a

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────────
        file_menu = mb.addMenu("File")

        new_action = file_menu.addAction("New")
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self._new_file)

        open_action = file_menu.addAction("Open…")
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)

        file_menu.addSeparator()

        save_action = file_menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_file)

        save_as_action = file_menu.addAction("Save As…")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_as_file)

        file_menu.addSeparator()

        import_dxf_action = file_menu.addAction("Import DXF…")
        import_dxf_action.triggered.connect(self._import_dxf)

        file_menu.addSeparator()

        export_dxf_action = file_menu.addAction("Export DXF…")
        export_dxf_action.setShortcut("Ctrl+Shift+D")
        export_dxf_action.triggered.connect(self._export_dxf)

        export_pdf_action = file_menu.addAction("Export PDF…")
        export_pdf_action.setShortcut("Ctrl+Shift+P")
        export_pdf_action.triggered.connect(self._export_pdf)

        # ── Edit ──────────────────────────────────────────────────────────────
        edit = mb.addMenu("Edit")

        undo = edit.addAction("Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        undo.triggered.connect(self.undo_stack.undo)

        redo = edit.addAction("Redo")
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        redo.triggered.connect(self.undo_stack.redo)

        edit.addSeparator()

        delete = edit.addAction("Delete selected")
        delete.setShortcut("Delete")
        delete.triggered.connect(self.view._delete_selected)

        # ── View ──────────────────────────────────────────────────────────────
        view_menu = mb.addMenu("View")
        props_action = self._props_dock.toggleViewAction()
        props_action.setText("Properties Panel")
        props_action.setShortcut("Ctrl+Shift+I")
        view_menu.addAction(props_action)

    # ── Properties dock ───────────────────────────────────────────────────────

    def _build_properties_dock(self):
        self._props_panel = PropertiesPanel(self.scene, self.view)
        self._props_dock = QDockWidget("Properties", self)
        self._props_dock.setWidget(self._props_panel)
        self._props_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea |
                                         Qt.DockWidgetArea.LeftDockWidgetArea)
        self._props_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable  |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._props_dock)

    # ── File operations ───────────────────────────────────────────────────────

    def _is_dirty(self) -> bool:
        return self.undo_stack._idx != self._save_idx

    def _confirm_save_if_needed(self) -> bool:
        """Returns True if caller may proceed, False if user cancelled."""
        if not self._is_dirty() and not self.scene.all_entities():
            return True
        if not self._is_dirty():
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "The drawing has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save   |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._save_file()
        if reply == QMessageBox.StandardButton.Discard:
            return True
        return False  # Cancel

    def _update_title(self):
        if self._current_file:
            self.setWindowTitle(f"CAD — {os.path.basename(self._current_file)}")
        else:
            self.setWindowTitle("CAD")

    def _new_file(self):
        if not self._confirm_save_if_needed():
            return
        self.scene.clear_all()
        self.undo_stack._stack.clear()
        self.undo_stack._idx = -1
        self._current_file = None
        self._save_idx      = -1
        self._activate_tool("select")
        self._update_title()

    def _open_file(self):
        if not self._confirm_save_if_needed():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open CAD File", "", "CAD Files (*.cad);;All Files (*.*)"
        )
        if not path:
            return
        try:
            from cad.file_io import load_file
            load_file(self.scene, self.layer_manager, path)
            self.undo_stack._stack.clear()
            self.undo_stack._idx = -1
            self._current_file = path
            self._save_idx      = -1
            self._activate_tool("select")
            self._update_title()
            self.view.zoom_extents()
            self.status.showMessage(f"Opened: {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Open failed", str(exc))

    def _save_file(self) -> bool:
        if not self._current_file:
            return self._save_as_file()
        try:
            from cad.file_io import save_file
            save_file(self.scene, self._current_file)
            self._save_idx = self.undo_stack._idx
            self._update_title()
            self.status.showMessage(f"Saved: {self._current_file}", 5000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False

    def _save_as_file(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save CAD File", "", "CAD Files (*.cad);;All Files (*.*)"
        )
        if not path:
            return False
        if not path.lower().endswith(".cad"):
            path += ".cad"
        try:
            from cad.file_io import save_file
            save_file(self.scene, path)
            self._current_file = path
            self._save_idx     = self.undo_stack._idx
            self._update_title()
            self.status.showMessage(f"Saved: {path}", 5000)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False

    def closeEvent(self, event):
        if self._confirm_save_if_needed():
            event.accept()
        else:
            event.ignore()

    # ── Export ────────────────────────────────────────────────────────────────

    def _import_dxf(self):
        if not HAS_EZDXF:
            QMessageBox.critical(self, "Missing dependency",
                                 "ezdxf is not installed.\n\nRun:  pip install ezdxf")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Import DXF", "", "DXF Files (*.dxf);;All Files (*.*)"
        )
        if not path:
            return
        try:
            from cad.export import import_dxf
            count = import_dxf(self.scene, self.layer_manager, path)
            self.view.zoom_extents()
            self.status.showMessage(f"Imported {count} entities from {path}", 5000)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))

    def _export_dxf(self):
        if not HAS_EZDXF:
            QMessageBox.critical(self, "Missing dependency",
                                 "ezdxf is not installed.\n\n"
                                 "Run:  pip install ezdxf")
            return
        if not self.scene.all_entities():
            QMessageBox.information(self, "Nothing to export", "The drawing is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DXF", "", "DXF Files (*.dxf)"
        )
        if not path:
            return
        try:
            export_dxf(self.scene, path)
            self.status.showMessage(f"Exported: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    def _export_pdf(self):
        if not self.scene.all_entities():
            QMessageBox.information(self, "Nothing to export", "The drawing is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            export_pdf(self.scene, path)
            self.status.showMessage(f"Exported: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ── Command handling ──────────────────────────────────────────────────────

    def _on_command(self, cmd: str):
        if not cmd:
            self._recall_last_tool()
            return

        active = self.view.current_tool

        # Let the active tool handle numeric / special input first
        if active and active is not self._select_tool:
            if hasattr(active, "on_command") and active.on_command(cmd):
                self._cmd_bar.add_history(f"  [{active.name.upper()}] {cmd}")
                self._update_prompt()
                return

            # Check built-in tool options (e.g. "C" in polyline)
            opts = TOOL_OPTIONS.get(active.name, {})
            if cmd in opts:
                action = opts[cmd]
                if action == "close" and hasattr(active, "_finish"):
                    active._finish(close=True)
                    self._activate_tool("select")
                self._cmd_bar.add_history(f"  [{active.name.upper()}] {action}")
                return

        # Global command lookup
        tool_name = COMMANDS.get(cmd)
        if tool_name:
            if tool_name == "zoom_extents":
                self.view.zoom_extents()
            else:
                self._activate_tool(tool_name)
            self._cmd_bar.add_history(f"  {cmd}")
        else:
            self._cmd_bar.add_history(f"  Unknown command: {cmd}")

    def _update_prompt(self):
        if self.view.current_tool and self._cmd_bar:
            self._cmd_bar.set_prompt(self.view.current_tool.prompt)

    # ── Tool activation ───────────────────────────────────────────────────────

    def _activate_tool(self, name: str):
        tool_map = {
            "select":    self._select_tool,
            "line":      self._line_tool,
            "polyline":  self._polyline_tool,
            "circle":    self._circle_tool,
            "arc":       self._arc_tool,
            "rectangle": self._rectangle_tool,
            "ellipse":   self._ellipse_tool,
            "move":      self._move_tool,
            "scale":     self._scale_tool,
            "copy":      self._copy_tool,
            "rotate":    self._rotate_tool,
            "mirror":    self._mirror_tool,
            "trim":      self._trim_tool,
            "extend":    self._extend_tool,
            "offset":    self._offset_tool,
            "fillet":    self._fillet_tool,
            "chamfer":   self._chamfer_tool,
            "break":     self._break_tool,
            "polygon":   self._polygon_tool,
            "xline":     self._xline_tool,
            "explode":   self._explode_tool,
            "join":      self._join_tool,
            "array":     self._array_tool,
            "stretch":   self._stretch_tool,
            "text":      self._text_tool,
            "dimlinear": self._dimlinear_tool,
            "dimangular": self._dimangular_tool,
            "hatch":     self._hatch_tool,
            "spline":    self._spline_tool,
            "lengthen":  self._lengthen_tool,
            "erase":     self._erase_tool,
            "point":     self._point_tool,
        }
        tool = tool_map.get(name)
        if tool is None:
            return
        if name != "select":
            self._last_draw_tool = name
        self._sync_tool_buttons(name)
        self.view.set_tool(tool)

    def _sync_tool_buttons(self, active_name: str):
        for name, action in self._tool_actions.items():
            action.setChecked(name == active_name)

    def _recall_last_tool(self):
        if self._last_draw_tool:
            self._activate_tool(self._last_draw_tool)

    # ── Snap toggles ──────────────────────────────────────────────────────────

    def _toggle_snap(self, mode: SnapMode, enabled: bool):
        if enabled:
            self.snap_manager.active_modes.add(mode)
        else:
            self.snap_manager.active_modes.discard(mode)

    def _toggle_grid_snap(self, enabled: bool):
        self.snap_manager.grid_snap_enabled = enabled

    def _toggle_ortho(self, enabled: bool):
        self.snap_manager.ortho_enabled = enabled
        self.view.viewport().update()
