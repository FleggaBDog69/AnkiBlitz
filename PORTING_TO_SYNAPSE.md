# Porting an add-on into SynapsePro

A helper doc, written from doing it once with AnkiBlitz. It's the recipe and the
traps, not a spec — SynapsePro is a moving target and every line number here will
rot. Read it for the shape, check the code for the detail.

The governing rule, which decides most of the arguments below: **you do not edit
SynapsePro.** It's a fork whose changes go upstream as PRs, and "let my add-on
in" isn't a change upstream should have to carry. Everything here is done from
the outside, and everything degrades to a plain standalone add-on when SynapsePro
isn't there.

---

## 0. Before anything: find SynapsePro properly

The single most common way to get this wrong:

```python
from SynapsePro.theme import palette      # will break on a real install
```

Its `manifest.json` declares `"package": "SynapsePro1"`. A git checkout is
usually symlinked in as `SynapsePro`. An AnkiWeb install lands in a **numeric**
folder. So resolve at runtime by manifest name, never by literal import:

```python
for pkg in mw.addonManager.allAddons():
    meta = mw.addonManager.addon_meta(pkg)
    name = meta.human_name() if callable(getattr(meta, "human_name", None)) else None
    if name == "SynapsePro" and getattr(meta, "enabled", True):
        mod = importlib.import_module(f"{pkg}.theme")
```

Cache the *module*, with a sentinel that tells "not looked yet" from "looked and
it isn't there". Wrap every step in `try/except Exception`.

Keep this in **one module** of your add-on. In AnkiBlitz that's
`engine/theme_bridge.py`; nothing else in the codebase knows SynapsePro exists.
That's what makes the whole integration removable and testable.

---

## 1. Colours — `theme.py`

SynapsePro keeps its look in `theme.py` at its add-on root:

- `palette(night_mode) -> dict` of semantic tokens
- `FONT_FAMILY`

Tokens worth knowing: `bg`, `surface`, `text`, `text_muted`, `text_faint`,
`grey_light`, `grey_mid`, `hover_subtle`, `selection_bg`, `blue`, `blue_hover`,
`blue_pressed`, `blue_bright`, `blue_accent`, `blue_border`, `red`, `green`.

Two rules:

- **Call `palette()` fresh every single time.** Its active colour theme is module
  state the user changes at runtime; a cached dict goes stale until restart.
- **Night state comes from `aqt.theme.theme_manager.night_mode`**, the *resolved*
  value. `mw.pm.night_mode()` — which SynapsePro itself uses — is only the stored
  preference and reads light while the OS is dark.

Its colour themes (ocean / orchid / forest / …) override only the six
blue-family tokens. So mapping two of your accents onto `blue` and `blue_accent`
makes them collapse into the same colour under some themes. Pick tokens that stay
distinct — e.g. `blue_bright` for a thing that must not look like a `blue_accent`
thing.

There is **no amber token**. If your design leans on amber for urgency, `red` is
the nearest thing; write the compromise down where the next person will see it.

### Give every lookup the old value as its fallback

```python
def color(key, fallback): ...
color("blue", "#3b82f6")     # Synapse's blue, or what we always used
```

Every call site passing its own pre-integration literal is what makes
"standalone is unchanged" checkable by *reading the diff* rather than by testing
every screen twice.

### Import-time constants are the trap

Anything like `_PILL_STYLE = f"background:{color(...)}"` at module level freezes
the palette at Anki launch, and theme switching mysteriously does nothing until
restart. Make them functions. This is the bug you will actually ship.

---

## 2. Two surfaces, styled two ways

### Webview

Emit a `<style>:root{--x:…}</style>` block from the bridge and prepend it to
whatever HTML you inject. In your stylesheets rewrite hardcoded colours as
`var(--x, <the literal you used before>)`. Custom properties resolve at use time,
so declaration order doesn't matter and the stylesheet stays cacheable.

With SynapsePro absent the vars are simply never defined and the old cascade
applies untouched.

### Qt

A stylesheet string built from the palette, applied per dialog. Model it on
SynapsePro's own `configuration.py::_build_style` so the windows sit together.

**The sub-control trap.** The moment a `QSpinBox` or `QComboBox` gets *any*
stylesheet, Qt stops drawing its native sub-controls and expects your sheet to
supply them. Style the box, say nothing about `::up-button` / `::down-arrow`, and
**the arrows silently vanish**. Qt stylesheets don't take `data:` URIs, so the
fix is to render arrow images to PNG at runtime (keyed by colour, under
`user_files/`) and reference them by path — and to skip styling the widget
entirely if that render fails. An unstyled control beats one you can't click.

