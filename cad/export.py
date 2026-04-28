from __future__ import annotations

import math
from PySide6.QtCore import QRectF, QSizeF, QMarginsF
from PySide6.QtGui import QPainter, QColor, QPdfWriter, QPageSize

try:
    import ezdxf
    HAS_EZDXF = True
except ImportError:
    HAS_EZDXF = False

from .constants import GRID_UNIT
from .entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity,
    XLineEntity, TextEntity, DimLinearEntity, DimAngularEntity,
    HatchEntity, SplineEntity, PointEntity,
)


# ── Coordinate helpers ────────────────────────────────────────────────────────
# Scene uses Y-down (Qt); DXF uses Y-up.  Divide by GRID_UNIT to get drawing units.

def _sx(x: float) -> float: return x / GRID_UNIT
def _sy(y: float) -> float: return -y / GRID_UNIT
def _p2(pt) -> tuple: return (_sx(pt.x()), _sy(pt.y()))
def _p3(pt) -> tuple: return (_sx(pt.x()), _sy(pt.y()), 0.0)


def _arc_angles(start: float, span: float) -> tuple[float, float]:
    """Convert Qt arc (start, span) to ezdxf (start, end) going CCW."""
    if span >= 0:
        s, e = start % 360, (start + span) % 360
    else:
        s, e = (start + span) % 360, start % 360
    if s < 0: s += 360
    if e < 0: e += 360
    return s, e


# ── DXF export ────────────────────────────────────────────────────────────────

def export_dxf(scene, path: str) -> None:
    if not HAS_EZDXF:
        raise RuntimeError("ezdxf is not installed — run: pip install ezdxf")

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    for ent in scene.all_entities():
        att = {"layer": ent.layer.name if ent.layer else "0"}

        if isinstance(ent, LineEntity):
            msp.add_line(_p3(ent.p1), _p3(ent.p2), dxfattribs=att)

        elif isinstance(ent, PolylineEntity):
            msp.add_lwpolyline([_p2(v) for v in ent.vertices()], dxfattribs=att)

        elif isinstance(ent, CircleEntity):
            msp.add_circle(_p3(ent.center), ent.radius / GRID_UNIT, dxfattribs=att)

        elif isinstance(ent, ArcEntity):
            dxf_start, dxf_end = _arc_angles(ent.start_angle, ent.span_angle)
            msp.add_arc(_p3(ent.center), ent.radius / GRID_UNIT,
                        dxf_start, dxf_end, dxfattribs=att)

        elif isinstance(ent, EllipseEntity):
            angle_rad = math.radians(ent.angle_deg)
            rx = ent.rx / GRID_UNIT
            major = (rx * math.cos(angle_rad), rx * math.sin(angle_rad), 0.0)
            ratio = (ent.ry / ent.rx) if ent.rx > 1e-9 else 1.0
            msp.add_ellipse(_p3(ent.center), major, ratio, dxfattribs=att)

        elif isinstance(ent, XLineEntity):
            angle_rad = math.radians(ent._angle_deg)
            msp.add_xline(_p3(ent._point),
                          (math.cos(angle_rad), math.sin(angle_rad), 0.0),
                          dxfattribs=att)

        elif isinstance(ent, PointEntity):
            msp.add_point(_p3(ent.pos), dxfattribs=att)

        elif isinstance(ent, TextEntity):
            msp.add_text(ent.text, dxfattribs={
                **att,
                "insert":   _p3(ent.pos),
                "height":   ent.height,
                "rotation": ent.angle_deg,
            })

        elif isinstance(ent, SplineEntity):
            pts = ent.curve_points()
            if len(pts) >= 2:
                msp.add_lwpolyline([_p2(p) for p in pts], dxfattribs=att)

        elif isinstance(ent, HatchEntity):
            boundary = [_p2(p) for p in ent.boundary()]
            if len(boundary) >= 3:
                hatch = msp.add_hatch(color=7, dxfattribs=att)
                hatch.paths.add_polyline_path(boundary, is_closed=True)
                try:
                    hatch.set_pattern_fill(ent._pattern, scale=ent._scale,
                                           angle=ent._angle)
                except Exception:
                    hatch.set_solid_fill()

        elif isinstance(ent, DimLinearEntity):
            q1, q2, _ux, _uy, _nx, _ny, length = ent._geometry()
            msp.add_line(_p3(ent.p1), _p3(q1), dxfattribs=att)
            msp.add_line(_p3(ent.p2), _p3(q2), dxfattribs=att)
            msp.add_line(_p3(q1), _p3(q2), dxfattribs=att)
            mid = ((q1.x() + q2.x()) / 2, (q1.y() + q2.y()) / 2)
            label = ent._text_override or f"{length / GRID_UNIT:.3f}"
            msp.add_text(label, dxfattribs={
                **att, "insert": (_sx(mid[0]), _sy(mid[1]), 0.0), "height": 2.0,
            })

        elif isinstance(ent, DimAngularEntity):
            a1, span = ent._angles()
            dxf_start, dxf_end = _arc_angles(a1, span)
            r = ent._radius / GRID_UNIT
            msp.add_arc(_p3(ent._center), r, dxf_start, dxf_end, dxfattribs=att)
            msp.add_line(_p3(ent._center), _p3(ent._p1), dxfattribs=att)
            msp.add_line(_p3(ent._center), _p3(ent._p2), dxfattribs=att)

    doc.saveas(path)


# ── PDF export ────────────────────────────────────────────────────────────────

def export_pdf(scene, path: str) -> None:
    items_rect = scene.itemsBoundingRect()
    if items_rect.isEmpty():
        items_rect = QRectF(0, 0, 2100, 2970)

    margin = GRID_UNIT * 5
    source = items_rect.adjusted(-margin, -margin, margin, margin)

    mm_per_unit = 3.5
    w_mm = max(50.0, source.width()  / GRID_UNIT * mm_per_unit)
    h_mm = max(50.0, source.height() / GRID_UNIT * mm_per_unit)

    writer = QPdfWriter(path)
    writer.setResolution(150)
    writer.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))

    # Override every entity to black for white-paper output, preserving selection
    BLACK = QColor(0, 0, 0)
    entities = scene.all_entities()
    saved = [(e.color_override, e.selected) for e in entities]
    for e in entities:
        e.color_override = BLACK
        e.selected = False

    try:
        painter = QPainter(writer)
        page_rect = QRectF(painter.viewport())
        painter.fillRect(page_rect, QColor(255, 255, 255))
        scene.render(painter, page_rect, source)
        painter.end()
    finally:
        for e, (orig_color, orig_sel) in zip(entities, saved):
            e.color_override = orig_color
            e.selected = orig_sel
