"""The AnkiBlitz panel — the ⚡ button in SynapsePro's sidebar opens this.

Everything the deck-list rail used to offer, plus Settings: quick-launch Blitz
presets, finish-all-due, stats, the break journal, the Quick Start toggle, music.
Pomodoro is here too, but it's the one thing that also keeps its own sidebar icon
— it's the button worth pressing without opening anything first.

Built as an HTML page in a ``QWebEngineView`` rather than a Qt dialog on purpose
— it's how SynapsePro presents its own settings and Pomodoro config, so this
lands as part of the same product instead of next to it. ``web/blitz_panel.html``
carries the styling; this module supplies the data and handles the clicks.

The bridge is ``console.log("blitz:<action>")`` intercepted by a QWebEnginePage
subclass — the same one SynapsePro uses, and it avoids a QWebChannel dependency.

Standalone-safe: if WebEngine isn't available the panel falls back to a plain Qt
list of the same actions, and none of this is reachable without SynapsePro
anyway (the button that opens it lives in SynapsePro's strip).
"""

import json
import os

from aqt import mw
from aqt.qt import QDialog, QVBoxLayout, QUrl, QColor, QPushButton, QLabel

from ..config import get_section, save_section
from . import theme_bridge

_HTML = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                     "web", "blitz_panel.html")

_dialog = None      # single live panel; reopened rather than stacked

BRIDGE_PREFIX = "blitz:"


# ----- Payload -----

def _payload() -> dict:
    from . import sprint, stats, widgets, pomodoro

    try:
        due = int(sprint._due_total())
    except Exception:
        due = 0

    presets = []
    try:
        for p in widgets.widget_presets():
            presets.append({
                "label": widgets._preset_label(p).lstrip("⏱➗🎴 ").strip(),
                "sub": _preset_sub(p),
            })
    except Exception:
        pass

    # The Pomodoro row mirrors the sidebar button: an unfinished run from earlier
    # today takes over, so one click picks it up rather than restarting at block 1.
    pomo = {"label": "Start a Pomodoro", "sub": ""}
    try:
        run = pomodoro.resumable_run()
        if run:
            pomo = {"label": "Resume Pomodoro",
                    "sub": pomodoro.resume_summary(run)}
        else:
            po = get_section("pomodoro")
            pomo["sub"] = _pomo_sub(po)
    except Exception:
        pass

    # Blitz cards and Pomodoro blocks are logged separately (by_day vs
    # pomodoro_log), so today's card count is the sum of both.
    cards_today = 0
    sprints = 0
    blocks = 0
    try:
        from datetime import date
        day = stats.load_stats().get("by_day", {}).get(date.today().isoformat(), {})
        cards_today = int(day.get("cards", 0) or 0)
        sprints = int(day.get("sprints", 0) or 0)
    except Exception:
        pass
    try:
        summary = stats.pomodoro_today_summary()
        blocks = int(summary.get("blocks", 0))
        cards_today += int(summary.get("cards", 0))
    except Exception:
        pass

    return {
        "dark": _is_dark(),
        "tokens": _css_tokens(),
        "due": due,
        "presets": presets,
        "pomodoro": pomo,
        "stats": [
            {"value": cards_today, "label": "cards"},
            {"value": sprints, "label": "blitzes"},
            {"value": blocks, "label": "pomodoro blocks"},
        ],
        "quickStart": bool(get_section("quick_start").get("enabled", True)),
        "music": theme_bridge.music_available(),
    }


def _preset_sub(p: dict) -> str:
    return {"time": "Timed run", "cards": "Card count",
            "fraction": "A share of what's due"}.get(p.get("mode"), "")


def _pomo_sub(po: dict) -> str:
    mode = po.get("work_mode", "time")
    t = int(po.get("work_target", 25))
    if mode == "time":
        return f"{t} min blocks"
    if mode == "fraction":
        return f"1/{max(2, t)} of due per block"
    return f"{t} cards per block"


def _is_dark() -> bool:
    try:
        from aqt.theme import theme_manager
        return bool(theme_manager.night_mode)
    except Exception:
        try:
            return bool(mw.pm.night_mode())
        except Exception:
            return False


def _css_tokens() -> dict:
    """SynapsePro's palette mapped onto the page's own token names.

    The page ships sensible defaults, so an empty dict here just leaves it
    looking like SynapsePro's stock light/dark styling.
    """
    pal = theme_bridge.tokens()
    if not pal:
        return {}
    out = {}
    for css, token in (("accent", "blue_accent"), ("bg", "bg"),
                       ("card", "surface"), ("text", "text"),
                       ("muted", "text_muted"), ("field-bg", "grey_light"),
                       ("switch-off", "grey_mid")):
        v = pal.get(token)
        if isinstance(v, str) and v:
            out[css] = v
    return out


