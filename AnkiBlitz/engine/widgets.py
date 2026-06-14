"""On-screen AnkiBlitz widgets for the deck browser and deck overview.

A compact **rail** is pinned to the right of the screen (next to the deck list /
overview), with quick-launch buttons that start a Blitz *immediately* from the
saved Blitz defaults — one per mode (timer / cards / fraction) — plus a Pomodoro
quick-launch, a Daily Quick Start toggle, and a settings (⚙) button.

Clicks travel back through the main webview's ``pycmd`` bridge, handled here by a
``focus:``-namespaced ``webview_did_receive_js_message`` handler (gui_hooks chain
multiple handlers, so this coexists with injection.py's reviewer bridge). All
handlers are best-effort and never raise into the host screen.
"""

from aqt import gui_hooks, mw

from ..config import get_section, suite_enabled
from . import sprint, pomodoro

PYCMD_PREFIX = "focus:"

_STYLE = """
<style>
.fs-rail{position:fixed;top:64px;right:14px;width:176px;z-index:50;
  border:1px solid var(--border, rgba(127,127,127,.35));
  background:var(--canvas-elevated, rgba(48,48,48,.97));
  border-radius:12px;padding:12px;color:var(--fg, inherit);
  font-size:13px;box-shadow:0 2px 12px rgba(0,0,0,.28);text-align:left;}
.fs-rail .fs-hd{display:flex;align-items:center;justify-content:space-between;}
.fs-rail .fs-title{font-weight:600;font-size:13px;}
.fs-rail .fs-gear{cursor:pointer;opacity:.55;text-decoration:none;
  color:var(--fg, inherit)!important;font-size:15px;}
.fs-rail .fs-gear:hover{opacity:1;}
.fs-rail .fs-due{font-size:11px;opacity:.6;margin:1px 0 6px;}
.fs-rail .fs-lab{font-size:10px;text-transform:uppercase;letter-spacing:.05em;
  opacity:.5;margin:9px 0 2px;}
.fs-rail .fs-b{display:block;width:100%;box-sizing:border-box;text-align:left;
  padding:7px 10px;margin:4px 0;border-radius:7px;
  border:1px solid var(--border, rgba(127,127,127,.4));
  background:var(--button-bg, rgba(127,127,127,.14));
  color:var(--fg, inherit)!important;text-decoration:none;cursor:pointer;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fs-rail .fs-b:hover{filter:brightness(1.13);}
.fs-rail .fs-b.fs-primary{background:#3b82f6;border-color:#3b82f6;color:#fff!important;}
.fs-rail .fs-b.fs-tom{background:#e0533d;border-color:#e0533d;color:#fff!important;}
.fs-rail .fs-toggle{display:block;margin-top:9px;font-size:11px;cursor:pointer;
  text-align:center;opacity:.85;text-decoration:none;color:var(--fg, inherit)!important;}
.fs-rail .fs-on{color:#22c55e;font-weight:600;}
.fs-rail .fs-off{opacity:.6;font-weight:600;}
</style>
"""


def _btn(label, action, cls="") -> str:
    return (f'<a class="fs-b {cls}" href="#" '
            f"onclick=\"pycmd('{PYCMD_PREFIX}{action}'); return false;\">{label}</a>")


def widget_presets() -> list:
    """The rail's quick-launch buttons. Uses the user's configured presets, or
    falls back to the three Blitz defaults (time / cards / fraction) when unset."""
    raw = get_section("home_widget").get("presets", [])
    cleaned = []
    if isinstance(raw, list):
        for p in raw:
            if isinstance(p, dict) and p.get("mode") in ("time", "cards", "fraction"):
                cleaned.append({"mode": p["mode"], "value": int(p.get("value", 0) or 0)})
    if cleaned:
        return cleaned
    sp = get_section("sprint")
    picks = sp.get("fraction_quick_picks", [2, 3])
    return [
        {"mode": "time", "value": int(sp.get("default_time_minutes", 15))},
        {"mode": "cards", "value": int(sp.get("default_target", 50))},
        {"mode": "fraction", "value": int(picks[0]) if picks else 2},
    ]


