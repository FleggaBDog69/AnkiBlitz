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
import shutil

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer
from aqt.sound import av_player
from aqt.utils import tooltip

from ..config import PACKAGE, get_section
from . import forecast, pace, reveal, session, topbar

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

# Warning alert: an alert.* in user_files overrides the bundled sounds/alert.*
_SUITE_DIR = os.path.dirname(os.path.dirname(__file__))


# The pause key's sticky state. Held here rather than in the JS so it survives
# the bundle being re-injected (leaving the reviewer and coming back), and is
# pushed out with every card payload. Cleared on profile close, not persisted.
_auto_paused = False

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


def _resume_hint() -> str:
    """How to lift the hold, naming only inputs that are switched on — the
    same wording as the on-card badge (resumeHint in focus_suite.js)."""
    sf = get_section("speed_focus")
    key = str(sf.get("pause_key") or "p").upper()
    key_on = bool(sf.get("pause_key_enabled", True))
    button_on = bool(sf.get("more_time_button", True))
    if button_on and key_on:
        return f"click the badge or press {key} to resume"
    if button_on:
        return "click the badge to resume"
    return f"press {key} to resume"


def clear_pause() -> None:
    """Drop the sticky hold (profile closing), so the next profile doesn't
    open on a paused timer it never asked for."""
    global _auto_paused
    _auto_paused = False


# Formats the reviewer webview can decode, best first. Anki ships the
# open-codec QtWebEngine build, which carries NO mp3 decoder (verified: no
# mpegaudiodec/mp3float symbol in QtWebEngineCore, while vorbis/opus/flac/pcm
# are all present). An .mp3 handed to <audio> therefore fails to decode, which
# is why the bundled alert is also shipped as .flac.
_WEB_AUDIO_EXTS = (".flac", ".ogg", ".oga", ".opus", ".wav")


def _alert_candidates():
    """(path, relative url) for the alert file, in precedence order.

    A user's own file in user_files always outranks the bundled one, even when
    it is an mp3 the webview cannot decode: the URL is still handed over, the
    JS play() fails, and the av_player fallback plays THEIR sound rather than
    silently substituting ours.
    """
    for folder in ("user_files", "sounds"):
        for ext in _WEB_AUDIO_EXTS + (".mp3",):
            path = os.path.join(_SUITE_DIR, folder, "alert" + ext)
            if os.path.exists(path):
                yield path, f"{folder}/alert{ext}"


def alert_url() -> str:
    """The warning alert as a URL the reviewer webview can play itself.

    Anki routes every sound FILE through mpv, and Anki's bundled mpv does not
    run on every macOS it ships to (on macOS 13 it aborts at launch on a
    missing Swift symbol), which silently costs you the alert. Card TTS is
    unaffected, as Anki's macOS TTS shells out to ``say``. Playing the alert in
    the webview sidesteps av_player entirely; ``_play_alert`` stays as the
    fallback for when the webview cannot play what it is given.
    """
    for path, rel in _alert_candidates():
        try:
            ver = str(int(os.path.getmtime(path)))
        except Exception:
            ver = "0"
        return f"/_addons/{PACKAGE}/{rel}?v={ver}"
    return ""


def _external_player_works() -> bool:
    """Whether Anki has a player for sound FILES. If mpv failed to start (as on
    macOS 13), Anki falls back to mplayer, and when that isn't installed either,
    every file it is handed pops up "Sound and video on cards will not function
    until mpv or mplayer is installed". Skipping the fallback keeps that pop-up
    from interrupting a review; the alert is just silent on that card."""
    try:
        from aqt import sound
        if getattr(sound, "mpvManager", None) is not None:
            return True
    except Exception:
        return False
    return shutil.which("mplayer") is not None


def _play_alert() -> None:
    """Fallback: hand the alert to Anki's own player (needs a working mpv)."""
    if not _external_player_works():
        return
    for path, _rel in _alert_candidates():
        try:
            av_player.play_file(path)
        except Exception:
            pass
        return


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
    payload = reveal.question_payload(card)
    payload["autoPaused"] = _sticky_pause(payload)
    # Paused launch: hold the auto-reveal and the session clock until the user
    # engages (the JS arms a one-shot click/key listener; see focus:engaged).
    s = session.get_active()
    if s is not None and getattr(s, "paused", False):
        payload["paused"] = True
    track = (payload.get("autoReveal") or {}).pop("_track", None)
    try:
        # A card whose timer is held from the start (the pause key, or a paused
        # launch waiting for your first key) never runs one: nothing to learn.
        if track and not payload["autoPaused"] and not payload.get("paused"):
            pace.start_card(card, get_section("speed_focus"),
                            track["inputs"], track["delay"],
                            cloze_words=track.get("cloze_words"))
        else:
            pace.clear_card()
    except Exception:
        pace.clear_card()
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
    try:
        pace.end_card(card, get_section("speed_focus"))
    except Exception:
        pass
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
            pace.note_auto_fire()   # before _showAnswer, which ends the card
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
    if action.startswith("cloze:"):
        # cloze:<index>:<timer uncovered it 0/1>:<held 0/1>:<ms it was up>
        try:
            index, auto, held, ms = action[len("cloze:"):].split(":")
            pace.note_cloze(int(index), auto == "1", held == "1", int(ms) / 1000.0)
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
        rv = mw.reviewer
        if _auto_paused and rv and rv.state == "question":
            pace.note_hold()
        tooltip(
            f"⏸ Speed Focus paused — {_resume_hint()}" if _auto_paused
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
    from ..config import get_section
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
    """Stop any pending auto-reveal / warning timers on the current card (used
    when a Pomodoro break takes over so Speed Focus doesn't fire behind it)."""
    _eval("window.FocusSuite && FocusSuite.pauseAuto && FocusSuite.pauseAuto();")


def register() -> None:
    # Anki serves /_addons/<pkg>/<sub> only when <sub> re.fullmatch-es this
    # pattern, so the alert has to be exported explicitly or the <audio> src
    # 404s and the sound silently never plays. user_files is opened for the
    # alert FILE ONLY, never the folder — it also holds the break journal,
    # sprint stats and music profile, and everything exported here is readable
    # by any page loaded in the webview.
    mw.addonManager.setWebExports(
        PACKAGE, r"web.*|sounds/alert\.[A-Za-z0-9]+|user_files/alert\.[A-Za-z0-9]+"
    )
    topbar.register()
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
