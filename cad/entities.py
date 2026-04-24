import math
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPen, QColor, QPainter, QPolygonF
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF

from .constants import SnapMode, GRIP_PX


class Layer:
    def __init__(self, name: str, color: QColor = None,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine, lineweight: float = 1.5):
        self.name       = name
        self.color      = color or QColor("#ffffff")
        self.linetype   = linetype
        self.lineweight = lineweight
        self.visible    = True
        self.locked     = False


class CADEntity(QGraphicsItem):
    """Abstract base for every CAD drawing entity."""

    SEL_COLOR   = QColor(255, 165,   0)        # orange when selected
    GRIP_FILL   = QColor(  0,  51, 153, 210)
    GRIP_BORDER = QColor( 80, 160, 255)

    def __init__(self, layer: Layer):
        super().__init__()
        self.layer             = layer
        self.color_override: QColor | None = None
        self._selected         = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setAcceptHoverEvents(False)

    # ── Selection ─────────────────────────────────────────────────────────────

    @property
    def selected(self) -> bool: return self._selected

    @selected.setter
    def selected(self, val: bool):
        if self._selected != val:
            self._selected = val
            self.update()

    @property
    def draw_color(self) -> QColor:
        return self.SEL_COLOR if self._selected else (self.color_override or self.layer.color)

    # ── Snap interface (override in subclasses) ────────────────────────────────

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        """Return snap points of the given type in scene coordinates."""
        return []

    def grip_points(self) -> list[QPointF]:
        """All points where grip squares should be drawn when selected."""
        pts = []
        for mode in (SnapMode.ENDPOINT, SnapMode.MIDPOINT, SnapMode.CENTER):
            pts.extend(self.snap_points(mode))
        return pts

    def line_segments(self) -> list[QLineF]:
        """Return constituent line segments (used for intersection snap)."""
        return []

    # ── Hit & rect tests (override in subclasses) ─────────────────────────────

    def hit_test(self, scene_pt: QPointF, threshold: float) -> bool:
        raise NotImplementedError

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        raise NotImplementedError

    # ── Transforms (override in subclasses) ───────────────────────────────────

    def translate(self, dx: float, dy: float):
        raise NotImplementedError

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        """Rotate CCW on screen by angle_deg around (cx, cy)."""
        raise NotImplementedError

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        """Mirror across the line from (ax,ay) to (bx,by)."""
        raise NotImplementedError

    def clone(self) -> "CADEntity":
        """Return a deep copy of this entity (unselected, not in any scene)."""
        raise NotImplementedError

    # ── Grip drawing ──────────────────────────────────────────────────────────

    def _paint_grips(self, painter: QPainter):
        scale = painter.transform().m11()
        s     = GRIP_PX / scale
        pen   = QPen(self.GRIP_BORDER, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(self.GRIP_FILL)
        for pt in self.grip_points():
            painter.drawRect(QRectF(pt.x() - s / 2, pt.y() - s / 2, s, s))


# ── Line ──────────────────────────────────────────────────────────────────────

class LineEntity(CADEntity):
    def __init__(self, p1: QPointF, p2: QPointF, layer: Layer,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine,
                 lineweight: float | None = None):
        super().__init__(layer)
        self._p1        = QPointF(p1)
        self._p2        = QPointF(p2)
        self.linetype   = linetype
        self.lineweight = lineweight   # None = use layer default

    @property
    def p1(self) -> QPointF: return QPointF(self._p1)
    @property
    def p2(self) -> QPointF: return QPointF(self._p2)

    @property
    def midpoint(self) -> QPointF:
        return QPointF((self._p1.x() + self._p2.x()) / 2,
                       (self._p1.y() + self._p2.y()) / 2)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT: return [self._p1, self._p2]
        if mode == SnapMode.MIDPOINT: return [self.midpoint]
        return []

    def line_segments(self) -> list[QLineF]:
        return [QLineF(self._p1, self._p2)]

    def boundingRect(self) -> QRectF:
        pad = 6
        x1, y1 = self._p1.x(), self._p1.y()
        x2, y2 = self._p2.x(), self._p2.y()
        return QRectF(min(x1, x2) - pad, min(y1, y2) - pad,
                      abs(x2 - x1) + pad * 2, abs(y2 - y1) + pad * 2)

    def paint(self, painter: QPainter, option, widget=None):
        lw  = self.lineweight if self.lineweight is not None else self.layer.lineweight
        pen = QPen(self.draw_color, lw, self.linetype)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(self._p1, self._p2)
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return _seg_dist(pt, self._p1, self._p2) <= threshold

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            if rect.contains(self._p1) or rect.contains(self._p2):
                return True
            seg = QLineF(self._p1, self._p2)
            for edge in _rect_edges(rect):
                itype, _ = seg.intersects(edge)
                if itype == QLineF.IntersectionType.BoundedIntersection:
                    return True
            return False
        return rect.contains(self._p1) and rect.contains(self._p2)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._p1 = QPointF(self._p1.x() + dx, self._p1.y() + dy)
        self._p2 = QPointF(self._p2.x() + dx, self._p2.y() + dy)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._p1 = _rotate_pt(self._p1, cx, cy, cos_a, sin_a)
        self._p2 = _rotate_pt(self._p2, cx, cy, cos_a, sin_a)
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._p1 = _mirror_pt(self._p1, ax, ay, bx, by)
        self._p2 = _mirror_pt(self._p2, ax, ay, bx, by)
        self.update()

    def clone(self) -> "LineEntity":
        return LineEntity(self._p1, self._p2, self.layer, self.linetype, self.lineweight)


# ── Polyline ──────────────────────────────────────────────────────────────────

class PolylineEntity(CADEntity):
    """
    A sequence of connected line segments treated as one entity.
    Crossing any segment selects the whole polyline.
    """

    def __init__(self, vertices: list[QPointF], layer: Layer,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine,
                 lineweight: float | None = None):
        super().__init__(layer)
        self._verts     = [QPointF(v) for v in vertices]
        self.linetype   = linetype
        self.lineweight = lineweight

    def vertices(self) -> list[QPointF]:
        return list(self._verts)

    def segments(self) -> list[tuple[QPointF, QPointF]]:
        return [(self._verts[i], self._verts[i + 1])
                for i in range(len(self._verts) - 1)]

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT:
            return list(self._verts)     # every vertex is an endpoint snap
        if mode == SnapMode.MIDPOINT:
            return [QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
                    for a, b in self.segments()]
        return []

    def line_segments(self) -> list[QLineF]:
        return [QLineF(a, b) for a, b in self.segments()]

    def boundingRect(self) -> QRectF:
        if not self._verts:
            return QRectF()
        xs  = [v.x() for v in self._verts]
        ys  = [v.y() for v in self._verts]
        pad = 6
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + pad * 2,
                      max(ys) - min(ys) + pad * 2)

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._verts) < 2:
            return
        lw  = self.lineweight if self.lineweight is not None else self.layer.lineweight
        pen = QPen(self.draw_color, lw, self.linetype)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for a, b in self.segments():
            painter.drawLine(a, b)
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return any(_seg_dist(pt, a, b) <= threshold for a, b in self.segments())

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            for a, b in self.segments():
                if rect.contains(a) or rect.contains(b):
                    return True
                seg = QLineF(a, b)
                for edge in _rect_edges(rect):
                    itype, _ = seg.intersects(edge)
                    if itype == QLineF.IntersectionType.BoundedIntersection:
                        return True
            return False
        return all(rect.contains(v) for v in self._verts)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._verts = [QPointF(v.x() + dx, v.y() + dy) for v in self._verts]
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._verts = [_rotate_pt(v, cx, cy, cos_a, sin_a) for v in self._verts]
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._verts = [_mirror_pt(v, ax, ay, bx, by) for v in self._verts]
        self.update()

    def clone(self) -> "PolylineEntity":
        return PolylineEntity(self._verts, self.layer, self.linetype, self.lineweight)


