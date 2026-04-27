from PySide6.QtWidgets import QGraphicsView
from PySide6.QtGui import (
    QPainter, QPen, QColor, QKeySequence, QFont,
    QMouseEvent, QKeyEvent, QWheelEvent, QPolygon
)
from PySide6.QtCore import Qt, QPointF, QRectF, QPoint

from .scene import CADScene
from .snap import SnapManager, SnapResult
from .constants import SnapMode, GRID_UNIT
from .undo import UndoStack, DeleteEntitiesCommand
from .layers import LayerManager
from .tools.base import BaseTool

GRID_MINOR = GRID_UNIT        # 10 scene px = 1 unit
GRID_MAJOR = GRID_UNIT * 10   # 100 scene px = 10 units
SNAP_MARK  = 11               # snap marker size, viewport px
APP_VERSION = "v0.2.0"


class CADView(QGraphicsView):
    def __init__(self, scene: CADScene, undo_stack: UndoStack,
                 snap_manager: SnapManager, layer_manager: LayerManager,
                 status_bar):
        super().__init__(scene)
        self.cad_scene      = scene
        self.undo_stack     = undo_stack
        self.snap_manager   = snap_manager
        self.layer_manager  = layer_manager
        self.status_bar     = status_bar

        self.current_tool: BaseTool | None = None
        self._select_tool:  BaseTool | None = None   # set by window after init
        self._command_bar   = None                   # set by window after init
        self._snap_result:  SnapResult | None = None
        self._hovered_entity = None
        self._show_select_indicator = False
        self._pan_origin:   QPoint | None = None
        self._clipboard:    list = []                # in-memory entity clipboard

        self._setup()

    def _setup(self):
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QColor("#1e1e1e"))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        # Start slightly zoomed so grid lines are visible
        self.scale(1.5, 1.5)

    # ── Tool management ───────────────────────────────────────────────────────

    def set_tool(self, tool: BaseTool):
        if self.current_tool:
            self.current_tool.deactivate()
        self.current_tool = tool
        if tool:
            tool.activate(self)
        self._update_prompt()
        self.viewport().update()

    def _update_prompt(self):
        if self._command_bar and self.current_tool:
            self._command_bar.set_prompt(self.current_tool.prompt)

    # ── Grid ─────────────────────────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)

        zoom = self.transform().m11()

        minor_pen = QPen(QColor("#272727"), 0)
        major_pen = QPen(QColor("#353535"), 0)
        axis_pen  = QPen(QColor("#484848"), 0)

        l = int(rect.left())
        t = int(rect.top())
        r = int(rect.right())
        b = int(rect.bottom())

        if zoom >= 0.25:
            painter.setPen(minor_pen)
            x = l - (l % GRID_MINOR)
            while x <= r:
                painter.drawLine(x, t, x, b)
                x += GRID_MINOR
            y = t - (t % GRID_MINOR)
            while y <= b:
                painter.drawLine(l, y, r, y)
                y += GRID_MINOR

        painter.setPen(major_pen)
        x = l - (l % GRID_MAJOR)
        while x <= r:
            painter.drawLine(x, t, x, b)
            x += GRID_MAJOR
        y = t - (t % GRID_MAJOR)
        while y <= b:
            painter.drawLine(l, y, r, y)
            y += GRID_MAJOR

        painter.setPen(axis_pen)
        painter.drawLine(0, t, 0, b)
        painter.drawLine(l, 0, r, 0)

    # ── Viewport overlays ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_hover_feedback(painter)

        if self.current_tool:
            self.current_tool.draw_overlay(painter)

        if self._snap_result and self._snap_result.mode != SnapMode.GRID:
            self._draw_snap_marker(painter, self._snap_result)

        painter.setPen(QPen(QColor("#555555"), 1))
        painter.setFont(QFont("Arial", 9))
        rect = self.viewport().rect()
        painter.drawText(rect.right() - 70, rect.bottom() - 8, APP_VERSION)

        painter.end()

    def _draw_snap_marker(self, painter: QPainter, snap: SnapResult):
        vp = self.mapFromScene(snap.point)
        s  = SNAP_MARK
        h  = s // 2

        pen = QPen(QColor("#ffff00"), 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if snap.mode == SnapMode.ENDPOINT:
            painter.drawRect(vp.x() - h, vp.y() - h, s, s)
        elif snap.mode == SnapMode.MIDPOINT:
            pts = QPolygon([
                QPoint(vp.x(),     vp.y() - h),
                QPoint(vp.x() + h, vp.y() + h),
                QPoint(vp.x() - h, vp.y() + h),
            ])
            painter.drawPolygon(pts)
        elif snap.mode == SnapMode.CENTER:
            painter.drawEllipse(vp.x() - h, vp.y() - h, s, s)
        elif snap.mode == SnapMode.INTERSECTION:
            # X shape
            painter.drawLine(vp.x() - h, vp.y() - h, vp.x() + h, vp.y() + h)
            painter.drawLine(vp.x() + h, vp.y() - h, vp.x() - h, vp.y() + h)

    def _draw_hover_feedback(self, painter: QPainter):
        if self._hovered_entity is None:
            return
        pen = QPen(QColor('#00ffff'), 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        scale = self.transform().m11()
        for seg in self._hovered_entity.line_segments():
            p1 = self.mapFromScene(seg.p1())
            p2 = self.mapFromScene(seg.p2())
            painter.drawLine(p1, p2)
        from .entities import CircleEntity, ArcEntity, TextEntity
        ent = self._hovered_entity
        if isinstance(ent, CircleEntity):
            c = self.mapFromScene(ent.center)
            r = ent.radius * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(ent, ArcEntity):
            c = self.mapFromScene(ent.center)
            r = ent.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(ent.start_angle * 16), int(ent.span_angle * 16))
        elif isinstance(ent, TextEntity):
            corners = ent._world_corners()
            for i in range(len(corners)):
                a = self.mapFromScene(corners[i])
                b = self.mapFromScene(corners[(i+1) % len(corners)])
                painter.drawLine(a, b)
        if self._show_select_indicator and self._snap_result:
            vp = self.mapFromScene(self._snap_result.point)
            painter.fillRect(vp.x() + 8, vp.y() - 13, 5, 5, QColor('#ffffff'))

    # ── Mouse events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if self.current_tool:
            raw     = self.mapToScene(event.position().toPoint())
            snapped = self._snap_result.point if self._snap_result else raw
            self.current_tool.on_press(snapped, event)
            self._update_prompt()

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        from .entities import TextEntity
        if isinstance(self._hovered_entity, TextEntity):
            text_ent = self._hovered_entity
            if hasattr(self, '_text_tool') and self._text_tool is not None:
                self.set_tool(self._text_tool)
                self._text_tool.begin_edit(text_ent)
                self._update_prompt()
                self.viewport().update()
                return

        if self.current_tool:
            raw     = self.mapToScene(event.position().toPoint())
            snapped = self._snap_result.point if self._snap_result else raw
            self.current_tool.on_press(snapped, event)
            self._update_prompt()

        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Pan
        if self._pan_origin and (event.buttons() & Qt.MouseButton.MiddleButton):
            delta = event.position().toPoint() - self._pan_origin
            self._pan_origin = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y())
            return

        raw    = self.mapToScene(event.position().toPoint())
        extras = (self.current_tool.snap_extras()
                  if self.current_tool else [])
        self._snap_result = self.snap_manager.snap(
            raw, self.cad_scene.all_entities(), self.transform().m11(), extras
        )
        threshold = 6.0 / self.transform().m11()
        self._hovered_entity = None
        for ent in self.cad_scene.all_entities():
            if ent.hit_test(self._snap_result.point, threshold):
                self._hovered_entity = ent
                break
        self._show_select_indicator = self._hovered_entity is not None

        pt = self._snap_result.point
        ux = pt.x() / GRID_UNIT
        uy = -pt.y() / GRID_UNIT   # flip Y for display
        mode_str = (f"   [{self._snap_result.mode.name}]"
                    if self._snap_result.mode != SnapMode.GRID else "")
        self.status_bar.showMessage(f"X: {ux:.3f}   Y: {uy:.3f}{mode_str}")

        if self.current_tool:
            self.current_tool.on_move(self._snap_result.point, raw, event)
        pass

        self.viewport().update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_origin = None
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        if self.current_tool:
            raw     = self.mapToScene(event.position().toPoint())
            snapped = self._snap_result.point if self._snap_result else raw
            self.current_tool.on_release(snapped, event)
            self._update_prompt()

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        current = self.transform().m11()
        new_scale = current * factor
        if new_scale < 0.01 or new_scale > 500:
            return
        self.scale(factor, factor)

    def zoom_extents(self, margin_factor: float = 1.15):
        entities = self.cad_scene.all_entities()
        if not entities:
            return
        from .entities import LineEntity, PolylineEntity, CircleEntity, ArcEntity
        import math
        xs, ys = [], []
        for e in entities:
            if isinstance(e, LineEntity):
                xs += [e.p1.x(), e.p2.x()]; ys += [e.p1.y(), e.p2.y()]
            elif isinstance(e, PolylineEntity):
                for v in e.vertices():
                    xs.append(v.x()); ys.append(v.y())
            elif isinstance(e, CircleEntity):
                xs += [e.center.x()-e.radius, e.center.x()+e.radius]
                ys += [e.center.y()-e.radius, e.center.y()+e.radius]
            elif isinstance(e, ArcEntity):
                xs += [e.center.x()-e.radius, e.center.x()+e.radius]
                ys += [e.center.y()-e.radius, e.center.y()+e.radius]
        if not xs:
            return
        from PySide6.QtCore import QRectF
        rect = QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys))
        if rect.width() < 1 and rect.height() < 1:
            rect = QRectF(rect.center().x()-50, rect.center().y()-50, 100, 100)
        rect = rect.adjusted(-rect.width()*(margin_factor-1)/2,
                              -rect.height()*(margin_factor-1)/2,
                               rect.width()*(margin_factor-1)/2,
                               rect.height()*(margin_factor-1)/2)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    # ── Keyboard ─────────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key  = event.key()
        mods = event.modifiers()
        text = event.text()

        if key == Qt.Key.Key_Escape:
            if self._command_bar and self._command_bar.has_input():
                self._command_bar.clear_input()
            else:
                self._handle_escape()

        elif key == Qt.Key.Key_Space:
            if self._command_bar and self._command_bar.has_input():
                # Space submits the command bar (same as Enter)
                self._command_bar.submit()
            else:
                self._handle_space()

        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._command_bar and self._command_bar.has_input():
                self._command_bar.submit()
            elif self.current_tool:
                self.current_tool.on_key(event)
                self._update_prompt()

        elif key == Qt.Key.Key_Tab:
            if self._command_bar and self._command_bar.has_input():
                self._command_bar.submit()
            elif self.current_tool:
                self.current_tool.on_key(event)
                self._update_prompt()
            return

        elif key == Qt.Key.Key_Backspace and mods == Qt.KeyboardModifier.NoModifier:
            if self._command_bar and self._command_bar.has_input():
                self._command_bar.feed_backspace()
            else:
                self._delete_selected()

        elif key == Qt.Key.Key_Delete:
            self._delete_selected()

        elif key == Qt.Key.Key_F9:
            self.snap_manager.grid_snap_enabled = not self.snap_manager.grid_snap_enabled
            state = "ON" if self.snap_manager.grid_snap_enabled else "OFF"
            self.status_bar.showMessage(f"Grid snap {state}", 2000)

        elif key == Qt.Key.Key_F8:
            self.snap_manager.ortho_enabled = not self.snap_manager.ortho_enabled
            state = "ON" if self.snap_manager.ortho_enabled else "OFF"
            self.status_bar.showMessage(f"Ortho {state}", 2000)
            self.viewport().update()

        elif event.matches(QKeySequence.StandardKey.Undo):
            self.undo_stack.undo()

        elif event.matches(QKeySequence.StandardKey.Redo):
            self.undo_stack.redo()

        elif event.matches(QKeySequence.StandardKey.Copy):
            self._copy_to_clipboard()

        elif event.matches(QKeySequence.StandardKey.Paste):
            self._paste_from_clipboard()

        elif ((mods == Qt.KeyboardModifier.NoModifier or
               mods == Qt.KeyboardModifier.KeypadModifier)
              and text and text.isprintable() and not text.isspace()):
            # Route printable characters to command bar
            if self._command_bar:
                self._command_bar.feed_char(text)

        else:
            if self.current_tool:
                self.current_tool.on_key(event)
                self._update_prompt()

        super().keyPressEvent(event)

    def _handle_escape(self):
        tool = self.current_tool
        if tool is None:
            return
        if tool is self._select_tool:
            self.cad_scene.clear_selection()
        else:
            tool.cancel()
            if self._select_tool:
                self.set_tool(self._select_tool)
                self._notify_tool_change("select")

    def _handle_space(self):
        """
        Space flow (mirrors right-click behaviour + recall):
          active op  → finish/commit, stay in tool (idle)
          tool idle  → exit to select
          select     → recall last drawing tool
        """
        tool = self.current_tool
        if tool is None:
            return
        if tool is self._select_tool:
            if self._on_space_recall:
                self._on_space_recall()
        elif not getattr(tool, "is_idle", True):
            tool.finish()          # commit current op, tool stays active but idle
            self._update_prompt()
        else:
            if self._select_tool:
                self.set_tool(self._select_tool)
                self._notify_tool_change("select")

    def _delete_selected(self):
        selected = self.cad_scene.selected_entities()
        if selected:
            self.undo_stack.push(DeleteEntitiesCommand(self.cad_scene, selected))

    def _copy_to_clipboard(self):
        selected = self.cad_scene.selected_entities()
        if selected:
            self._clipboard = [e.clone() for e in selected]

    def _paste_from_clipboard(self):
        if not self._clipboard:
            return
        from .undo import AddEntityCommand
        PASTE_OFFSET = 20.0
        for proto in self._clipboard:
            e = proto.clone()
            e.translate(PASTE_OFFSET, PASTE_OFFSET)
            self.undo_stack.push(AddEntityCommand(self.cad_scene, e))
        # Shift clipboard so repeated pastes cascade
        for proto in self._clipboard:
            proto.translate(PASTE_OFFSET, PASTE_OFFSET)

    # ── Callbacks set by MainWindow ───────────────────────────────────────────

    def _notify_tool_change(self, name: str):
        if self._on_tool_change:
            self._on_tool_change(name)

    _on_tool_change  = None   # called when view changes tool internally
    _on_space_recall = None   # called when Space is pressed in select mode
