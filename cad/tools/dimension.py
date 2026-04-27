import math
from PySide6.QtCore import Qt, QPointF, QLineF
from PySide6.QtGui import QPen, QColor, QPainter
from .base import BaseTool
from ..entities import DimLinearEntity, DimAngularEntity, LineEntity, PolylineEntity
from ..undo import AddEntityCommand
from ..constants import GRID_UNIT

PREVIEW_COLOR = QColor("#ffffff")

STATE_P1 = 0
STATE_P2 = 1
STATE_OFFSET = 2

STATE_LINE1 = 0
STATE_LINE2 = 1


class _PreviewDimLinearEntity(DimLinearEntity):
    def paint(self, painter: QPainter, option, widget=None):
        q1, q2, ux, uy, nx, ny, length = self._geometry()
        color = QColor(PREVIEW_COLOR)
        color.setAlpha(150)
        pen = QPen(color, 0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(color)
        painter.drawLine(self._p1, q1)
        painter.drawLine(self._p2, q2)
        painter.drawLine(q1, q2)
        self._draw_arrow(painter, q1, ux, uy)
        self._draw_arrow(painter, q2, -ux, -uy)
        mid = QPointF((q1.x()+q2.x())/2, (q1.y()+q2.y())/2)
        text = self._text_override or f"{length/GRID_UNIT:.3f}"
        painter.drawText(mid.x()+6, mid.y()-6, text)


class _PreviewDimAngularEntity(DimAngularEntity):
    def paint(self, painter: QPainter, option, widget=None):
        color = QColor(PREVIEW_COLOR)
        color.setAlpha(150)
        pen = QPen(color, 0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(color)
        a1, span = self._angles()
        rect = self.boundingRect().adjusted(20, 20, -20, -20)
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
        painter.drawText(text_pt.x()+6, text_pt.y()-6, f"{abs(span):.1f}°")


class DimLinearTool(BaseTool):
    name = "dimlinear"

    def __init__(self):
        super().__init__()
        self._state = STATE_P1
        self._p1: QPointF | None = None
        self._p2: QPointF | None = None
        self._cursor: QPointF | None = None
        self._offset = 0.0

    @property
    def is_idle(self):
        return self._state == STATE_P1

    @property
    def prompt(self):
        if self._state == STATE_P1:
            return "DIMLINEAR  Specify first extension line origin:"
        if self._state == STATE_P2:
            return "DIMLINEAR  Specify second extension line origin:"
        return f"DIMLINEAR  offset={abs(self._offset)/GRID_UNIT:.2f}u  [type offset + Enter]"

    def activate(self, view):
        super().activate(view)
        self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._state == STATE_P1:
            self._p1 = QPointF(snapped)
            self._state = STATE_P2
        elif self._state == STATE_P2:
            self._p2 = QPointF(snapped)
            self._state = STATE_OFFSET
        elif self._state == STATE_OFFSET:
            self._commit()
        if self.view:
            self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self._state == STATE_OFFSET and self._p1 and self._p2:
            self._offset = _signed_offset(self._p1, self._p2, snapped)
        if self.view:
            self.view._update_prompt()
            self.view.viewport().update()

    def on_command(self, cmd: str) -> bool:
        if self._state != STATE_OFFSET:
            return False
        try:
            self._offset = float(cmd) * GRID_UNIT
        except ValueError:
            return False
        self._commit()
        return True

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_OFFSET or self._p1 is None or self._p2 is None:
            return
        ent = _PreviewDimLinearEntity(self._p1, self._p2, self._offset,
                                      layer=self.view.layer_manager.current)
        painter.save()
        painter.setWorldTransform(self.view.viewportTransform())
        ent.paint(painter, None)
        painter.restore()
        if self._cursor is not None:
            vp = self.view.mapFromScene(self._cursor)
            painter.setPen(QPen(PREVIEW_COLOR, 1))
            painter.drawText(vp.x() + 8, vp.y() - 10,
                             f"{abs(self._offset)/GRID_UNIT:.2f}u")

    def cancel(self):
        self._state = STATE_P1
        self._p1 = None
        self._p2 = None
        self._cursor = None
        self._offset = 0.0
        if self.view:
            self.view.viewport().update()

    def _commit(self):
        if self._p1 is None or self._p2 is None:
            return
        ent = DimLinearEntity(self._p1, self._p2, self._offset,
                              layer=self.view.layer_manager.current)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self.cancel()


class DimAngularTool(BaseTool):
    name = "dimangular"

    def __init__(self):
        super().__init__()
        self._state = STATE_LINE1
        self._line1 = None
        self._line2 = None
        self._cursor: QPointF | None = None

    @property
    def is_idle(self):
        return self._state == STATE_LINE1

    @property
    def prompt(self):
        if self._state == STATE_LINE1:
            return "DIMANGULAR  Select first line:"
        return "DIMANGULAR  Select second line:"

    def activate(self, view):
        super().activate(view)
        self.cancel()

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        threshold = 8.0 / self.view.transform().m11()
        if self._state == STATE_LINE1:
            pick = _pick_line_segment(self.view.cad_scene.all_entities(), snapped, threshold)
            if pick is None:
                return
            self._line1 = pick
            self._line1[0].selected = True
            self._state = STATE_LINE2
        elif self._state == STATE_LINE2:
            exclude = self._line1[0] if self._line1 else None
            pick = _pick_line_segment(self.view.cad_scene.all_entities(), snapped, threshold, exclude)
            if pick is None:
                return
            self._line2 = pick
            if self._line1:
                self._line1[0].selected = False
            self._commit()
        if self.view:
            self.view.viewport().update()

    def on_move(self, snapped: QPointF, raw: QPointF, event):
        self._cursor = QPointF(snapped)
        if self.view:
            self.view.viewport().update()

    def draw_overlay(self, painter: QPainter):
        if self._state != STATE_LINE2 or self._line1 is None:
            return
        hovered = getattr(self.view, "_hovered_entity", None)
        if hovered is None or hovered is self._line1[0]:
            return
        if not isinstance(hovered, (LineEntity, PolylineEntity)):
            return
        pick2 = _nearest_segment_for_entity(hovered, self._cursor)
        if pick2 is None:
            return
        geom = _angular_geometry(self._line1[1], pick2)
        if geom is None:
            return
        center, p1, p2, radius = geom
        ent = _PreviewDimAngularEntity(center, p1, p2, radius,
                                       layer=self.view.layer_manager.current)
        painter.save()
        painter.setWorldTransform(self.view.viewportTransform())
        ent.paint(painter, None)
        painter.restore()

    def cancel(self):
        if self._line1:
            self._line1[0].selected = False
        self._state = STATE_LINE1
        self._line1 = None
        self._line2 = None
        self._cursor = None
        if self.view:
            self.view.viewport().update()

    def _commit(self):
        if self._line1 is None or self._line2 is None:
            return
        geom = _angular_geometry(self._line1[1], self._line2[1])
        if geom is None:
            if self.view:
                self.view.status_bar.showMessage("Lines are parallel", 2000)
            self.cancel()
            return
        center, p1, p2, radius = geom
        ent = DimAngularEntity(center, p1, p2, radius,
                               layer=self.view.layer_manager.current)
        self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        self.cancel()


def _signed_offset(p1: QPointF, p2: QPointF, pt: QPointF) -> float:
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 0.0
    nx = -dy / length
    ny = dx / length
    return (pt.x() - p1.x()) * nx + (pt.y() - p1.y()) * ny


def _pick_line_segment(entities: list, pt: QPointF, threshold: float, exclude=None):
    best = None
    best_dist = threshold
    for ent in entities:
        if ent is exclude:
            continue
        if not isinstance(ent, (LineEntity, PolylineEntity)):
            continue
        for seg in ent.line_segments():
            dist = _seg_dist(pt, seg.p1(), seg.p2())
            if dist <= best_dist:
                best = (ent, QLineF(seg))
                best_dist = dist
    return best


def _nearest_segment_for_entity(ent, pt: QPointF | None):
    segs = ent.line_segments()
    if not segs:
        return None
    if pt is None:
        return QLineF(segs[0])
    return QLineF(min(segs, key=lambda seg: _seg_dist(pt, seg.p1(), seg.p2())))


def _angular_geometry(seg1: QLineF, seg2: QLineF):
    itype, center = seg1.intersects(seg2)
    if itype == QLineF.IntersectionType.NoIntersection:
        return None
    p1 = _arm_point(center, seg1)
    p2 = _arm_point(center, seg2)
    if p1 is None or p2 is None:
        return None
    return center, p1, p2, GRID_UNIT * 8


def _arm_point(center: QPointF, seg: QLineF):
    a = seg.p1()
    b = seg.p2()
    da = math.hypot(a.x() - center.x(), a.y() - center.y())
    db = math.hypot(b.x() - center.x(), b.y() - center.y())
    far = a if da >= db else b
    dx = far.x() - center.x()
    dy = far.y() - center.y()
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    scale = GRID_UNIT * 5 / length
    return QPointF(center.x() + dx * scale, center.y() + dy * scale)


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx = b.x() - a.x()
    dy = b.y() - a.y()
    if dx == 0 and dy == 0:
        return math.hypot(p.x() - a.x(), p.y() - a.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / (dx * dx + dy * dy)))
    cx = a.x() + t * dx
    cy = a.y() + t * dy
    return math.hypot(p.x() - cx, p.y() - cy)
