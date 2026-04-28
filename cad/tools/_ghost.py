import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen

from ..entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity,
    TextEntity, XLineEntity, SplineEntity, HatchEntity,
    DimLinearEntity, DimAngularEntity, PointEntity,
    _mirror_pt, _scale_pt,
)


GHOST_PEN = QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine)
GHOST_PEN.setCosmetic(True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _translate_pt(pt: QPointF, dx: float, dy: float) -> QPointF:
    return QPointF(pt.x() + dx, pt.y() + dy)


def _vp(view, pt: QPointF) -> QPointF:
    return QPointF(view.mapFromScene(pt))


def _xline_draw(painter, view, pt: QPointF, angle_deg: float):
    HALF = XLineEntity.XLINE_HALF
    rad = math.radians(angle_deg)
    ddx = math.cos(rad) * HALF
    ddy = math.sin(rad) * HALF
    p1 = _vp(view, QPointF(pt.x() - ddx, pt.y() + ddy))
    p2 = _vp(view, QPointF(pt.x() + ddx, pt.y() - ddy))
    painter.drawLine(p1, p2)


def _draw_polyline(painter, view, pts):
    for a, b in zip(pts, pts[1:]):
        painter.drawLine(_vp(view, a), _vp(view, b))


def _draw_closed_poly(painter, view, pts):
    for i in range(len(pts)):
        painter.drawLine(_vp(view, pts[i]), _vp(view, pts[(i + 1) % len(pts)]))


def _dimlinear_segs(p1, p2, offset):
    """Return (p1, q1, p2, q2) for a DimLinear with given p1, p2, offset."""
    ddx = p2.x() - p1.x()
    ddy = p2.y() - p1.y()
    L = math.hypot(ddx, ddy)
    if L < 1e-6:
        nx, ny = 0.0, 1.0
    else:
        ux, uy = ddx / L, ddy / L
        nx, ny = -uy, ux
    q1 = QPointF(p1.x() + nx * offset, p1.y() + ny * offset)
    q2 = QPointF(p2.x() + nx * offset, p2.y() + ny * offset)
    return p1, q1, p2, q2


def _draw_dimlinear(painter, view, p1, p2, offset):
    p1v, q1v, p2v, q2v = _dimlinear_segs(p1, p2, offset)
    painter.drawLine(_vp(view, p1v), _vp(view, q1v))
    painter.drawLine(_vp(view, p2v), _vp(view, q2v))
    painter.drawLine(_vp(view, q1v), _vp(view, q2v))


def _draw_dimangular(painter, view, center, p1, p2, radius, scale):
    a1 = math.degrees(math.atan2(-(p1.y() - center.y()),
                                   p1.x() - center.x())) % 360
    a2 = math.degrees(math.atan2(-(p2.y() - center.y()),
                                   p2.x() - center.x())) % 360
    span = (a2 - a1) % 360
    if span > 180:
        span -= 360
    cv = _vp(view, center)
    r = radius * scale
    rect = QRectF(cv.x() - r, cv.y() - r, r * 2, r * 2)
    painter.drawArc(rect, int(a1 * 16), int(span * 16))
    p1v = _vp(view, p1)
    p2v = _vp(view, p2)
    painter.drawLine(cv, p1v)
    painter.drawLine(cv, p2v)


# ── translated ────────────────────────────────────────────────────────────────

def draw_entities_ghost_translated(painter, view, entities, dx, dy):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, _translate_pt(entity.p1, dx, dy)),
                             _vp(view, _translate_pt(entity.p2, dx, dy)))
        elif isinstance(entity, PolylineEntity):
            _draw_polyline(painter, view,
                           [_translate_pt(v, dx, dy) for v in entity.vertices()])
        elif isinstance(entity, CircleEntity):
            c = _vp(view, _translate_pt(entity.center, dx, dy))
            r = entity.radius * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            c = _vp(view, _translate_pt(entity.center, dx, dy))
            r = entity.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(entity.start_angle * 16), int(entity.span_angle * 16))
        elif isinstance(entity, EllipseEntity):
            c = _vp(view, _translate_pt(entity.center, dx, dy))
            rx = entity.rx * scale
            ry = entity.ry * scale
            painter.save()
            painter.translate(c)
            painter.rotate(-entity.angle_deg)
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()
        elif isinstance(entity, XLineEntity):
            _xline_draw(painter, view,
                        _translate_pt(entity._point, dx, dy), entity._angle_deg)
        elif isinstance(entity, SplineEntity):
            _draw_polyline(painter, view,
                           [_translate_pt(p, dx, dy) for p in entity.curve_points()])
        elif isinstance(entity, HatchEntity):
            _draw_closed_poly(painter, view,
                              [_translate_pt(p, dx, dy) for p in entity.boundary()])
        elif isinstance(entity, DimLinearEntity):
            _draw_dimlinear(painter, view,
                            _translate_pt(entity.p1, dx, dy),
                            _translate_pt(entity.p2, dx, dy),
                            entity._offset)
        elif isinstance(entity, DimAngularEntity):
            _draw_dimangular(painter, view,
                             _translate_pt(entity._center, dx, dy),
                             _translate_pt(entity._p1, dx, dy),
                             _translate_pt(entity._p2, dx, dy),
                             entity._radius, scale)
        elif isinstance(entity, PointEntity):
            painter.drawPoint(_vp(view, _translate_pt(entity.pos, dx, dy)))
        elif isinstance(entity, TextEntity):
            corners = entity._world_corners()
            translated = [QPointF(p.x() + dx, p.y() + dy) for p in corners]
            _draw_closed_poly(painter, view, translated)