**And the escape hatch has to cover the box rule too.** This one was live in
AnkiBlitz for months. The arrow rules were correctly conditional on the PNG
render succeeding — but `QComboBox` was *also* named in the shared
`QLineEdit, QPlainTextEdit, QTextEdit, QComboBox { … }` rule, which isn't. So if
the render ever failed, the box still got styled, Qt still dropped the chevron,
and the "leave it native" fallback never fired. Keep **every** rule for a
sub-controlled widget inside the same conditional; don't let it share a selector
list with widgets that have no sub-controls. Ankisstant's offline harness asserts
exactly this, and it's what found it:

```python
for widget in ("QSpinBox", "QComboBox"):
    if f"{widget}::" in sheet:
        self.assertIn(f"{widget}::down-arrow", sheet)   # styled -> arrows required
    else:
        self.assertNotIn(widget, sheet)                 # unstyled -> unmentioned
```

**Checkboxes and radios: leave them native.** A mis-specified `::indicator`
reads as permanently unchecked, and a settings window whose state you can't read
is worse than one that doesn't quite match.

Build the sheet through a lookup that can't `KeyError` (a tiny wrapper class with
per-token fallbacks). Otherwise one renamed token upstream takes the whole sheet
down to `""` and the window silently un-themes.

---

## 3. The sidebar

`launcher_widget.py::SidebarWidget` builds its strip from a **hardcoded
`feature_map` in `init_ui()`. There is no extension point.** So:

- Find it live: `mw.findChild(QWidget, "SidebarContent")`.
- Add ordinary `QPushButton`s to its layout — but **insert, don't append**. The
  layout is `stretch → feature buttons → stretch → timer / music / separator`,
  so appending lands you in the footer, below everything, reading as an
  afterthought rather than as another feature. Walk the layout, find the last
  widget whose `isMainIconButton` property is set, and `insertWidget` after it.
  Locating the group by that property rather than by a hardcoded index means a
  reordered or extended strip upstream can't silently strand your buttons —
  and skip your own marked widgets while walking, or a re-injection chases
  itself down the strip.
- Set `btn.setProperty("isMainIconButton", True)` — that's the selector its own
  stylesheet keys off. Without it your button is a grey lump in the middle of its
  strip.
- Size `(45, 40)` with a 30px icon, i.e. `(SIDEBAR_WIDTH-10, BUTTON_ICON_SIZE+10)`.
- A separator is a `QFrame` with `setObjectName("bottomSeparatorLine")`, which it
  also styles.

- Set **`normalIcon` and `whiteIcon`** as well, both real `QIcon`s. Its
  `eventFilter` swaps between those two dynamic properties on hover, and
  `_update_button_active_state` uses the same pair for the checked state. Set
  `isMainIconButton` alone and the button is styled correctly but goes dead
  under the mouse while every SynapsePro button beside it lights up.
- The filter is installed by the `SidebarWidget` on the buttons *it* creates, so
  an injected button has to ask: `btn.installEventFilter(sidebar)`.

**The cost of injecting rather than being invited in: your buttons go with the
strip whenever it's rebuilt.** So make injection idempotent (mark your widgets
with an attribute, check for them first) and re-run it. Also fire a few delayed
attempts at profile open — you can't know whose hook runs first.

**Correction to an earlier version of this doc:** the rebuild trigger is
**profile open, not settings-apply**. `init_ui()` runs once from `__init__`;
applying settings only calls `apply_stylesheet()`. The whole widget is recreated
by `__init__.py::_init_launcher_dock`, which is guarded by a module global and
called from `on_profile_open` plus a 300 ms `_init_ui_delayed`. Hook
`profile_did_open` rather than `state_did_change` if you only want one (though
both is cheap, and `state_did_change` covers a rebuild neither of us predicted).

**Register your hooks once, not per profile.** `gui_hooks` lists are global. If
your `register()` runs from a profile-open handler and appends to them, every
profile switch stacks another copy of your callback for the rest of the session.
Re-run the *injection* every time; guard the *hook registration* with a flag.

Icons: generate SVG and recolour from the palette rather than shipping colour
variants. Render with `QSvgRenderer` + `QPainter` at 2× — `QPixmap.loadFromData(…,
"SVG")` only honours the viewBox and comes out blurry. `QSvgRenderer` lives in
`PyQt6.QtSvg`, which `aqt.qt` does **not** re-export.

