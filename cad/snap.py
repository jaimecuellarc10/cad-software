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
            SnapMode.GRID,
        }
        self.grid_snap_enabled = True
        self.ortho_enabled = False

    def snap(self, cursor_scene: QPointF, entities: list, view_scale: float,
             extra_points: list | None = None) -> SnapResult:
        threshold = SNAP_PX / view_scale

        best_dist = threshold
        best_pt   = None
        best_mode = SnapMode.GRID

        # ── Geometry snaps (endpoint, midpoint, center) ───────────────────────
        for mode in (SnapMode.ENDPOINT, SnapMode.MIDPOINT, SnapMode.CENTER):
            if mode not in self.active_modes:
                continue
            for ent in entities:
                for pt in ent.snap_points(mode):
                    d = _dist(cursor_scene, pt)
                    if d < best_dist:
                        best_dist, best_pt, best_mode = d, pt, mode

        # ── Intersection snap ─────────────────────────────────────────────────
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

        # ── Extra points from in-progress tool geometry ────────────────────────
        if extra_points:
            for pt, mode in extra_points:
                if mode in self.active_modes:
                    d = _dist(cursor_scene, pt)
                    if d < best_dist:
                        best_dist, best_pt, best_mode = d, pt, mode

        if best_pt is not None:
            result = QPointF(best_pt)
            mode = best_mode
        elif self.grid_snap_enabled:
            result = _grid_snap(cursor_scene)
            mode = SnapMode.GRID
        else:
            result = QPointF(cursor_scene)
            mode = SnapMode.NONE

        if self.ortho_enabled and extra_points:
            base = extra_points[0][0] if isinstance(extra_points[0], tuple) else extra_points[0]
            dx = abs(result.x() - base.x())
            dy = abs(result.y() - base.y())
            if dx >= dy:
                result = QPointF(result.x(), base.y())
            else:
                result = QPointF(base.x(), result.y())
        return SnapResult(result, mode)


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _grid_snap(pos: QPointF) -> QPointF:
    x = round(pos.x() / GRID_UNIT) * GRID_UNIT
    y = round(pos.y() / GRID_UNIT) * GRID_UNIT
    return QPointF(x, y)