# ── mirrored ─────────────────────────────────────────────────────────────────

def draw_entities_ghost_mirrored(painter, view, entities, ax, ay, bx, by):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()
    axis_angle = math.degrees(math.atan2(by - ay, bx - ax))

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, _mirror_pt(entity.p1, ax, ay, bx, by)),
                             _vp(view, _mirror_pt(entity.p2, ax, ay, bx, by)))
        elif isinstance(entity, PolylineEntity):
            _draw_polyline(painter, view,
                           [_mirror_pt(v, ax, ay, bx, by) for v in entity.vertices()])
        elif isinstance(entity, CircleEntity):
            c = _vp(view, _mirror_pt(entity.center, ax, ay, bx, by))
            r = entity.radius * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            ghost = entity.clone()
            ghost.mirror_across(ax, ay, bx, by)
            c = _vp(view, ghost.center)
            r = ghost.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(ghost.start_angle * 16), int(ghost.span_angle * 16))
        elif isinstance(entity, EllipseEntity):
            new_c = _mirror_pt(entity.center, ax, ay, bx, by)
            c = _vp(view, new_c)
            rx = entity.rx * scale
            ry = entity.ry * scale
            new_angle = 2 * axis_angle - entity.angle_deg
            painter.save()
            painter.translate(c)
            painter.rotate(-new_angle)
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()
        elif isinstance(entity, XLineEntity):
            new_pt = _mirror_pt(entity._point, ax, ay, bx, by)
            new_angle = (2 * axis_angle - entity._angle_deg) % 360
            _xline_draw(painter, view, new_pt, new_angle)
        elif isinstance(entity, SplineEntity):
            _draw_polyline(painter, view,
                           [_mirror_pt(p, ax, ay, bx, by) for p in entity.curve_points()])
        elif isinstance(entity, HatchEntity):
            _draw_closed_poly(painter, view,
                              [_mirror_pt(p, ax, ay, bx, by) for p in entity.boundary()])
        elif isinstance(entity, DimLinearEntity):
            _draw_dimlinear(painter, view,
                            _mirror_pt(entity.p1, ax, ay, bx, by),
                            _mirror_pt(entity.p2, ax, ay, bx, by),
                            -entity._offset)
        elif isinstance(entity, DimAngularEntity):
            _draw_dimangular(painter, view,
                             _mirror_pt(entity._center, ax, ay, bx, by),
                             _mirror_pt(entity._p1, ax, ay, bx, by),
                             _mirror_pt(entity._p2, ax, ay, bx, by),
                             entity._radius, scale)
        elif isinstance(entity, PointEntity):
            painter.drawPoint(_vp(view, _mirror_pt(entity.pos, ax, ay, bx, by)))
        elif isinstance(entity, TextEntity):
            corners = entity._world_corners()
            mirrored = [_mirror_pt(p, ax, ay, bx, by) for p in corners]
            _draw_closed_poly(painter, view, mirrored)


# ── scaled ────────────────────────────────────────────────────────────────────

