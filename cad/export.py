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
from PySide6.QtCore import QPointF

from .entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity,
    XLineEntity, TextEntity, DimLinearEntity, DimAngularEntity,
    HatchEntity, SplineEntity, PointEntity,
)


# ── Coordinate helpers ────────────────────────────────────────────────────────
# Scene uses Y-down (Qt); DXF uses Y-up.  Divide/multiply by GRID_UNIT for units.

# export: scene → DXF
def _sx(x: float) -> float: return x / GRID_UNIT
def _sy(y: float) -> float: return -y / GRID_UNIT
def _p2(pt) -> tuple: return (_sx(pt.x()), _sy(pt.y()))
def _p3(pt) -> tuple: return (_sx(pt.x()), _sy(pt.y()), 0.0)

# import: DXF → scene  (unit_scale computed per-file from $INSUNITS)
# 1 scene unit = 1 mm;  GRID_UNIT used as fallback for unitless files
_INSUNITS_TO_MM: dict[int, float] = {
    1: 25.4,    # inches
    2: 304.8,   # feet
    3: 1609344, # miles (unlikely but complete)
    4: 1.0,     # millimeters
    5: 10.0,    # centimeters
    6: 1000.0,  # meters
    7: 1e6,     # kilometers
    8: 0.0254,  # microinches
    9: 0.001,   # mils
    10: 914.4,  # yards
    11: 1e-7,   # angstroms
    12: 1e-6,   # nanometers
    13: 1e-3,   # microns
    14: 100.0,  # decimeters
    15: 10000.0,# dekameters
    16: 100000.0,# hectometers
    17: 1e9,    # gigameters
    18: 1.496e14,# astronomical units
    19: 9.461e18,# light years
    20: 3.086e19,# parsecs
}

def _ix(x: float, us: float = GRID_UNIT) -> float: return  x * us
def _iy(y: float, us: float = GRID_UNIT) -> float: return -y * us
def _ip(v, us: float = GRID_UNIT) -> QPointF: return QPointF(v.x * us, -v.y * us)


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
    doc.header["$INSUNITS"] = scene.drawing_unit.insunits
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


# ── DXF import ────────────────────────────────────────────────────────────────

