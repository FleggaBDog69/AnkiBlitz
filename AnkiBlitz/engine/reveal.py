"""Builds the per-card payload handed to the JS bundle.

One place decides, for the current card, whether the progressive reveal and the
adaptive auto-reveal timer should run, and with what parameters. The JS bundle
is "dumb": it just executes whatever payload Python sends.
"""

from aqt import mw

from ..config import get_section, suite_enabled
from . import adaptive, tts_sync


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


def question_payload(card) -> dict:
    """Payload for reviewer_did_show_question."""
    suite_on = suite_enabled()
    wr = get_section("word_reveal")
    sf = get_section("speed_focus")

    reveal_on = bool(suite_on and wr.get("enabled", True) and not _section_excluded(card, wr))
    auto_on = bool(suite_on and sf.get("enabled", True) and not _section_excluded(card, sf))
    if auto_on and adaptive.is_new_card(card) and not sf.get("enable_on_new", True):
        auto_on = False

    delay_ms = 0
    if auto_on:
        delay_ms = int(adaptive.reveal_delay_seconds(card, sf) * 1000)

    return {
        "side": "question",
        "reveal": _reveal_block(wr, reveal_on, card, "question"),
        "autoReveal": {
            "enabled": auto_on,
            "delayMs": delay_ms,
            "minPostMs": int(float(sf.get("min_post_seconds", 1.0)) * 1000),
            "showCountdown": bool(sf.get("show_countdown", True)),
            "warn": bool(sf.get("warning_sound", True)),
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
