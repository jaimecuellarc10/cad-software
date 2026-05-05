import math
from PySide6.QtCore import QPointF, QLineF

from .constants import SnapMode, GRID_UNIT, SNAP_PX


class SnapResult:
    def __init__(self, point: QPointF, mode: SnapMode):
        self.point = point
        self.mode  = mode


class SnapManager:
    def __init__(self):
        self.active_modes: set[SnapMode] = {
            SnapMode.ENDPOINT,
            SnapMode.MIDPOINT,
            SnapMode.CENTER,
            SnapMode.INTERSECTION,
            SnapMode.GRID,
        }
        self.grid_snap_enabled = True
        self.ortho_enabled     = False
        self.osnap_enabled     = True   # master object-snap toggle (F3)
        self.grid_visible      = True   # visual grid display toggle (F7)

        # Set by modify tools (Move/Copy/Mirror) to their base point so that
        # ortho and context-aware snaps (perpendicular, tangent, parallel) work
        # correctly even when no drawing extra_points are present.
        self.ortho_base: QPointF | None = None

    def snap(self, cursor_scene: QPointF, entities: list, view_scale: float,
             extra_points: list | None = None) -> SnapResult:
        threshold = SNAP_PX / view_scale

        # Resolve the "from" point used by perpendicular / tangent / parallel
        # and by ortho constraint.  Prefer ortho_base (set by modify tools);
        # fall back to extra_points[0] (set by drawing tools).
        from_pt: QPointF | None = self.ortho_base
        if from_pt is None and extra_points:
            entry = extra_points[0]
            from_pt = entry[0] if isinstance(entry, tuple) else entry

        best_dist = threshold
        best_pt   = None
        best_mode = SnapMode.GRID

        if self.osnap_enabled:
            # ── Geometry snaps: endpoint, midpoint, center ────────────────────
            for mode in (SnapMode.ENDPOINT, SnapMode.MIDPOINT, SnapMode.CENTER):
                if mode not in self.active_modes:
                    continue
                for ent in entities:
                    for pt in ent.snap_points(mode):
                        d = _dist(cursor_scene, pt)
                        if d < best_dist:
                            best_dist, best_pt, best_mode = d, pt, mode

            # ── Intersection snap ─────────────────────────────────────────────
            if SnapMode.INTERSECTION in self.active_modes:
                segs: list[QLineF] = []
                for ent in entities:
                    segs.extend(ent.line_segments())
                for i in range(len(segs)):
                    for j in range(i + 1, len(segs)):
                        itype, pt = segs[i].intersects(segs[j])
                        if itype == QLineF.IntersectionType.BoundedIntersection:
                            d = _dist(cursor_scene, pt)
                            if d < best_dist:
                                best_dist, best_pt, best_mode = d, pt, SnapMode.INTERSECTION

            # ── Extra points from in-progress tool geometry ───────────────────
            if extra_points:
                for pt, mode in extra_points:
                    if mode in self.active_modes:
                        d = _dist(cursor_scene, pt)
                        if d < best_dist:
                            best_dist, best_pt, best_mode = d, pt, mode

            # ── Perpendicular snap ────────────────────────────────────────────
            if SnapMode.PERPENDICULAR in self.active_modes and from_pt is not None:
                for ent in entities:
                    for seg in ent.line_segments():
                        pt = _perp_foot_on_seg(from_pt, seg)
                        if pt is not None:
                            d = _dist(cursor_scene, pt)
                            if d < best_dist:
                                best_dist, best_pt, best_mode = d, pt, SnapMode.PERPENDICULAR

            # ── Tangent snap ──────────────────────────────────────────────────
            if SnapMode.TANGENT in self.active_modes and from_pt is not None:
                for ent in entities:
                    center = getattr(ent, 'center', None)
                    radius = getattr(ent, 'radius', None)
                    if center is not None and radius is not None:
                        for pt in _tangent_pts(from_pt, center, float(radius)):
                            d = _dist(cursor_scene, pt)
                            if d < best_dist:
                                best_dist, best_pt, best_mode = d, pt, SnapMode.TANGENT

            # ── Parallel snap ─────────────────────────────────────────────────
            if SnapMode.PARALLEL in self.active_modes and from_pt is not None:
                for ent in entities:
                    for seg in ent.line_segments():
                        pt = _parallel_pt(from_pt, cursor_scene, seg)
                        if pt is not None:
                            d = _dist(cursor_scene, pt)
                            if d < best_dist:
                                best_dist, best_pt, best_mode = d, pt, SnapMode.PARALLEL

            # ── Nearest snap (lowest priority — only if nothing else matched) ─
            if SnapMode.NEAREST in self.active_modes and best_pt is None:
                for ent in entities:
                    for seg in ent.line_segments():
                        pt = _nearest_on_seg(cursor_scene, seg)
                        d = _dist(cursor_scene, pt)
                        if d < best_dist:
                            best_dist, best_pt, best_mode = d, pt, SnapMode.NEAREST
                    center = getattr(ent, 'center', None)
                    radius = getattr(ent, 'radius', None)
                    if center is not None and radius is not None:
                        pt = _nearest_on_circle(cursor_scene, center, float(radius))
                        d = _dist(cursor_scene, pt)
                        if d < best_dist:
                            best_dist, best_pt, best_mode = d, pt, SnapMode.NEAREST

        if best_pt is not None:
            result = QPointF(best_pt)
            mode   = best_mode
        elif self.grid_snap_enabled:
            result = _grid_snap(cursor_scene)
            mode   = SnapMode.GRID
        else:
            result = QPointF(cursor_scene)
            mode   = SnapMode.NONE

        # ── Ortho constraint (applied after all geometry snaps) ───────────────
        if self.ortho_enabled and from_pt is not None:
            dx = abs(result.x() - from_pt.x())
            dy = abs(result.y() - from_pt.y())
            if dx >= dy:
                result = QPointF(result.x(), from_pt.y())
            else:
                result = QPointF(from_pt.x(), result.y())

        return SnapResult(result, mode)


