from __future__ import annotations

import math
from PySide6.QtWidgets import QGraphicsItem
from PySide6.QtGui import QPen, QColor, QPainter, QPolygonF, QFont, QPainterPath, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF

from .constants import SnapMode, GRIP_PX, GRID_UNIT


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

    def scale_about(self, cx: float, cy: float, factor: float):
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

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._p1 = _scale_pt(self._p1, cx, cy, factor)
        self._p2 = _scale_pt(self._p2, cx, cy, factor)
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


class PointEntity(CADEntity):
    def __init__(self, pos: QPointF, layer: Layer):
        super().__init__(layer)
        self._pos = QPointF(pos)

    @property
    def pos(self) -> QPointF:
        return QPointF(self._pos)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT:
            return [QPointF(self._pos)]
        return []

    def line_segments(self) -> list[QLineF]:
        return []

    def boundingRect(self) -> QRectF:
        return QRectF(self._pos.x() - 5, self._pos.y() - 5, 10, 10)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(self.draw_color, 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        scale = painter.transform().m11()
        s = 3 / scale if scale else 3
        painter.drawLine(QPointF(self._pos.x() - s, self._pos.y()),
                         QPointF(self._pos.x() + s, self._pos.y()))
        painter.drawLine(QPointF(self._pos.x(), self._pos.y() - s),
                         QPointF(self._pos.x(), self._pos.y() + s))
        painter.drawPoint(self._pos)
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return math.hypot(pt.x() - self._pos.x(), pt.y() - self._pos.y()) <= threshold

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        return rect.contains(self._pos)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._pos = QPointF(self._pos.x() + dx, self._pos.y() + dy)
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._pos = _scale_pt(self._pos, cx, cy, factor)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._pos = _rotate_pt(self._pos, cx, cy, cos_a, sin_a)
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._pos = _mirror_pt(self._pos, ax, ay, bx, by)
        self.update()

    def clone(self) -> "PointEntity":
        return PointEntity(self._pos, self.layer)


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

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._verts = [_scale_pt(v, cx, cy, factor) for v in self._verts]
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
                 lineweight: float | None = None,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine):
        super().__init__(layer)
        self._center    = QPointF(center)
        self._radius    = float(radius)
        self.lineweight = lineweight
        self.linetype   = linetype

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
        pen = QPen(self.draw_color, lw, self.linetype)
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

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._center = _scale_pt(self._center, cx, cy, factor)
        self._radius *= abs(factor)
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
        return CircleEntity(self._center, self._radius, self.layer, self.lineweight, self.linetype)


# ── Arc ───────────────────────────────────────────────────────────────────────

class ArcEntity(CADEntity):
    """
    Arc defined by center, radius, startAngle, spanAngle (Qt convention:
    degrees × 16 are used only at paint time; we store plain degrees here).
    Positive spanAngle = counter-clockwise on screen.
    """

    def __init__(self, center: QPointF, radius: float,
                 start_angle: float, span_angle: float, layer: Layer,
                 lineweight: float | None = None,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine):
        super().__init__(layer)
        self._center      = QPointF(center)
        self._radius      = float(radius)
        self._start_angle = float(start_angle)   # degrees
        self._span_angle  = float(span_angle)    # degrees, CCW positive
        self.lineweight   = lineweight
        self.linetype     = linetype

    @property
    def center(self) -> QPointF: return QPointF(self._center)
    @property
    def radius(self) -> float: return self._radius
    @property
    def start_angle(self) -> float: return self._start_angle
    @property
    def span_angle(self) -> float: return self._span_angle

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
        pen = QPen(self.draw_color, lw, self.linetype)
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

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._center = _scale_pt(self._center, cx, cy, factor)
        self._radius *= abs(factor)
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
                         self._span_angle, self.layer, self.lineweight, self.linetype)


