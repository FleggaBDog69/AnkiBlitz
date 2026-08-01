"""Configuration for Adaptive Speed Focus (aSFM).

A single, flat add-on config (one JSON). This is a standalone add-on — it owns
just the adaptive auto-reveal knobs, so there's no per-feature namespacing: every
key lives at the top level and is read live per card.

The auto-reveal delay math lives in ``engine/adaptive.py``; these are its knobs.
"""

from aqt import mw

PACKAGE = __name__.split(".")[0]

# Defaults reproduce a calm ~7s reveal on a 12-word card (base 3 + 0.3×words,
# nudged a little by the card's FSRS difficulty), clamped to [2, 20] s.
DEFAULTS = {
    "enabled": True,              # master switch
    "base_seconds": 3.0,          # fixed thinking budget added to every card
    "seconds_per_word": 0.30,     # reading budget scaled by question length
    "min_delay_seconds": 2.0,     # floor for the computed delay
    "max_delay_seconds": 20.0,    # ceiling for the computed delay
    "unfamiliar_multiplier": 1.2, # extra time for learning / relearning cards
    "new_multiplier": 1.5,        # extra time for genuinely new cards
    "enable_on_new": True,        # run the auto-reveal timer on new cards
    "difficulty_weight": 0.20,    # max ± swing from FSRS difficulty (0 = off)
    "show_countdown": True,       # show the depleting countdown indicator
    "warning_sound": True,        # play an alert before the answer auto-shows
    "warning_at_percent": 75,     # warn once this % of the delay has elapsed
    "pause_key_enabled": True,    # a key that holds/releases the auto-reveal timer
    "pause_key": "p",             # which key that is
    "excluded_note_types": [],    # skip the auto-reveal timer for these note types
    "excluded_decks": [],         # skip the auto-reveal timer for these decks
    # Picture / visual cards: ignore word count and familiarity; give a SET reveal
    # time with only difficulty as a modifier (there's nothing to read). Matched by
    # note-type name or deck like the exclusion lists.
    "fixed_time_enabled": True,
    "fixed_time_base_seconds": 6.0,
    "fixed_time_note_types": [],
    "fixed_time_decks": [],
}


def _all() -> dict:
    return mw.addonManager.getConfig(PACKAGE) or {}


def _write_all(cfg: dict) -> None:
    mw.addonManager.writeConfig(PACKAGE, cfg)


def get_config() -> dict:
    """The live config, with defaults filled in for any missing key."""
    cfg = dict(DEFAULTS)
    saved = _all()
    if isinstance(saved, dict):
        cfg.update(saved)
    return cfg


def save_config(data: dict) -> None:
    _write_all(data)


def ensure_defaults() -> None:
    """Backfill any missing key additively, then persist."""
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
