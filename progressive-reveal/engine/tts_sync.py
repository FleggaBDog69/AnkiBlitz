"""TTS sync: keep the progressive reveal in step with native Anki/AnKing TTS.

Anki's macOS TTS player (`aqt/tts.py` MacTTSPlayer) shells out to
``say -r (base_wpm × speed)`` with ``base_wpm`` hardcoded to 170, so a card's
spoken rate is a known, linear function of its ``{{tts}}`` ``speed=``. That makes
the reveal rate that matches the voice exact, with no calibration:

    tts_wps   = base_wpm × speed / 60
    ideal speed= = reveal_wps × 60 / base_wpm

Two uses:
  * a settings readout telling the user the ideal ``speed=`` for their reveal
    rate, and the rates already used by their note types;
  * an opt-in per-card auto-match that drives the reveal speed from each card's
    *active* TTS tag (read via ``card.question_av_tags()`` — Anki only surfaces
    uncommented tags there, so disabled AnKing TTS is naturally ignored).

Everything here is best-effort / read-only and never raises into the host.
"""

import re

DEFAULT_BASE_WPM = 170

# Matches an active {{tts ... speed=1.6 ...}} or a commented <!--tts ... speed=1.6 ...-->
_TTS_RE = re.compile(r"(<!--\s*)?\{?\{?\s*tts\b[^}>]*?\bspeed\s*=\s*([0-9]*\.?[0-9]+)", re.I)


def wps_for_speed(speed: float, base_wpm: int = DEFAULT_BASE_WPM) -> float:
    """Words/sec the reveal should run at to match a TTS tag of this ``speed=``."""
    return (float(base_wpm) * float(speed)) / 60.0


def ideal_speed(wps: float, base_wpm: int = DEFAULT_BASE_WPM) -> float:
    """The TTS ``speed=`` whose playback rate matches this reveal words/sec."""
    if base_wpm <= 0:
        return 0.0
    return (float(wps) * 60.0) / float(base_wpm)


def _first_tts_speed(av_tags) -> float | None:
    """Return the first TTSTag's speed in an av-tag list, or None."""
    try:
        from anki.sound import TTSTag
    except Exception:
        return None
    for tag in av_tags or []:
        if isinstance(tag, TTSTag):
            try:
                return float(tag.speed)
            except Exception:
                return None
    return None


def tts_wps_for_card(card, side: str, base_wpm: int = DEFAULT_BASE_WPM):
    """Reveal words/sec matching the card's active TTS on ``side``, or None.

    ``side`` is "question" or "answer". Returns None when the card has no active
    TTS tag for that side (e.g. AnKing's commented-out default) or anything
    fails — callers fall back to the configured words_per_second.
    """
    try:
        tags = card.answer_av_tags() if side == "answer" else card.question_av_tags()
    except Exception:
        return None
    speed = _first_tts_speed(tags)
    if speed is None or speed <= 0:
        return None
    return wps_for_speed(speed, base_wpm)


def scan_collection_tts(limit: int = 12) -> list:
    """Scan note-type templates for TTS tags, for the settings readout.

    Returns a de-duplicated list of ``(notetype_name, speed, active)`` where
    ``active`` is False for tags AnKing ships commented out. Read-only and
    best-effort; returns [] if the collection isn't available.
    """
    out = []
    try:
        from aqt import mw
        if not mw or not mw.col:
            return out
        seen = set()
        for nt in mw.col.models.all():
            name = nt.get("name", "?")
            for tmpl in nt.get("tmpls", []):
                for fmt in (tmpl.get("qfmt", ""), tmpl.get("afmt", "")):
                    for m in _TTS_RE.finditer(fmt or ""):
                        active = m.group(1) is None  # no leading <!-- => live tag
                        try:
                            speed = round(float(m.group(2)), 2)
                        except Exception:
                            continue
                        key = (name, speed, active)
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append((name, speed, active))
    except Exception:
        return out
    # Active tags first, then by note-type name; cap for a compact readout.
    out.sort(key=lambda r: (not r[2], r[0].lower(), r[1]))
    return out[:limit]