# ── Circle ───────────────────────────────────────────────────────────────────

class CircleEntity(CADEntity):
    def __init__(self, center: QPointF, radius: float, layer: Layer,
                 lineweight: float | None = None):
        super().__init__(layer)
        self._center    = QPointF(center)
        self._radius    = float(radius)
        self.lineweight = lineweight

    @property
    def center(self) -> QPointF: return QPointF(self._center)
    @property
    def radius(self) -> float: return self._radius

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        if mode == SnapMode.CENTER:
            return [QPointF(cx, cy)]
        if mode == SnapMode.ENDPOINT:          # quadrant points
            return [QPointF(cx+r, cy), QPointF(cx, cy-r),
                    QPointF(cx-r, cy), QPointF(cx, cy+r)]
        return []

    def boundingRect(self) -> QRectF:
        r = self._radius + 2
        return QRectF(self._center.x()-r, self._center.y()-r, r*2, r*2)

    def paint(self, painter: QPainter, option, widget=None):
        lw  = self.lineweight if self.lineweight is not None else self.layer.lineweight
        pen = QPen(self.draw_color, lw)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self._center, self._radius, self._radius)
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        d = math.hypot(pt.x()-self._center.x(), pt.y()-self._center.y())
        return abs(d - self._radius) <= threshold

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        cx, cy, r = self._center.x(), self._center.y(), self._radius
        if crossing:
            nx = max(rect.left(), min(cx, rect.right()))
            ny = max(rect.top(),  min(cy, rect.bottom()))
            return math.hypot(cx-nx, cy-ny) <= r
        return (rect.left()   <= cx-r and rect.right()  >= cx+r and
                rect.top()    <= cy-r and rect.bottom() >= cy+r)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._center = _rotate_pt(self._center, cx, cy, cos_a, sin_a)
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._center = _mirror_pt(self._center, ax, ay, bx, by)
        self.update()

    def clone(self) -> "CircleEntity":
        return CircleEntity(self._center, self._radius, self.layer, self.lineweight)