def draw_entities_ghost_scaled(painter, view, entities, cx, cy, factor):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()

    def sc(pt):
        return QPointF(cx + (pt.x() - cx) * factor, cy + (pt.y() - cy) * factor)

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, sc(entity.p1)), _vp(view, sc(entity.p2)))
        elif isinstance(entity, PolylineEntity):
            _draw_polyline(painter, view, [sc(v) for v in entity.vertices()])
        elif isinstance(entity, CircleEntity):
            c = _vp(view, sc(entity.center))
            r = entity.radius * abs(factor) * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            ghost = entity.clone()
            ghost.scale_about(cx, cy, factor)
            c = _vp(view, ghost.center)
            r = ghost.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(ghost.start_angle * 16), int(ghost.span_angle * 16))
        elif isinstance(entity, EllipseEntity):
            c = _vp(view, sc(entity.center))
            rx = entity.rx * abs(factor) * scale
            ry = entity.ry * abs(factor) * scale
            painter.save()
            painter.translate(c)
            painter.rotate(-entity.angle_deg)
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()
        elif isinstance(entity, XLineEntity):
            _xline_draw(painter, view, sc(entity._point), entity._angle_deg)
        elif isinstance(entity, SplineEntity):
            _draw_polyline(painter, view, [sc(p) for p in entity.curve_points()])
        elif isinstance(entity, HatchEntity):
            _draw_closed_poly(painter, view, [sc(p) for p in entity.boundary()])
        elif isinstance(entity, DimLinearEntity):
            _draw_dimlinear(painter, view, sc(entity.p1), sc(entity.p2),
                            entity._offset * factor)
        elif isinstance(entity, DimAngularEntity):
            _draw_dimangular(painter, view,
                             sc(entity._center), sc(entity._p1), sc(entity._p2),
                             entity._radius * abs(factor), scale)
        elif isinstance(entity, PointEntity):
            painter.drawPoint(_vp(view, sc(entity.pos)))
        elif isinstance(entity, TextEntity):
            corners = entity._world_corners()
            scaled_corners = [_scale_pt(p, cx, cy, factor) for p in corners]
            _draw_closed_poly(painter, view, scaled_corners)


# ── rotated ───────────────────────────────────────────────────────────────────

def draw_entities_ghost_rotated(painter, view, entities, cx, cy, angle_deg):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()
    cos_a = math.cos(math.radians(angle_deg))
    sin_a = math.sin(math.radians(angle_deg))

    def rot(pt):
        dx = pt.x() - cx
        dy = pt.y() - cy
        return QPointF(cx + dx * cos_a + dy * sin_a,
                       cy - dx * sin_a + dy * cos_a)

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, rot(entity.p1)), _vp(view, rot(entity.p2)))
        elif isinstance(entity, PolylineEntity):
            _draw_polyline(painter, view, [rot(v) for v in entity.vertices()])
        elif isinstance(entity, CircleEntity):
            c = _vp(view, rot(entity.center))
            r = entity.radius * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            ghost = entity.clone()
            ghost.rotate_about(cx, cy, angle_deg)
            c = _vp(view, ghost.center)
            r = ghost.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(ghost.start_angle * 16), int(ghost.span_angle * 16))
        elif isinstance(entity, EllipseEntity):
            c = _vp(view, rot(entity.center))
            rx = entity.rx * scale
            ry = entity.ry * scale
            painter.save()
            painter.translate(c)
            painter.rotate(-(entity.angle_deg + angle_deg))
            painter.drawEllipse(QRectF(-rx, -ry, rx * 2, ry * 2))
            painter.restore()
        elif isinstance(entity, XLineEntity):
            new_pt = rot(entity._point)
            new_angle = (entity._angle_deg + angle_deg) % 360
            _xline_draw(painter, view, new_pt, new_angle)
        elif isinstance(entity, SplineEntity):
            _draw_polyline(painter, view, [rot(p) for p in entity.curve_points()])
        elif isinstance(entity, HatchEntity):
            _draw_closed_poly(painter, view, [rot(p) for p in entity.boundary()])
        elif isinstance(entity, DimLinearEntity):
            _draw_dimlinear(painter, view, rot(entity.p1), rot(entity.p2), entity._offset)
        elif isinstance(entity, DimAngularEntity):
            _draw_dimangular(painter, view,
                             rot(entity._center), rot(entity._p1), rot(entity._p2),
                             entity._radius, scale)
        elif isinstance(entity, PointEntity):
            painter.drawPoint(_vp(view, rot(entity.pos)))
        elif isinstance(entity, TextEntity):
            corners = entity._world_corners()
            rotated = [rot(p) for p in corners]
            _draw_closed_poly(painter, view, rotated)
