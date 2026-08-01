"""AnkiBlitz's two buttons inside SynapsePro's launcher strip.

When SynapsePro is installed, its 55px icon rail on the edge of the window is
where features live — so that's where AnkiBlitz goes too, instead of drawing a
second panel of its own on the deck list.

Two buttons, appended below SynapsePro's own timer group:

    🍅  start / resume a Pomodoro   — the one thing worth a dedicated icon
    ⚡  open the AnkiBlitz panel    — everything else, settings included, is in there

The tomato takes the accent colour (it *does* something the moment you press it);
the bolt is drawn in the text colour, so the strip has one coloured thing in it
rather than two competing for the eye.

**Nothing in SynapsePro is modified.** The buttons are ordinary ``QPushButton``s
appended to the live ``SidebarWidget``'s layout at runtime. They carry the
``isMainIconButton`` property SynapsePro's own stylesheet keys off, so they pick
up its hover and accent colours for free and stay in step when its theme changes.

The trade-off of injecting rather than being invited in: SynapsePro rebuilds its
sidebar when its settings are applied, which drops our buttons. So injection is
idempotent and re-runs on state changes — see ``_ensure``.
"""

import weakref

from aqt import gui_hooks, mw
from aqt.qt import (
    QByteArray, QFrame, QIcon, QPixmap, QPushButton, QSize, Qt, QWidget,
)

from ..config import get_section, suite_enabled
from . import theme_bridge

# SynapsePro's SidebarWidget sets this on itself; findChild is a stabler handle
# than reaching for the add-on's module globals.
SIDEBAR_OBJECT_NAME = "SidebarContent"

# Marks the widgets we own, so re-injection can tell "already there" from
# "SynapsePro rebuilt the strip and ours are gone".
_MARK = "ankiblitz_sidebar_item"

_injected_into = None       # weakref to the SidebarWidget we last populated
_buttons: list = []         # kept alive; also how we refresh icons on theme change


# ----- Icons -----
#
# Drawn as SVG here rather than shipped as files: they have to be recoloured to
# whatever accent SynapsePro is on (and to white when a button is hovered or
# active, matching its other icons), and generating them is less fuss than
# maintaining a folder of colour variants.

_SVG_BOLT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<path fill="{c}" d="M13.5 2 4 13.2h6.1L9.8 22 20 10.6h-6.3z"/></svg>'
)

# A tomato, drawn from primitives rather than a traced path — it has to stay
# legible at 30px, and it has to stay clearly *not* SynapsePro's own clock icon
# sitting a few pixels above it.
_SVG_TOMATO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    '<ellipse cx="12" cy="14" rx="7.6" ry="6.8" fill="{c}"/>'
    '<path d="M12 7.4 8.2 4.6M12 7.4l3.8-2.8M12 7.4V4.2" stroke="{c}" '
    'stroke-width="1.7" stroke-linecap="round" fill="none"/></svg>'
)

# SynapsePro's BUTTON_ICON_SIZE is 30; render at 2x so it stays crisp on Retina.
_ICON_PX = 60


def _icon(svg_template: str, colour: str):
    """An SVG string rendered into a QIcon at the strip's icon size."""
    svg = svg_template.format(c=colour).encode("utf-8")
    # QSvgRenderer draws at whatever size we ask for; QPixmap's SVG loader only
    # honours the viewBox, so a 24px icon would come out blurry on the button.
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from aqt.qt import QPainter
        pix = QPixmap(_ICON_PX, _ICON_PX)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        try:
            QSvgRenderer(QByteArray(svg)).render(painter)
        finally:
            painter.end()
        return QIcon(pix)
    except Exception:
        pass
    try:
        pix = QPixmap()
        if not pix.loadFromData(QByteArray(svg), "SVG"):
            return None
        return QIcon(pix)
    except Exception:
        return None


def _accent() -> str:
    # Same token SynapsePro colours its own settings icon with, so ours sits in
    # the strip rather than next to it.
    return theme_bridge.color("blue_accent", "#0071D3")


def _ink() -> str:
    """The un-accented icon colour — dark on a light theme, light on a dark one."""
    return theme_bridge.color("text", "#1d1d1f")


# Which of the two each button paints itself with, resolved fresh every time so a
# theme switch (SynapsePro's accent, or Anki's light/dark) is picked up live.
_ACCENT = "accent"
_INK = "ink"


def _colour_for(role: str) -> str:
    return _accent() if role == _ACCENT else _ink()


# ----- Buttons -----

def _make_button(svg: str, tooltip: str, on_click, role: str = _ACCENT) -> "QPushButton":
    btn = QPushButton()
    btn.setToolTip(tooltip)
    btn.setFlat(True)
    btn.setCheckable(False)
    # The property SynapsePro's sidebar stylesheet selects on. Without it the
    # button would be an unstyled grey lump in the middle of its strip.
    btn.setProperty("isMainIconButton", True)
    setattr(btn, _MARK, True)
    btn.setFixedSize(QSize(45, 40))     # SIDEBAR_WIDTH - 10, BUTTON_ICON_SIZE + 10
    btn.setIconSize(QSize(30, 30))
    ic = _icon(svg, _colour_for(role))
    if ic is not None:
        btn.setIcon(ic)
    else:
        btn.setText("?")
    btn._ab_svg = svg                   # for recolouring on theme change
    btn._ab_role = role
    btn.clicked.connect(lambda _checked=False: _safely(on_click))
    return btn