# ── Arc ───────────────────────────────────────────────────────────────────────

class ArcEntity(CADEntity):
    """
    Arc defined by center, radius, startAngle, spanAngle (Qt convention:
    degrees × 16 are used only at paint time; we store plain degrees here).
    Positive spanAngle = counter-clockwise on screen.
    """

    def __init__(self, center: QPointF, radius: float,
                 start_angle: float, span_angle: float, layer: Layer,
                 lineweight: float | None = None):
        super().__init__(layer)
        self._center      = QPointF(center)
        self._radius      = float(radius)
        self._start_angle = float(start_angle)   # degrees
        self._span_angle  = float(span_angle)    # degrees, CCW positive
        self.lineweight   = lineweight

    @property
    def center(self) -> QPointF: return QPointF(self._center)

    def _point_at(self, deg: float) -> QPointF:
        rad = math.radians(deg)
        return QPointF(self._center.x() + self._radius * math.cos(rad),
                       self._center.y() - self._radius * math.sin(rad))

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.CENTER:
            return [QPointF(self._center)]
        if mode == SnapMode.ENDPOINT:
            return [self._point_at(self._start_angle),
                    self._point_at(self._start_angle + self._span_angle)]
        if mode == SnapMode.MIDPOINT:
            return [self._point_at(self._start_angle + self._span_angle / 2)]
        return []

    def boundingRect(self) -> QRectF:
        r = self._radius + 2
        return QRectF(self._center.x()-r, self._center.y()-r, r*2, r*2)

    def paint(self, painter: QPainter, option, widget=None):
        lw  = self.lineweight if self.lineweight is not None else self.layer.lineweight
        pen = QPen(self.draw_color, lw)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r    = self._radius
        rect = QRectF(self._center.x()-r, self._center.y()-r, r*2, r*2)
        painter.drawArc(rect,
                        int(self._start_angle * 16),
                        int(self._span_angle  * 16))
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        d = math.hypot(pt.x()-self._center.x(), pt.y()-self._center.y())
        if abs(d - self._radius) > threshold:
            return False
        ang = math.degrees(math.atan2(-(pt.y()-self._center.y()),
                                       pt.x()-self._center.x())) % 360
        return _angle_in_span(ang, self._start_angle % 360, self._span_angle)

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            cx, cy, r = self._center.x(), self._center.y(), self._radius
            nx = max(rect.left(), min(cx, rect.right()))
            ny = max(rect.top(),  min(cy, rect.bottom()))
            return math.hypot(cx-nx, cy-ny) <= r
        return rect.contains(self.boundingRect())

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._center = QPointF(self._center.x() + dx, self._center.y() + dy)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._center = _rotate_pt(self._center, cx, cy, cos_a, sin_a)
        self._start_angle = (self._start_angle + angle_deg) % 360
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        start_pt = self._point_at(self._start_angle)
        end_pt   = self._point_at(self._start_angle + self._span_angle)
        new_center    = _mirror_pt(self._center,  ax, ay, bx, by)
        new_start_pt  = _mirror_pt(start_pt,      ax, ay, bx, by)
        new_end_pt    = _mirror_pt(end_pt,         ax, ay, bx, by)
        cx, cy = new_center.x(), new_center.y()
        self._center = new_center
        new_sa = math.degrees(math.atan2(-(new_start_pt.y()-cy), new_start_pt.x()-cx))
        new_ea = math.degrees(math.atan2(-(new_end_pt.y()-cy),   new_end_pt.x()-cx))
        # Mirror reverses arc direction
        if self._span_angle >= 0:
            raw_span = (new_sa - new_ea) % 360
            self._span_angle = -raw_span if raw_span != 0 else -360
        else:
            self._span_angle = (new_ea - new_sa) % 360
        self._start_angle = new_sa
        self.update()

    def clone(self) -> "ArcEntity":
        return ArcEntity(self._center, self._radius, self._start_angle,
                         self._span_angle, self.layer, self.lineweight)


