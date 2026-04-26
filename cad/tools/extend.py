import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF, QLineF, QEvent
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ReplaceEntityCommand

WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_BOUNDARY = 0
STATE_EXTEND = 1


class ExtendTool(BaseTool):
    """Click near the end of a line to extend it to the nearest other entity."""

    name = "extend"

    def __init__(self):
        super().__init__()
        self._state = STATE_BOUNDARY
        self._boundaries: set = set()
        self._hovered_entity = None
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False
        self._double_click = False
        self._last_click_was_double = False
        self._hover_scene_pt: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return False

    @property
    def prompt(self) -> str:
        if self._state == STATE_BOUNDARY:
            return f"EXTEND  Boundaries [Enter=all]  ({len(self._boundaries)})"
        return "EXTEND  Click endpoint to extend"

    def activate(self, view):
        super().activate(view)
        view.cad_scene.clear_selection()
        self._state = STATE_BOUNDARY
        self._boundaries.clear()
        self._hovered_entity = None
        self._hover_scene_pt = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._double_click = False
        self._last_click_was_double = False

    def deactivate(self):
        self._clear_boundaries()
        self._state = STATE_BOUNDARY
        self._hovered_entity = None
        self._hover_scene_pt = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._double_click = False
        self._last_click_was_double = False
        super().deactivate()

    def on_key(self, event):
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            return
        if self._state == STATE_BOUNDARY:
            self._confirm_boundaries()
        else:
            self._exit_to_select()

    def finish(self):
        if self._state == STATE_BOUNDARY:
            self._confirm_boundaries()
        else:
            self._exit_to_select()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._last_click_was_double and event.type() != QEvent.Type.MouseButtonDblClick:
            self._last_click_was_double = False
            return
        self._press_vp = event.position().toPoint()
        self._cur_vp = self._press_vp
        self._dragging = False
        self._double_click = event.type() == QEvent.Type.MouseButtonDblClick
        if self._double_click:
            self._last_click_was_double = True

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        if self._state == STATE_EXTEND:
            self._hovered_entity = _hit_entity(self.view.cad_scene.all_entities(), raw,
                                               6.0 / self.view.transform().m11())
            self._hover_scene_pt = QPointF(raw) if self._hovered_entity is not None else None
        else:
            self._hovered_entity = None
            self._hover_scene_pt = None
        if self._press_vp is None:
            if self.view:
                self.view.viewport().update()
            return
        self._cur_vp = event.position().toPoint()
        dx = abs(self._cur_vp.x() - self._press_vp.x())
        dy = abs(self._cur_vp.y() - self._press_vp.y())
        if not self._dragging and (dx > DRAG_THRESHOLD or dy > DRAG_THRESHOLD):
            self._dragging = True
        if self.view:
            self.view.viewport().update()

    def on_release(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._press_vp is None:
            return
        if self._state == STATE_BOUNDARY:
            if self._dragging:
                self._finish_boundary_box(event.position().toPoint())
            else:
                self._toggle_boundary(snapped)
        elif self._dragging:
            p1 = self.view.mapToScene(self._press_vp)
            p2 = self.view.mapToScene(event.position().toPoint())
            self._do_box_extend(p1, p2)
        else:
            self._do_extend(snapped, through=self._double_click)
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._double_click = False
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._clear_boundaries()
        self._state = STATE_BOUNDARY
        self._hovered_entity = None
        self._hover_scene_pt = None
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._double_click = False
        self._last_click_was_double = False
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._hovered_entity is not None and self._state == STATE_EXTEND:
            _draw_entities(painter, self.view, [self._hovered_entity], QColor("#00ffff"), 2)
            preview = self._extension_preview(self._hover_scene_pt)
            if preview is not None:
                start, end = preview
                painter.setPen(QPen(QColor("#ffffff"), 1, Qt.PenStyle.DashLine))
                painter.drawLine(self.view.mapFromScene(start), self.view.mapFromScene(end))
        if self._dragging and self._press_vp is not None and self._cur_vp is not None:
            crossing = self._cur_vp.x() < self._press_vp.x()
            fill = CRS_FILL if crossing else WIN_FILL
            border = CRS_BORDER if crossing else WIN_BORDER
            style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
            painter.setPen(QPen(border, 1, style))
            painter.setBrush(QBrush(fill))
            painter.drawRect(_make_rect(self._press_vp, self._cur_vp))

    def _confirm_boundaries(self):
        if not self._boundaries:
            self._boundaries = set(self.view.cad_scene.all_entities())
            for ent in self._boundaries:
                ent.selected = True
        for ent in self._boundaries:
            ent.selected = False
        self._state = STATE_EXTEND
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._hovered_entity = None
        self._hover_scene_pt = None
        if self.view:
            self.view.viewport().update()

    def _exit_to_select(self):
        view = self.view
        self.cancel()
        if view and view._select_tool:
            view.set_tool(view._select_tool)
            view._notify_tool_change("select")

    def _toggle_boundary(self, scene_pt: QPointF):
        hit = _hit_entity(self.view.cad_scene.all_entities(), scene_pt,
                          6.0 / self.view.transform().m11())
        if hit is None:
            return
        if hit in self._boundaries:
            self._boundaries.remove(hit)
            hit.selected = False
        else:
            self._boundaries.add(hit)
            hit.selected = True

    def _finish_boundary_box(self, vp_end: QPoint):
        start = self._press_vp
        s_scene = self.view.mapToScene(start)
        e_scene = self.view.mapToScene(vp_end)
        rect = QRectF(s_scene, e_scene).normalized()
        crossing = vp_end.x() < start.x()
        for ent in self.view.cad_scene.all_entities():
            if ent.intersects_rect(rect, crossing):
                self._boundaries.add(ent)
                ent.selected = True

    def _clear_boundaries(self):
        for ent in self._boundaries:
            ent.selected = False
        self._boundaries.clear()

    # ── Extend logic ──────────────────────────────────────────────────────────

    def _do_extend(self, click_pt: QPointF, through: bool = False):
        scene     = self.view.cad_scene
        entities  = scene.all_entities()
        boundaries = [ent for ent in self._boundaries if ent in entities]
        if not boundaries:
            return

        target = self._find_extend_target(click_pt, entities, boundaries)
        if target is None:
            return
        hit_entity, hit_seg_idx, extend_end, fixed_end, endpoint, direction = target
        origin = endpoint

        dir_len  = math.hypot(direction.x(), direction.y())
        if dir_len < 1e-9:
            return

        steps = 0
        while True:
            best = _find_next_boundary(origin, direction, boundaries, hit_entity)
            if best is None:
                break
            _, best_pt = best
            new_ent = _rebuild_segment(hit_entity, hit_seg_idx,
                                       fixed_end, best_pt, extend_end)
            if new_ent is None:
                return
            self.view.undo_stack.push(ReplaceEntityCommand(scene, hit_entity, new_ent))
            hit_entity = new_ent
            origin = best_pt
            steps += 1
            if not through:
                break

        if steps and self.view:
            self.view.viewport().update()

    def _find_extend_target(self, click_pt: QPointF, entities: list, boundaries: list):
        scale = self.view.transform().m11()
        threshold = 10.0 / scale
        hit_entity = None
        extend_end = None
        best_dist = threshold
        hit_seg_idx = 0
        endpoint = None
        fixed_end = None
        direction = None

        for ent in entities:
            segs = _entity_segments(ent)
            for i, (a, b) in enumerate(segs):
                for end_pt, side in ((a, 'a'), (b, 'b')):
                    d = math.hypot(click_pt.x()-end_pt.x(), click_pt.y()-end_pt.y())
                    if d >= best_dist:
                        continue
                    if _point_touches_boundary(end_pt, boundaries, ent, threshold):
                        continue
                    best_dist = d
                    hit_entity = ent
                    extend_end = side
                    hit_seg_idx = i
                    endpoint = end_pt
                    if side == 'b':
                        fixed_end = a
                        direction = QPointF(b.x()-a.x(), b.y()-a.y())
                    else:
                        fixed_end = b
                        direction = QPointF(a.x()-b.x(), a.y()-b.y())

        if hit_entity is None:
            return None
        return hit_entity, hit_seg_idx, extend_end, fixed_end, endpoint, direction

    def _extension_preview(self, scene_pt: QPointF | None):
        if scene_pt is None:
            return None
        entities = self.view.cad_scene.all_entities()
        boundaries = [ent for ent in self._boundaries if ent in entities]
        if not boundaries:
            return None
        target = self._find_extend_target(scene_pt, entities, boundaries)
        if target is None:
            return None
        hit_entity, _seg_idx, _side, _fixed, endpoint, direction = target
        best = _find_next_boundary(endpoint, direction, boundaries, hit_entity)
        if best is None:
            return None
        _, best_pt = best
        return endpoint, best_pt

    def _do_box_extend(self, p1: QPointF, p2: QPointF):
        scene = self.view.cad_scene
        entities = scene.all_entities()
        boundaries = [ent for ent in self._boundaries if ent in entities]
        if not boundaries:
            return
        scale = self.view.transform().m11()
        threshold = 10.0 / scale
        rect = QRectF(p1, p2).normalized()
        rect = rect.adjusted(-threshold, -threshold, threshold, threshold)

        for ent in entities:
            segs = _entity_segments(ent)
            for i, (a, b) in enumerate(segs):
                for end_pt, side in [(a, 'a'), (b, 'b')]:
                    if rect.contains(end_pt):
                        if _point_touches_boundary(end_pt, boundaries, ent, threshold):
                            continue
                        if side == 'b':
                            origin = b
                            direction = QPointF(b.x()-a.x(), b.y()-a.y())
                            fixed = a
                        else:
                            origin = a
                            direction = QPointF(a.x()-b.x(), a.y()-b.y())
                            fixed = b
                        best_pt2 = None
                        dir_len = math.hypot(direction.x(), direction.y())
                        if dir_len < 1e-9:
                            continue
                        best = _find_next_boundary(origin, direction, boundaries, ent)
                        if best is not None:
                            _, best_pt2 = best
                        if best_pt2 is not None:
                            new_ent = _rebuild_segment(ent, i, fixed, best_pt2, side)
                            if new_ent is not None:
                                self.view.undo_stack.push(ReplaceEntityCommand(scene, ent, new_ent))
                                break
        if self.view:
            self.view.viewport().update()


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _entity_segments(ent) -> list[tuple[QPointF, QPointF]]:
    if isinstance(ent, LineEntity):
        return [(ent.p1, ent.p2)]
    if isinstance(ent, PolylineEntity):
        return ent.segments()
    return []


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x()-a.x(), b.y()-a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x()-a.x(), p.y()-a.y())
    t = max(0.0, min(1.0, ((p.x()-a.x())*dx + (p.y()-a.y())*dy) / (dx*dx+dy*dy)))
    return math.hypot(p.x()-(a.x()+t*dx), p.y()-(a.y()+t*dy))


