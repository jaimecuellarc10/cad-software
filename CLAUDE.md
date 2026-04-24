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
    line.py          — LineTool (L): chaining lines
    polyline.py      — PolylineTool (PL): multi-vertex, C=close
    circle.py        — CircleTool (C): center + radius
    arc.py           — ArcTool (A): 3-point arc
    rectangle.py     — RectangleTool (REC): 2-corner closed polyline
    move.py          — MoveTool (M): select first, base pt → dest
    copy_tool.py     — CopyTool (CO): like Move, stays active for multi-copy
    rotate.py        — RotateTool (RO): base pt + drag/type angle (CCW)
    mirror.py        — MirrorTool (MI): 2-pt mirror line, Y=keep original
    trim.py          — TrimTool (TR): click segment to trim at intersections
    extend.py        — ExtendTool (EX): click near line end to extend
```

## Architecture

### Entity System (`cad/entities.py`)

All entities subclass `CADEntity(QGraphicsItem)`. Every entity must implement:
- `snap_points(mode)` — returns snap points for a given SnapMode
- `line_segments()` — constituent QLineF segments (for intersection snap)
- `hit_test(pt, threshold)` — point proximity test
- `intersects_rect(rect, crossing)` — window/crossing selection test
- `translate(dx, dy)` / `rotate_about(cx, cy, angle_deg)` / `mirror_across(ax, ay, bx, by)` — in-place transforms, each calls `prepareGeometryChange()` then `update()`
- `clone()` — deep copy, unselected, not in any scene

Entity classes: `LineEntity`, `PolylineEntity`, `CircleEntity`, `ArcEntity`.

**Default layer color is white (`#ffffff`).** Orange (`255, 165, 0`) is the selection highlight.

Angle convention in `ArcEntity`: `_start_angle` and `_span_angle` are stored in degrees, CCW-positive from 3-o'clock (standard math convention with Y-negated for Qt).

### Tool System (`cad/tools/`)

Tools are stateless-between-activations singletons created once in `MainWindow` and reused. Key lifecycle:
- `activate(view)` — called by `CADView.set_tool()`; grabs scene state (e.g., selected entities for editing tools)
- `deactivate()` — calls `cancel()`, clears state, sets `self.view = None`
- `on_press / on_move / on_release / on_key` — input handlers
- `cancel()` — abort current op, reset state
- `finish()` — commit current op (default = `cancel()`; PolylineTool overrides to commit)
- `draw_overlay(painter)` — viewport-space preview drawing
- `snap_extras()` — extra snap targets from in-progress geometry
- `on_command(cmd) -> bool` — optional; called by window before global command lookup; return True to consume (used by RotateTool for numeric angle input)

**All preview overlays use white (`#ffffff`) solid lines.** Only helper/projection lines (e.g., circle radius) are dashed.

### Undo System (`cad/undo.py`)

Command pattern. `UndoStack.push(cmd)` calls `cmd.execute()` immediately. Commands:
- `AddEntityCommand` / `DeleteEntitiesCommand`
- `MoveEntitiesCommand(entities, dx, dy)`
- `CopyEntitiesCommand(scene, entities, dx, dy)` — creates clones on first execute
- `RotateEntitiesCommand(entities, cx, cy, angle_deg)`
- `MirrorEntitiesCommand(scene, entities, ax, ay, bx, by, keep_original)`
- `ReplaceEntityCommand(scene, old, new)` — used by Trim/Extend

### View (`cad/view.py`)

Key behaviors:
- **Escape**: one hit always cancels current op AND exits to select tool (if already on select → clears selection)
- **Space**: if tool active → `tool.finish()` (commit, stay in tool); if tool idle → exit to select; if in select → recall last draw tool
- **Delete / Backspace**: deletes selected entities when command bar has no input (Mac Delete key sends `Key_Backspace`)
- **Ctrl+C / Ctrl+V**: in-memory clipboard; paste offsets by 20 scene units, cascades on repeated pastes
- Key routing: printable chars go to `_command_bar.feed_char()`; Enter submits command bar

### Snap System (`cad/snap.py`)

`SnapManager.snap(cursor, entities, view_scale, extra_points)` returns a `SnapResult(point, mode)`. Checks ENDPOINT → MIDPOINT → CENTER → INTERSECTION in priority order, falls back to grid. `extra_points` comes from the active tool's `snap_extras()` — used to snap to in-progress geometry vertices.

**CRITICAL**: `QLineF.intersects()` in PySide6 returns a tuple `(IntersectionType, QPointF)` — always unpack it:
```python
itype, pt = seg.intersects(other)
if itype == QLineF.IntersectionType.BoundedIntersection:
    ...
```

### Command Bar (`cad/command_bar.py`)

Read-only display widget. The view routes keypresses to it — no QLineEdit focus stealing. Buffer is uppercase. `submit()` emits `submitted(str)`, then clears buffer and refocuses the view.

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

## User Preferences

- Default drawing color: **white** (entities inherit from their layer, default layer = `#ffffff`)
- Preview lines: **solid**; projection/helper lines only: **dashed**
- Editing tools (Move, Copy, Rotate, Mirror) require entities to be **selected first** before activating the tool
- Rotate: positive angle = **CCW on screen**; can be typed in command bar after picking base point
- Mirror: type `Y` + Enter to keep original (mirror-copy mode)

## Known Limitations / Future Work

- Trim/Extend only operate on `LineEntity` and `PolylineEntity` (not circles or arcs yet)
- No DXF import/export yet
- No layers UI (layer 0 is the only layer; color defaults to white)
- No dimension tools
- No text/annotation
- No hatch/fill
