import math
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF, QLineF
from PySide6.QtGui import QPen, QColor, QPainter, QBrush
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity, XLineEntity
from ..undo import DeleteEntitiesCommand, ReplaceEntityCommand, SplitEntityCommand

PREVIEW_COLOR = QColor("#ffffff")
WIN_FILL = QColor(0, 100, 255, 35)
WIN_BORDER = QColor(0, 100, 255, 220)
CRS_FILL = QColor(0, 200, 0, 35)
CRS_BORDER = QColor(0, 200, 0, 220)
DRAG_THRESHOLD = 6

STATE_CUTEDGE = 0
STATE_TRIM = 1


class TrimTool(BaseTool):
    """Click on the part of a line/polyline segment you want to remove.
    The segment is trimmed at its intersections with all other entities."""

    name = "trim"

    def __init__(self):
        super().__init__()
        self._state = STATE_CUTEDGE
        self._cut_edges: set = set()
        self._press_vp: QPoint | None = None
        self._cur_vp: QPoint | None = None
        self._dragging = False
        self._last_click_pt: QPointF | None = None

    @property
    def is_idle(self) -> bool:
        return False

    @property
    def prompt(self) -> str:
        if self._state == STATE_CUTEDGE:
            return f"TRIM  Cutting edges [Enter=all]  ({len(self._cut_edges)})"
        return "TRIM  Pick object to trim"

    def activate(self, view):
        super().activate(view)
        view.cad_scene.clear_selection()
        self._state = STATE_CUTEDGE
        self._cut_edges.clear()
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._last_click_pt = None

    def deactivate(self):
        self._clear_cut_edges()
        self._state = STATE_CUTEDGE
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._last_click_pt = None
        super().deactivate()

    def on_key(self, event):
        if event.key() not in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            return
        if self._state == STATE_CUTEDGE:
            if not self._cut_edges:
                self._cut_edges = set(self.view.cad_scene.all_entities())
                for ent in self._cut_edges:
                    ent.selected = True
            self._state = STATE_TRIM
            self._press_vp = None
            self._cur_vp = None
            self._dragging = False
            if self.view:
                self.view.viewport().update()
        else:
            self._exit_to_select()

    def finish(self):
        if self._state == STATE_CUTEDGE:
            if not self._cut_edges:
                self._cut_edges = set(self.view.cad_scene.all_entities())
                for ent in self._cut_edges:
                    ent.selected = True
            self._state = STATE_TRIM
            self._press_vp = None
            self._cur_vp = None
            self._dragging = False
            if self.view:
                self.view.viewport().update()
        else:
            self._exit_to_select()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_vp = event.position().toPoint()
        self._cur_vp = self._press_vp
        self._dragging = False

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._last_click_pt = QPointF(raw)
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
        if self._state == STATE_CUTEDGE:
            if self._dragging:
                self._finish_cutedge_box(event.position().toPoint())
            else:
                self._toggle_cutedge(snapped)
        elif self._dragging:
            p1 = self.view.mapToScene(self._press_vp)
            p2 = self.view.mapToScene(event.position().toPoint())
            self._do_fence_trim(p1, p2)
        else:
            self._do_trim(snapped)
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._clear_cut_edges()
        self._state = STATE_CUTEDGE
        self._press_vp = None
        self._cur_vp = None
        self._dragging = False
        self._last_click_pt = None
        if self.view:
            self.view.viewport().update()

    def _exit_to_select(self):
        view = self.view
        self.cancel()
        if view and view._select_tool:
            view.set_tool(view._select_tool)
            view._notify_tool_change("select")

    def draw_overlay(self, painter: QPainter):
        hovered = getattr(self.view, '_hovered_entity', None) if self.view else None
        if hovered is not None and self._state == STATE_TRIM:
            removed = _trim_removed_segments(hovered, self._last_click_pt,
                                             [ent for ent in self._cut_edges
                                              if ent in self.view.cad_scene.all_entities()])
            if removed:
                painter.setPen(QPen(QColor("#ff4444"), 2, Qt.PenStyle.DashLine))
                for a, b in removed:
                    painter.drawLine(self.view.mapFromScene(a), self.view.mapFromScene(b))
        if not self._dragging or self._press_vp is None or self._cur_vp is None:
            return
        if self._state == STATE_CUTEDGE:
            crossing = self._cur_vp.x() < self._press_vp.x()
            fill = CRS_FILL if crossing else WIN_FILL
            border = CRS_BORDER if crossing else WIN_BORDER
            style = Qt.PenStyle.DashLine if crossing else Qt.PenStyle.SolidLine
            painter.setPen(QPen(border, 1, style))
            painter.setBrush(QBrush(fill))
            painter.drawRect(_make_rect(self._press_vp, self._cur_vp))
        else:
            painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine))
            painter.drawLine(self._press_vp, self._cur_vp)

    # ── Cutting-edge selection ────────────────────────────────────────────────

    def _clear_cut_edges(self):
        for ent in self._cut_edges:
            ent.selected = False
        self._cut_edges.clear()

    def _toggle_cutedge(self, scene_pt: QPointF):
        scene = self.view.cad_scene
        threshold = 6.0 / self.view.transform().m11()
        hit = None
        for ent in scene.all_entities():
            if ent.hit_test(scene_pt, threshold):
                hit = ent
                break
        if hit is None:
            return
        if hit in self._cut_edges:
            self._cut_edges.remove(hit)
            hit.selected = False
        else:
            self._cut_edges.add(hit)
            hit.selected = True

    def _finish_cutedge_box(self, vp_end: QPoint):
        start = self._press_vp
        s_scene = self.view.mapToScene(start)
        e_scene = self.view.mapToScene(vp_end)
        rect = QRectF(s_scene, e_scene).normalized()
        crossing = vp_end.x() < start.x()
        for ent in self.view.cad_scene.all_entities():
            if ent.intersects_rect(rect, crossing):
                self._cut_edges.add(ent)
                ent.selected = True

    # ── Trim logic ────────────────────────────────────────────────────────────

    def _do_trim(self, click_pt: QPointF):
        scene     = self.view.cad_scene
        entities  = scene.all_entities()
        cut_edges = [ent for ent in self._cut_edges if ent in entities]
        if not cut_edges:
            return
        scale     = self.view.transform().m11()
        threshold = 10.0 / scale

        hit_entity  = None
        hit_seg_idx = 0
        best_dist   = threshold

        for ent in entities:
            for i, (a, b) in enumerate(_entity_segments(ent)):
                d = _seg_dist(click_pt, a, b)
                if d < best_dist:
                    best_dist   = d
                    hit_entity  = ent
                    hit_seg_idx = i

        if hit_entity is None:
            return

        self._trim_entity_at(hit_entity, hit_seg_idx, click_pt, cut_edges)
        if self.view:
            self.view.viewport().update()

    def _do_fence_trim(self, p1: QPointF, p2: QPointF):
        scene = self.view.cad_scene
        entities = scene.all_entities()
        cut_edges = [ent for ent in self._cut_edges if ent in entities]
        if not cut_edges:
            return
        targets = []
        for ent in list(entities):
            for i, (a, b) in enumerate(_entity_segments(ent)):
                pt = _seg_seg_intersect(a, b, p1, p2)
                if pt is None:
                    continue
                targets.append((ent, i, pt))
                break
        for ent, i, pt in targets:
            if ent in self.view.cad_scene.all_entities():
                self._trim_entity_at(ent, i, pt, cut_edges)
        if self.view:
            self.view.viewport().update()

    def _trim_entity_at(self, ent, seg_idx: int, click_pt: QPointF, cut_edges: list):
        scene = self.view.cad_scene
        parts = _trim_entity_parts(ent, seg_idx, click_pt, cut_edges)
        if parts is None:
            return
        part1, part2 = parts
        if part1 is None and part2 is None:
            self.view.undo_stack.push(DeleteEntitiesCommand(scene, [ent]))
        elif part1 is not None and part2 is not None:
            self.view.undo_stack.push(SplitEntityCommand(scene, ent, part1, part2))
        else:
            self.view.undo_stack.push(ReplaceEntityCommand(scene, ent, part1 or part2))


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _entity_segments(ent) -> list[tuple[QPointF, QPointF]]:
    if isinstance(ent, LineEntity):
        return [(ent.p1, ent.p2)]
    if isinstance(ent, PolylineEntity):
        return ent.segments()
    if isinstance(ent, XLineEntity):
        rad = math.radians(ent.angle_deg)
        dx = math.cos(rad) * 45000.0
        dy = math.sin(rad) * 45000.0
        center = ent.point
        return [(QPointF(center.x() - dx, center.y() + dy),
                 QPointF(center.x() + dx, center.y() - dy))]
    return []


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x()-a.x(), b.y()-a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x()-a.x(), p.y()-a.y())
    t = max(0.0, min(1.0, ((p.x()-a.x())*dx + (p.y()-a.y())*dy) / (dx*dx+dy*dy)))
    return math.hypot(p.x()-(a.x()+t*dx), p.y()-(a.y()+t*dy))


