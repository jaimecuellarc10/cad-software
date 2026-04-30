# CLAUDE.md — CAD Software

## Overview

A desktop 2D CAD application targeting AutoCAD LT workflow parity, built with **Python 3.13 + PySide6 6.11**. Runs on Windows. No build system — launch directly via `run.bat` or the full Python path.

## Running

```bash
# Windows (Python not on PATH — use full path)
C:\Users\Setup-PC1\AppData\Local\Programs\Python\Python313\python.exe main.py

# Or use the batch file
run.bat
```

## Package Layout

```
main.py              — entry point (QApplication + MainWindow, applies dark theme)
window.py            — MainWindow: toolbar, snap bar, menu, file ops, command routing
theme.py             — AutoCAD-style dark QSS theme (apply_theme, Colors, Metrics)
icons.py             — SVG/icon helpers
run.bat              — launch script
cad/
  constants.py       — GRID_UNIT=10, SNAP_PX, GRIP_PX, SnapMode enum
  entities.py        — All CAD entity classes + geometry helpers + to_props_dict()
  layers.py          — LayerManager, Layer (default color: white #ffffff)
  scene.py           — CADScene(QGraphicsScene): entity list + selection
  view.py            — CADView(QGraphicsView): grid, overlays, input routing
  snap.py            — SnapManager: endpoint/midpoint/center/intersection snap
  undo.py            — UndoStack + all Command subclasses
  command_bar.py     — Read-only command bar widget (no QLineEdit)
  export.py          — DXF export + DXF import (ezdxf) + PDF export
  file_io.py         — Native .cad JSON format: save_file / load_file
  properties_panel.py — Adapter wrapping widgets.PropertiesPanel; polls scene 120ms
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
    text_tool.py     — TextTool (T): inline text box, blinking cursor, font support
    dimension.py     — DimLinearTool (DIM), DimAngularTool (DAN)
    hatch.py         — HatchTool (H): click inside closed region, auto-detect boundary
    spline.py        — SplineTool (SPL): Catmull-Rom spline, C=close
    lengthen.py      — LengthenTool (LEN): type delta, click near endpoint to extend/shorten
    _ghost.py        — Ghost preview helpers (GHOST_PEN, draw_entities_ghost_*)
widgets/
  __init__.py
  property_editors.py — NumericEditor, StringEditor, ColorEditor, ChoiceEditor,
                        ReadOnlyEditor, FontEditor (QFontComboBox wrapper)
  properties_panel.py — PropertiesPanel widget: collapsible categories, set_selection(),
                        propertyChanged signal; used via cad/properties_panel.py adapter
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
- `to_props_dict()` — returns `{'type': str, 'properties': dict}` for the properties panel

Entity classes: `LineEntity`, `PolylineEntity`, `CircleEntity`, `ArcEntity`, `EllipseEntity`, `XLineEntity`, `TextEntity`, `DimLinearEntity`, `DimAngularEntity`, `HatchEntity`, `SplineEntity`, `PointEntity`.

**Default layer color is white (`#ffffff`).** Orange (`255, 165, 0`) is the selection highlight.

**`TextEntity`** has a `font_family: str` attribute (default `"Arial"`). Serialized in `.cad` files; backward-compatible (missing → Arial).

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
- `on_press(snapped, event)` / `on_move(snapped, raw, event)` / `on_release(snapped, event)` / `on_key(event)` — input handlers
- `cancel()` — abort current op, reset state
- `finish()` — commit current op (default = `cancel()`; PolylineTool overrides to commit)
- `draw_overlay(painter)` — viewport-space preview drawing
- `snap_extras()` — extra snap targets from in-progress geometry
- `on_command(cmd) -> bool` — called by window before global command lookup; return True to consume
- `wants_raw_keys() -> bool` — if True, ALL key events bypass the command bar and go directly to `on_key()`; used by TextTool while typing

**In-tool selection** (Move, Copy, Rotate, Mirror, Scale): if no entities pre-selected, tool enters `STATE_SELECT` with blue/green box drag (left→right = window, right→left = crossing) and click-to-select. Space/Enter confirms selection.

**Ghost overlays** (`_ghost.py`): `GHOST_PEN = QPen(QColor(255,255,255,110), 1, DashLine)`. Functions: `draw_entities_ghost_translated`, `draw_entities_ghost_rotated`, `draw_entities_ghost_mirrored`, `draw_entities_ghost_scaled`.

**All preview overlays use white (`#ffffff`) solid lines.** Ghost/projection lines use `GHOST_PEN` (semi-transparent dashed).

**Precision input**: drawing tools (Line, Polyline, Circle, Rectangle, Move, Copy, Rotate, Scale, Stretch) accept typed values via the command bar — type a number and press Enter to commit at that exact distance/angle/factor in the current direction.

### Text Tool (`cad/tools/text_tool.py`)

Word-processor-style inline editing:
- Click to place → blue dashed text box appears with blinking cursor
- Full keyboard: lowercase, uppercase, Space inserts space, Left/Right/Home/End move cursor, Backspace/Delete work correctly
- Enter commits text → auto-exits to select tool
- Escape cancels → auto-exits to select tool
- Click outside box → commits text → auto-exits to select tool
- Drag bottom-right triangle grip to resize the box width
- Double-click existing TextEntity → enters edit mode with pre-filled buffer; commit/cancel returns to select
- `wants_raw_keys()` returns True while typing, bypassing command bar entirely

