# CLAUDE.md — CAD Software

## Overview

A desktop 2D CAD application targeting AutoCAD LT workflow parity, built with **Python 3.13 + PySide6 6.11**. Runs on macOS and Windows. No build system — launch directly with `python3 main.py`.

## Running

```bash
cd "/Users/jaimecuellar/Documents/ClaudeCode/Cad Software"
python3 main.py
```

## Package Layout

```
main.py              — entry point (QApplication + MainWindow)
window.py            — MainWindow: toolbar, snap bar, menu, command routing
cad/
  constants.py       — GRID_UNIT, SNAP_PX, GRIP_PX, SnapMode enum
  entities.py        — All CAD entity classes + geometry helpers
  layers.py          — LayerManager, Layer (default color: white #ffffff)
  scene.py           — CADScene(QGraphicsScene): entity list + selection
  view.py            — CADView(QGraphicsView): grid, overlays, input routing
  snap.py            — SnapManager: endpoint/midpoint/center/intersection snap
  undo.py            — UndoStack + all Command subclasses
  command_bar.py     — Read-only command bar widget (no QLineEdit)
  tools/
    base.py          — BaseTool abstract state machine
    select.py        — SelectTool: click + window/crossing selection
    line.py          — LineTool (L): chaining lines, type distance + Enter
    polyline.py      — PolylineTool (PL): multi-vertex, C=close, type distance + Enter
    circle.py        — CircleTool (C): center + radius, type radius + Enter
    arc.py           — ArcTool (A): 3-point arc
    rectangle.py     — RectangleTool (REC): 2-corner or type "W,H" + Enter
    move.py          — MoveTool (M): in-tool select, ghost preview, type distance + Enter
    copy_tool.py     — CopyTool (CO): like Move, stays active for multi-copy
    rotate.py        — RotateTool (RO): in-tool select, ghost preview, type angle + Enter
    mirror.py        — MirrorTool (MI): in-tool select, ghost preview, Y=keep original
    trim.py          — TrimTool (TR): click or fence drag to trim; sticking-out segments supported
    extend.py        — ExtendTool (EX): click or box drag to extend
    offset.py        — OffsetTool (O): type distance, pick entity, pick side
    scale.py         — ScaleTool (SC): in-tool select, ghost preview, type factor + Enter
    fillet.py        — FilletTool (F): type radius, pick two lines → arc fillet
    chamfer.py       — ChamferTool (CHA): type distance(s), pick two lines → chamfer
    break_tool.py    — BreakTool (BR): pick entity, pick two break points
    ellipse.py       — EllipseTool (EL): center → axis1 → axis2, type half-length
    polygon.py       — PolygonTool (POL): sides → center → radius, I/C inscribed/circumscribed
    xline.py         — XLineTool (XLINE): infinite construction line, H/V/angle
    explode.py       — ExplodeTool (X): polyline → individual line segments
    join_tool.py     — JoinTool (J): chain lines/polylines into one polyline
    array.py         — ArrayTool (AR): rectangular (rows,cols,dx,dy) or polar (count,angle)
    stretch.py       — StretchTool (S): crossing box → base pt → dest, type distance
    text_tool.py     — TextTool (T): click insertion point, type text in command bar
    dimension.py     — DimLinearTool (DIM), DimAngularTool (DAN)
    hatch.py         — HatchTool (H): click inside closed region, auto-detect boundary
    spline.py        — SplineTool (SPL): Catmull-Rom spline, C=close
    lengthen.py      — LengthenTool (LEN): type delta, click near endpoint to extend/shorten
    _ghost.py        — Ghost preview helpers (GHOST_PEN, draw_entities_ghost_*)
```

## Architecture

### Entity System (`cad/entities.py`)

