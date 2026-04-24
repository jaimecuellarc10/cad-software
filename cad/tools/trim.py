import math
from PySide6.QtCore import Qt, QPointF, QLineF
from PySide6.QtGui import QPainter
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity
from ..undo import ReplaceEntityCommand


class TrimTool(BaseTool):
    """Click on the part of a line/polyline segment you want to remove.
    The segment is trimmed at its intersections with all other entities."""

    name = "trim"

    @property
    def is_idle(self) -> bool:
        return True

    @property
    def prompt(self) -> str:
        return "TRIM  Click the part of a line/polyline segment to trim  [Esc = exit]"

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._do_trim(snapped)

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        pass

    def cancel(self):
        pass

    def draw_overlay(self, painter: QPainter):
        pass

    # ── Trim logic ────────────────────────────────────────────────────────────

    def _do_trim(self, click_pt: QPointF):
        scene     = self.view.cad_scene
        entities  = scene.all_entities()
        scale     = self.view.transform().m11()
        threshold = 10.0 / scale

        # Find the entity / segment closest to the click
        hit_entity  = None
        hit_seg_idx = 0
        hit_seg     = None
        best_dist   = threshold

        for ent in entities:
            for i, (a, b) in enumerate(_entity_segments(ent)):
                d = _seg_dist(click_pt, a, b)
                if d < best_dist:
                    best_dist   = d
                    hit_entity  = ent
                    hit_seg_idx = i
                    hit_seg     = (a, b)

        if hit_entity is None:
            return

        a, b = hit_seg

        # Collect all bounded intersections on this segment with other entities
        intersections: list[QPointF] = []
        for other in entities:
            if other is hit_entity:
                continue
            for oa, ob in _entity_segments(other):
                pt = _seg_seg_intersect(a, b, oa, ob)
                if pt is not None:
                    intersections.append(pt)

        if not intersections:
            return

        seg_len = math.hypot(b.x()-a.x(), b.y()-a.y())
        if seg_len < 1e-9:
            return

        def param(pt: QPointF) -> float:
            return ((pt.x()-a.x())*(b.x()-a.x()) +
                    (pt.y()-a.y())*(b.y()-a.y())) / (seg_len * seg_len)

        click_t     = max(0.0, min(1.0, param(click_pt)))
        sorted_ints = sorted([(param(p), p) for p in intersections], key=lambda x: x[0])

        left  = [(t, p) for t, p in sorted_ints if t <= click_t]
        right = [(t, p) for t, p in sorted_ints if t >  click_t]

        if left and right:
            new_a, new_b = left[-1][1], right[0][1]
        elif left:
            new_a, new_b = left[-1][1], b
        elif right:
            new_a, new_b = a, right[0][1]
        else:
            return

        new_ent = _rebuild_entity(hit_entity, hit_seg_idx, new_a, new_b)
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


def _seg_seg_intersect(a: QPointF, b: QPointF,
                       c: QPointF, d: QPointF) -> QPointF | None:
    itype, pt = QLineF(a, b).intersects(QLineF(c, d))
    if itype == QLineF.IntersectionType.BoundedIntersection:
        return pt
    return None


def _rebuild_entity(ent, seg_idx: int, new_a: QPointF, new_b: QPointF):
    if isinstance(ent, LineEntity):
        if math.hypot(new_b.x()-new_a.x(), new_b.y()-new_a.y()) < 1:
            return None
        return LineEntity(new_a, new_b, ent.layer, ent.linetype, ent.lineweight)

    if isinstance(ent, PolylineEntity):
        verts = ent.vertices()
        new_verts = verts[:seg_idx] + [new_a, new_b] + verts[seg_idx + 2:]
        if len(new_verts) < 2:
            return None
        return PolylineEntity(new_verts, ent.layer, ent.linetype, ent.lineweight)

    return None
