# The SynapsePro bridge — what was built, and why it differs from the sketch

This started as a plan to soft-bridge AnkiBlitz's webview colours to SynapsePro's
`theme.py`. Reading both add-ons first changed four of its premises; this file
records the shipped design and those corrections, so nobody re-derives them.

It has since grown past colours into a proper integration: AnkiBlitz now *lives
in* SynapsePro's sidebar rather than drawing a panel of its own.

Three modules, all no-ops without SynapsePro. Configured under the `synapse`
config section (see `config.md`) and **Settings ▸ SynapsePro**.

| Module | Job |
|---|---|
| `engine/theme_bridge.py` | Resolves SynapsePro, serves its palette as CSS vars and a Qt stylesheet, decides the music question |
| `engine/synapse_sidebar.py` | The two buttons in its launcher strip |
| `engine/panel.py` + `web/blitz_panel.html` | The ⚡ panel |

## The sidebar, without touching SynapsePro

Its `SidebarWidget.init_ui()` builds the strip from a hardcoded `feature_map`;
there's no extension point. So AnkiBlitz finds the live widget
(`mw.findChild(QWidget, "SidebarContent")`) and appends ordinary `QPushButton`s
to its layout, each carrying the `isMainIconButton` property its stylesheet
selects on — which is what makes them pick up its hover and accent colours
rather than sitting there as grey lumps.

The cost of injecting rather than being invited in: **SynapsePro rebuilds the
sidebar when its settings are applied**, dropping ours. So injection is
idempotent and re-runs on `state_did_change` (see `synapse_sidebar._ensure`).

Icons are generated SVG, recoloured from the palette — a folder of colour
variants would need maintaining, and they have to track whatever accent
SynapsePro is on.

**Only the tomato is accented.** The bolt is drawn in the `text` token. A strip
where every icon is the accent colour has no hierarchy in it, and the tomato is
the one that acts the instant you press it; the bolt just opens a window. Roles
(`_ACCENT` / `_INK`) are stored per button and resolved fresh in
`refresh_icons`, so both follow a theme switch.

Settings has **no sidebar button** — it's a row in the panel. Two AnkiBlitz icons
next to SynapsePro's own gear was one gear too many, and settings is not
something you reach for mid-review.

## The panel

`web/blitz_panel.html` is built to SynapsePro's settings-page design language —
same token names, same `.group` / `.row` cards, same switch — shown in a
`QWebEngineView`. The bridge is `console.log("blitz:<action>")` intercepted by a
`QWebEnginePage` subclass, the same trick SynapsePro's own settings page uses,
which avoids a QWebChannel dependency. There's a plain-Qt fallback with the same
actions for a build without WebEngine.

The page ships SynapsePro's stock light/dark defaults, so if the token injection
ever fails it still looks right rather than unstyled. Keep those defaults in step.

## Corrections to the original sketch

1. **"AnkiBlitz has no native Qt chrome" — not true.** The full-page Pomodoro
   break screen, stats, settings, onboarding, the Blitz completion screen and the
   music box are all `QDialog` + `setStyleSheet`. The webview surface is only the
   deck-list rail (`engine/widgets.py`) and the reveal overlay
   (`web/focus_suite.css`). Both layers are themed; the Qt one is the bigger of
   the two by far.
2. **The existing CSS custom properties covered almost nothing.** Four vars, all
   in the rail (`--fg`, `--border`, `--canvas-elevated`, `--button-bg`). The
   overlay's colours were hardcoded with no var in reach. Both stylesheets now
   use `var(--ab-x, <the literal AnkiBlitz always used>)`, with Anki's own vars
   kept as the middle link where they existed.
3. **`from SynapsePro.theme import …` would not have survived an install.** Its
   `manifest.json` declares `"package": "SynapsePro1"`, a git checkout is usually
   symlinked in as `SynapsePro`, and an AnkiWeb install lands in a numeric folder.
   The module is resolved at runtime by walking `mw.addonManager.allAddons()` and
   matching the manifest's human name.
4. **The Pomodoro clash needed no SynapsePro code.** Its timer is already gated
   on `addon_settings["pomodoro_enabled"]`, so this is a one-time notice plus a
   button into its settings — see "Not our config" below.

## How it hangs together

