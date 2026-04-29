"""
Native .cad file format — JSON serialization of all scene entities.

save_file(scene, path)               → writes JSON to path
load_file(scene, layer_manager, path) → clears scene and loads from JSON
"""

from __future__ import annotations

import json
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor

from .entities import (
    LineEntity, PolylineEntity, CircleEntity, ArcEntity, EllipseEntity,
    XLineEntity, TextEntity, DimLinearEntity, DimAngularEntity,
    HatchEntity, SplineEntity, PointEntity, Layer,
)

FILE_VERSION = 1

_LT_TO_NAME = {
    Qt.PenStyle.SolidLine:      "Solid",
    Qt.PenStyle.DashLine:       "Dashed",
    Qt.PenStyle.DotLine:        "Dotted",
    Qt.PenStyle.DashDotLine:    "Dash-Dot",
    Qt.PenStyle.DashDotDotLine: "Dash-Dot-Dot",
}
_NAME_TO_LT = {v: k for k, v in _LT_TO_NAME.items()}


def _pt(p: QPointF) -> list:
    return [p.x(), p.y()]

def _qpt(lst: list) -> QPointF:
    return QPointF(lst[0], lst[1])

def _color_out(c: QColor | None) -> str | None:
    return c.name() if c else None

def _color_in(s: str | None) -> QColor | None:
    return QColor(s) if s else None

def _lt_out(style: Qt.PenStyle) -> str:
    return _LT_TO_NAME.get(style, "Solid")

def _lt_in(name: str) -> Qt.PenStyle:
    return _NAME_TO_LT.get(name, Qt.PenStyle.SolidLine)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def _serialize(e) -> dict | None:
    base = {
        "layer":          e.layer.name,
        "color_override": _color_out(e.color_override),
    }

    if isinstance(e, LineEntity):
        return {**base, "type": "Line",
                "p1": _pt(e._p1), "p2": _pt(e._p2),
                "linetype": _lt_out(e.linetype), "lineweight": e.lineweight}

    if isinstance(e, PolylineEntity):
        return {**base, "type": "Polyline",
                "vertices": [_pt(v) for v in e._verts],
                "linetype": _lt_out(e.linetype), "lineweight": e.lineweight}

    if isinstance(e, CircleEntity):
        return {**base, "type": "Circle",
                "center": _pt(e._center), "radius": e._radius,
                "linetype": _lt_out(e.linetype), "lineweight": e.lineweight}

    if isinstance(e, ArcEntity):
        return {**base, "type": "Arc",
                "center": _pt(e._center), "radius": e._radius,
                "start_angle": e._start_angle, "span_angle": e._span_angle,
                "linetype": _lt_out(e.linetype), "lineweight": e.lineweight}

    if isinstance(e, EllipseEntity):
        return {**base, "type": "Ellipse",
                "center": _pt(e._center), "rx": e._rx, "ry": e._ry,
                "angle_deg": e._angle_deg,
                "linetype": _lt_out(e.linetype), "lineweight": e.lineweight}

    if isinstance(e, XLineEntity):
        return {**base, "type": "XLine",
                "point": _pt(e._point), "angle_deg": e._angle_deg,
                "lineweight": e.lineweight}

    if isinstance(e, TextEntity):
        return {**base, "type": "Text",
                "pos": _pt(e._pos), "text": e._text,
                "height": e._height, "angle_deg": e._angle_deg}

    if isinstance(e, DimLinearEntity):
        return {**base, "type": "DimLinear",
                "p1": _pt(e._p1), "p2": _pt(e._p2),
                "offset": e._offset, "text_override": e._text_override,
                "arrow_size": e.arrow_size, "text_height": e.text_height}

    if isinstance(e, DimAngularEntity):
        return {**base, "type": "DimAngular",
                "center": _pt(e._center), "p1": _pt(e._p1), "p2": _pt(e._p2),
                "radius": e._radius,
                "arrow_size": e.arrow_size, "text_height": e.text_height}

    if isinstance(e, HatchEntity):
        return {**base, "type": "Hatch",
                "boundary": [_pt(p) for p in e._boundary],
                "pattern": e._pattern, "scale": e._scale, "angle": e._angle}

    if isinstance(e, SplineEntity):
        return {**base, "type": "Spline",
                "control_points": [_pt(p) for p in e._control_points],
                "closed": e._closed}

    if isinstance(e, PointEntity):
        return {**base, "type": "Point", "pos": _pt(e._pos)}

    return None  # unknown — skip


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------

def _deserialize(data: dict, layer: Layer):
    t  = data.get("type")
    lt = _lt_in(data.get("linetype", "Solid"))
    lw = data.get("lineweight")   # None or float

    e = None
    if t == "Line":
        e = LineEntity(_qpt(data["p1"]), _qpt(data["p2"]), layer, lt, lw)

    elif t == "Polyline":
        e = PolylineEntity([_qpt(v) for v in data["vertices"]], layer, lt, lw)

    elif t == "Circle":
        e = CircleEntity(_qpt(data["center"]), data["radius"], layer, lw, lt)

    elif t == "Arc":
        e = ArcEntity(_qpt(data["center"]), data["radius"],
                      data["start_angle"], data["span_angle"], layer, lw, lt)

    elif t == "Ellipse":
        e = EllipseEntity(_qpt(data["center"]), data["rx"], data["ry"],
                          data["angle_deg"], layer, lw, lt)

    elif t == "XLine":
        e = XLineEntity(_qpt(data["point"]), data["angle_deg"], layer, lw)

    elif t == "Text":
        e = TextEntity(_qpt(data["pos"]), data["text"],
                       data.get("height", 2.5), data.get("angle_deg", 0.0), layer)

    elif t == "DimLinear":
        e = DimLinearEntity(_qpt(data["p1"]), _qpt(data["p2"]),
                            data["offset"], data.get("text_override", ""),
                            layer,
                            data.get("arrow_size", 8.0),
                            data.get("text_height", 2.5))

    elif t == "DimAngular":
        e = DimAngularEntity(_qpt(data["center"]), _qpt(data["p1"]), _qpt(data["p2"]),
                             data["radius"], layer,
                             data.get("arrow_size", 8.0),
                             data.get("text_height", 2.5))

    elif t == "Hatch":
        e = HatchEntity([_qpt(p) for p in data["boundary"]],
                        data.get("pattern", "ANSI31"),
                        data.get("scale", 1.0),
                        data.get("angle", 0.0),
                        layer)

    elif t == "Spline":
        e = SplineEntity([_qpt(p) for p in data["control_points"]],
                         data.get("closed", False), layer)

    elif t == "Point":
        e = PointEntity(_qpt(data["pos"]), layer)

    if e is not None:
        e.color_override = _color_in(data.get("color_override"))
    return e


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_file(scene, path: str) -> None:
    entities_data = [d for e in scene.all_entities() if (d := _serialize(e)) is not None]
    doc = {"version": FILE_VERSION, "entities": entities_data}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)


def load_file(scene, layer_manager, path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    scene.clear_all()

    for data in doc.get("entities", []):
        layer_name = data.get("layer", "0")
        layer = layer_manager.get(layer_name) or layer_manager.current
        e = _deserialize(data, layer)
        if e is not None:
            scene.add_entity(e)
