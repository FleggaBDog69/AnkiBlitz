"""The one place in AnkiBlitz that knows SynapsePro exists.

SynapsePro keeps its whole look in a ``theme.py`` at its add-on root: a
``palette(night) -> dict`` of semantic colour tokens plus a ``FONT_FAMILY``
constant. If it's installed, AnkiBlitz borrows those tokens so the two add-ons
read as one product — including when the user switches SynapsePro's colour
theme, since ``palette()`` is asked fresh every time rather than cached.

Everything here is a **soft bridge**, per the house rule: SynapsePro is never a
dependency, every lookup is ``try/except``-wrapped, and when it's absent (or
broken, or the user has switched the bridge off) every call falls back to the
colour AnkiBlitz has always used. Standalone AnkiBlitz is unchanged.

Two things worth knowing before you edit this:

- **Don't import SynapsePro by name.** Its ``manifest.json`` declares the package
  as ``SynapsePro1``, a git checkout is usually symlinked in as ``SynapsePro``,
  and an AnkiWeb install lands in a numeric folder. The module is resolved at
  runtime by reading manifests, not by a literal import.
- **Don't hold on to the palette.** SynapsePro's active theme is module state it
  rewrites when the user picks a different colour; a cached dict would go stale
  until the next Anki restart.
"""

import hashlib
import importlib
import os

from aqt import mw

from ..config import get_section

# The add-on's advertised name in its manifest — stable across the package-name
# variants above, and what we actually match on.
SYNAPSE_NAME = "SynapsePro"

# Resolved SynapsePro theme module, or None. Sentinel distinguishes "not looked
# yet" from "looked and it isn't there", so a missing add-on costs one scan.
_UNSET = object()
_theme_mod = _UNSET


def _find_theme_module():
    """Locate SynapsePro's theme module by manifest name. None if absent."""
    try:
        packages = mw.addonManager.allAddons()
    except Exception:
        return None
    for pkg in packages:
        try:
            meta = mw.addonManager.addon_meta(pkg)
            name = getattr(meta, "human_name", None)
            name = name() if callable(name) else name
            if name != SYNAPSE_NAME and pkg != SYNAPSE_NAME:
                continue
            if getattr(meta, "enabled", True) is False:
                continue
            return importlib.import_module(f"{pkg}.theme")
        except Exception:
            continue
    return None


def _theme():
    global _theme_mod
    if _theme_mod is _UNSET:
        try:
            _theme_mod = _find_theme_module()
        except Exception:
            _theme_mod = None
    return _theme_mod


def reset_cache() -> None:
    """Forget the resolved module — for after an add-on is enabled or installed."""
    global _theme_mod
    _theme_mod = _UNSET


def synapse_available() -> bool:
    """True when SynapsePro is installed, enabled, and exposes its palette."""
    return _theme() is not None


def theme_module():
    """SynapsePro's ``theme`` module, or None — for callers that need its path
    or its package name (icon files, the settings entry point)."""
    return _theme()


def package_name() -> str:
    """SynapsePro's actual add-on package name, whatever the folder is called."""
    mod = _theme()
    return mod.__name__.split(".")[0] if mod is not None else ""


def _bridge_on() -> bool:
    return bool(get_section("synapse").get("theme_bridge", True))


def _night() -> bool:
    """Anki's *resolved* dark state.

    ``theme_manager.night_mode`` accounts for "follow system"; ``pm.night_mode()``
    is only the stored preference, so it reads light while the OS is dark.
    """
    try:
        from aqt.theme import theme_manager
        return bool(theme_manager.night_mode)
    except Exception:
        try:
            return bool(mw.pm.night_mode())
        except Exception:
            return False


def tokens() -> dict:
    """SynapsePro's palette for the current light/dark state, or {} without it.

    Asked fresh every call on purpose — see the module docstring.
    """
    if not _bridge_on():
        return {}
    mod = _theme()
    if mod is None:
        return {}
    try:
        pal = mod.palette(_night())
        return pal if isinstance(pal, dict) else {}
    except Exception:
        return {}


def color(key: str, fallback: str) -> str:
    """One token, with AnkiBlitz's own colour as the fallback.

    Written as ``color("blue", "#3b82f6")`` so every call site carries the value
    it used before the bridge existed — which is what makes "standalone looks
    identical" checkable by reading the diff.
    """
    try:
        value = tokens().get(key)
    except Exception:
        value = None
    return value if isinstance(value, str) and value else fallback