def _import_entity(dxf_ent, layer, us: float):
    """Convert one ezdxf entity to a CAD entity. us = scene units per DXF unit."""
    def ix(x): return  x * us
    def iy(y): return -y * us
    def ip(v):  return QPointF(v.x * us, -v.y * us)

    t = dxf_ent.dxftype()

    if t == "LINE":
        return LineEntity(ip(dxf_ent.dxf.start), ip(dxf_ent.dxf.end), layer)

    if t == "LWPOLYLINE":
        pts = [QPointF(ix(x), iy(y)) for x, y, *_ in dxf_ent.get_points()]
        if len(pts) >= 2:
            closed = bool(dxf_ent.closed)
            if closed and pts[0] != pts[-1]:
                pts.append(pts[0])
            return PolylineEntity(pts, layer)

    if t == "POLYLINE" and dxf_ent.is_2d_polyline:
        pts = [QPointF(ix(v.dxf.location.x), iy(v.dxf.location.y))
               for v in dxf_ent.vertices]
        if len(pts) >= 2:
            return PolylineEntity(pts, layer)

    if t == "CIRCLE":
        c = dxf_ent.dxf.center
        return CircleEntity(QPointF(ix(c.x), iy(c.y)), ix(dxf_ent.dxf.radius), layer)

    if t == "ARC":
        c     = dxf_ent.dxf.center
        start = dxf_ent.dxf.start_angle
        end   = dxf_ent.dxf.end_angle
        span  = (end - start) % 360
        return ArcEntity(QPointF(ix(c.x), iy(c.y)), ix(dxf_ent.dxf.radius),
                         start, span, layer)

    if t == "ELLIPSE":
        c     = dxf_ent.dxf.center
        major = dxf_ent.dxf.major_axis
        rx    = math.hypot(major.x, major.y) * us
        ry    = rx * dxf_ent.dxf.ratio
        angle = math.degrees(math.atan2(major.y, major.x))
        return EllipseEntity(QPointF(ix(c.x), iy(c.y)), rx, ry, angle, layer)

    if t == "XLINE":
        pt = dxf_ent.dxf.start
        uv = dxf_ent.dxf.unit_vector
        angle = math.degrees(math.atan2(uv.y, uv.x))
        return XLineEntity(QPointF(ix(pt.x), iy(pt.y)), angle, layer)

    if t == "POINT":
        loc = dxf_ent.dxf.location
        return PointEntity(QPointF(ix(loc.x), iy(loc.y)), layer)

    if t == "TEXT":
        ins    = dxf_ent.dxf.insert
        text   = dxf_ent.dxf.text
        height = getattr(dxf_ent.dxf, "height", 2.5) * us
        rot    = getattr(dxf_ent.dxf, "rotation", 0.0)
        return TextEntity(QPointF(ix(ins.x), iy(ins.y)), text, height, rot, layer)

    if t == "MTEXT":
        if not dxf_ent.dxf.hasattr("insert"):
            return None
        ins = dxf_ent.dxf.insert
        try:
            text = dxf_ent.plain_mtext()
        except AttributeError:
            raw = getattr(dxf_ent, "text", "") or getattr(dxf_ent.dxf, "text", "")
            import re
            text = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", raw)
        height = getattr(dxf_ent.dxf, "char_height", 2.5) * us
        rot    = getattr(dxf_ent.dxf, "rotation", 0.0)
        return TextEntity(QPointF(ix(ins.x), iy(ins.y)), text, height, rot, layer)

    if t == "SPLINE":
        ctrl = list(dxf_ent.control_points)
        if len(ctrl) >= 2:
            pts = [QPointF(ix(p.x), iy(p.y)) for p in ctrl]
            return SplineEntity(pts, layer=layer)

    if t == "HATCH":
        for path in dxf_ent.paths:
            vertices = getattr(path, "vertices", None)
            if vertices:
                pts = [QPointF(ix(v[0]), iy(v[1])) for v in vertices]
                if len(pts) >= 3:
                    pattern = getattr(dxf_ent.dxf, "pattern_name", "ANSI31") or "ANSI31"
                    return HatchEntity(pts, pattern=pattern, layer=layer)
            edges = getattr(path, "edges", None)
            if edges:
                pts = []
                for edge in edges:
                    start = getattr(edge, "start", None)
                    if start is not None:
                        pts.append(QPointF(ix(start.x), iy(start.y)))
                if len(pts) >= 3:
                    return HatchEntity(pts, layer=layer)

    return None


def import_dxf(scene, layer_manager, path: str) -> int:
    """
    Merge all supported entities from a DXF file into scene.
    Returns the number of entities successfully imported.
    """
    if not HAS_EZDXF:
        raise RuntimeError("ezdxf is not installed — run: pip install ezdxf")

    doc = ezdxf.readfile(path)
    insunits = doc.header.get("$INSUNITS", 0)

    # Inherit drawing unit from the file if it declares one
    from .constants import INSUNITS_TO_UNIT
    if insunits in INSUNITS_TO_UNIT:
        scene.drawing_unit = INSUNITS_TO_UNIT[insunits]

    # scene_coord = dxf_coord × (dxf_mm / drawing_mm) × GRID_UNIT
    dxf_mm     = _INSUNITS_TO_MM.get(insunits, scene.drawing_unit.mm_per_unit)
    drawing_mm = scene.drawing_unit.mm_per_unit
    unit_scale = dxf_mm * GRID_UNIT / drawing_mm

    msp = doc.modelspace()
    count = 0

    for dxf_ent in msp:
        try:
            layer_name = dxf_ent.dxf.layer if dxf_ent.dxf.hasattr("layer") else "0"
            layer = layer_manager.get(layer_name) or layer_manager.current
            ent = _import_entity(dxf_ent, layer, unit_scale)
            if ent is not None:
                scene.add_entity(ent)
                count += 1
        except Exception:
            pass  # skip unsupported/malformed entities without aborting

    return count


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