# ----- Actions -----

def _handle(action: str) -> None:
    from . import sprint, stats, pomodoro, widgets

    if action == "ready":
        return
    if action == "blitz-all":
        _close()
        sprint.start_blitz_all_due()
        return
    if action.startswith("blitz-"):
        rest = action.split("-", 1)[1]
        if rest == "dialog":
            _close()
            sprint.start_blitz_dialog()
            return
        try:
            idx = int(rest)
        except ValueError:
            return
        presets = widgets.widget_presets()
        if 0 <= idx < len(presets):
            _close()
            p = presets[idx]
            sprint.start_blitz_now(p["mode"], p["value"])
        return
    if action == "pomodoro":
        _close()
        pomodoro.start_pomodoro(use_defaults=True)
        return
    if action == "pomodoro-dialog":
        _close()
        pomodoro.start_pomodoro()
        return
    if action == "stats":
        _close()
        stats.open_stats_window()
        return
    if action == "journal":
        _close()
        pomodoro.open_journal_viewer()
        return
    if action == "settings":
        from ..settings import open_settings
        _close()
        open_settings()
        return
    if action == "music":
        from . import music
        _close()
        music.toggle_dock()
        return
    if action.startswith("quickstart:"):
        # Toggled in place — the panel stays open, so no _close() here.
        qs = get_section("quick_start")
        qs["enabled"] = action.endswith("1")
        save_section("quick_start", qs)
        return


def _close() -> None:
    global _dialog
    dlg, _dialog = _dialog, None
    try:
        if dlg is not None:
            dlg.close()
    except Exception:
        pass


# ----- The window -----

def _webengine():
    try:
        from aqt.qt import QWebEngineView, QWebEnginePage
        return QWebEngineView, QWebEnginePage
    except Exception:
        pass
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEnginePage
        return QWebEngineView, QWebEnginePage
    except Exception:
        return None, None


def _build_web_panel(parent):
    View, Page = _webengine()
    if View is None or not os.path.exists(_HTML):
        return None

    class _Page(Page):
        """console.log is the bridge — same trick SynapsePro's settings page uses."""

        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            try:
                if isinstance(message, str) and message.startswith(BRIDGE_PREFIX):
                    _handle(message[len(BRIDGE_PREFIX):])
                    return
            except Exception:
                pass

    dlg = QDialog(parent)
    dlg.setWindowTitle("AnkiBlitz")
    dlg.resize(460, 620)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(0, 0, 0, 0)

    view = View(dlg)
    page = _Page(view)
    view.setPage(page)
    # Paint the theme background before the page loads, or the view flashes
    # white in dark mode — the same problem SynapsePro solves this way.
    try:
        page.setBackgroundColor(QColor("#1c1c1e") if _is_dark() else QColor("#f5f5f7"))
    except Exception:
        pass

    def _loaded(ok: bool) -> None:
        if not ok:
            return
        try:
            view.page().runJavaScript(
                f"window.__blitz_init && __blitz_init({json.dumps(_payload())});")
        except Exception:
            pass

    view.loadFinished.connect(_loaded)
    view.load(QUrl.fromLocalFile(_HTML))
    lay.addWidget(view)
    dlg._ab_view = view          # keep the view alive with the dialog
    return dlg


def _build_fallback_panel(parent):
    """Plain buttons, for a build without WebEngine. Same actions, no styling."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("AnkiBlitz")
    lay = QVBoxLayout(dlg)
    p = _payload()

    head = QLabel(f"<b>AnkiBlitz</b> — {p['due']} due")
    lay.addWidget(head)
    rows = [(pr["label"], f"blitz-{i}") for i, pr in enumerate(p["presets"])]
    if p["due"]:
        rows.append((f"Finish all {p['due']} due", "blitz-all"))
    rows += [("Start Blitz…", "blitz-dialog"),
             (p["pomodoro"]["label"], "pomodoro"),
             ("Start Pomodoro…", "pomodoro-dialog"),
             ("Blitz stats", "stats"),
             ("Break journal", "journal")]
    if p["music"]:
        rows.append(("Music player", "music"))
    rows.append(("Settings…", "settings"))
    for label, action in rows:
        b = QPushButton(label)
        b.clicked.connect(lambda _c=False, a=action: _handle(a))
        lay.addWidget(b)
    return dlg


def open_panel() -> None:
    global _dialog
    if _dialog is not None:
        try:
            _dialog.raise_()
            _dialog.activateWindow()
            return
        except Exception:
            _dialog = None

    dlg = _build_web_panel(mw) or _build_fallback_panel(mw)
    _dialog = dlg

    def _forget() -> None:
        global _dialog
        _dialog = None

    try:
        dlg.finished.connect(lambda _r=0: _forget())
    except Exception:
        pass
    dlg.show()