def _point_touches_boundary(pt: QPointF, entities: list, owning_ent, tol: float) -> bool:
    for other in entities:
        if other is owning_ent:
            continue
        for a, b in _entity_segments(other):
            if _seg_dist(pt, a, b) <= tol:
                return True
    return False


def _find_next_boundary(origin: QPointF, direction: QPointF, boundaries: list, owning_ent):
    best_t = None
    best_pt = None
    dir_len = math.hypot(direction.x(), direction.y())
    if dir_len < 1e-9:
        return None
    for other in boundaries:
        if other is owning_ent:
            continue
        for oa, ob in _entity_segments(other):
            pt = _line_line_intersect(origin, direction, oa, ob)
            if pt is None:
                continue
            t = ((pt.x()-origin.x())*direction.x() +
                 (pt.y()-origin.y())*direction.y()) / (dir_len * dir_len)
            if t > 1e-6 and (best_t is None or t < best_t):
                best_t = t
                best_pt = pt
    if best_pt is None:
        return None
    return best_t, best_pt


def _line_line_intersect(origin: QPointF, direction: QPointF,
                         c: QPointF, d: QPointF) -> QPointF | None:
    """Intersect ray (origin + t*direction) with segment c→d. Returns point or None."""
    far = QPointF(origin.x() + direction.x() * 1e6,
                  origin.y() + direction.y() * 1e6)
    itype, pt = QLineF(origin, far).intersects(QLineF(c, d))
    if itype == QLineF.IntersectionType.BoundedIntersection:
        return pt
    # Also check unbounded (segment c→d might be on the extending side)
    itype2, pt2 = QLineF(origin, far).intersects(QLineF(c, d))
    return None


