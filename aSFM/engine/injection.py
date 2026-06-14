"""The reviewer injection point for aSFM.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle into the reviewer. Python then computes the per-card auto-reveal delay and
pushes it with a single ``ASFM.onCard(...)`` call; the JS owns the timer, the
countdown, and the warning. When the timer expires the JS asks Python to show the
answer (``asfm:reveal``). It NEVER grades the card.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer
from aqt.sound import av_player

from ..config import PACKAGE, get_config
from . import adaptive

PYCMD_PREFIX = "asfm:"

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


def question_payload(card) -> dict:
    cfg = get_config()
    if not cfg.get("enabled", True) or _excluded(card, cfg):
        return {"enabled": False}
    if adaptive.is_new_card(card) and not cfg.get("enable_on_new", True):
        return {"enabled": False}
    delay_ms = int(adaptive.reveal_delay_seconds(card, cfg) * 1000)
    return {
        "enabled": True,
        "delayMs": delay_ms,
        "showCountdown": bool(cfg.get("show_countdown", True)),
        "warn": bool(cfg.get("warning_sound", True)),
        "warnPercent": int(cfg.get("warning_at_percent", 75)),
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
    _eval("window.ASFM && ASFM.onCard({enabled:false});")


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
    return handled


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
