from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPen

from ..entities import LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity, _mirror_pt


GHOST_PEN = QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine)
GHOST_PEN.setCosmetic(True)


def draw_entities_ghost_translated(painter, view, entities, dx, dy):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, _translate_pt(entity.p1, dx, dy)),
                             _vp(view, _translate_pt(entity.p2, dx, dy)))
        elif isinstance(entity, PolylineEntity):
            verts = [_vp(view, _translate_pt(v, dx, dy)) for v in entity.vertices()]
            for a, b in zip(verts, verts[1:]):
                painter.drawLine(a, b)
        elif isinstance(entity, CircleEntity):
            c = _vp(view, _translate_pt(entity.center, dx, dy))
            r = entity.radius * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            c = _vp(view, _translate_pt(entity.center, dx, dy))
            r = entity.radius * scale
            rect = QRectF(c.x() - r, c.y() - r, r * 2, r * 2)
            painter.drawArc(rect, int(entity.start_angle * 16), int(entity.span_angle * 16))


def draw_entities_ghost_mirrored(painter, view, entities, ax, ay, bx, by):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, _mirror_pt(entity.p1, ax, ay, bx, by)),
                             _vp(view, _mirror_pt(entity.p2, ax, ay, bx, by)))
        elif isinstance(entity, PolylineEntity):
            verts = [_vp(view, _mirror_pt(v, ax, ay, bx, by)) for v in entity.vertices()]
            for a, b in zip(verts, verts[1:]):
                painter.drawLine(a, b)
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


def draw_entities_ghost_scaled(painter, view, entities, cx, cy, factor):
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()

    def sc(pt):
        return QPointF(cx + (pt.x()-cx)*factor, cy + (pt.y()-cy)*factor)

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, sc(entity.p1)), _vp(view, sc(entity.p2)))
        elif isinstance(entity, PolylineEntity):
            verts = [_vp(view, sc(v)) for v in entity.vertices()]
            for a, b in zip(verts, verts[1:]):
                painter.drawLine(a, b)
        elif isinstance(entity, CircleEntity):
            c = _vp(view, sc(entity.center))
            r = entity.radius * abs(factor) * scale
            painter.drawEllipse(c, r, r)
        elif isinstance(entity, ArcEntity):
            ghost = entity.clone()
            ghost.scale_about(cx, cy, factor)
            c = _vp(view, ghost.center)
            r = ghost.radius * scale
            rect = QRectF(c.x()-r, c.y()-r, r*2, r*2)
            painter.drawArc(rect, int(ghost.start_angle*16), int(ghost.span_angle*16))


def draw_entities_ghost_rotated(painter, view, entities, cx, cy, angle_deg):
    import math
    painter.setPen(GHOST_PEN)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    scale = view.transform().m11()
    cos_a = math.cos(math.radians(angle_deg))
    sin_a = math.sin(math.radians(angle_deg))

    def rot(pt):
        dx = pt.x() - cx
        dy = pt.y() - cy
        nx = cx + dx * cos_a + dy * sin_a
        ny = cy - dx * sin_a + dy * cos_a
        return QPointF(nx, ny)

    for entity in entities:
        if isinstance(entity, LineEntity):
            painter.drawLine(_vp(view, rot(entity.p1)), _vp(view, rot(entity.p2)))
        elif isinstance(entity, PolylineEntity):
            verts = [_vp(view, rot(v)) for v in entity.vertices()]
            for a, b in zip(verts, verts[1:]):
                painter.drawLine(a, b)
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


def _translate_pt(pt: QPointF, dx: float, dy: float) -> QPointF:
    return QPointF(pt.x() + dx, pt.y() + dy)


def _vp(view, pt: QPointF) -> QPointF:
    return QPointF(view.mapFromScene(pt))
