import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..undo import ArrayCommand
from ..constants import GRID_UNIT

WIN_FILL   = QColor(0,100,255,35);  WIN_BORDER = QColor(0,100,255,220)
CRS_FILL   = QColor(0,200,0,35);    CRS_BORDER = QColor(0,200,0,220)
DRAG_THRESHOLD = 6
PREVIEW_COLOR = QColor("#ffffff")

STATE_SELECT       = 0
STATE_TYPE         = 1
STATE_RECT_PARAMS  = 2
STATE_POLAR_CENTER = 3
STATE_POLAR_PARAMS = 4


class ArrayTool(BaseTool):
    name = "array"

    def __init__(self):
        super().__init__()
        self._state = STATE_SELECT
        self._entities: list = []
        self._array_type = "R"
        self._polar_center: QPointF | None = None
        self._cursor: QPointF | None = None
        self._press_vp: QPoint | None = None
        self._cur_vp:   QPoint | None = None
        self._dragging  = False

    @property
    def is_idle(self): return True

    @property
    def prompt(self):
        if self._state == STATE_SELECT:
            return f"ARRAY  Select objects ({len(self._entities)}) [Space/Enter = confirm, Esc = cancel]"
        if self._state == STATE_TYPE:
            return "ARRAY  [R]ectangular or [P]olar:"
        if self._state == STATE_RECT_PARAMS:
            return "ARRAY  Type: rows,cols,x_spacing,y_spacing  (e.g. 3,4,10,10):"
        if self._state == STATE_POLAR_CENTER:
            return "ARRAY  Polar: Specify center point:"
        return "ARRAY  Polar: Type: count,total_angle  (e.g. 6,360):"

    def activate(self, view):
        super().activate(view)
        self._entities = view.cad_scene.selected_entities()
        self._state = STATE_TYPE if self._entities else STATE_SELECT
        self._polar_center = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False

    def deactivate(self):
        self._entities = []; self._polar_center = self._cursor = None
        self._press_vp = self._cur_vp = None
        super().deactivate()

    def on_command(self, cmd: str) -> bool:
        import re
        up = cmd.strip().upper()
        if self._state == STATE_TYPE:
            if up in ("R", "RECT", "RECTANGULAR"):
                self._array_type = "R"; self._state = STATE_RECT_PARAMS; return True
            if up in ("P", "POLAR"):
                self._array_type = "P"; self._state = STATE_POLAR_CENTER; return True
            return False
        if self._state == STATE_SELECT and self._entities:
            if up in ("R", "P"):
                self._state = STATE_TYPE; return self.on_command(cmd)
        if self._state == STATE_RECT_PARAMS:
            parts = re.split(r'[,\s]+', cmd.strip())
            try:
                if len(parts) == 1:
                    r = c = int(parts[0]); dx = dy = 10*GRID_UNIT
                elif len(parts) == 2:
                    r, c = int(parts[0]), int(parts[1]); dx = dy = 10*GRID_UNIT
                elif len(parts) == 3:
                    r, c = int(parts[0]), int(parts[1])
                    dx = dy = float(parts[2]) * GRID_UNIT
                else:
                    r, c = int(parts[0]), int(parts[1])
                    dx = float(parts[2]) * GRID_UNIT
                    dy = float(parts[3]) * GRID_UNIT
                self._apply_rect(r, c, dx, dy); return True
            except (ValueError, IndexError):
                return False
        if self._state == STATE_POLAR_PARAMS:
            parts = re.split(r'[,\s]+', cmd.strip())
            try:
                count = int(parts[0])
                total_angle = float(parts[1]) if len(parts) > 1 else 360.0
                self._apply_polar(count, total_angle); return True
            except (ValueError, IndexError):
                return False
        return False

    def on_key(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._state == STATE_SELECT and self._entities:
                self._state = STATE_TYPE

    def finish(self):
        if self._state == STATE_SELECT and self._entities:
            self._state = STATE_TYPE

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton: return
        if self._state == STATE_SELECT:
            self._press_vp = event.position().toPoint()
            self._cur_vp = self._press_vp; self._dragging = False
        elif self._state == STATE_POLAR_CENTER:
            self._polar_center = QPointF(snapped)
            self._state = STATE_POLAR_PARAMS

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self._state == STATE_SELECT and self._press_vp is not None:
            self._cur_vp = event.position().toPoint()
            dx = abs(self._cur_vp.x()-self._press_vp.x())
            dy = abs(self._cur_vp.y()-self._press_vp.y())
            if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
                self._dragging = True
        if self.view: self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton or self._state != STATE_SELECT:
            return
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._dragging:
            self._finish_box(event.position().toPoint(), shift)
        else:
            self._click_select(snapped, shift)
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def cancel(self):
        self._state = STATE_SELECT; self._entities = []
        self._polar_center = self._cursor = None
        self._press_vp = self._cur_vp = None; self._dragging = False
        if self.view: self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if not self._dragging or self._press_vp is None or self._cur_vp is None: return
        crossing = self._cur_vp.x() < self._press_vp.x()
        fill = CRS_FILL if crossing else WIN_FILL
        border = CRS_BORDER if crossing else WIN_BORDER
        style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
        painter.setPen(QPen(border, 1, style)); painter.setBrush(QBrush(fill))
        painter.drawRect(QRect(min(self._press_vp.x(), self._cur_vp.x()),
                               min(self._press_vp.y(), self._cur_vp.y()),
                               abs(self._cur_vp.x()-self._press_vp.x()),
                               abs(self._cur_vp.y()-self._press_vp.y())))

    def _apply_rect(self, rows: int, cols: int, dx: float, dy: float):
        copies = []
        for r in range(rows):
            for c in range(cols):
                if r == 0 and c == 0: continue
                for ent in self._entities:
                    clone = ent.clone()
                    clone.translate(c*dx, r*dy)
                    copies.append(clone)
        if copies:
            self.view.undo_stack.push(ArrayCommand(self.view.cad_scene, copies))
        self._state = STATE_SELECT; self._entities = []
        if self.view: self.view.viewport().update()

    def _apply_polar(self, count: int, total_angle: float):
        if self._polar_center is None or count < 2: return
        cx, cy = self._polar_center.x(), self._polar_center.y()
        step = total_angle / count
        copies = []
        for i in range(1, count):
            angle = step * i
            for ent in self._entities:
                clone = ent.clone()
                clone.rotate_about(cx, cy, angle)
                copies.append(clone)
        if copies:
            self.view.undo_stack.push(ArrayCommand(self.view.cad_scene, copies))
        self._polar_center = None; self._state = STATE_SELECT; self._entities = []
        if self.view: self.view.viewport().update()

    def _click_select(self, scene_pt: QPointF, shift: bool):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if ent.hit_test(scene_pt, threshold): hit = ent; break
        if not shift: scene.clear_selection()
        if hit: hit.selected = False if (shift and hit.selected) else True
        self._entities = scene.selected_entities()

    def _finish_box(self, vp_end: QPoint, shift: bool):
        scene = self.view.cad_scene
        s = self.view.mapToScene(self._press_vp); e = self.view.mapToScene(vp_end)
        rect = QRectF(s, e).normalized()
        crossing = vp_end.x() < self._press_vp.x()
        scene.select_in_rect(rect, crossing, add=shift)
        self._entities = scene.selected_entities()