- `tokens()` calls SynapsePro's `palette(night)` **fresh on every call**. Its
  active colour theme is module state the user can change without restarting; a
  cached dict would go stale until the next launch.
- Night state comes from `aqt.theme.theme_manager.night_mode` — the *resolved*
  value. `mw.pm.night_mode()` (which SynapsePro itself uses) is only the stored
  preference and reads light while the OS is dark.
- `color(key, fallback)` is the workhorse. Every call site passes the colour it
  used before the bridge existed, which is what makes "standalone is unchanged"
  checkable by reading the diff.
- **Timeline pill styles are functions, not module constants.** Import-time
  constants were the one real trap: they'd freeze the palette at Anki launch.
- The rail bakes its colours into rendered HTML, so it's redrawn on
  `theme_did_change` and after Settings closes.

## Token map

| AnkiBlitz's own | SynapsePro token |
|---|---|
| `#3b82f6` primary Blitz button, focus-rating buttons | `blue` |
| `#e0533d` Pomodoro rail button | `red` |
| `#e0883c` floating break pill, "now" timeline pill | `blue_accent` |
| `#2e7d32` completed-block pill | `green` |
| `#7e57c2` / `#b39ddb` long-break pill | `blue_bright` |
| `rgba(150,150,150,.7)` "next" dashed pill | `text_faint` |
| `#22c55e` rail "on" state | `green` |
| `rgba(20,22,28,.92)` / `#eaeaea` overlay panel | `surface` / `text` |
| `rgba(255,255,255,.08)` tracks and dividers | `grey_light` |
| `#f59e0b → #ef4444` countdown gradient | `blue → red` |
| `rgba(245,158,11,.92)` pre-reveal warning chip | `red` |
| `#4ade80 → #22d3ee` accuracy gradient | `green → blue_bright` |
| `#fbbf24` streak flash | `blue_bright` |

Two deliberate compromises: SynapsePro has no amber token, so the **warning chip**
and the **countdown gradient** lose their amber "time's nearly up" read — `red` is
the nearest thing that still means urgency. And **long-break purple maps to
`blue_bright`, not `blue_accent`**, so a long break stays visually distinct from a
short one under every SynapsePro colour theme.

## Not our config

AnkiBlitz reads SynapsePro (palette, and `addon_settings["pomodoro_enabled"]`) and
**never writes to it**. The Pomodoro clash is surfaced as a one-time dialog with a
button that opens SynapsePro's own settings; turning its timer off is the user's
call. Writing into another add-on's config is the hard coupling the
add-on-independence rule exists to prevent — and SynapsePro here is a fork whose
changes go upstream as PRs.

## If you're changing this

Run `scratchpad/test_theme_bridge.py` (offline, stubs aqt and fakes a SynapsePro
theme module). It covers both directions — absent/disabled/broken SynapsePro
falling back to AnkiBlitz's own values, and present SynapsePro coming through
including a live theme switch.

The non-negotiable manual check: **disable SynapsePro, restart, and confirm
AnkiBlitz looks exactly as it did before any of this.**

## Deliberately not done

- **Any edit inside the SynapsePro add-on.** Not even to add an extension point:
  it's a fork whose changes go upstream as PRs, and "let AnkiBlitz in" isn't a
  change upstream should have to carry.
- **Rebuilding AnkiBlitz's Settings as an HTML page.** It's recoloured with a Qt
  stylesheet instead. Re-expressing ~1,600 lines of Qt panels across nine tabs in
  HTML plus a JSON bridge buys a closer visual match at a real risk of settings
  silently not saving.
- **Restyling checkbox indicators.** See `theme_bridge.qt_stylesheet`.

## The sub-control trap

Giving a `QSpinBox` or `QComboBox` *any* stylesheet makes Qt stop drawing its
native sub-controls and expect the sheet to supply them — so styling the box and
saying nothing about `::up-button` / `::down-arrow` **silently deletes the
arrows**. That's exactly what happened on the first pass.

There's no built-in arrow image to point at and Qt stylesheets don't accept
`data:` URIs, so `_spin_arrows` renders two chevrons to PNG under
`user_files/theme/` (named by colour hash, so a theme switch makes new ones) and
the sheet references them by path. **If that render fails for any reason,
`_spinbox_rules` returns `""` and spin boxes stay native** — an unstyled control
beats a control you can't click.

Checkboxes are the same trap dodged the other way: left native on purpose.