**Be sparing.** Two buttons is plenty; one accented, the rest in the `text`
colour. A strip where everything is the accent colour has no hierarchy left. Put
the rest behind one of them.

---

## 3b. Docking your own panel beside its own

The sidebar has no extension point, but the **dock placement does**, and it's the
one part of this where SynapsePro actively helps you.

`constants.place_feature_dock(dock)` is registered onto the `constants` module at
runtime (`__init__.py:438`, defined at `:379`) and is what every one of its own
features calls — AI assistant, website, notebook, mind-map. It docks to the right
region, handles the awkward case where the launcher strip is *itself* on the
right (it splits so the launcher keeps the outer edge), and wires
`visibilityChanged` into its launcher-visibility logic. Use it exactly as they
do, and fall back to a plain `addDockWidget` if it isn't there:

```python
place = getattr(constants_module(), "place_feature_dock", None)
if callable(place):
    place(dock)
else:
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
```

Copy the rest of the idiom from `ai_assistant.py:1780-1796`:
`setAllowedAreas(Left|Right)`, `setFeatures(Floatable|Movable|Closable)`,
**`setTitleBarWidget(QWidget())`** (all its panels suppress the native title bar;
yours would otherwise be the only one with a grey strip on top), a
`setMinimumWidth`, and `setVisible(False)` before placing.

**Several panels open at once needs no work.** Its `_handle_feature_click`
(`launcher_widget.py:300`) doesn't close or hide siblings — it runs the tool's
toggle and connects `visibilityChanged` to the button's checked state. Every
feature adds to the same right-hand area with a plain `addDockWidget`, and Qt
**splits** docks in one area rather than tabbing them. So they sit side by side
on their own.

Four things to know:

- **A UI built for a window will run off the right edge of a dock, and a
  scrollbar won't save you.** The culprit is `setMinimumWidth()` on form fields —
  a minimum is a floor the layout can't negotiate below, so it pushes the scroll
  area's contents wider than the viewport instead of letting the fields shrink.
  Walk the panel once in dock mode and lower every minimum above ~170px. Skip
  widgets where minimum == maximum: those came from `setFixedWidth` and are sized
  to their own text, so squeezing them clips rather than reflows. There's nothing
  to undo when the panel goes back into a window — the fields still expand to
  fill it, which was always the layout doing it, not the minimum.
- **If you offer a pop-out, offer the way back in the popped-out chrome.**
  Obvious written down; easy to miss, because the state you're testing from is
  the one that still has the button.
- **Closing a `QDockWidget` hides it, it doesn't destroy it.** If your close
  handler drops your singleton, the next open builds a *second* dock with the
  same objectName and Qt has two of them fighting over the area. Keep the
  reference; re-`show()` it.
- **`sync_dock_button()` won't work for you.** It looks the button up in
  `_dock_button_refs`, which is populated only from its hardcoded feature map.
  Drive your own button's checked state and icon off your dock's
  `visibilityChanged` instead — six lines, no edit on their side.
- **`_feature_panel_dock_names()` (`__init__.py:370`) is a hardcoded list**, so
  `_any_feature_panel_visible()` won't count your dock, and opening it mid-review
  won't auto-reveal the launcher strip. That one you can't fix from outside.
  Write it down and move on.

If your UI already exists as a `QDialog`, the port is smaller than it looks:
split the contents into a plain `QWidget` body with two thin hosts (the dialog
and the dock), and make a "pop out" button **re-parent** the body between them.
Rebuilding instead is a trap if your panels are cached in module globals — you'd
be handing the same widget to two parents — and re-parenting has the nicer
property that a half-filled form survives the move. Point whatever singleton the
rest of your add-on reaches for at the **body**, not the host, so nothing else
has to care which one it's in.

A narrow dock also wants narrower chrome. A 200px text nav that's fine in a
900px window eats a third of a 560px panel, so swap it for an icon rail in dock
mode and keep the text labels in the popped-out window. If those labels carried
counts, the rail needs to carry them too — a dot on the icon plus **the number in
the tooltip**, never the dot alone.

---

## 4. Popup panels

SynapsePro's own settings and Pomodoro screens are HTML files in a
`QWebEngineView`, with a `QWebEnginePage` subclass overriding
`javaScriptConsoleMessage` as the JS→Python bridge — no QWebChannel. Copy that:

- Python → page: `runJavaScript("window.__init && __init({...})")` on
  `loadFinished`.