class EllipseEntity(CADEntity):
    """Ellipse defined by center, semi-axes rx/ry, and rotation angle (CCW on screen)."""
    def __init__(self, center: QPointF, rx: float, ry: float,
                 angle_deg: float, layer: "Layer", lineweight: float | None = None,
                 linetype: Qt.PenStyle = Qt.PenStyle.SolidLine):
        super().__init__(layer)
        self._center    = QPointF(center)
        self._rx        = float(rx)
        self._ry        = float(ry)
        self._angle_deg = float(angle_deg)
        self.lineweight = lineweight
        self.linetype   = linetype

    @property
    def center(self) -> QPointF: return QPointF(self._center)
    @property
    def rx(self) -> float: return self._rx
    @property
    def ry(self) -> float: return self._ry
    @property
    def angle_deg(self) -> float: return self._angle_deg

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.CENTER:
            return [QPointF(self._center)]
        if mode == SnapMode.ENDPOINT:
            cos_a = math.cos(math.radians(self._angle_deg))
            sin_a = math.sin(math.radians(self._angle_deg))
            cx, cy = self._center.x(), self._center.y()
            return [
                QPointF(cx + self._rx*cos_a, cy - self._rx*sin_a),
                QPointF(cx - self._rx*cos_a, cy + self._rx*sin_a),
                QPointF(cx - self._ry*sin_a, cy - self._ry*cos_a),
                QPointF(cx + self._ry*sin_a, cy + self._ry*cos_a),
            ]
        return []

    def line_segments(self) -> list:
        return []

    def boundingRect(self) -> QRectF:
        r = max(self._rx, self._ry) + 2
        return QRectF(self._center.x()-r, self._center.y()-r, r*2, r*2)

    def paint(self, painter: QPainter, option, widget=None):
        lw  = self.lineweight if self.lineweight is not None else self.layer.lineweight
        pen = QPen(self.draw_color, lw, self.linetype)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.translate(self._center)
        painter.rotate(-self._angle_deg)   # Qt rotates CW; negate for CCW convention
        painter.drawEllipse(QRectF(-self._rx, -self._ry, self._rx*2, self._ry*2))
        painter.restore()
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        cos_a = math.cos(math.radians(-self._angle_deg))
        sin_a = math.sin(math.radians(-self._angle_deg))
        dx = pt.x()-self._center.x(); dy = pt.y()-self._center.y()
        lx = dx*cos_a - dy*sin_a
        ly = dx*sin_a + dy*cos_a
        if self._rx < 1e-6 or self._ry < 1e-6: return False
        d = math.hypot(lx/self._rx, ly/self._ry)
        return abs(d - 1.0) * min(self._rx, self._ry) <= threshold

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        cx, cy = self._center.x(), self._center.y()
        r = max(self._rx, self._ry)
        if crossing:
            nx = max(rect.left(), min(cx, rect.right()))
            ny = max(rect.top(),  min(cy, rect.bottom()))
            return math.hypot(cx-nx, cy-ny) <= r
        return (rect.left() <= cx-r and rect.right()  >= cx+r and
                rect.top()  <= cy-r and rect.bottom() >= cy+r)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._center = QPointF(self._center.x()+dx, self._center.y()+dy)
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        dx = self._center.x()-cx; dy = self._center.y()-cy
        self._center = QPointF(cx+dx*factor, cy+dy*factor)
        self._rx *= factor; self._ry *= factor
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._center = _rotate_pt(self._center, cx, cy, cos_a, sin_a)
        self._angle_deg = (self._angle_deg + angle_deg) % 360
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._center = _mirror_pt(self._center, ax, ay, bx, by)
        axis_angle = math.degrees(math.atan2(by-ay, bx-ax))
        self._angle_deg = 2*axis_angle - self._angle_deg
        self.update()

    def clone(self) -> "EllipseEntity":
        return EllipseEntity(self._center, self._rx, self._ry,
                             self._angle_deg, self.layer, self.lineweight, self.linetype)


