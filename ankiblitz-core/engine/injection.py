"""The ONE reviewer injection point for AnkiBlitz Core.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle into the reviewer webview. Python then pushes the per-card payload — only
the paused-launch flag — with ``FocusSuite.onCard(...)`` and drives the Blitz
progress bar with ``setProgress``. All DOM, timing and animation live in the JS.

``push_progress`` falls through to ``sprint.ambient_payload()`` when no Blitz is
running, so an ordinary review session still gets a (dimmed) bar filling against
the whole due pile.

This is the Core build: it has no auto-reveal timer and no progressive reveal
(those ship as the separate aSFM and Progressive Word Reveal add-ons), so the JS
owns just the progress bar and the paused-launch engagement hold.

Bridge messages (pycmd) use the ``focus:`` namespace:
  - ``focus:timeup``  — a time-mode Blitz reached its deadline.
  - ``focus:engaged`` — first interaction on a paused launch; start the clock.
"""

import json
import os

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer

from ..config import PACKAGE, get_section
from . import forecast, session, topbar

PYCMD_PREFIX = "focus:"

# Cache-bust both files on their own mtime. Anki's webview caches add-on assets
# hard, and a restart doesn't clear it — so an edit to the CSS could land while
# the JS was still the old one (or the reverse), which shows up as a bar that
# renders into a layout the stylesheet doesn't know about. The version has to
# come off the file, not the add-on version, or editing during development
# reintroduces exactly that.
_WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")


def _stamp(name: str) -> str:
    try:
        return str(int(os.path.getmtime(os.path.join(_WEB_DIR, name))))
    except Exception:
        return "0"


_CSS_HREF = f"/_addons/{PACKAGE}/web/focus_suite.css?v={_stamp('focus_suite.css')}"
_JS_SRC = f"/_addons/{PACKAGE}/web/focus_suite.js?v={_stamp('focus_suite.js')}"

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

def _tracker():
    """The live tracker: the Blitz if one is running, else the ambient one.

    Arms the ambient tracker if it isn't up yet. The first card's thinking
    window opens before anything has been graded, so leaving the arming to
    push_progress would lose exactly one band at the start of every session.
    """
    s = session.get_active()
    if s is not None and not s.completed:
        return s
    from . import sprint  # lazy: sprint imports injection at module load
    try:
        sprint._maybe_arm_ambient()
    except Exception:
        return None
    return session.get_ambient()


def _on_show_question(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    # Open this card's thinking window — question up, answer not yet shown.
    t = _tracker()
    if t is not None:
        t.note_question_shown()
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
    # Close the thinking window: everything from here to the grade press is the
    # answer side, which no band is charged for.
    t = _tracker()
    if t is not None:
        t.note_answer_shown()
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

def _estimate_fields(s, cfg: dict, hide_acc: bool, remaining=None) -> dict:
    """The grade split and the time estimate, for either tracker.

    ``remaining`` is passed (the live due count) by the ambient bar, whose
    estimate is the whole pile; leave it None for a Blitz and the estimate
    covers what's left of its target. The Blitz's target is in the counter's
    unit, so in ``answers`` mode it already counts the repeats and isn't
    charged for them again.

    Split colours are an accuracy display, so the anti-pressure switch takes
    them with everything else. The estimate isn't: it says how long you'll be
    sitting there, not how well you're doing, and the Again rate only ever
    reaches it as arithmetic you don't see.
    """
    split = bool(cfg.get("split_bar_by_grade", True)) and not hide_acc
    out = {
        "overlayStats": bool(cfg.get("overlay_stats_on_bar", True)),
        "splitBar": split,
        "doneGood": s.done_good,
        "doneAgain": s.done_again,
        # One band per answer, in order, weighted by thinking time. Only shipped
        # when the split is actually being drawn — it is the largest thing in
        # this payload and it goes out on every card.
        "segs": s.segment_weights() if split else [],
        "showEta": bool(cfg.get("show_eta", True)),
        "showPace": bool(cfg.get("show_pace", False)),
        "etaSeconds": None,
        "projCards": None,
        "perMin": None,
    }
    # The estimate prices what's left in the pile off your own history — see
    # forecast.py. It has a number from the first card and doesn't need the
    # pile to be visibly shrinking: learning cards waiting on a step timer are
    # charged for even while Anki's counts leave them out.
    try:
        pl = forecast.pile()
        spp = forecast.seconds_per_press(s)
    except Exception:
        pl, spp = None, None
    if not pl or not spp:
        return out
    unique = getattr(s, "count_mode", "unique") == "unique"
    per_unit = pl["per_card"] if unique else 1.0
    out["perMin"] = round(60.0 / (spp * per_unit), 1)

    if getattr(s, "mode", None) == session.MODE_TIME:
        # Time mode runs the estimate backwards: the minutes are fixed, so what
        # you don't know is how much of the pile they'll buy.
        left = s.remaining_seconds()
        out["projCards"] = int(left / (spp * per_unit)) if left > 0 else None
        return out

    if remaining is None:
        # A Blitz: what's left of its target, in the counter's unit. It can't
        # cost more than the whole pile does.
        left = max(0, int(getattr(s, "target_cards", 0)) - s.cards_done)
        presses = min(left * per_unit, pl["presses"]) if left else 0.0
    else:
        presses = pl["presses"]
    out["etaSeconds"] = int(presses * spp) if presses > 0 else None
    return out


def push_progress() -> None:
    s = session.get_active()
    if s is None:
        # No Blitz — fall back to the ambient "whole due pile" bar, if one is
        # armed for this ordinary review session.
        from . import sprint  # lazy: sprint imports injection at module load
        ambient = sprint.ambient_payload()
        if ambient:
            _eval(f"window.FocusSuite && FocusSuite.setProgress({json.dumps(ambient)});")
            topbar.claim()
        else:
            clear_progress()
        return
    cfg = get_section("sprint")
    # The anti-pressure master switch hides every accuracy / streak / again figure.
    hide_acc = bool(cfg.get("hide_all_accuracy_stats", True))
    payload = {}
    payload.update(_estimate_fields(s, cfg, hide_acc))
    payload.update({
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
    })
    _eval(f"window.FocusSuite && FocusSuite.setProgress({json.dumps(payload)});")
    topbar.claim()


def clear_progress() -> None:
    _eval("window.FocusSuite && FocusSuite.clearProgress();")
    topbar.release()


def pause_auto_reveal() -> None:
    """No-op in the Core build (kept so the Pomodoro break code can call it
    unconditionally). The auto-reveal timer lives in the separate aSFM add-on."""
    return


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    topbar.register()
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
