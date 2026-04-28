import math
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPolygonF
from .base import BaseTool
from ..entities import LineEntity, PolylineEntity, HatchEntity
from ..undo import AddEntityCommand

STATE_PICK = 0


class HatchTool(BaseTool):
    name = "hatch"

    def __init__(self):
        super().__init__()
        self._state = STATE_PICK
        self._pattern = "ANSI31"
        self._scale = 1.0

    @property
    def is_idle(self):
        return True

    _PATTERNS = ("ANSI31", "SOLID", "HORIZONTAL", "VERTICAL", "CROSS", "NET45", "NET")

    @property
    def prompt(self):
        return (f"HATCH  [{self._pattern}  scale={self._scale:.2g}]"
                f"  Click inside closed region  [ANSI31/SOLID/HORIZONTAL/VERTICAL/CROSS/NET45/NET  or scale number]")

    def activate(self, view):
        super().activate(view)
        self._state = STATE_PICK

    def on_command(self, cmd: str) -> bool:
        up = cmd.strip().upper()
        if up in self._PATTERNS:
            self._pattern = up
            return True
        try:
            scale = float(cmd)
        except ValueError:
            return False
        if scale > 0:
            self._scale = scale
        return True

    def on_press(self, snapped: QPointF, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        boundary = _find_boundary(self.view.cad_scene.all_entities(), snapped)
        if boundary:
            ent = HatchEntity(boundary, self._pattern, self._scale,
                              layer=self.view.layer_manager.current)
            self.view.undo_stack.push(AddEntityCommand(self.view.cad_scene, ent))
        if self.view:
            self.view.viewport().update()

    def cancel(self):
        self._state = STATE_PICK
        if self.view:
            self.view.viewport().update()


def _find_boundary(entities: list, pt: QPointF) -> list[QPointF] | None:
    segments = []
    for ent in entities:
        if isinstance(ent, LineEntity):
            segments.append((ent.p1, ent.p2))
        elif isinstance(ent, PolylineEntity):
            segments.extend(ent.segments())
    nodes, edges = _build_graph(segments, 2.0)
    cycles = _find_cycles(nodes, edges)
    containing = []
    for cycle in cycles:
        poly = QPolygonF(cycle)
        if poly.containsPoint(pt, Qt.FillRule.OddEvenFill):
            containing.append(cycle)
    if not containing:
        return None
    containing.sort(key=_area)
    return containing[0]


def _build_graph(segments: list, tol: float):
    nodes: list[QPointF] = []
    edges: dict[int, set[int]] = {}

    def node_for(p: QPointF) -> int:
        for i, n in enumerate(nodes):
            if math.hypot(p.x()-n.x(), p.y()-n.y()) <= tol:
                return i
        nodes.append(QPointF(p))
        edges[len(nodes)-1] = set()
        return len(nodes)-1

    for a, b in segments:
        ia = node_for(a)
        ib = node_for(b)
        if ia != ib:
            edges[ia].add(ib)
            edges[ib].add(ia)
    return nodes, edges


def _find_cycles(nodes: list[QPointF], edges: dict[int, set[int]]) -> list[list[QPointF]]:
    found: set[tuple[int, ...]] = set()
    cycles = []
    max_len = min(24, len(nodes))

    def canonical(path):
        body = path[:-1]
        variants = []
        for seq in (body, list(reversed(body))):
            for i in range(len(seq)):
                variants.append(tuple(seq[i:] + seq[:i]))
        return min(variants)

    def dfs(start, cur, path):
        if len(path) > max_len:
            return
        for nxt in edges.get(cur, set()):
            if nxt == start and len(path) >= 3:
                key = canonical(path + [start])
                if key not in found:
                    found.add(key)
                    cycles.append([QPointF(nodes[i]) for i in key])
            elif nxt not in path and nxt >= start:
                dfs(start, nxt, path + [nxt])

    for start in range(len(nodes)):
        dfs(start, start, [start])
    return cycles


def _area(poly: list[QPointF]) -> float:
    total = 0.0
    for a, b in zip(poly, poly[1:] + poly[:1]):
        total += a.x()*b.y() - b.x()*a.y()
    return abs(total) / 2