class XLineEntity(CADEntity):
    """Infinite construction line through _point in direction _angle_deg."""
    XLINE_HALF = 45000.0

    def __init__(self, point: QPointF, angle_deg: float, layer: "Layer",
                 lineweight: float | None = None):
        super().__init__(layer)
        self._point     = QPointF(point)
        self._angle_deg = float(angle_deg)
        self.lineweight = lineweight

    @property
    def point(self) -> QPointF: return QPointF(self._point)
    @property
    def angle_deg(self) -> float: return self._angle_deg

    def _endpoints(self):
        rad = math.radians(self._angle_deg)
        dx = math.cos(rad) * self.XLINE_HALF
        dy = math.sin(rad) * self.XLINE_HALF
        p1 = QPointF(self._point.x() - dx, self._point.y() + dy)
        p2 = QPointF(self._point.x() + dx, self._point.y() - dy)
        return p1, p2

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.MIDPOINT:
            return [QPointF(self._point)]
        return []

    def line_segments(self) -> list[QLineF]:
        p1, p2 = self._endpoints()
        return [QLineF(p1, p2)]

    def boundingRect(self) -> QRectF:
        h = self.XLINE_HALF + 2
        return QRectF(-h, -h, h*2, h*2).translated(self._point)

    def paint(self, painter: QPainter, option, widget=None):
        lw = self.lineweight if self.lineweight is not None else self.layer.lineweight
        color = self.draw_color
        pen = QPen(color, lw, Qt.PenStyle.DashDotLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        p1, p2 = self._endpoints()
        painter.drawLine(p1, p2)
        if self._selected:
            self._paint_grips(painter)

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        p1, p2 = self._endpoints()
        return _seg_dist(pt, p1, p2) <= threshold

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        p1, p2 = self._endpoints()
        if crossing:
            seg = QLineF(p1, p2)
            for edge in _rect_edges(rect):
                itype, _ = seg.intersects(edge)
                if itype == QLineF.IntersectionType.BoundedIntersection:
                    return True
            return rect.contains(self._point)
        return False

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._point = QPointF(self._point.x()+dx, self._point.y()+dy)
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        dx = self._point.x()-cx; dy = self._point.y()-cy
        self._point = QPointF(cx+dx*factor, cy+dy*factor)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._point = _rotate_pt(self._point, cx, cy, cos_a, sin_a)
        self._angle_deg = (self._angle_deg + angle_deg) % 360
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._point = _mirror_pt(self._point, ax, ay, bx, by)
        axis_angle = math.degrees(math.atan2(by-ay, bx-ax))
        self._angle_deg = (2*axis_angle - self._angle_deg) % 360
        self.update()

    def clone(self) -> "XLineEntity":
        return XLineEntity(self._point, self._angle_deg, self.layer, self.lineweight)


class TextEntity(CADEntity):
    def __init__(self, pos: QPointF, text: str, height: float = 2.5,
                 angle_deg: float = 0.0, layer: "Layer" | None = None):
        super().__init__(layer or Layer("0"))
        self._pos = QPointF(pos)
        self._text = text
        self._height = float(height)
        self._angle_deg = float(angle_deg)

    @property
    def pos(self) -> QPointF: return QPointF(self._pos)
    @property
    def text(self) -> str: return self._text
    @property
    def height(self) -> float: return self._height
    @property
    def angle_deg(self) -> float: return self._angle_deg

    def _local_rect(self) -> QRectF:
        scene_h = self._height * GRID_UNIT
        scene_w = max(1.0, len(self._text) * scene_h * 0.6)
        return QRectF(0, -scene_h, scene_w, scene_h)

    def _world_corners(self) -> list[QPointF]:
        r = self._local_rect()
        cos_a = math.cos(math.radians(self._angle_deg))
        sin_a = math.sin(math.radians(self._angle_deg))
        pts = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
        return [
            QPointF(self._pos.x() + p.x()*cos_a + p.y()*sin_a,
                    self._pos.y() - p.x()*sin_a + p.y()*cos_a)
            for p in pts
        ]

    def boundingRect(self) -> QRectF:
        pts = self._world_corners()
        xs = [p.x() for p in pts]; ys = [p.y() for p in pts]
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)).adjusted(-4, -4, 4, 4)

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        painter.translate(self._pos)
        painter.rotate(-self._angle_deg)
        painter.setFont(QFont("Arial", max(1, int(self._height * GRID_UNIT))))
        painter.setPen(QPen(QColor(255, 165, 0) if self._selected else QColor("#ffffff"), 0))
        painter.drawText(0, 0, self._text)
        painter.restore()
        if self._selected:
            self._paint_grips(painter)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT:
            return [QPointF(self._pos)]
        return []

    def line_segments(self) -> list[QLineF]:
        return []

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        dx = pt.x() - self._pos.x()
        dy = pt.y() - self._pos.y()
        cos_a = math.cos(math.radians(self._angle_deg))
        sin_a = math.sin(math.radians(self._angle_deg))
        lx = dx*cos_a - dy*sin_a
        ly = dx*sin_a + dy*cos_a
        return self._local_rect().adjusted(-threshold, -threshold, threshold, threshold).contains(QPointF(lx, ly))

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        return rect.contains(self._pos)

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._pos = QPointF(self._pos.x()+dx, self._pos.y()+dy)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._pos = _rotate_pt(self._pos, cx, cy, cos_a, sin_a)
        self._angle_deg = (self._angle_deg + angle_deg) % 360
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._pos = _mirror_pt(self._pos, ax, ay, bx, by)
        self._angle_deg = -self._angle_deg
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._pos = _scale_pt(self._pos, cx, cy, factor)
        self._height *= abs(factor)
        self.update()

    def clone(self) -> "TextEntity":
        return TextEntity(QPointF(self._pos), self._text, self._height,
                          self._angle_deg, self.layer)


