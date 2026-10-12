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

from ..config import DEFAULTS, PACKAGE, get_config
from . import adaptive, pace

PYCMD_PREFIX = "asfm:"

# The pause key's sticky state. Held here rather than in the JS so it survives
# the bundle being re-injected (leaving the reviewer and coming back), and is
# pushed out with every card payload. Cleared on profile load, not persisted.
_auto_paused = False


def auto_reveal_paused() -> bool:
    return _auto_paused


_CSS_HREF = f"/_addons/{PACKAGE}/web/asfm.css"
_JS_SRC = f"/_addons/{PACKAGE}/web/asfm.js"

# Warning alert: an alert.* in user_files overrides the bundled sounds/alert.*
_DIR = os.path.dirname(os.path.dirname(__file__))


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
            path = os.path.join(_DIR, folder, "alert" + ext)
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


def _play_alert() -> None:
    """Fallback: hand the alert to Anki's own player (needs a working mpv)."""
    for path, _rel in _alert_candidates():
        try:
            av_player.play_file(path)
        except Exception:
            pass
        return


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
    if adaptive.is_new_card(card) and not cfg.get("enable_on_new",
                                                  DEFAULTS["enable_on_new"]):
        return off
    inputs = adaptive.card_inputs(card, cfg)
    cur_pace = pace.current(cfg)
    delay_s = adaptive.delay_for(cfg, pace=cur_pace, **inputs)
    track = {"inputs": inputs, "delay": delay_s}
    one_by_one = None
    plan = adaptive.one_by_one_plan(cfg, card, inputs, cur_pace)
    if plan:
        # A one-by-one card's wait isn't a read-the-question wait, so it
        # stays out of the pace tracker.
        delay_s = plan["delay"]
        track = None
        one_by_one = {"mode": plan["mode"],
                      "delaysMs": [int(d * 1000) for d in plan.get("delays", [])]}
    return {
        "enabled": True,
        # Stripped before the payload goes to the webview; the pace tracker
        # needs the card's inputs and doesn't want to measure them twice.
        "_track": track,
        "delayMs": int(delay_s * 1000),
        "oneByOne": one_by_one,
        "showCountdown": bool(cfg.get("show_countdown", True)),
        "warnColour": bool(cfg.get("countdown_warning_colour",
                                   DEFAULTS["countdown_warning_colour"])),
        "warn": bool(cfg.get("warning_sound", True)),
        "alertUrl": alert_url() if cfg.get("warning_sound", True) else "",
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
    payload = question_payload(card)
    track = payload.pop("_track", None)
    try:
        # A card that opens with the timer already held never runs one, so
        # there's nothing to learn from it.
        if track and not payload.get("autoPaused"):
            pace.start_card(card, get_config(), track["inputs"], track["delay"])
        else:
            pace.clear_card()
    except Exception:
        pace.clear_card()
    _eval(f"window.ASFM && ASFM.onCard({json.dumps(payload)});")


def _on_show_answer(*args, **kwargs) -> None:
    # Cancel any pending timer/countdown the moment the answer shows (manually or
    # via the timer).
    # The pause block still rides along: the key has to keep working (and the
    # sticky flag has to stay true) while the answer is on screen.
    try:
        pace.end_card(mw.reviewer.card if mw.reviewer else None, get_config())
    except Exception:
        pass
    payload = {"enabled": False, **_pause_block(get_config())}
    _eval(f"window.ASFM && ASFM.onCard({json.dumps(payload)});")


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
    if action == "warn":
        _play_alert()
        return (True, None)
    if action.startswith("autopause:"):
        global _auto_paused
        _auto_paused = action.endswith("1")
        rv = mw.reviewer
        if _auto_paused and rv and rv.state == "question":
            pace.note_hold()
        key = str(get_config().get("pause_key") or "p").upper()
        tooltip(
            f"⏸ Auto-reveal paused — press {key} to resume" if _auto_paused
            else "▶ Auto-reveal resumed",
            period=1800,
        )
        return (True, None)
    return handled


def register() -> None:
    # Anki serves /_addons/<pkg>/<sub> only when <sub> re.fullmatch-es this
    # pattern, so the alert has to be exported explicitly or the <audio> src
    # 404s and the sound silently never plays. user_files is opened for the
    # alert FILE ONLY, never the whole folder: everything exported here is
    # readable by any page loaded in the webview.
    mw.addonManager.setWebExports(
        PACKAGE, r"web.*|sounds/alert\.[A-Za-z0-9]+|user_files/alert\.[A-Za-z0-9]+"
    )
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
