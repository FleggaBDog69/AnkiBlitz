"""The reviewer injection point for Progressive Word Reveal.

A single ``webview_will_set_content`` handler injects one CSS file and one JS
bundle. Python decides, per card, whether the reveal should run and with what
parameters, and pushes that with a single ``PWReveal.onCard(...)`` call. The JS
owns all DOM, timing and animation.

One message comes back the other way (pycmd, ``pwr:`` namespace):
  - ``pwr:stopaudio`` — the reveal was skipped; stop the card's audio. Anki's
    own playback lives in mpv, so only Python can cut it.
"""

import json

from aqt import gui_hooks, mw
from aqt.reviewer import Reviewer
from aqt.sound import av_player

from ..config import PACKAGE, get_config
from . import tts_sync

_CSS_HREF = f"/_addons/{PACKAGE}/web/reveal.css"
_JS_SRC = f"/_addons/{PACKAGE}/web/reveal.js"

_SHIM = (
    "<script>(function(){if(window.PWReveal)return;var q=[];var s={_queue:q};"
    "['onCard'].forEach(function(m){s[m]=function(){q.push([m,arguments]);};});"
    "window.PWReveal=s;})();</script>"
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


def _reveal_block(cfg: dict, enabled: bool, card, side: str) -> dict:
    """The reveal sub-payload. When TTS auto-match is on and the card has an active
    {{tts}} tag for this side, the reveal speed is driven from that tag."""
    wps = float(cfg.get("words_per_second", 6.0))
    if enabled and card is not None and cfg.get("tts_auto_match", False):
        matched = tts_sync.tts_wps_for_card(
            card, side, int(cfg.get("tts_base_wpm", tts_sync.DEFAULT_BASE_WPM)))
        if matched and matched > 0:
            wps = matched
    return {
        "enabled": enabled,
        "wordsPerSecond": wps,
        "mode": str(cfg.get("reveal_mode", "words")),
        "chunkWords": max(1, int(cfg.get("chunk_words", 3))),
        "revealKey": str(cfg.get("reveal_key") or "p").lower(),
        "stopAudio": bool(cfg.get("stop_audio_on_reveal", True)),
    }


def question_payload(card) -> dict:
    cfg = get_config()
    on = bool(cfg.get("enabled", True) and not _excluded(card, cfg))
    return {"reveal": _reveal_block(cfg, on, card, "question")}


def answer_payload(card) -> dict:
    cfg = get_config()
    on = bool(
        cfg.get("enabled", True)
        and cfg.get("reveal_on_answer", False)
        and not _excluded(card, cfg))
    return {"reveal": _reveal_block(cfg, on, card, "answer")}


# ----- hooks -----

def _on_will_set_content(web_content, context, *args, **kwargs) -> None:
    if isinstance(context, Reviewer):
        web_content.body += _INJECT


def _on_show_question(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    _eval(f"window.PWReveal && PWReveal.onCard({json.dumps(question_payload(card))});")


def _on_show_answer(*args, **kwargs) -> None:
    card = mw.reviewer.card if mw.reviewer else None
    if not card:
        return
    _eval(f"window.PWReveal && PWReveal.onCard({json.dumps(answer_payload(card))});")


def _on_js_message(handled, message: str, context, *args, **kwargs):
    if message == "pwr:stopaudio":
        # The reveal was skipped: cut whatever the card is still saying (and
        # drop the rest of its queue, so the next tag doesn't start up).
        try:
            av_player.stop_and_clear_queue()
        except Exception:
            pass
        return (True, None)
    return handled


def register() -> None:
    mw.addonManager.setWebExports(PACKAGE, r"web.*")
    gui_hooks.webview_will_set_content.append(_on_will_set_content)
    gui_hooks.reviewer_did_show_question.append(_on_show_question)
    gui_hooks.reviewer_did_show_answer.append(_on_show_answer)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