All entities subclass `CADEntity(QGraphicsItem)`. Every entity must implement:
- `snap_points(mode)` — returns snap points for a given SnapMode
- `line_segments()` — constituent QLineF segments (for intersection snap)
- `hit_test(pt, threshold)` — point proximity test
- `intersects_rect(rect, crossing)` — window/crossing selection test
- `translate(dx, dy)` / `rotate_about(cx, cy, angle_deg)` / `mirror_across(ax, ay, bx, by)` / `scale_about(cx, cy, factor)` — in-place transforms, each calls `prepareGeometryChange()` then `update()`
- `clone()` — deep copy, unselected, not in any scene

Entity classes: `LineEntity`, `PolylineEntity`, `CircleEntity`, `ArcEntity`, `EllipseEntity`, `XLineEntity`, `TextEntity`, `DimLinearEntity`, `DimAngularEntity`, `HatchEntity`, `SplineEntity`.

**Default layer color is white (`#ffffff`).** Orange (`255, 165, 0`) is the selection highlight.

Angle convention in `ArcEntity`: `_start_angle` and `_span_angle` are stored in degrees, CCW-positive from 3-o'clock (standard math convention with Y-negated for Qt).

Qt Y-down rotation formula (used everywhere — do NOT use standard math formula):
```python
nx = cx + dx * cos_a + dy * sin_a
ny = cy - dx * sin_a + dy * cos_a
```

### Tool System (`cad/tools/`)

Tools are stateless-between-activations singletons created once in `MainWindow` and reused. Key lifecycle:
- `activate(view)` — called by `CADView.set_tool()`; grabs scene state (e.g., selected entities for editing tools)
- `deactivate()` — calls `cancel()`, clears state, sets `self.view = None`
- `on_press / on_move / on_release / on_key` — input handlers
- `cancel()` — abort current op, reset state
- `finish()` — commit current op (default = `cancel()`; PolylineTool overrides to commit)
- `draw_overlay(painter)` — viewport-space preview drawing
- `snap_extras()` — extra snap targets from in-progress geometry
- `on_command(cmd) -> bool` — called by window before global command lookup; return True to consume

**In-tool selection** (Move, Copy, Rotate, Mirror, Scale): if no entities pre-selected, tool enters `STATE_SELECT` with blue/green box drag (left→right = window, right→left = crossing) and click-to-select. Space/Enter confirms selection.

**Ghost overlays** (`_ghost.py`): `GHOST_PEN = QPen(QColor(255,255,255,110), 1, DashLine)`. Functions: `draw_entities_ghost_translated`, `draw_entities_ghost_rotated`, `draw_entities_ghost_mirrored`, `draw_entities_ghost_scaled`.

**All preview overlays use white (`#ffffff`) solid lines.** Ghost/projection lines use `GHOST_PEN` (semi-transparent dashed).

**Precision input**: drawing tools (Line, Polyline, Circle, Rectangle, Move, Copy, Rotate, Scale, Stretch) accept typed values via the command bar — type a number and press Enter to commit at that exact distance/angle/factor in the current direction.

### Undo System (`cad/undo.py`)

Command pattern. `UndoStack.push(cmd)` calls `cmd.execute()` immediately. Commands:
- `AddEntityCommand` / `DeleteEntitiesCommand`
- `MoveEntitiesCommand(entities, dx, dy)`
- `CopyEntitiesCommand(scene, entities, dx, dy)` — creates clones on first execute
- `RotateEntitiesCommand(entities, cx, cy, angle_deg)`
- `MirrorEntitiesCommand(scene, entities, ax, ay, bx, by, keep_original)`
- `ReplaceEntityCommand(scene, old, new)` — used by Trim/Extend/Lengthen
- `SplitEntityCommand(scene, old, new1, new2)` — used by Trim (between two intersections)
- `ScaleEntitiesCommand(entities, cx, cy, factor)`
- `FilletCommand(scene, line1, line2, arc, new_l1, new_l2)` — atomic replace + add
- `ChamferCommand(scene, line1, line2, new_l1, new_l2, chamfer_line)`
- `BreakEntityCommand(scene, old, part1, part2)`
- `ArrayCommand(scene, clones)` — clones added; originals stay
- `ExplodeCommand(scene, poly, lines)`
- `JoinCommand(scene, originals, result)`
- `StretchCommand(scene, old_new_pairs)`