# ── Distance helper ───────────────────────────────────────────────────────────

def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


# ── Grid snap ─────────────────────────────────────────────────────────────────

def _grid_snap(pos: QPointF) -> QPointF:
    x = round(pos.x() / GRID_UNIT) * GRID_UNIT
    y = round(pos.y() / GRID_UNIT) * GRID_UNIT
    return QPointF(x, y)


# ── Perpendicular helper ──────────────────────────────────────────────────────

def _perp_foot_on_seg(from_pt: QPointF, seg: QLineF) -> QPointF | None:
    """Return the foot of the perpendicular from *from_pt* to *seg*, or None
    if the foot lies outside the segment."""
    dx = seg.x2() - seg.x1()
    dy = seg.y2() - seg.y1()
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return None
    t = ((from_pt.x() - seg.x1()) * dx + (from_pt.y() - seg.y1()) * dy) / length_sq
    if t < 0.0 or t > 1.0:
        return None
    return QPointF(seg.x1() + t * dx, seg.y1() + t * dy)


# ── Tangent helpers ───────────────────────────────────────────────────────────

def _tangent_pts(from_pt: QPointF, center: QPointF,
                 radius: float) -> list[QPointF]:
    """Return the two tangent points on *circle* from an external *from_pt*.
    Returns an empty list if *from_pt* is inside or on the circle."""
    dx = center.x() - from_pt.x()
    dy = center.y() - from_pt.y()
    d_sq = dx * dx + dy * dy
    if d_sq <= radius * radius + 1e-9:
        return []
    d = math.sqrt(d_sq)
    L = math.sqrt(d_sq - radius * radius)
    # Rotate the local tangent vectors into global coords.
    # In local coords (from_pt at origin, center on x-axis):
    #   T = (L²/d, ±r·L/d)  →  rotate by φ = atan2(dy, dx)
    scale = L / d_sq
    perp_x = -dy / d   # unit perpendicular to from_pt→center
    perp_y =  dx / d
    along_x = dx / d
    along_y = dy / d
    t1 = QPointF(from_pt.x() + scale * (L * dx - radius * dy),
                 from_pt.y() + scale * (L * dy + radius * dx))
    t2 = QPointF(from_pt.x() + scale * (L * dx + radius * dy),
                 from_pt.y() + scale * (L * dy - radius * dx))
    return [t1, t2]


# ── Nearest helpers ───────────────────────────────────────────────────────────

def _nearest_on_seg(pt: QPointF, seg: QLineF) -> QPointF:
    """Project *pt* onto *seg*, clamped to [0, 1]."""
    dx = seg.x2() - seg.x1()
    dy = seg.y2() - seg.y1()
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return QPointF(seg.x1(), seg.y1())
    t = ((pt.x() - seg.x1()) * dx + (pt.y() - seg.y1()) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    return QPointF(seg.x1() + t * dx, seg.y1() + t * dy)


def _nearest_on_circle(pt: QPointF, center: QPointF, radius: float) -> QPointF:
    """Return the nearest point on the circle perimeter to *pt*."""
    dx = pt.x() - center.x()
    dy = pt.y() - center.y()
    dist = math.hypot(dx, dy)
    if dist < 1e-9:
        return QPointF(center.x() + radius, center.y())
    return QPointF(center.x() + dx / dist * radius,
                   center.y() + dy / dist * radius)


# ── Parallel helper ───────────────────────────────────────────────────────────

def _parallel_pt(from_pt: QPointF, cursor: QPointF, seg: QLineF) -> QPointF | None:
    """Return the point on the line through *from_pt* parallel to *seg*
    that is closest to *cursor*."""
    dx = seg.x2() - seg.x1()
    dy = seg.y2() - seg.y1()
    length_sq = dx * dx + dy * dy
    if length_sq < 1e-12:
        return None
    ex = cursor.x() - from_pt.x()
    ey = cursor.y() - from_pt.y()
    t = (ex * dx + ey * dy) / length_sq
    return QPointF(from_pt.x() + t * dx, from_pt.y() + t * dy)
