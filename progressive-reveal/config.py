"""Configuration for Progressive Word Reveal.

A single, flat add-on config (one JSON). Standalone — it owns just the
progressive-reveal knobs, read live per card.
"""

from aqt import mw

PACKAGE = __name__.split(".")[0]

DEFAULTS = {
    "enabled": True,
    "words_per_second": 6.0,      # reading speed; total time scales with length
    "reveal_mode": "words",       # "words" (one at a time) or "chunks"
    "chunk_words": 3,             # words revealed together per chunk in chunk mode
    "reveal_on_answer": False,    # also fade in the answer side
    "reveal_key": "p",            # key (besides click) to reveal instantly
    # TTS sync: keep the reveal in step with native Anki/AnKing {{tts}} playback.
    # macOS `say` runs at (base_wpm × speed) words/min, so the matching reveal rate
    # is (base_wpm × speed / 60) words/sec.
    "tts_auto_match": True,       # per-card: drive reveal speed from the card's active TTS
    "tts_base_wpm": 170,          # `say` base wpm (170 × speed); platform-tunable
    "excluded_note_types": [],
    "excluded_decks": [],
}


def _all() -> dict:
    return mw.addonManager.getConfig(PACKAGE) or {}


def _write_all(cfg: dict) -> None:
    mw.addonManager.writeConfig(PACKAGE, cfg)


def get_config() -> dict:
    cfg = dict(DEFAULTS)
    saved = _all()
    if isinstance(saved, dict):
        cfg.update(saved)
    return cfg


def save_config(data: dict) -> None:
    _write_all(data)


def ensure_defaults() -> None:
    cfg = _all()
    changed = False
    for key, default in DEFAULTS.items():
        if key not in cfg:
            cfg[key] = default
            changed = True
    if changed:
        _write_all(cfg)


def enabled() -> bool:
    return bool(_all().get("enabled", DEFAULTS["enabled"]))


def set_enabled(value: bool) -> None:
    cfg = _all()
    cfg["enabled"] = bool(value)
    _write_all(cfg)