### View (`cad/view.py`)

Key behaviors:
- **Escape**: cancels current op and exits to select tool (if already on select → clears selection)
- **Space**: if tool active and op in progress → `tool.finish()` (commit, stay in tool); if tool idle → exit to select; if in select → recall last draw tool
- **Tab**: submits command bar if it has input, otherwise passes to tool's `on_key`
- **Delete / Backspace**: deletes selected entities when command bar has no input
- **Ctrl+C / Ctrl+V**: in-memory clipboard; paste offsets by 20 scene units, cascades on repeated pastes
- **ZE / EXTENTS / ZOOM**: `zoom_extents()` — fits all entities in view
- Key routing: printable chars → `_command_bar.feed_char()`; Enter/Space/Tab → submit command bar
- Zoom clamped to [0.01, 500] scale to prevent crash

### Snap System (`cad/snap.py`)

`SnapManager.snap(cursor, entities, view_scale, extra_points)` returns a `SnapResult(point, mode)`. Checks ENDPOINT → MIDPOINT → CENTER → INTERSECTION in priority order, falls back to grid. `extra_points` comes from the active tool's `snap_extras()`.

**CRITICAL**: `QLineF.intersects()` in PySide6 returns a tuple `(IntersectionType, QPointF)` — always unpack it:
```python
itype, pt = seg.intersects(other)
if itype == QLineF.IntersectionType.BoundedIntersection:
    ...
```

### Command Bar (`cad/command_bar.py`)

Read-only display widget. The view routes keypresses to it — no QLineEdit focus stealing. Buffer is uppercase. `submit()` emits `submitted(str)`, then clears buffer and refocuses the view. `add_history(text)` updates the history label.

## AutoCAD Commands

| Command(s) | Tool |
|---|---|
| L, LINE | Line |
| PL, PLINE, POLYLINE | Polyline |
| C, CIRCLE | Circle |
| A, ARC | Arc |
| REC, RECT, RECTANGLE | Rectangle |
| M, MOVE | Move |
| CO, CP, COPY | Copy |
| RO, ROTATE | Rotate |
| MI, MIRROR | Mirror |
| TR, TRIM | Trim |
| EX, EXTEND | Extend |
| O, OF, OFFSET | Offset |
| SC, SCALE | Scale |
| F, FI, FILLET | Fillet |
| CHA, CHAMFER | Chamfer |
| BR, BREAK | Break |
| EL, ELLIPSE | Ellipse |
| POL, POLYGON | Polygon |
| XLINE, XL, RAY | XLine (infinite construction line) |
| X, EXPLODE | Explode |
| J, JOIN | Join |
| AR, ARRAY | Array |
| S, STRETCH | Stretch |
| T, TEXT, MT, MTEXT | Text |
| DIM, DIMLINEAR, DLI | Linear Dimension |
| DIMANGULAR, DAN | Angular Dimension |
| H, HATCH, BH | Hatch |
| SPL, SPLINE | Spline |
| LEN, LENGTHEN | Lengthen |
| ZE, EXTENTS, ZOOM | Zoom Extents |

## User Preferences

- Default drawing color: **white** (entities inherit from their layer, default layer = `#ffffff`)
- Preview lines: **solid white**; ghost/projection lines: **semi-transparent dashed** (`GHOST_PEN`)
- Editing tools (Move, Copy, Rotate, Mirror, Scale) support in-tool selection — no need to pre-select
- Rotate: positive angle = **CCW on screen**; type angle in command bar after picking base point
- Mirror: type `Y` + Enter to keep original (mirror-copy mode)
- Precision input: type a value + Enter at any point during drawing/editing to commit at exact distance

## Known Limitations / Future Work

- Trim/Extend only operate on `LineEntity` and `PolylineEntity` (not circles or arcs yet)
- No DXF import/export yet
- No layers UI (layer 0 is the only layer; color defaults to white)
- No radius/diameter dimension tools yet
- Hatch boundary detection uses graph walk — complex overlapping geometry may not resolve
