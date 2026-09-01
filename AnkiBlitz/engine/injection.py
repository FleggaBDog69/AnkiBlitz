"""The ONE reviewer injection point.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle into the reviewer webview. After that, Python never touches the DOM
directly: it computes per-card payloads and pushes them with a single
``FocusSuite.onCard(...)`` call (plus ``setProgress`` for the sprint bar). All
DOM, timing, and animation live in the JS bundle.

Bridge messages (pycmd) use the ``focus:`` namespace:
  - ``focus:reveal`` — the auto-reveal timer expired; show the answer.
  - ``focus:autopause:1|0`` — the pause key held / released the auto-reveal timer.
  - ``focus:stopaudio`` — the word reveal was skipped; stop the card's audio.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer
from aqt.sound import av_player
from aqt.utils import tooltip

from ..config import PACKAGE, get_section
from . import reveal, session

PYCMD_PREFIX = "focus:"

_CSS_HREF = f"/_addons/{PACKAGE}/web/focus_suite.css"
_JS_SRC = f"/_addons/{PACKAGE}/web/focus_suite.js"

# Warning alert: user_files/alert.mp3 overrides the bundled sounds/alert.mp3.
_SUITE_DIR = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_ALERT = os.path.join(_SUITE_DIR, "sounds", "alert.mp3")
_USER_ALERT = os.path.join(_SUITE_DIR, "user_files", "alert.mp3")


# The pause key's sticky state. Held here rather than in the JS so it survives
# the bundle being re-injected (leaving the reviewer and coming back), and is
# pushed out with every card payload. Cleared on profile load, not persisted.
_auto_paused = False


def auto_reveal_paused() -> bool:
    return _auto_paused


def _sticky_pause(payload: dict) -> bool:
    """The sticky pause flag for this card, dropping a hold that can no longer be
    released.

    A hold needs an input to lift it: the pause key or the "More time" button. If
    both have been switched off since you paused, keeping the flag would strand
    the card behind a badge naming an input you no longer have. Cleared for good
    rather than hidden — a pause resurrected by re-enabling the key weeks later
    would be its own surprise.
    """
    global _auto_paused
    if _auto_paused:
        ar = payload.get("autoReveal") or {}
        if not (ar.get("pauseEnabled") or ar.get("moreTimeButton")):
            _auto_paused = False
    return _auto_paused


def _play_alert() -> None:
    path = _USER_ALERT if os.path.exists(_USER_ALERT) else _DEFAULT_ALERT
    try:
        av_player.play_file(path)
    except Exception:
        pass

# The external bundle loads async, so the first onCard() eval can arrive before
# it is ready. This inline shim installs a stub that buffers calls; the real
# bundle flushes the queue once loaded.
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


def _inject_html() -> str:
    """The bundle, with SynapsePro's palette in front of it when it's installed.

    The stylesheet is a static file, so it can't interpolate colours itself — the
    vars have to arrive as an inline block. It's built per injection rather than
    at import so switching SynapsePro's theme takes effect on the next card.
    """
    from . import theme_bridge
    try:
        return theme_bridge.css_vars() + _INJECT
    except Exception:
        return _INJECT


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
        web_content.body += _inject_html()


# ----- Per-card payload push -----

def _on_show_question(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    payload = reveal.question_payload(card)
    payload["autoPaused"] = _sticky_pause(payload)
    # Paused launch: hold the auto-reveal and the session clock until the user
    # engages (the JS arms a one-shot click/key listener; see focus:engaged).
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
    payload = reveal.answer_payload(card)
    payload["autoPaused"] = _sticky_pause(payload)
    _eval(f"window.FocusSuite && FocusSuite.onCard({json.dumps(payload)});")
    push_progress()


# ----- Bridge: JS -> Python -----

def _on_js_message(handled, message: str, context, *args, **kwargs):
    if not isinstance(message, str) or not message.startswith(PYCMD_PREFIX):
        return handled
    action = message[len(PYCMD_PREFIX):]
    if action == "reveal":
        rv = mw.reviewer
        if rv and rv.card and rv.state == "question":
            rv._showAnswer()
        return (True, None)
    if action == "stopaudio":
        # The word reveal was skipped: cut whatever the card is still saying
        # (and drop the rest of its queue, so the next tag doesn't start up).
        try:
            av_player.stop_and_clear_queue()
        except Exception:
            pass
        return (True, None)
    if action == "warn":
        _play_alert()
        return (True, None)
    if action == "timeup":
        from . import sprint  # lazy: sprint imports injection at module load
        sprint.on_time_up()
        return (True, None)
    if action.startswith("autopause:"):
        global _auto_paused
        _auto_paused = action.endswith("1")
        key = str(get_section("speed_focus").get("pause_key") or "p").upper()
        tooltip(
            f"⏸ Speed Focus paused — press {key} to resume" if _auto_paused
            else "▶ Speed Focus resumed",
            period=1800,
        )
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
        # No Blitz — fall back to the ambient "whole due pile" bar, if one is
        # armed for this ordinary review session.
        from . import sprint  # lazy: sprint imports injection at module load
        ambient = sprint.ambient_payload()
        if ambient:
            _eval(f"window.FocusSuite && FocusSuite.setProgress({json.dumps(ambient)});")
        else:
            clear_progress()
        return
    from ..config import get_section
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
        "ambient": False,
    }
    _eval(f"window.FocusSuite && FocusSuite.setProgress({json.dumps(payload)});")


def clear_progress() -> None:
    _eval("window.FocusSuite && FocusSuite.clearProgress();")


def pause_auto_reveal() -> None:
    """Stop any pending auto-reveal / warning timers on the current card (used
    when a Pomodoro break takes over so Speed Focus doesn't fire behind it)."""
    _eval("window.FocusSuite && FocusSuite.pauseAuto && FocusSuite.pauseAuto();")


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