def _hit_entity(entities, scene_pt: QPointF, threshold: float):
    for ent in entities:
        if ent.hit_test(scene_pt, threshold):
            return ent
    return None


def _draw_entities(painter: QPainter, view, entities, color: QColor, width: float):
    painter.setPen(QPen(color, width))
    for ent in entities:
        for seg in ent.line_segments():
            painter.drawLine(view.mapFromScene(seg.p1()), view.mapFromScene(seg.p2()))


def _rebuild_segment(ent, seg_idx: int, fixed: QPointF, new_end: QPointF, side: str):
    if isinstance(ent, LineEntity):
        if side == 'b':
            p1, p2 = fixed, new_end
        else:
            p1, p2 = new_end, fixed
        if math.hypot(p2.x()-p1.x(), p2.y()-p1.y()) < 1:
            return None
        return LineEntity(p1, p2, ent.layer, ent.linetype, ent.lineweight)

    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        a_idx = seg_idx
        b_idx = seg_idx + 1
        new_verts = list(verts)
        if side == 'b':
            new_verts[b_idx] = new_end
        else:
            new_verts[a_idx] = new_end
        return PolylineEntity(new_verts, ent.layer, ent.linetype, ent.lineweight)

    return None


def _make_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                 abs(b.x() - a.x()), abs(b.y() - a.y()))
