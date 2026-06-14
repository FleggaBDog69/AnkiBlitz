"""The ONE reviewer injection point for AnkiBlitz Core.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle into the reviewer webview. Python then pushes the per-card payload — only
the paused-launch flag — with ``FocusSuite.onCard(...)`` and drives the Blitz
progress bar with ``setProgress``. All DOM, timing and animation live in the JS.

This is the Core build: it has no auto-reveal timer and no progressive reveal
(those ship as the separate aSFM and Progressive Word Reveal add-ons), so the JS
owns just the progress bar and the paused-launch engagement hold.

Bridge messages (pycmd) use the ``focus:`` namespace:
  - ``focus:timeup``  — a time-mode Blitz reached its deadline.
  - ``focus:engaged`` — first interaction on a paused launch; start the clock.
"""

import json

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer

from ..config import PACKAGE, get_section
from . import session

PYCMD_PREFIX = "focus:"

_CSS_HREF = f"/_addons/{PACKAGE}/web/focus_suite.css"
_JS_SRC = f"/_addons/{PACKAGE}/web/focus_suite.js"

# The external bundle loads async, so the first call can arrive before it is
# ready. This inline shim buffers calls; the real bundle flushes them on load.
_SHIM = (
    "<script>(function(){if(window.FocusSuite)return;var q=[];var s={_queue:q};"
    "['onCard','setProgress','clearProgress'].forEach(function(m){"
    "s[m]=function(){q.push([m,arguments]);};});window.FocusSuite=s;})();</script>"
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


# ----- The single injection -----

def _on_will_set_content(web_content, context, *args, **kwargs) -> None:
    if isinstance(context, Reviewer):
        web_content.body += _INJECT


# ----- Per-card payload push -----

def _on_show_question(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    payload = {}
    # Paused launch: hold the session clock until the user engages (the JS arms a
    # one-shot click/key listener; see focus:engaged).
    s = session.get_active()
    if s is not None and getattr(s, "paused", False):
        payload["paused"] = True
    _eval(f"window.FocusSuite && FocusSuite.onCard({json.dumps(payload)});")
    push_progress()


def _on_show_answer(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    # Flipping the first card starts the time-mode countdown.
    s = session.get_active()
    if s is not None:
        s.start_clock()
    push_progress()


# ----- Bridge: JS -> Python -----

def _on_js_message(handled, message: str, context, *args, **kwargs):
    if not isinstance(message, str) or not message.startswith(PYCMD_PREFIX):
        return handled
    action = message[len(PYCMD_PREFIX):]
    if action == "timeup":
        from . import sprint  # lazy: sprint imports injection at module load
        sprint.on_time_up()
        return (True, None)
    if action == "engaged":
        # First interaction on a paused launch: start the session clock and
        # re-push so the bar reflects the now-running session.
        s = session.get_active()
        if s is not None:
            s.begin_engagement()
            push_progress()
        return (True, None)
    return handled


# ----- Sprint progress bar -----

def push_progress() -> None:
    s = session.get_active()
    if s is None:
        clear_progress()
        return
    cfg = get_section("sprint")
    # The anti-pressure master switch hides every accuracy / streak / again figure.
    hide_acc = bool(cfg.get("hide_all_accuracy_stats", True))
    payload = {
        "mode": s.mode,
        "cardsDone": s.cards_done,
        "target": s.target_cards,
        "unit": s.unit,
        # Paused launch: freeze the elapsed clock at 0:00 until the user engages.
        "paused": bool(getattr(s, "paused", False)),
        "startedAtMs": s.started_at_ms(),
        "deadlineMs": s.deadline_ms(),
        "targetMs": s.target_ms(),
        "running": s.clock_running() if s.mode == "time" else True,
        "showBar": bool(cfg.get("show_progress_bar", True)),
        "showCounter": bool(cfg.get("show_card_counter", True)),
        "showElapsed": bool(cfg.get("show_elapsed_time", True)),
        # Live in-Blitz stats (each gated by its own toggle; all off when the
        # anti-pressure switch is on).
        "showAccuracy": bool(cfg.get("show_live_accuracy", False)) and not hide_acc,
        "accuracy": round(s.accuracy()),
        "showAgain": bool(cfg.get("show_again_count", False)) and not hide_acc,
        "again": s.again_count,
        "showStreak": bool(cfg.get("show_streak_counter", False)) and not hide_acc,
        "streak": s.current_streak,
        "streakAnim": bool(cfg.get("streak_animations", False)),
    }
    _eval(f"window.FocusSuite && FocusSuite.setProgress({json.dumps(payload)});")


def clear_progress() -> None:
    _eval("window.FocusSuite && FocusSuite.clearProgress();")


def pause_auto_reveal() -> None:
    """No-op in the Core build (kept so the Pomodoro break code can call it
    unconditionally). The auto-reveal timer lives in the separate aSFM add-on."""
    return


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