class DimLinearEntity(CADEntity):
    def __init__(self, p1: QPointF, p2: QPointF, offset: float,
                 text_override: str = "", layer: "Layer" | None = None,
                 arrow_size: float = 8.0, text_height: float = 2.5):
        super().__init__(layer or Layer("0"))
        self._p1 = QPointF(p1)
        self._p2 = QPointF(p2)
        self._offset = float(offset)
        self._text_override = text_override
        self.arrow_size = float(arrow_size)
        self.text_height = float(text_height)

    @property
    def p1(self) -> QPointF: return QPointF(self._p1)
    @property
    def p2(self) -> QPointF: return QPointF(self._p2)
    @property
    def offset(self) -> float: return self._offset

    def _geometry(self):
        dx = self._p2.x() - self._p1.x()
        dy = self._p2.y() - self._p1.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            ux, uy = 1.0, 0.0
        else:
            ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        q1 = QPointF(self._p1.x() + nx*self._offset, self._p1.y() + ny*self._offset)
        q2 = QPointF(self._p2.x() + nx*self._offset, self._p2.y() + ny*self._offset)
        return q1, q2, ux, uy, nx, ny, length

    def boundingRect(self) -> QRectF:
        q1, q2, *_ = self._geometry()
        pts = [self._p1, self._p2, q1, q2]
        xs = [p.x() for p in pts]; ys = [p.y() for p in pts]
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)).adjusted(-20, -20, 20, 20)

    def paint(self, painter: QPainter, option, widget=None):
        q1, q2, ux, uy, nx, ny, length = self._geometry()
        color = QColor(255, 165, 0) if self._selected else (self.color_override or QColor("#ffffff"))
        painter.setPen(QPen(color, 0))
        painter.setBrush(color)
        painter.drawLine(self._p1, q1)
        painter.drawLine(self._p2, q2)
        painter.drawLine(q1, q2)
        self._draw_arrow(painter, q1, ux, uy)
        self._draw_arrow(painter, q2, -ux, -uy)
        mid = QPointF((q1.x()+q2.x())/2, (q1.y()+q2.y())/2)
        text = self._text_override or f"{length/GRID_UNIT:.3f}"
        th_px = max(1, int(self.text_height * GRID_UNIT))
        painter.setFont(QFont("Arial", th_px))
        off = th_px * 0.4
        painter.drawText(mid.x() + off, mid.y() - off, text)
        if self._selected:
            self._paint_grips(painter)

    def _draw_arrow(self, painter: QPainter, tip: QPointF, ux: float, uy: float):
        size = self.arrow_size
        nx, ny = -uy, ux
        back = QPointF(tip.x()+ux*size, tip.y()+uy*size)
        pts = QPolygonF([
            tip,
            QPointF(back.x()+nx*size*0.35, back.y()+ny*size*0.35),
            QPointF(back.x()-nx*size*0.35, back.y()-ny*size*0.35),
        ])
        painter.drawPolygon(pts)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT:
            return [self._p1, self._p2]
        if mode == SnapMode.MIDPOINT:
            q1, q2, *_ = self._geometry()
            return [QPointF((q1.x()+q2.x())/2, (q1.y()+q2.y())/2)]
        return []

    def line_segments(self) -> list[QLineF]:
        q1, q2, *_ = self._geometry()
        return [QLineF(self._p1, q1), QLineF(self._p2, q2), QLineF(q1, q2)]

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return any(_seg_dist(pt, s.p1(), s.p2()) <= threshold for s in self.line_segments())

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            for seg in self.line_segments():
                if rect.contains(seg.p1()) or rect.contains(seg.p2()):
                    return True
                for edge in _rect_edges(rect):
                    itype, _ = seg.intersects(edge)
                    if itype == QLineF.IntersectionType.BoundedIntersection:
                        return True
            return False
        return rect.contains(self.boundingRect())

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._p1 = QPointF(self._p1.x()+dx, self._p1.y()+dy)
        self._p2 = QPointF(self._p2.x()+dx, self._p2.y()+dy)
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._p1 = _scale_pt(self._p1, cx, cy, factor)
        self._p2 = _scale_pt(self._p2, cx, cy, factor)
        self._offset *= factor
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
        self._offset = -self._offset
        self.update()

    def clone(self) -> "DimLinearEntity":
        return DimLinearEntity(self._p1, self._p2, self._offset,
                               self._text_override, self.layer,
                               self.arrow_size, self.text_height)