def font_family(fallback: str) -> str:
    if not _bridge_on() or not get_section("synapse").get("match_font", False):
        return fallback
    mod = _theme()
    if mod is None:
        return fallback
    try:
        fam = getattr(mod, "FONT_FAMILY", None)
        return fam if isinstance(fam, str) and fam else fallback
    except Exception:
        return fallback


# ----- Webview side -----
#
# The rail and the reveal overlay style themselves with `var(--ab-x, <today's
# colour>)`. When SynapsePro is absent this block is empty, none of the vars
# resolve, and every fallback applies — i.e. exactly the old stylesheet.

# CSS var name -> (SynapsePro token, AnkiBlitz's current value)
_CSS_MAP = {
    "--ab-primary":    ("blue",        "#3b82f6"),
    "--ab-primary-fg": ("surface",     "#ffffff"),
    "--ab-tomato":     ("red",         "#e0533d"),
    "--ab-on":         ("green",       "#22c55e"),
    "--ab-surface":    ("surface",     "rgba(20, 22, 28, 0.92)"),
    "--ab-text":       ("text",        "#eaeaea"),
    "--ab-track":      ("grey_light",  "rgba(255, 255, 255, 0.08)"),
    "--ab-bar-from":   ("blue",        "#f59e0b"),
    "--ab-bar-to":     ("red",         "#ef4444"),
    "--ab-warn":       ("red",         "rgba(245, 158, 11, 0.92)"),
    "--ab-warn-fg":    ("surface",     "#1b1b1b"),
    "--ab-acc-from":   ("green",       "#4ade80"),
    "--ab-acc-to":     ("blue_bright", "#22d3ee"),
    "--ab-flash":      ("blue_bright", "#fbbf24"),
    "--ab-fg":         ("text",        ""),
    "--ab-border":     ("grey_mid",    ""),
    "--ab-elevated":   ("surface",     ""),
    "--ab-button-bg":  ("grey_light",  ""),
}


def css_vars() -> str:
    """A ``<style>:root{…}</style>`` block, or "" when there's nothing to theme."""
    pal = tokens()
    if not pal:
        return ""
    decls = []
    for var, (token, _fallback) in _CSS_MAP.items():
        value = pal.get(token)
        if isinstance(value, str) and value:
            decls.append(f"{var}:{value};")
    fam = font_family("")
    if fam:
        decls.append(f"--ab-font:{fam};")
    if not decls:
        return ""
    return "<style>:root{" + "".join(decls) + "}</style>"


# ----- Qt side -----

# Anki-neutral stand-ins, used only if SynapsePro's palette is missing a key.
_QSS_FALLBACKS = {
    "bg": "#f5f5f7", "surface": "#ffffff", "text": "#1d1d1f",
    "text_muted": "#86868b", "text_faint": "#aaaaaa",
    "grey_light": "#e5e5ea", "grey_mid": "#d1d1d6",
    "hover_subtle": "#f0f0f0", "selection_bg": "#e4f2ff",
    "blue": "#0071d3", "blue_hover": "#0062c4", "blue_pressed": "#004990",
    "blue_bright": "#007aff", "blue_accent": "#0071d3", "blue_border": "none",
}


class _WithFallbacks:
    """dict-style lookup that can't KeyError — ``c['thing']`` always yields a colour."""

    def __init__(self, palette: dict, fallbacks: dict):
        self._p = palette
        self._f = fallbacks

    def __getitem__(self, key: str) -> str:
        value = self._p.get(key)
        if isinstance(value, str) and value:
            return value
        return self._f.get(key, "inherit")


# ----- Spin-box arrows -----
#
# The moment a QSpinBox gets *any* stylesheet, Qt stops drawing its native
# up/down buttons and expects the sheet to supply them — so styling the box and
# saying nothing about the sub-controls silently deletes the arrows. There's no
# built-in arrow image to point at and Qt stylesheets don't take data: URIs, so
# we render two small chevrons to PNG and reference them by path. If that fails
# for any reason, `qt_stylesheet` leaves spin boxes native rather than shipping a
# control you can't click.

_SPIN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
    '<path d="{d}" fill="none" stroke="{c}" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_SPIN_UP = "M3 7.5 6 4.5 9 7.5"
_SPIN_DOWN = "M3 4.5 6 7.5 9 4.5"

_ARROW_PX = 24          # 12px chevron at 2x, for Retina
_arrow_cache: dict = {}


def _arrow_dir() -> str:
    # user_files/ survives add-on updates, and these are disposable anyway.
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "user_files", "theme")
    os.makedirs(path, exist_ok=True)
    return path


