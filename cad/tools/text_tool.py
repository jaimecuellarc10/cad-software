from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygon
from .base import BaseTool
from ..constants import GRID_UNIT
from ..entities import TextEntity
from ..undo import AddEntityCommand

STATE_POS = 0
STATE_TYPING = 1

_BOX_PAD_H = 6    # horizontal padding each side (viewport pixels)
_BOX_PAD_V = 4    # vertical padding top/bottom (viewport pixels)
_HANDLE_SZ = 10   # resize grip triangle size (viewport pixels)


class TextTool(BaseTool):
    name = "text"

    def __init__(self):
        super().__init__()
        self._state = STATE_POS
        self._pos: QPointF | None = None
        self._height = 2.5
        self._buffer = ""
        self._cursor_pos = 0
        self._font_family = "Arial"
        self._editing_entity: TextEntity | None = None
        self._cursor_visible = True
        self._blink_timer = QTimer()
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._on_blink)
        self._box_w = 0.0        # scene units; 0 = auto-size
        self._resize_dragging = False
        self._drag_start_x = 0.0

    # ── Blink timer ───────────────────────────────────────────────────────────

    def _on_blink(self):
        self._cursor_visible = not self._cursor_visible
        if self.view:
            self.view.viewport().update()

    # ── Tool protocol ─────────────────────────────────────────────────────────

    def wants_raw_keys(self) -> bool:
        return self._state == STATE_TYPING

    @property
    def is_idle(self):
        return self._state == STATE_POS

    @property
    def prompt(self):
        if self._state == STATE_POS:
            return f"TEXT  h={self._height:.1f}  Click to place  [H<val>=height]"
        return f"TEXT  Editing  h={self._height:.1f}  [Enter=commit  Esc=cancel]"

    def activate(self, view):
        super().activate(view)
        self._reset_state()

    def deactivate(self):
        self._reset_state()
        super().deactivate()

    def _reset_state(self):
        self._blink_timer.stop()
        self._state = STATE_POS
        self._pos = None
        self._buffer = ""
        self._cursor_pos = 0
        self._editing_entity = None
        self._cursor_visible = True
        self._resize_dragging = False
        self._box_w = 0.0

    # ── External API ──────────────────────────────────────────────────────────

    def begin_edit(self, ent: TextEntity):
        self._editing_entity = ent
        self._pos = QPointF(ent.pos)
        self._height = ent.height
        self._font_family = ent.font_family
        self._buffer = ent.text
        self._cursor_pos = len(self._buffer)
        self._box_w = 0.0
        self._state = STATE_TYPING
        self._cursor_visible = True
        self._blink_timer.start()
        if self.view:
            self.view.viewport().update()

    # ── Input handlers ────────────────────────────────────────────────────────

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_POS:
            self._pos = QPointF(snapped)
            self._buffer = ""
            self._cursor_pos = 0
            self._box_w = 0.0
            self._state = STATE_TYPING
            self._cursor_visible = True
            self._blink_timer.start()
            if self.view:
                self.view.viewport().update()
        elif self._state == STATE_TYPING:
            vp = event.position()
            if self._hit_resize_handle(vp.x(), vp.y()):
                if self._box_w <= 0:
                    self._box_w = self._auto_box_w_scene()
                self._resize_dragging = True
                self._drag_start_x = vp.x()
            else:
                # Clicking outside the box commits and exits (no new box)
                self._commit()
            if self.view:
                self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._resize_dragging and self.view:
            dx_vp = event.position().x() - self._drag_start_x
            self._drag_start_x = event.position().x()
            scale = self.view.transform().m11()
            self._box_w = max(20.0 / scale, self._box_w + dx_vp / scale)
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._resize_dragging = False

    def on_key(self, event):
        if self._state != STATE_TYPING:
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.cancel()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._commit()
            return
        if key == Qt.Key.Key_Backspace:
            if self._cursor_pos > 0:
                self._buffer = (self._buffer[:self._cursor_pos - 1]
                                + self._buffer[self._cursor_pos:])
                self._cursor_pos -= 1
        elif key == Qt.Key.Key_Delete:
            if self._cursor_pos < len(self._buffer):
                self._buffer = (self._buffer[:self._cursor_pos]
                                + self._buffer[self._cursor_pos + 1:])
        elif key == Qt.Key.Key_Left:
            self._cursor_pos = max(0, self._cursor_pos - 1)
        elif key == Qt.Key.Key_Right:
            self._cursor_pos = min(len(self._buffer), self._cursor_pos + 1)
        elif key == Qt.Key.Key_Home:
            self._cursor_pos = 0
        elif key == Qt.Key.Key_End:
            self._cursor_pos = len(self._buffer)
        else:
            ch = event.text()
            if ch and ch.isprintable():
                self._buffer = (self._buffer[:self._cursor_pos]
                                + ch
                                + self._buffer[self._cursor_pos:])
                self._cursor_pos += 1
        self._cursor_visible = True
        if self.view:
            self.view.viewport().update()

    def on_command(self, cmd: str) -> bool:
        # Only reachable in STATE_POS — STATE_TYPING bypasses command bar
        stripped = cmd.strip()
        if stripped.upper().startswith("H"):
            try:
                self._height = float(stripped[1:])
            except ValueError:
                pass
            else:
                if self.view:
                    self.view._update_prompt()
                    self.view.viewport().update()
                return True
        try:
            self._height = float(stripped)
        except ValueError:
            pass
        else:
            if self.view:
                self.view._update_prompt()
                self.view.viewport().update()
            return True
        coord = self._parse_coord(cmd)
        if coord is not None:
            self._pos = coord
            self._buffer = ""
            self._cursor_pos = 0
            self._box_w = 0.0
            self._state = STATE_TYPING
            self._cursor_visible = True
            self._blink_timer.start()
            if self.view:
                self.view.viewport().update()
            return True
        return False

    # ── Overlay drawing ───────────────────────────────────────────────────────

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_TYPING or self._pos is None or not self.view:
            return
        origin = self.view.mapFromScene(self._pos)
        ox = float(origin.x())
        oy = float(origin.y())
        scale = self.view.transform().m11()

        font_px = max(8, int(self._height * GRID_UNIT * scale))
        font = QFont(self._font_family)
        font.setPixelSize(font_px)
        painter.setFont(font)
        fm = QFontMetrics(font)

        if self._box_w > 0:
            bw_vp = self._box_w * scale
        else:
            bw_vp = max(60.0, fm.horizontalAdvance(self._buffer or "W") + _BOX_PAD_H * 2 + 20)

        bh = font_px + _BOX_PAD_V * 2
        box_l = ox - _BOX_PAD_H
        box_t = oy - font_px - _BOX_PAD_V
        box_rect = QRectF(box_l, box_t, bw_vp + _BOX_PAD_H * 2, bh)

        painter.fillRect(box_rect, QColor(20, 25, 45, 210))
        painter.setPen(QPen(QColor(70, 130, 230), 1, Qt.PenStyle.DashLine))
        painter.drawRect(box_rect)

        painter.setClipRect(box_rect.adjusted(1, 1, -1, -1))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(int(ox), int(oy), self._buffer)
        painter.setClipping(False)

        if self._cursor_visible:
            pre = self._buffer[:self._cursor_pos]
            cx = ox + fm.horizontalAdvance(pre)
            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.drawLine(int(cx), int(oy - font_px + 2), int(cx), int(oy + 2))

        # Resize grip at bottom-right
        hx = int(box_l + bw_vp + _BOX_PAD_H * 2)
        hy = int(box_t + bh)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(70, 130, 230, 200))
        painter.drawPolygon(QPolygon([
            QPoint(hx - _HANDLE_SZ, hy),
            QPoint(hx, hy),
            QPoint(hx, hy - _HANDLE_SZ),
        ]))

    def snap_extras(self):
        return []

    # ── State management ──────────────────────────────────────────────────────

    def cancel(self):
        self._reset_state()
        if self.view:
            self.view.viewport().update()

    def _commit(self):
        if self._pos is None or not self._buffer:
            self.cancel()
            return
        layer = self.view.layer_manager.current
        angle = self._editing_entity.angle_deg if self._editing_entity else 0.0
        new_ent = TextEntity(
            self._pos, self._buffer,
            height=self._height,
            angle_deg=angle,
            layer=layer,
            font_family=self._font_family,
        )
        if self._editing_entity is not None:
            from ..undo import ReplaceEntityCommand
            self.view.undo_stack.push(
                ReplaceEntityCommand(self.view.cad_scene, self._editing_entity, new_ent))
        else:
            self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, new_ent))
        self._reset_state()
        if self.view:
            self.view.viewport().update()

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _auto_box_w_scene(self) -> float:
        if not self.view:
            return 100.0
        scale = self.view.transform().m11()
        font_px = max(8, int(self._height * GRID_UNIT * scale))
        font = QFont(self._font_family)
        font.setPixelSize(font_px)
        fm = QFontMetrics(font)
        bw_vp = max(60.0, fm.horizontalAdvance(self._buffer or "W") + _BOX_PAD_H * 2 + 20)
        return bw_vp / scale

    def _hit_resize_handle(self, vx: float, vy: float) -> bool:
        if self._pos is None or not self.view:
            return False
        origin = self.view.mapFromScene(self._pos)
        ox = float(origin.x())
        oy = float(origin.y())
        scale = self.view.transform().m11()
        font_px = max(8, int(self._height * GRID_UNIT * scale))
        font = QFont(self._font_family)
        font.setPixelSize(font_px)
        fm = QFontMetrics(font)
        if self._box_w > 0:
            bw_vp = self._box_w * scale
        else:
            bw_vp = max(60.0, fm.horizontalAdvance(self._buffer or "W") + _BOX_PAD_H * 2 + 20)
        hx = ox + bw_vp + _BOX_PAD_H
        hy = oy + _BOX_PAD_V
        return abs(vx - hx) <= _HANDLE_SZ and abs(vy - hy) <= _HANDLE_SZ