class DimAngularEntity(CADEntity):
    def __init__(self, center: QPointF, p1: QPointF, p2: QPointF,
                 radius: float, layer: "Layer" | None = None,
                 arrow_size: float = 8.0, text_height: float = 2.5):
        super().__init__(layer or Layer("0"))
        self._center = QPointF(center)
        self._p1 = QPointF(p1)
        self._p2 = QPointF(p2)
        self._radius = float(radius)
        self.arrow_size = float(arrow_size)
        self.text_height = float(text_height)

    def _angles(self):
        a1 = math.degrees(math.atan2(-(self._p1.y()-self._center.y()),
                                      self._p1.x()-self._center.x())) % 360
        a2 = math.degrees(math.atan2(-(self._p2.y()-self._center.y()),
                                      self._p2.x()-self._center.x())) % 360
        span = (a2 - a1) % 360
        if span > 180:
            span -= 360
        return a1, span

    def _point_at(self, deg: float) -> QPointF:
        rad = math.radians(deg)
        return QPointF(self._center.x()+self._radius*math.cos(rad),
                       self._center.y()-self._radius*math.sin(rad))

    def boundingRect(self) -> QRectF:
        r = self._radius + 20
        return QRectF(self._center.x()-r, self._center.y()-r, r*2, r*2)

    def paint(self, painter: QPainter, option, widget=None):
        color = QColor(255, 165, 0) if self._selected else (self.color_override or QColor("#ffffff"))
        painter.setPen(QPen(color, 0))
        painter.setBrush(color)
        a1, span = self._angles()
        rect = QRectF(self._center.x()-self._radius, self._center.y()-self._radius,
                      self._radius*2, self._radius*2)
        painter.drawArc(rect, int(a1*16), int(span*16))
        e1 = self._point_at(a1)
        e2 = self._point_at(a1 + span)
        painter.drawLine(self._center, e1)
        painter.drawLine(self._center, e2)
        sign = 1 if span >= 0 else -1
        self._draw_tangent_arrow(painter, e1, a1, -sign)
        self._draw_tangent_arrow(painter, e2, a1 + span, sign)
        mid_ang = a1 + span/2
        text_pt = self._point_at(mid_ang)
        th_px = max(1, int(self.text_height * GRID_UNIT))
        painter.setFont(QFont("Arial", th_px))
        off = th_px * 0.4
        painter.drawText(text_pt.x() + off, text_pt.y() - off, f"{abs(span):.1f}°")
        if self._selected:
            self._paint_grips(painter)

    def _draw_tangent_arrow(self, painter: QPainter, tip: QPointF, angle: float, sign: float):
        rad = math.radians(angle)
        tx = -math.sin(rad) * sign
        ty = -math.cos(rad) * sign
        nx, ny = -ty, tx
        size = self.arrow_size
        back = QPointF(tip.x()-tx*size, tip.y()-ty*size)
        painter.drawPolygon(QPolygonF([
            tip,
            QPointF(back.x()+nx*size*0.35, back.y()+ny*size*0.35),
            QPointF(back.x()-nx*size*0.35, back.y()-ny*size*0.35),
        ]))

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.CENTER:
            return [self._center]
        if mode == SnapMode.ENDPOINT:
            return [self._p1, self._p2]
        return []

    def line_segments(self) -> list[QLineF]:
        pts = [self._point_at(self._angles()[0] + self._angles()[1]*i/24) for i in range(25)]
        return [QLineF(a, b) for a, b in zip(pts, pts[1:])]

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return any(_seg_dist(pt, s.p1(), s.p2()) <= threshold for s in self.line_segments())

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            return rect.intersects(self.boundingRect())
        return rect.contains(self.boundingRect())

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._center = QPointF(self._center.x()+dx, self._center.y()+dy)
        self._p1 = QPointF(self._p1.x()+dx, self._p1.y()+dy)
        self._p2 = QPointF(self._p2.x()+dx, self._p2.y()+dy)
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._center = _scale_pt(self._center, cx, cy, factor)
        self._p1 = _scale_pt(self._p1, cx, cy, factor)
        self._p2 = _scale_pt(self._p2, cx, cy, factor)
        self._radius *= abs(factor)
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._center = _rotate_pt(self._center, cx, cy, cos_a, sin_a)
        self._p1 = _rotate_pt(self._p1, cx, cy, cos_a, sin_a)
        self._p2 = _rotate_pt(self._p2, cx, cy, cos_a, sin_a)
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._center = _mirror_pt(self._center, ax, ay, bx, by)
        self._p1 = _mirror_pt(self._p1, ax, ay, bx, by)
        self._p2 = _mirror_pt(self._p2, ax, ay, bx, by)
        self.update()

    def clone(self) -> "DimAngularEntity":
        return DimAngularEntity(self._center, self._p1, self._p2,
                                self._radius, self.layer,
                                self.arrow_size, self.text_height)


