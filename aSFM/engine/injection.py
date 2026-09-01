"""The reviewer injection point for aSFM.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle into the reviewer. Python then computes the per-card auto-reveal delay and
pushes it with a single ``ASFM.onCard(...)`` call; the JS owns the timer, the
countdown, and the warning. When the timer expires the JS asks Python to show the
answer (``asfm:reveal``). It NEVER grades the card.

The one message going the other way is ``asfm:autopause:1|0`` — the pause key
held or released the timer.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer
from aqt.sound import av_player
from aqt.utils import tooltip

from ..config import PACKAGE, get_config
from . import adaptive

PYCMD_PREFIX = "asfm:"

# The pause key's sticky state. Held here rather than in the JS so it survives
# the bundle being re-injected (leaving the reviewer and coming back), and is
# pushed out with every card payload. Cleared on profile load, not persisted.
_auto_paused = False


def auto_reveal_paused() -> bool:
    return _auto_paused


_CSS_HREF = f"/_addons/{PACKAGE}/web/asfm.css"
_JS_SRC = f"/_addons/{PACKAGE}/web/asfm.js"

# Warning alert: user_files/alert.mp3 overrides the bundled sounds/alert.mp3.
_DIR = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_ALERT = os.path.join(_DIR, "sounds", "alert.mp3")
_USER_ALERT = os.path.join(_DIR, "user_files", "alert.mp3")


def _play_alert() -> None:
    path = _USER_ALERT if os.path.exists(_USER_ALERT) else _DEFAULT_ALERT
    try:
        av_player.play_file(path)
    except Exception:
        pass


# The external bundle loads async, so the first onCard() eval can arrive before it
# is ready. This inline shim buffers calls; the real bundle flushes them on load.
_SHIM = (
    "<script>(function(){if(window.ASFM)return;var q=[];var s={_queue:q};"
    "['onCard'].forEach(function(m){s[m]=function(){q.push([m,arguments]);};});"
    "window.ASFM=s;})();</script>"
)

_INJECT = (
    f'<link rel="stylesheet" href="{_CSS_HREF}">'
    f"{_SHIM}"
    f'<script src="{_JS_SRC}"></script>'
)


def _eval(js: str) -> None:
    try:
        web = mw.reviewer.web if mw.reviewer else None
        if web:
            web.eval(js)
    except Exception:
        pass


def _deck_excluded(deck_name: str, excluded: list) -> bool:
    if not deck_name:
        return False
    for entry in excluded:
        if entry and (deck_name == entry or deck_name.startswith(entry + "::")):
            return True
    return False


def _excluded(card, cfg: dict) -> bool:
    try:
        nt = card.note_type()
        if nt and nt.get("name") in cfg.get("excluded_note_types", []):
            return True
    except Exception:
        pass
    try:
        deck_name = mw.col.decks.name(card.current_deck_id())
        if _deck_excluded(deck_name, cfg.get("excluded_decks", [])):
            return True
    except Exception:
        pass
    return False


def _pause_block(cfg: dict) -> dict:
    """The pause-key half of every payload.

    It rides on the disabled payloads too: the sticky flag has to reach the JS
    even on a card aSFM isn't timing, or pausing on one card and moving to an
    excluded one would silently drop the hold.

    The key and the "More time" button are gated separately — they apply the
    same hold, but you may well want the button without knowing a key exists,
    or the key without a control sitting over your cards.
    """
    global _auto_paused
    on = bool(cfg.get("enabled", True))
    key_on = on and bool(cfg.get("pause_key_enabled", True))
    button_on = on and bool(cfg.get("more_time_button", True))
    # A hold with nothing left to release it is a stuck card: if both the key and
    # the button have been switched off since you paused, drop the hold rather
    # than showing a badge that names an input you no longer have. Cleared for
    # good, not just hidden — a pause resurrected by re-enabling the key weeks
    # later would be its own surprise.
    if _auto_paused and not (key_on or button_on):
        _auto_paused = False
    return {
        "pauseKey": str(cfg.get("pause_key") or "p").lower(),
        "pauseEnabled": key_on,
        "moreTimeButton": button_on,
        "autoPaused": _auto_paused,
    }


def question_payload(card) -> dict:
    cfg = get_config()
    off = {"enabled": False, **_pause_block(cfg)}
    if not cfg.get("enabled", True) or _excluded(card, cfg):
        return off
    if adaptive.is_new_card(card) and not cfg.get("enable_on_new", True):
        return off
    delay_ms = int(adaptive.reveal_delay_seconds(card, cfg) * 1000)
    return {
        "enabled": True,
        "delayMs": delay_ms,
        "showCountdown": bool(cfg.get("show_countdown", True)),
        "warn": bool(cfg.get("warning_sound", True)),
        "warnPercent": int(cfg.get("warning_at_percent", 75)),
        **_pause_block(cfg),
    }


# ----- hooks -----

def _on_will_set_content(web_content, context, *args, **kwargs) -> None:
    if isinstance(context, Reviewer):
        web_content.body += _INJECT


def _on_show_question(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    _eval(f"window.ASFM && ASFM.onCard({json.dumps(question_payload(card))});")


def _on_show_answer(*args, **kwargs) -> None:
    # Cancel any pending timer/countdown the moment the answer shows (manually or
    # via the timer).
    # The pause block still rides along: the key has to keep working (and the
    # sticky flag has to stay true) while the answer is on screen.
    payload = {"enabled": False, **_pause_block(get_config())}
    _eval(f"window.ASFM && ASFM.onCard({json.dumps(payload)});")


def _on_js_message(handled, message: str, context, *args, **kwargs):
    if not isinstance(message, str) or not message.startswith(PYCMD_PREFIX):
        return handled
    action = message[len(PYCMD_PREFIX):]
    if action == "reveal":
        rv = mw.reviewer
        if rv and rv.card and rv.state == "question":
            rv._showAnswer()
        return (True, None)
    if action == "warn":
        _play_alert()
        return (True, None)
    if action.startswith("autopause:"):
        global _auto_paused
        _auto_paused = action.endswith("1")
        key = str(get_config().get("pause_key") or "p").upper()
        tooltip(
            f"⏸ Auto-reveal paused — press {key} to resume" if _auto_paused
            else "▶ Auto-reveal resumed",
            period=1800,
        )
        return (True, None)
    return handled


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