def _safely(fn) -> None:
    """A click must never propagate an exception into SynapsePro's strip."""
    try:
        fn()
    except Exception:
        pass


def _on_pomodoro() -> None:
    from . import pomodoro
    pomodoro.start_pomodoro(use_defaults=True)


def _on_panel() -> None:
    from . import panel
    panel.open_panel()


def _pomodoro_tooltip() -> str:
    from . import pomodoro
    try:
        run = pomodoro.resumable_run()
        if run:
            return f"AnkiBlitz — resume Pomodoro ({pomodoro.resume_summary(run)})"
    except Exception:
        pass
    return "AnkiBlitz — start a Pomodoro"


# ----- Injection -----

def _find_sidebar():
    try:
        return mw.findChild(QWidget, SIDEBAR_OBJECT_NAME)
    except Exception:
        return None


def _already_ours(sidebar) -> bool:
    """True when our buttons are still in this sidebar."""
    try:
        for child in sidebar.findChildren(QPushButton):
            if getattr(child, _MARK, False):
                return True
    except Exception:
        pass
    return False


def _enabled() -> bool:
    return (suite_enabled()
            and get_section("synapse").get("sidebar_buttons", True)
            and theme_bridge.synapse_available())


def active() -> bool:
    """True when the sidebar is AnkiBlitz's home — so the deck rail stands down.

    Deliberately the *intent* (SynapsePro present, integration on) rather than
    "are the buttons in the layout right now". Injection can lose a race with
    SynapsePro rebuilding its strip, and the rail flickering back in for one
    render would look far worse than a moment with neither.
    """
    return _enabled() and get_section("synapse").get("hide_rail", True)


def _inject(sidebar) -> bool:
    global _injected_into, _buttons
    layout = sidebar.layout()
    if layout is None:
        return False

    sep = QFrame()
    sep.setObjectName("bottomSeparatorLine")   # SynapsePro styles this too
    sep.setFrameShape(QFrame.Shape.HLine)
    setattr(sep, _MARK, True)
    layout.addWidget(sep)

    pomo = _make_button(_SVG_TOMATO, _pomodoro_tooltip(), _on_pomodoro, _ACCENT)
    blitz = _make_button(_SVG_BOLT, "AnkiBlitz — sessions, stats and settings",
                         _on_panel, _ACCENT)
    for b in (pomo, blitz):
        layout.addWidget(b)

    _buttons = [pomo, blitz]
    _injected_into = weakref.ref(sidebar)
    return True


def _ensure() -> None:
    """Put our buttons in the strip if they aren't already there.

    Cheap enough to call often, and it needs to be: SynapsePro rebuilds its whole
    sidebar when its settings are applied, taking ours with it. Called on profile
    open, on every Anki state change, and after AnkiBlitz's own settings close.
    """
    try:
        if not _enabled():
            return
        sidebar = _find_sidebar()
        if sidebar is None or _already_ours(sidebar):
            return
        _inject(sidebar)
    except Exception:
        pass


def refresh_icons() -> None:
    """Recolour the icons — SynapsePro's accent or Anki's light/dark changed."""
    try:
        for btn in _buttons:
            svg = getattr(btn, "_ab_svg", None)
            if svg is None:
                continue
            ic = _icon(svg, _colour_for(getattr(btn, "_ab_role", _ACCENT)))
            if ic is not None:
                btn.setIcon(ic)
        if _buttons:
            _buttons[0].setToolTip(_pomodoro_tooltip())
    except Exception:
        pass


def remove() -> None:
    """Take our buttons back out — the integration was switched off."""
    global _buttons, _injected_into
    sidebar = _injected_into() if _injected_into is not None else None
    try:
        if sidebar is not None:
            for child in list(sidebar.findChildren(QWidget)):
                if getattr(child, _MARK, False):
                    child.setParent(None)
                    child.deleteLater()
    except Exception:
        pass
    _buttons = []
    _injected_into = None


def apply_settings_change() -> None:
    """Add or drop the buttons right after Settings closes, no restart needed."""
    try:
        if _enabled():
            _ensure()
            refresh_icons()
        else:
            remove()
    except Exception:
        pass


def _on_state_change(new_state, old_state) -> None:
    _ensure()
    refresh_icons()          # the Pomodoro tooltip tracks a resumable run


def register() -> None:
    # SynapsePro builds its sidebar at profile open too, and we can't know whose
    # hook runs first — so retry a few times rather than racing it once.
    for delay in (400, 1200, 3000):
        mw.progress.single_shot(delay, _ensure, False)
    gui_hooks.state_did_change.append(_on_state_change)
    gui_hooks.theme_did_change.append(refresh_icons)