def _preset_label(p: dict) -> str:
    mode, value = p["mode"], p["value"]
    if mode == "time":
        return f"⏱ {max(1, value)} min"
    if mode == "fraction":
        return f"➗ 1 / {max(2, value)} of due"
    return f"🎴 {max(1, value)} cards"


def _pomo_label() -> str:
    po = get_section("pomodoro")
    mode = po.get("work_mode", "time")
    t = int(po.get("work_target", 25))
    if mode == "time":
        return f"🍅 Pomodoro · {t} min"
    if mode == "fraction":
        return f"🍅 Pomodoro · 1/{max(2, t)}"
    return f"🍅 Pomodoro · {t} cards"


def _rail(due: int) -> str:
    blitz_btns = ""
    for i, p in enumerate(widget_presets()):
        cls = "fs-primary" if i == 0 else ""
        blitz_btns += _btn(_preset_label(p), f"blitz-{i}", cls)
    # Blitz the entire due pile (finishes when your dues are cleared).
    blitz_btns += _btn(f"✅ Finish all {due} due", "blitz-all")

    pomo_block = ""
    if get_section("pomodoro").get("enabled", True):
        pomo_block = '<div class="fs-lab">Pomodoro</div>' + _btn(
            _pomo_label(), "pomodoro", "fs-tom")

    music_block = ""
    mu = get_section("music")
    if mu.get("enabled", False) and mu.get("show_on_home", True):
        music_block = '<div class="fs-lab">Music</div>' + _btn(
            "♪ Music player", "music")

    gear = (f'<a class="fs-gear" href="#" '
            f"onclick=\"pycmd('{PYCMD_PREFIX}settings'); return false;\">⚙</a>")

    return (
        f'{_STYLE}<div class="fs-rail">'
        f'<div class="fs-hd"><span class="fs-title">⚡ AnkiBlitz</span>{gear}</div>'
        f'<div class="fs-due">{due} card{"s" if due != 1 else ""} due</div>'
        f'<div class="fs-lab">Blitz</div>{blitz_btns}'
        f"{pomo_block}"
        f"{music_block}"
        f"</div>"
    )


# ----- Render hooks -----

def _on_deck_browser(deck_browser, content) -> None:
    try:
        if not suite_enabled() or not get_section("home_widget").get("enabled", True):
            return
        content.tree += _rail(sprint._due_total())
    except Exception:
        pass


def _on_overview(overview, content) -> None:
    try:
        if not suite_enabled() or not get_section("home_widget").get("show_on_overview", True):
            return
        content.table += _rail(sprint._due_total())
    except Exception:
        pass


# ----- Bridge: JS -> Python -----

def _open_settings() -> None:
    from ..settings import open_settings  # lazy: avoid import cycle at load
    open_settings()


def _on_js_message(handled, message, context, *args, **kwargs):
    if not isinstance(message, str) or not message.startswith(PYCMD_PREFIX):
        return handled
    action = message[len(PYCMD_PREFIX):]
    if action.startswith("blitz-"):
        try:
            idx = int(action.split("-", 1)[1])
        except ValueError:
            return (True, None)
        presets = widget_presets()
        if 0 <= idx < len(presets):
            p = presets[idx]
            sprint.start_blitz_now(p["mode"], p["value"])
        return (True, None)
    if action == "blitz-all":
        sprint.start_blitz_all_due()
        return (True, None)
    if action == "pomodoro":
        pomodoro.start_pomodoro(use_defaults=True)
        return (True, None)
    if action == "settings":
        _open_settings()
        return (True, None)
    if action == "music":
        from . import music  # lazy: keep widgets standalone-safe
        music.toggle_home_box()
        return (True, None)
    return handled


def _refresh_home() -> None:
    # The deck browser's first render can happen before this hook is registered
    # at profile open, so the rail wouldn't appear until a later re-render. Force
    # one refresh so it shows on initial load.
    try:
        if mw.state == "deckBrowser":
            mw.deckBrowser.refresh()
    except Exception:
        pass


def register() -> None:
    gui_hooks.deck_browser_will_render_content.append(_on_deck_browser)
    gui_hooks.overview_will_render_content.append(_on_overview)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
    mw.progress.single_shot(150, _refresh_home, False)