def _spin_arrows(colour: str):
    """(up_path, down_path) as forward-slashed strings, or None if we can't."""
    if colour in _arrow_cache:
        return _arrow_cache[colour]
    result = None
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from aqt.qt import QByteArray, QPainter, QPixmap, Qt

        tag = hashlib.md5(colour.encode("utf-8")).hexdigest()[:8]
        folder = _arrow_dir()
        paths = []
        for name, d in (("up", _SPIN_UP), ("down", _SPIN_DOWN)):
            target = os.path.join(folder, f"spin_{name}_{tag}.png")
            if not os.path.exists(target):
                svg = _SPIN_SVG.format(d=d, c=colour).encode("utf-8")
                pix = QPixmap(_ARROW_PX, _ARROW_PX)
                pix.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pix)
                try:
                    QSvgRenderer(QByteArray(svg)).render(painter)
                finally:
                    painter.end()
                if not pix.save(target, "PNG"):
                    raise RuntimeError("could not write " + target)
            paths.append(target.replace("\\", "/"))
        result = (paths[0], paths[1])
    except Exception:
        result = None
    # Only successes are cached. A one-off failure (asked before the Qt app is up,
    # say) would otherwise disable the arrows for the rest of the session, and
    # retrying costs a failed import.
    if result is not None:
        _arrow_cache[colour] = result
    return result


