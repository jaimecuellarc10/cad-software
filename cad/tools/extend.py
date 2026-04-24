import math
from PySide6.QtCore import Qt, QPointF, QLineF
from PySide6.QtGui import QPainter
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ReplaceEntityCommand


class ExtendTool(BaseTool):
    """Click near the end of a line to extend it to the nearest other entity."""

    name = "extend"

    @property
    def is_idle(self) -> bool:
        return True

    @property
    def prompt(self) -> str:
        return "EXTEND  Click near the end of a line to extend it  [Esc = exit]"

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._do_extend(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        pass

    def cancel(self):
        pass

    def draw_overlay(self, painter: QPainter):
        pass

    # ── Extend logic ──────────────────────────────────────────────────────────

    def _do_extend(self, click_pt: QPointF):
        scene     = self.view.cad_scene
        entities  = scene.all_entities()
        scale     = self.view.transform().m11()
        threshold = 10.0 / scale

        # Find line entity + which end the click is closest to
        hit_entity = None
        extend_end = None   # 'a' or 'b'
        best_dist  = threshold

        for ent in entities:
            segs = _entity_segments(ent)
            for i, (a, b) in enumerate(segs):
                d = _seg_dist(click_pt, a, b)
                if d >= best_dist:
                    continue
                best_dist  = d
                hit_entity = ent
                # Which end is the click closest to?
                da = math.hypot(click_pt.x()-a.x(), click_pt.y()-a.y())
                db = math.hypot(click_pt.x()-b.x(), click_pt.y()-b.y())
                extend_end = 'a' if da < db else 'b'
                hit_seg_idx = i

        if hit_entity is None:
            return

        segs = _entity_segments(hit_entity)
        a, b = segs[hit_seg_idx]

        # Extend the line from the far end through the near end
        if extend_end == 'b':
            origin, direction = a, QPointF(b.x()-a.x(), b.y()-a.y())
            fixed_end = a
        else:
            origin, direction = b, QPointF(a.x()-b.x(), a.y()-b.y())
            fixed_end = b

        # Find nearest intersection with any other entity (using infinite line)
        best_t   = None
        best_pt  = None
        dir_len  = math.hypot(direction.x(), direction.y())
        if dir_len < 1e-9:
            return

        for other in entities:
            if other is hit_entity:
                continue
            for oa, ob in _entity_segments(other):
                pt = _line_line_intersect(origin, direction, oa, ob)
                if pt is None:
                    continue
                # t = how far along our ray is the intersection
                t = ((pt.x()-origin.x())*direction.x() +
                     (pt.y()-origin.y())*direction.y()) / (dir_len * dir_len)
                if t > 1e-6:   # must be in front of origin
                    if best_t is None or t < best_t:
                        best_t  = t
                        best_pt = pt

        if best_pt is None:
            return

        new_ent = _rebuild_segment(hit_entity, hit_seg_idx,
                                   fixed_end, best_pt, extend_end)
        if new_ent is None:
            return
        self.view.undo_stack.push(ReplaceEntityCommand(scene, hit_entity, new_ent))
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