class HatchEntity(CADEntity):
    def __init__(self, boundary: list[QPointF], pattern: str = "ANSI31",
                 scale: float = 1.0, angle: float = 0.0,
                 layer: "Layer" | None = None):
        super().__init__(layer or Layer("0"))
        self._boundary = [QPointF(p) for p in boundary]
        self._pattern = pattern
        self._scale = float(scale)
        self._angle = float(angle)

    def boundary(self) -> list[QPointF]:
        return [QPointF(p) for p in self._boundary]

    def boundingRect(self) -> QRectF:
        if not self._boundary:
            return QRectF()
        xs = [p.x() for p in self._boundary]; ys = [p.y() for p in self._boundary]
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)).adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None):
        if len(self._boundary) < 3:
            return
        poly = QPolygonF(self._boundary)
        color = QColor(255, 165, 0) if self._selected else (self.color_override or self.layer.color)
        path = QPainterPath()
        path.addPolygon(poly)
        painter.save()
        if self._pattern == "SOLID":
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(color)
            fill.setAlpha(80)
            painter.setBrush(QBrush(fill))
            painter.drawPolygon(poly)
        else:
            painter.setClipPath(path)
            painter.setPen(QPen(color, 0))
            rect = self.boundingRect().adjusted(-100, -100, 100, 100)
            spacing = max(1.0, 10.0 * self._scale)
            h = rect.height() + rect.width()
            if self._pattern in ("ANSI31",):
                # 45° diagonal (bottom-left to top-right in Qt coords)
                x = rect.left() - h
                while x <= rect.right() + h:
                    painter.drawLine(QPointF(x, rect.bottom()),
                                     QPointF(x + h, rect.top()))
                    x += spacing
            elif self._pattern == "NET45":
                # -45° diagonal
                x = rect.left() - h
                while x <= rect.right() + h:
                    painter.drawLine(QPointF(x, rect.top()),
                                     QPointF(x + h, rect.bottom()))
                    x += spacing
            elif self._pattern == "CROSS":
                # Crosshatch: both diagonals
                x = rect.left() - h
                while x <= rect.right() + h:
                    painter.drawLine(QPointF(x, rect.bottom()), QPointF(x + h, rect.top()))
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x + h, rect.bottom()))
                    x += spacing
            elif self._pattern == "HORIZONTAL":
                y = rect.top()
                while y <= rect.bottom():
                    painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                    y += spacing
            elif self._pattern == "VERTICAL":
                x = rect.left()
                while x <= rect.right():
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                    x += spacing
            elif self._pattern == "NET":
                # Grid: horizontal + vertical
                y = rect.top()
                while y <= rect.bottom():
                    painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
                    y += spacing
                x = rect.left()
                while x <= rect.right():
                    painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                    x += spacing
        painter.restore()
        if self._selected:
            self._paint_grips(painter)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if mode == SnapMode.ENDPOINT:
            return [QPointF(p) for p in self._boundary]
        return []

    def line_segments(self) -> list[QLineF]:
        pts = self._boundary
        return [QLineF(pts[i], pts[(i+1) % len(pts)]) for i in range(len(pts))]

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return QPolygonF(self._boundary).containsPoint(pt, Qt.FillRule.OddEvenFill)

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            return rect.intersects(self.boundingRect())
        return rect.contains(self.boundingRect())

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._boundary = [QPointF(p.x()+dx, p.y()+dy) for p in self._boundary]
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._boundary = [_rotate_pt(p, cx, cy, cos_a, sin_a) for p in self._boundary]
        self._angle = (self._angle + angle_deg) % 360
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._boundary = [_mirror_pt(p, ax, ay, bx, by) for p in self._boundary]
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._boundary = [_scale_pt(p, cx, cy, factor) for p in self._boundary]
        self._scale *= abs(factor)
        self.update()

    def clone(self) -> "HatchEntity":
        return HatchEntity(self._boundary, self._pattern, self._scale,
                           self._angle, self.layer)