- Page → Python: `console.log("myprefix:action")`, intercepted and dispatched.
- Call `page.setBackgroundColor(...)` **before** load or the view flashes white in
  dark mode.

Match its design language rather than inventing one: same token names
(`--accent`, `--bg`, `--card`, `--border`, `--text`, `--muted`, `--field-bg`,
`--switch-off`), same `.group` / `.row` cards, same `.switch`. Ship its stock
light/dark values as CSS defaults so the page still looks right if token
injection ever fails.

Keep a plain-Qt fallback path for a build without WebEngine.

---

## 5. Overlapping features

Where both add-ons do the same job, decide **once**, per feature, and make it a
config key the user can flip. AnkiBlitz's calls:

| Feature | Who wins | How |
|---|---|---|
| Music player | SynapsePro | AnkiBlitz's menu item, rail block and break-screen box are hidden |
| Pomodoro | AnkiBlitz | one-time notice + a button into SynapsePro's settings |

**Read SynapsePro's settings, never write them.** Note its settings are *not* in
Anki's add-on config — `config.json` holds only `addon_version`. They live in a
module-global `addon_settings` dict on the package root, persisted to
`addon_settings.json`. So:

```python
root = importlib.import_module(package_name())
bool(getattr(root, "addon_settings", {}).get("pomodoro_enabled", True))
```

Writing into another add-on's config is the hard coupling the independence rule
exists to prevent. Tell the user and give them the button.

---

## 6. Config and settings UI

- New keys go in your `DEFAULTS` and get backfilled by your `ensure_defaults()`.
  **Never hand-edit `meta.json`** — the user's live values are in there.
- Give it its own tab with a kill switch per behaviour: theme on/off, sidebar
  on/off, defer-music on/off, and so on. Every one of them should return the
  add-on to exactly how it looked before the integration existed.
- State detection **in words** ("SynapsePro detected" / "not detected"), not by
  colouring something green.

---

## 7. Testing it

`.py` changes need an Anki restart; web assets reload from disk.

Write an **offline harness** — stub `aqt` and `aqt.theme` with `MagicMock`, fake a
`SynapsePro` module with a `palette()` and an `addon_settings` dict, and point a
fake package at your add-on folder so relative imports resolve. That covers the
matrix cheaply: absent / disabled / broken SynapsePro, light vs dark, a live
theme switch, every kill switch. AnkiBlitz's is
`scratchpad/test_theme_bridge.py`; it caught a real bug (one missing token
blanking the entire Qt stylesheet) that no amount of clicking would have shown.

Make your fake palette **deliberately thin** — three or four tokens. If your code
only works against a complete palette, you want to know now.

The one manual check that isn't optional: **disable SynapsePro, restart, and
confirm your add-on looks and behaves exactly as it did before any of this.**

---

## Tools used

Nothing exotic:

- `grep` / `Read` across both add-on folders — most of the work was reading
  `launcher_widget.py`, `theme.py`, `configuration.py` and `settings_web/*.html`
  before writing anything.
- `python3 -m py_compile`, `node --check`, `json.load` as the static sweep.
- A hand-rolled `unittest.mock`-based harness (above). No pytest, no Anki.
- `qlmanage -t -s 96 -o . icon.svg` to render an SVG to PNG and actually **look**
  at it. Hand-written icon paths are wrong more often than you'd think, and this
  is faster than restarting Anki to find out.

---

## Checklist

- [ ] SynapsePro resolved by manifest name, never imported literally
- [ ] One bridge module; nothing else knows SynapsePro exists
- [ ] `palette()` called fresh; no import-time colour constants
- [ ] Night state from `theme_manager.night_mode`
- [ ] Every `color()` call passes the pre-integration literal as fallback
- [ ] Spin box / combo sub-controls supplied, or those widgets left native —
      including their *box* rule, not just the arrow rule
- [ ] Checkbox indicators left native
- [ ] Sidebar injection idempotent and re-run (profile open is the real trigger)
- [ ] Hook registration guarded by a flag, so profile switches don't stack it
- [ ] `isMainIconButton` **and** `normalIcon` / `whiteIcon` on every injected button
- [ ] Docked via `constants.place_feature_dock` when it exists
- [ ] Closing your dock hides it — the singleton survives, no second dock
- [ ] Read SynapsePro's settings; write none of them
- [ ] A kill switch per behaviour, each restoring the standalone look
- [ ] Offline harness green, including a thin fake palette
- [ ] Manually verified with SynapsePro disabled