### Undo System (`cad/undo.py`)

Command pattern. `UndoStack.push(cmd)` calls `cmd.execute()` immediately. Commands:
- `AddEntityCommand` / `DeleteEntitiesCommand`
- `MoveEntitiesCommand(entities, dx, dy)`
- `CopyEntitiesCommand(scene, entities, dx, dy)` — creates clones on first execute
- `RotateEntitiesCommand(entities, cx, cy, angle_deg)`
- `MirrorEntitiesCommand(scene, entities, ax, ay, bx, by, keep_original)`
- `ReplaceEntityCommand(scene, old, new)` — used by Trim/Extend/Lengthen/Text edit
- `SplitEntityCommand(scene, old, new1, new2)` — used by Trim (between two intersections)
- `ScaleEntitiesCommand(entities, cx, cy, factor)`
- `FilletCommand(scene, line1, line2, arc, new_l1, new_l2)` — atomic replace + add
- `ChamferCommand(scene, line1, line2, new_l1, new_l2, chamfer_line)`
- `BreakEntityCommand(scene, old, part1, part2)`
- `ArrayCommand(scene, clones)` — clones added; originals stay
- `ExplodeCommand(scene, poly, lines)`
- `JoinCommand(scene, originals, result)`
- `StretchCommand(scene, old_new_pairs)`

Dirty tracking: `window._save_idx` stores `undo_stack._idx` at last save; compare to detect unsaved changes.

### View (`cad/view.py`)

Key behaviors:
- **Escape**: cancels current op and exits to select tool (if already on select → clears selection)
- **Space**: if tool active and op in progress → `tool.finish()` (commit, stay in tool); if tool idle → exit to select; if in select → recall last draw tool
- **Tab**: submits command bar if it has input, otherwise passes to tool's `on_key`
- **Delete / Backspace**: deletes selected entities when command bar has no input
- **Ctrl+C / Ctrl+V**: in-memory clipboard; paste offsets by 20 scene units, cascades on repeated pastes
- **ZE / EXTENTS / ZOOM**: `zoom_extents()` — fits all entities in view
- Key routing: if active tool returns `wants_raw_keys() == True`, ALL keys go to `tool.on_key()` with `_auto_exit` called after; otherwise printable chars → `_command_bar.feed_char()`
- Zoom clamped to [0.01, 500] scale to prevent crash
- `_auto_exit(was_idle, undo_before)` — switches to select when tool transitions active→idle or always-idle tool places an entity

### Properties Panel (`cad/properties_panel.py` + `widgets/properties_panel.py`)

Two-layer architecture:
- `widgets/properties_panel.py` — pure UI: `PropertiesPanel.set_selection(list[dict])`, emits `propertyChanged(prop_name, value)`
- `cad/properties_panel.py` — adapter: polls `scene.selected_entities()` every 120ms, calls `to_props_dict()`, feeds to widget, routes `propertyChanged` back to entity attributes via `_apply_one()`

Properties are grouped in collapsible CategoryGroups: General, Geometry, Text, Hatch, Dimension. The Text category includes Content (StringEditor), Height (NumericEditor), Font (FontEditor / QFontComboBox).

### File I/O

**Native format** (`.cad`): JSON via `cad/file_io.py`. `save_file(scene, path)` / `load_file(scene, layer_manager, path)`. FILE_VERSION = 1. All entity types serialized including font_family for TextEntity (backward-compatible default "Arial").

**DXF**: export + import via `cad/export.py` using `ezdxf`. Coordinate convention: scene Y-down ↔ DXF Y-up via `_sy = -y/GRID_UNIT`. Import reverses with `_iy = -y * GRID_UNIT`. Supports LINE, LWPOLYLINE, CIRCLE, ARC, ELLIPSE, XLINE, POINT, TEXT, MTEXT, SPLINE, HATCH.

**PDF**: export via `cad/export.py` using `QPdfWriter`. Overrides all entity colors to black for white-paper output.

**File menu**: New (Ctrl+N), Open (Ctrl+O), Save (Ctrl+S), Save As (Ctrl+Shift+S), Import DXF, Export DXF (Ctrl+Shift+D), Export PDF (Ctrl+Shift+P). Unsaved-changes prompt on New/Open/Close.

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

Note: when `wants_raw_keys()` is True on the active tool, the command bar receives NO input at all.

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
- Text tool: Enter commits and returns to select; Escape cancels and returns to select; Space inserts a space character (does NOT submit)

## Known Limitations / Future Work

- Trim/Extend only operate on `LineEntity` and `PolylineEntity` (not circles or arcs yet)
- No layers UI (layer 0 is the only layer; color defaults to white)
- No radius/diameter dimension tools yet
- Hatch boundary detection uses graph walk — complex overlapping geometry may not resolve
- Text tool does not support click-drag text selection within the editing box
- Text tool does not support multiline text (Enter commits; no newline insertion)