class SplineEntity(CADEntity):
    def __init__(self, control_points: list[QPointF], closed: bool = False,
                 layer: "Layer" | None = None):
        super().__init__(layer or Layer("0"))
        self._control_points = [QPointF(p) for p in control_points]
        self._closed = bool(closed)

    def control_points(self) -> list[QPointF]:
        return [QPointF(p) for p in self._control_points]

    def curve_points(self) -> list[QPointF]:
        return _catmull_rom_points(self._control_points, self._closed)

    def boundingRect(self) -> QRectF:
        pts = self.curve_points() or self._control_points
        if not pts:
            return QRectF()
        xs = [p.x() for p in pts]; ys = [p.y() for p in pts]
        return QRectF(min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)).adjusted(-6, -6, 6, 6)

    def paint(self, painter: QPainter, option, widget=None):
        pts = self.curve_points()
        if len(pts) < 2:
            return
        pen = QPen(self.draw_color, self.layer.lineweight)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for a, b in zip(pts, pts[1:]):
            painter.drawLine(a, b)
        if self._selected:
            self._paint_grips(painter)

    def snap_points(self, mode: SnapMode) -> list[QPointF]:
        if not self._control_points:
            return []
        if mode == SnapMode.ENDPOINT:
            return [self._control_points[0], self._control_points[-1]]
        if mode == SnapMode.MIDPOINT:
            pts = self.curve_points()
            return [QPointF((a.x()+b.x())/2, (a.y()+b.y())/2)
                    for a, b in zip(pts, pts[1:])]
        return []

    def line_segments(self) -> list[QLineF]:
        pts = self.curve_points()
        return [QLineF(a, b) for a, b in zip(pts, pts[1:])]

    def hit_test(self, pt: QPointF, threshold: float) -> bool:
        return any(_seg_dist(pt, s.p1(), s.p2()) <= threshold for s in self.line_segments())

    def intersects_rect(self, rect: QRectF, crossing: bool) -> bool:
        if crossing:
            for seg in self.line_segments():
                if rect.contains(seg.p1()) or rect.contains(seg.p2()):
                    return True
                for edge in _rect_edges(rect):
                    itype, _ = seg.intersects(edge)
                    if itype == QLineF.IntersectionType.BoundedIntersection:
                        return True
            return False
        return rect.contains(self.boundingRect())

    def translate(self, dx: float, dy: float):
        self.prepareGeometryChange()
        self._control_points = [QPointF(p.x()+dx, p.y()+dy) for p in self._control_points]
        self.update()

    def rotate_about(self, cx: float, cy: float, angle_deg: float):
        self.prepareGeometryChange()
        cos_a = math.cos(math.radians(angle_deg))
        sin_a = math.sin(math.radians(angle_deg))
        self._control_points = [_rotate_pt(p, cx, cy, cos_a, sin_a) for p in self._control_points]
        self.update()

    def mirror_across(self, ax: float, ay: float, bx: float, by: float):
        self.prepareGeometryChange()
        self._control_points = [_mirror_pt(p, ax, ay, bx, by) for p in self._control_points]
        self.update()

    def scale_about(self, cx: float, cy: float, factor: float):
        self.prepareGeometryChange()
        self._control_points = [_scale_pt(p, cx, cy, factor) for p in self._control_points]
        self.update()

    def clone(self) -> "SplineEntity":
        return SplineEntity(self._control_points, self._closed, self.layer)


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