def _angle_in_span(angle: float, start: float, span: float) -> bool:
    """True if angle (0-360) lies within the arc span."""
    start = start % 360
    if span >= 0:
        end = (start + span) % 360
        if start <= end:
            return start <= angle <= end
        return angle >= start or angle <= end
    else:
        end = (start + span) % 360
        if end <= start:
            return end <= angle <= start
        return angle <= start or angle >= end


def _circumscribed_circle(p1: QPointF, p2: QPointF, p3: QPointF):
    """Return (center: QPointF, radius: float) or (None, None) if collinear."""
    ax, ay = p1.x(), p1.y()
    bx, by = p2.x(), p2.y()
    cx, cy = p3.x(), p3.y()
    D = 2*(ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
    if abs(D) < 1e-10:
        return None, None
    ux = ((ax*ax+ay*ay)*(by-cy) + (bx*bx+by*by)*(cy-ay) + (cx*cx+cy*cy)*(ay-by)) / D
    uy = ((ax*ax+ay*ay)*(cx-bx) + (bx*bx+by*by)*(ax-cx) + (cx*cx+cy*cy)*(bx-ax)) / D
    center = QPointF(ux, uy)
    radius = math.hypot(ax-ux, ay-uy)
    return center, radius


# ── helpers ───────────────────────────────────────────────────────────────────

def _rotate_pt(pt: QPointF, cx: float, cy: float, cos_a: float, sin_a: float) -> QPointF:
    """Rotate pt CCW on screen (Qt Y-down) around (cx, cy) by angle (cos_a, sin_a)."""
    dx = pt.x() - cx
    dy = pt.y() - cy
    return QPointF(cx + dx * cos_a + dy * sin_a,
                   cy - dx * sin_a + dy * cos_a)


def _mirror_pt(pt: QPointF, ax: float, ay: float, bx: float, by: float) -> QPointF:
    """Mirror pt across the line from (ax,ay) to (bx,by)."""
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 < 1e-12:
        return QPointF(pt)
    t  = ((pt.x() - ax) * dx + (pt.y() - ay) * dy) / d2
    px = ax + t * dx
    py = ay + t * dy
    return QPointF(2 * px - pt.x(), 2 * py - pt.y())


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t  = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (dx * dx + dy * dy)))
    cx = a.x() + t * dx
    cy = a.y() + t * dy
    return math.hypot(p.x() - cx, p.y() - cy)


def _rect_edges(r: QRectF) -> list[QLineF]:
    tl, tr = r.topLeft(), r.topRight()
    bl, br = r.bottomLeft(), r.bottomRight()
    return [QLineF(tl, tr), QLineF(tr, br), QLineF(br, bl), QLineF(bl, tl)]
