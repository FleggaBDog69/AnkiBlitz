"""Builds the per-card payload handed to the JS bundle.

One place decides, for the current card, whether the progressive reveal and the
adaptive auto-reveal timer should run, and with what parameters. The JS bundle
is "dumb": it just executes whatever payload Python sends.
"""

from aqt import mw

from ..config import DEFAULTS, get_section, suite_enabled
from . import adaptive, pace, tts_sync


def _deck_excluded(deck_name: str, excluded: list) -> bool:
    if not deck_name:
        return False
    for entry in excluded:
        if entry and (deck_name == entry or deck_name.startswith(entry + "::")):
            return True
    return False


def _section_excluded(card, section: dict) -> bool:
    """True if this card's note type or deck is in the section's exclusion lists.
    Shared by word_reveal and speed_focus (both carry the same two list keys)."""
    try:
        nt = card.note_type()
        if nt and nt.get("name") in section.get("excluded_note_types", []):
            return True
    except Exception:
        pass
    try:
        deck_name = mw.col.decks.name(card.current_deck_id())
        if _deck_excluded(deck_name, section.get("excluded_decks", [])):
            return True
    except Exception:
        pass
    return False


def _reveal_block(wr: dict, enabled: bool, card=None, side: str = "question") -> dict:
    """The reveal sub-payload, shared by both sides.

    When TTS auto-match is on and the card has an active {{tts}} tag for this
    side, the reveal speed is driven from that tag so words finish in step with
    the voice; otherwise the configured words_per_second is used.
    """
    wps = float(wr.get("words_per_second", 6.0))
    if enabled and card is not None and wr.get("tts_auto_match", False):
        matched = tts_sync.tts_wps_for_card(
            card, side, int(wr.get("tts_base_wpm", tts_sync.DEFAULT_BASE_WPM))
        )
        if matched and matched > 0:
            wps = matched
    return {
        "enabled": enabled,
        "wordsPerSecond": wps,
        "mode": str(wr.get("reveal_mode", "words")),
        "chunkWords": max(1, int(wr.get("chunk_words", 3))),
        "revealKey": str(wr.get("reveal_key") or "p").lower(),
        "stopAudio": bool(wr.get("stop_audio_on_reveal", True)),
    }


def _alert_url() -> str:
    """The warning alert as a webview-playable URL.

    Lazy import: ``injection`` imports this module at load time, so the reverse
    cannot be a top-level import. Empty string on any failure — the JS then
    falls back to asking Python to play it.
    """
    try:
        from . import injection
        return injection.alert_url()
    except Exception:
        return ""


def question_payload(card) -> dict:
    """Payload for reviewer_did_show_question."""
    suite_on = suite_enabled()
    wr = get_section("word_reveal")
    sf = get_section("speed_focus")

    reveal_on = bool(suite_on and wr.get("enabled", True) and not _section_excluded(card, wr))
    auto_on = bool(suite_on and sf.get("enabled", True) and not _section_excluded(card, sf))
    if auto_on and adaptive.is_new_card(card) and not sf.get(
            "enable_on_new", DEFAULTS["speed_focus"]["enable_on_new"]):
        auto_on = False

    delay_ms = 0
    track = None
    if auto_on:
        inputs = adaptive.card_inputs(card, sf)
        delay_s = adaptive.delay_for(sf, pace=pace.current(sf), **inputs)
        delay_ms = int(delay_s * 1000)
        # Stripped before the payload reaches the webview; the pace tracker
        # needs the card's inputs and doesn't want to measure them twice.
        track = {"inputs": inputs, "delay": delay_s}

    return {
        "side": "question",
        "reveal": _reveal_block(wr, reveal_on, card, "question"),
        "autoReveal": {
            "enabled": auto_on,
            "delayMs": delay_ms,
            "_track": track,
            "minPostMs": int(float(sf.get("min_post_seconds", 1.0)) * 1000),
            "showCountdown": bool(sf.get("show_countdown", True)),
            "warnColour": bool(sf.get("countdown_warning_colour", True)),
            "warn": bool(sf.get("warning_sound", True)),
            "alertUrl": _alert_url() if sf.get("warning_sound", True) else "",
            "warnPercent": int(sf.get("warning_at_percent", 60)),
            **_pause_block(sf, suite_on),
        },
    }


def _pause_block(sf: dict, suite_on: bool) -> dict:
    """The pause-key half of the autoReveal payload. Deliberately allowed to be
    the same key as word_reveal's reveal key — the JS gives the reveal first
    claim while words are still fading in, then the key pauses the timer.

    The key and the "More time" button are gated separately: they apply the same
    hold, but you may well want the button without knowing a key exists, or the
    key without a control sitting over your cards."""
    return {
        "pauseKey": str(sf.get("pause_key") or "p").lower(),
        "pauseEnabled": bool(suite_on and sf.get("enabled", True)
                             and sf.get("pause_key_enabled", True)),
        "moreTimeButton": bool(suite_on and sf.get("enabled", True)
                               and sf.get("more_time_button", True)),
    }


def answer_payload(card) -> dict:
    """Payload for reviewer_did_show_answer."""
    suite_on = suite_enabled()
    wr = get_section("word_reveal")
    sf = get_section("speed_focus")
    reveal_on = bool(
        suite_on
        and wr.get("enabled", True)
        and wr.get("reveal_on_answer", False)
        and not _section_excluded(card, wr)
    )
    return {
        "side": "answer",
        "reveal": _reveal_block(wr, reveal_on, card, "answer"),
        # No timer runs on the answer side, but the pause key stays live so you
        # can arm/disarm it there too (it applies from the next question).
        "autoReveal": {"enabled": False, "delayMs": 0, "minPostMs": 0,
                       "showCountdown": False, **_pause_block(sf, suite_on)},
    }