def _catmull_rom_points(pts: list[QPointF], closed: bool, steps: int = 20) -> list[QPointF]:
    if len(pts) < 2:
        return [QPointF(p) for p in pts]
    src = [QPointF(p) for p in pts]
    count = len(src) if closed else len(src) - 1
    out = []
    for i in range(count):
        p0 = src[(i - 1) % len(src)] if closed or i > 0 else src[0]
        p1 = src[i % len(src)]
        p2 = src[(i + 1) % len(src)]
        p3 = src[(i + 2) % len(src)] if closed or i + 2 < len(src) else src[-1]
        for j in range(steps):
            t = j / steps
            t2 = t * t
            t3 = t2 * t
            x = 0.5 * ((2*p1.x()) + (-p0.x()+p2.x())*t +
                       (2*p0.x()-5*p1.x()+4*p2.x()-p3.x())*t2 +
                       (-p0.x()+3*p1.x()-3*p2.x()+p3.x())*t3)
            y = 0.5 * ((2*p1.y()) + (-p0.y()+p2.y())*t +
                       (2*p0.y()-5*p1.y()+4*p2.y()-p3.y())*t2 +
                       (-p0.y()+3*p1.y()-3*p2.y()+p3.y())*t3)
            out.append(QPointF(x, y))
    if closed:
        out.append(QPointF(out[0]))
    else:
        out.append(QPointF(src[-1]))
    return out


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


def _scale_pt(pt: QPointF, cx: float, cy: float, factor: float) -> QPointF:
    return QPointF(cx + (pt.x()-cx)*factor, cy + (pt.y()-cy)*factor)


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
