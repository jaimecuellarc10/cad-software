from PySide6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QLabel, QWidget, QVBoxLayout
)
from PySide6.QtGui import QAction, QKeySequence, QFont
from PySide6.QtCore import Qt

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
    "A": "arc", "AR": "arc", "ARC": "arc",
    # Rectangle
    "REC": "rectangle", "RECT": "rectangle",
    "RECTANGLE": "rectangle", "RECTANG": "rectangle",
    # Move
    "M": "move", "MO": "move", "MOV": "move", "MOVE": "move",
    # Copy
    "CO": "copy", "CP": "copy", "COPY": "copy",
    # Rotate
    "RO": "rotate", "ROT": "rotate", "ROTATE": "rotate",
    # Mirror
    "MI": "mirror", "MIR": "mirror", "MIRROR": "mirror",
    # Trim
    "TR": "trim", "TRIM": "trim",
    # Extend
    "EX": "extend", "EXT": "extend", "EXTEND": "extend",
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
    "move":      {},
    "copy":      {},
    "rotate":    {},
    "trim":      {},
    "extend":    {},
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

        self._last_draw_tool: str | None = None

        self.view._select_tool     = self._select_tool
        self.view._on_tool_change  = self._sync_tool_buttons
        self.view._on_space_recall = self._recall_last_tool

        # ── UI ────────────────────────────────────────────────────────────────
        self._build_draw_toolbar()
        self._build_snap_bar()
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
        tb.addSeparator()
        add("move",      "Move",
            "Move  [M]\nSelect objects first, then pick base point → destination")
        add("copy",      "Copy",
            "Copy  [CO]\nSelect objects first, then pick base point → destination")
        add("rotate",    "Rotate",
            "Rotate  [RO]\nSelect objects first, then pick base point → drag or type angle")
        add("mirror",    "Mirror",
            "Mirror  [MI]\nSelect objects first, then pick 2 mirror-line points\nY+Enter = keep original")
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
        mb   = self.menuBar()
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
            "move":      self._move_tool,
            "copy":      self._copy_tool,
            "rotate":    self._rotate_tool,
            "mirror":    self._mirror_tool,
            "trim":      self._trim_tool,
            "extend":    self._extend_tool,
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