def _seg_seg_intersect(a: QPointF, b: QPointF,
                       c: QPointF, d: QPointF) -> QPointF | None:
    itype, pt = QLineF(a, b).intersects(QLineF(c, d))
    if itype == QLineF.IntersectionType.BoundedIntersection:
        return pt
    return None


def _segment_line_intersection_t(a: QPointF, b: QPointF,
                                 c: QPointF, d: QPointF) -> float | None:
    dx_ab = b.x()-a.x()
    dy_ab = b.y()-a.y()
    dx_cd = d.x()-c.x()
    dy_cd = d.y()-c.y()
    denom = dx_ab*dy_cd - dy_ab*dx_cd
    if abs(denom) < 1e-10:
        return None
    dx_ac = c.x()-a.x()
    dy_ac = c.y()-a.y()
    t = (dx_ac*dy_cd - dy_ac*dx_cd) / denom
    if t < -1e-6 or t > 1+1e-6:
        return None
    return max(0.0, min(1.0, t))


def _trim_entity_parts(ent, seg_idx: int, click_pt: QPointF, cut_edges: list):
    if isinstance(ent, (LineEntity, XLineEntity)):
        a, b = _entity_segments(ent)[0]
        cuts = _segment_cut_params(ent, seg_idx, a, b, cut_edges)
        if not cuts:
            return None
        click_t = _param_on_segment(click_pt, a, b)
        left_t, right_t = _remove_interval(cuts, click_t, 0.0, 1.0)
        left_pt = _point_at(a, b, left_t)
        right_pt = _point_at(a, b, right_t)
        return (_make_line(a, left_pt, ent),
                _make_line(right_pt, b, ent))

    if isinstance(ent, PolylineEntity):
        segs = ent.segments()
        if not segs:
            return None
        cuts = []
        for i, (a, b) in enumerate(segs):
            for t in _segment_cut_params(ent, i, a, b, cut_edges):
                cuts.append(i + t)
        cuts = _unique_params(cuts)
        if not cuts:
            return None
        a, b = segs[seg_idx]
        click_t = _param_on_segment(click_pt, a, b)
        click_pos = seg_idx + click_t
        left_pos, right_pos = _remove_interval(cuts, click_pos, 0.0, float(len(segs)))
        return (_polyline_part(ent, 0.0, left_pos),
                _polyline_part(ent, right_pos, float(len(segs))))

    return None


