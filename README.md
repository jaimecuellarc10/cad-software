# CAD UI Starter — AutoCAD-style refresh for a PySide6 app

## What you have

```
cad_ui_starter/
├── theme.py                   # Colors, Metrics, build_qss(), apply_theme()
├── icons.py                   # IconProvider — QtAwesome backend, swappable
├── demo.py                    # Run this to see properties panel live
└── widgets/
    ├── property_editors.py    # NumericEditor, ColorEditor, ChoiceEditor, ReadOnlyEditor
    └── properties_panel.py    # PropertiesPanel with collapsible CategoryGroup
```

## Run it

```bash
pip install PySide6 qtawesome
python demo.py
```

Click the "Two Lines (varies)" button to see the multi-selection `*VARIES*`
behavior. Edit any field — status bar shows the emitted `propertyChanged` signal.

## Integration into your existing app

1. Drop `theme.py` in your project, call `apply_theme(app)` after `QApplication(sys.argv)`.
2. Drop `icons.py` and the `widgets/` folder in.
3. Replace your existing properties panel with `PropertiesPanel`.
4. Adapt the entity model — wherever your selection changes, call:
   ```python
   self.props_panel.set_selection([entity.to_props_dict() for entity in selected])
   ```
   where `to_props_dict()` returns `{"type": "Line", "properties": {...}}`.
5. Connect `propertyChanged` to your entity update logic.

## Roadmap — give Claude Code one of these per session

### Session 1 ✅ Theme + Properties panel (this starter)

### Session 2 — Ribbon system
> Build a ribbon widget at the top of the main window. Use `QTabWidget` with
> tabs for Home, Insert, Annotate, View, Output. Each tab contains a row of
> `RibbonPanel` widgets (custom — header strip, button area, footer with title
> and dropdown launcher). Mix large buttons (48×64, icon above label) and small
> buttons (icon + label beside). Use `Icons` from `icons.py`. Match theme from
> `theme.py`. Make the ribbon collapsible (double-click tab to collapse).

### Session 3 — Status bar polish
> Replace the current status bar with a row of toggleable icon buttons:
> Grid, Snap, Ortho, Polar, Object Snap, Dynamic Input. Each is a `QPushButton`
> with `setCheckable(True)` and the `:checked` style from theme.qss. To the
> right of these, show coordinates of the cursor (X, Y) updated from canvas
> mouse events. Use `Icons.GRID`, `Icons.SNAP`, etc.

### Session 4 — Command line widget
> Build a `CommandLine(QWidget)` at the bottom of the main window: a
> `QTextEdit` (read-only, monospace) for output history above a `QLineEdit`
> for input. Up/down arrows cycle through command history. Tab autocompletes
> against a list of registered commands. Emit a `commandEntered(str)` signal.

### Session 5 — Tooltip enhancement
> Replace standard tooltips on ribbon buttons with rich tooltips showing
> command name in bold, keyboard shortcut in monospace gray, and a one-line
> description. Use a custom `QFrame` shown via the button's `enterEvent`.

### Session 6 — Custom icons
> Design 24×24 SVGs at 1.5px stroke matching the AutoCAD two-tone style for
> the most-used commands. Drop into `resources/icons/`, build a `.qrc`, and
> swap `IconProvider._MAP` values to `:/icons/line.svg` paths.

## Theme customization

All colors live in `theme.Colors`. Tweak `BG_PANEL`, `ACCENT`, etc. to
fine-tune. The `build_qss()` function pulls from these constants — change once,
applies everywhere.

If you want a lighter theme later (AutoCAD has both), make a `Colors` subclass
with overridden values and pass it into a refactored `build_qss(palette)`.

## Why this structure

- **Theme is data, not code.** Single source of truth — Claude Code can't
  drift the palette across files because there's only one file.
- **Icon abstraction.** When custom SVGs land, you change `IconProvider.icon()`
  and nothing else.
- **Properties panel is self-contained.** Standalone-runnable via `demo.py`.
  You can iterate on it without touching the rest of the app, and Claude Code
  can work on it in isolation.
- **Editors are interchangeable.** Each editor implements the same minimal
  interface — adding a new property type means writing one new editor class.