def _spinbox_rules(c) -> str:
    """Spin-box styling, or "" to leave them native with their arrows intact."""
    arrows = _spin_arrows(c["text_muted"])
    if arrows is None:
        return ""
    up, down = arrows
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {c['surface']};
            border: 1px solid {c['grey_mid']};
            border-radius: 8px; padding: 4px 7px; color: {c['text']};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{
            border: 2px solid {c['blue_bright']};
        }}
        QSpinBox::up-button, QDoubleSpinBox::up-button {{
            subcontrol-origin: border; subcontrol-position: top right;
            width: 17px; height: 11px; margin: 1px 2px 0 0;
            border: none; background: transparent;
        }}
        QSpinBox::down-button, QDoubleSpinBox::down-button {{
            subcontrol-origin: border; subcontrol-position: bottom right;
            width: 17px; height: 11px; margin: 0 2px 1px 0;
            border: none; background: transparent;
        }}
        QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
        QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
            background: {c['hover_subtle']}; border-radius: 4px;
        }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
            image: url({up}); width: 9px; height: 9px;
        }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
            image: url({down}); width: 9px; height: 9px;
        }}
        """


def _combo_rules(c) -> str:
    """*Everything* QComboBox — the box, the drop-down and the chevron — or "".

    This has to be all-or-nothing, and that's subtler than it looks. Styling the
    box is what makes Qt stop drawing the chevron, so a sheet that styles
    `QComboBox` in a shared input rule and then omits `::down-arrow` (because the
    arrow render failed) leaves flat text fields with no affordance that they
    open at all. The escape hatch only works if the box rule sits inside the same
    conditional as the arrow rule — which is why QComboBox is deliberately NOT in
    the QLineEdit rule above.

    That was live here until Ankisstant's port grew an offline test for it.
    """
    arrows = _spin_arrows(c["text_muted"])
    if arrows is None:
        return ""
    return f"""
        QComboBox {{
            background-color: {c['surface']};
            border: 1px solid {c['grey_mid']};
            border-radius: 8px; padding: 4px 7px; color: {c['text']};
        }}
        QComboBox:focus {{ border: 2px solid {c['blue_bright']}; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: center right;
            width: 18px; border: none; background: transparent;
        }}
        QComboBox::down-arrow {{ image: url({arrows[1]}); width: 10px; height: 10px; }}
        QComboBox QAbstractItemView {{
            background-color: {c['surface']}; color: {c['text']};
            selection-background-color: {c['selection_bg']};
            selection-color: {c['text']};
            border: 1px solid {c['grey_mid']};
        }}
        """


def qt_stylesheet() -> str:
    """A Qt stylesheet for AnkiBlitz's own dialogs, from SynapsePro's palette.

    Modelled on how SynapsePro styles its native dialogs (its
    ``configuration.py::_build_style``) so the two windows sit together: same
    card surfaces, same accent buttons, same input radii.

    Returns "" when there's nothing to theme, and the dialog keeps inheriting
    Anki's own look exactly as before.

    **Checkbox and radio indicators are deliberately left alone.** Restyling them
    is where this kind of sheet usually goes wrong — a mis-specified indicator
    reads as permanently unchecked, and a settings window you can't read the
    state of is worse than one that doesn't match.

    Spin boxes and combos are the other side of the same coin: styling the box at
    all makes Qt stop drawing its sub-controls, so their arrows have to be
    supplied here or they vanish. See ``_spinbox_rules``.
    """
    if not get_section("synapse").get("theme_settings", True):
        return ""
    pal = tokens()
    if not pal:
        return ""
    # Per-token fallbacks rather than pal[key]. A single missing token — an older
    # SynapsePro, a renamed key upstream — would otherwise take the whole
    # stylesheet down to "" and silently un-theme the window.
    c = _WithFallbacks(pal, _QSS_FALLBACKS)
    try:
        fam = font_family("")
        font_line = f"font-family: {fam};" if fam else ""
        return f"""
        QDialog {{ background-color: {c['bg']}; color: {c['text']}; {font_line} }}
        QWidget {{ color: {c['text']}; }}
        QLabel {{ color: {c['text']}; background: transparent; }}

        QTabWidget::pane {{
            background-color: {c['surface']};
            border: 1px solid {c['grey_light']};
            border-radius: 10px;
        }}
        QTabBar::tab {{
            background: transparent; color: {c['text_muted']};
            padding: 6px 12px; margin-right: 2px;
            border-top-left-radius: 8px; border-top-right-radius: 8px;
        }}
        QTabBar::tab:hover {{ color: {c['text']}; background: {c['hover_subtle']}; }}
        QTabBar::tab:selected {{
            color: {c['text']}; background: {c['surface']};
            border-bottom: 2px solid {c['blue_accent']};
        }}

        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}

        QLineEdit, QPlainTextEdit, QTextEdit {{
            background-color: {c['surface']};
            border: 1px solid {c['grey_mid']};
            border-radius: 8px; padding: 4px 7px; color: {c['text']};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 2px solid {c['blue_bright']};
        }}
        {_spinbox_rules(c)}
        {_combo_rules(c)}

        QListWidget {{
            background-color: {c['surface']};
            border: 1px solid {c['grey_light']};
            border-radius: 8px; color: {c['text']};
        }}
        QListWidget::item {{ padding: 5px 7px; }}
        QListWidget::item:selected {{
            background-color: {c['selection_bg']}; color: {c['text']};
        }}

        QPushButton {{
            background-color: {c['grey_light']}; color: {c['text']};
            border: none; border-radius: 8px; padding: 6px 14px; font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {c['grey_mid']}; }}
        QPushButton:disabled {{ background-color: {c['grey_light']};
            color: {c['text_faint']}; }}
        QDialogButtonBox QPushButton {{
            background-color: {c['blue']}; color: #ffffff; border: {c['blue_border']};
            min-width: 76px;
        }}
        QDialogButtonBox QPushButton:hover {{ background-color: {c['blue_hover']}; }}
        QDialogButtonBox QPushButton:pressed {{ background-color: {c['blue_pressed']}; }}

        QGroupBox {{ border: 1px solid {c['grey_light']}; border-radius: 10px;
            margin-top: 8px; padding-top: 8px; }}
        QGroupBox::title {{ color: {c['text_muted']}; subcontrol-origin: margin;
            left: 10px; padding: 0 4px; }}
        """
    except Exception:
        return ""


# ----- Music: SynapsePro's player wins -----

def music_deferred() -> bool:
    """True when SynapsePro's player should be the only one on screen.

    It ships a background music player of its own, so running both means two
    players fighting over one pair of ears. AnkiBlitz's steps aside — the feature
    isn't removed, just hidden, and it comes straight back if SynapsePro goes
    away or ``defer_music`` is turned off.
    """
    if not get_section("synapse").get("defer_music", True):
        return False
    return synapse_available()


def music_available() -> bool:
    """Whether to show AnkiBlitz's music player — enabled AND not deferred.

    For the call sites that already tested ``music.enabled`` themselves.
    """
    return get_section("music").get("enabled", False) and not music_deferred()


# ----- Pomodoro: AnkiBlitz's wins, but only the user can say so -----

def synapse_pomodoro_on() -> bool:
    """True when SynapsePro's own Pomodoro timer is also switched on.

    Its settings aren't in Anki's add-on config — they're a live ``addon_settings``
    dict on the package module, backed by its own ``addon_settings.json``. Read
    the live dict so this reflects a mid-session change.

    Read-only, deliberately. AnkiBlitz never writes into another add-on's config
    — it points the clash out and opens SynapsePro's settings; flipping the
    switch is the user's call.
    """
    pkg = package_name()
    if not pkg:
        return False
    try:
        root = importlib.import_module(pkg)
        settings = getattr(root, "addon_settings", None)
        if not isinstance(settings, dict):
            return False
        return bool(settings.get("pomodoro_enabled", True))
    except Exception:
        return False