def _trim_removed_segments(ent, click_pt: QPointF | None, cut_edges: list):
    if click_pt is None or not cut_edges:
        return []
    segs = _entity_segments(ent)
    if not segs:
        return []
    best_idx = 0
    best_dist = None
    for i, (a, b) in enumerate(segs):
        d = _seg_dist(click_pt, a, b)
        if best_dist is None or d < best_dist:
            best_dist = d
            best_idx = i
    if isinstance(ent, (LineEntity, XLineEntity)):
        a, b = _entity_segments(ent)[0]
        cuts = _segment_cut_params(ent, 0, a, b, cut_edges)
        if not cuts:
            return []
        click_t = _param_on_segment(click_pt, a, b)
        left_t, right_t = _remove_interval(cuts, click_t, 0.0, 1.0)
        return [(_point_at(a, b, left_t), _point_at(a, b, right_t))]
    if isinstance(ent, PolylineEntity):
        cuts = []
        for i, (a, b) in enumerate(segs):
            for t in _segment_cut_params(ent, i, a, b, cut_edges):
                cuts.append(i + t)
        cuts = _unique_params(cuts)
        if not cuts:
            return []
        a, b = segs[best_idx]
        click_pos = best_idx + _param_on_segment(click_pt, a, b)
        left_pos, right_pos = _remove_interval(cuts, click_pos, 0.0, float(len(segs)))
        return _polyline_segments_between(segs, left_pos, right_pos)
    return []


def _segment_cut_params(ent, seg_idx: int, a: QPointF, b: QPointF, cut_edges: list) -> list[float]:
    params = []
    for edge in cut_edges:
        if edge is ent:
            continue
        for c, d in _entity_segments(edge):
            t = _segment_line_intersection_t(a, b, c, d)
            if t is not None:
                params.append(t)
    return _unique_params(params)


def _remove_interval(cuts: list[float], click_pos: float,
                     start_pos: float, end_pos: float) -> tuple[float, float]:
    left = [t for t in cuts if t <= click_pos + 1e-6]
    right = [t for t in cuts if t > click_pos + 1e-6]
    left_pos = left[-1] if left else start_pos
    right_pos = right[0] if right else end_pos
    return left_pos, right_pos


def _param_on_segment(pt: QPointF, a: QPointF, b: QPointF) -> float:
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    l2 = dx*dx + dy*dy
    if l2 < 1e-12:
        return 0.0
    return max(0.0, min(1.0, ((pt.x()-a.x())*dx + (pt.y()-a.y())*dy) / l2))


def _point_at(a: QPointF, b: QPointF, t: float) -> QPointF:
    return QPointF(a.x() + (b.x() - a.x()) * t,
                   a.y() + (b.y() - a.y()) * t)


def _polyline_segments_between(segs: list[tuple[QPointF, QPointF]],
                               start_pos: float, end_pos: float):
    if end_pos - start_pos < 1e-6:
        return []
    result = []
    start_idx = max(0, int(math.floor(start_pos)))
    end_idx = min(len(segs) - 1, int(math.floor(end_pos)))
    for i in range(start_idx, end_idx + 1):
        seg_start = max(start_pos, float(i))
        seg_end = min(end_pos, float(i + 1))
        if seg_end - seg_start < 1e-6:
            continue
        a, b = segs[i]
        result.append((_point_at(a, b, seg_start - i),
                       _point_at(a, b, seg_end - i)))
    return result


def _unique_params(values: list[float]) -> list[float]:
    result = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > 1e-5:
            result.append(value)
    return result


def _polyline_part(ent, start_pos: float, end_pos: float):
    if end_pos - start_pos < 1e-6:
        return None
    segs = ent.segments()
    if not segs:
        return None
    verts = ent.vertices()
    n = len(segs)
    start_pos = max(0.0, min(float(n), start_pos))
    end_pos = max(0.0, min(float(n), end_pos))
    start_pt = _point_on_polyline_pos(segs, start_pos)
    end_pt = _point_on_polyline_pos(segs, end_pos)
    first_vertex = int(math.floor(start_pos)) + 1
    last_vertex = int(math.floor(end_pos))
    if abs(end_pos - round(end_pos)) < 1e-6:
        last_vertex = int(round(end_pos)) - 1
    middle = [QPointF(v) for v in verts[first_vertex:last_vertex + 1]]
    return _make_polyline([start_pt] + middle + [end_pt], ent)


def _point_on_polyline_pos(segs: list[tuple[QPointF, QPointF]], pos: float) -> QPointF:
    if pos <= 0:
        return QPointF(segs[0][0])
    if pos >= len(segs):
        return QPointF(segs[-1][1])
    idx = min(int(math.floor(pos)), len(segs) - 1)
    t = pos - idx
    a, b = segs[idx]
    return _point_at(a, b, t)


def _make_polyline(verts: list[QPointF], ent):
    deduped = []
    for pt in verts:
        if not deduped or not _same_point(pt, deduped[-1]):
            deduped.append(QPointF(pt))
    if len(deduped) < 2:
        return None
    if all(math.hypot(b.x()-a.x(), b.y()-a.y()) < 1 for a, b in zip(deduped, deduped[1:])):
        return None
    return PolylineEntity(deduped, ent.layer, ent.linetype, ent.lineweight)


def _make_line(a: QPointF, b: QPointF, ent):
    if math.hypot(b.x()-a.x(), b.y()-a.y()) < 1:
        return None
    return LineEntity(a, b, ent.layer, ent.linetype, ent.lineweight)


def _same_point(a: QPointF, b: QPointF) -> bool:
    return math.hypot(b.x()-a.x(), b.y()-a.y()) < 1e-6


def _draw_entity(painter: QPainter, view, ent, color: QColor, width: float):
    painter.setPen(QPen(color, width))
    for seg in ent.line_segments():
        painter.drawLine(view.mapFromScene(seg.p1()), view.mapFromScene(seg.p2()))


def _make_rect(a: QPoint, b: QPoint) -> QRect:
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()),
                 abs(b.x() - a.x()), abs(b.y() - a.y()))
