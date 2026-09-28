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
    # Answer length: give cards whose ANSWER is long more thinking time. A
    # short question with a five-item answer needs more than its front side
    # suggests. Additive and capped (see engine/adaptive.py), so it does NOT
    # scale with question length, but IS scaled by the new / learning /
    # difficulty modifiers. 0.0 seconds per answer word switches it off.
    "seconds_per_answer_word": 0.1,   # seconds added per answer-side word (0 = off)
    "max_answer_seconds": 5.0,        # ceiling on that addition
    "min_delay_seconds": 2.0,     # floor for the computed delay
    "max_delay_seconds": 20.0,    # ceiling for the computed delay
    "unfamiliar_multiplier": 1.1, # extra time for learning / relearning cards
    "new_multiplier": 1.5,        # extra time for genuinely new cards
    "enable_on_new": False,        # run the auto-reveal timer on new cards
    "difficulty_weight": 0.30,    # max ± swing from FSRS difficulty (0 = off)
    "show_countdown": True,       # show the depleting countdown indicator
    # Turn the countdown bar from Anki's blue to red once the warning point
    # (warning_at_percent) is reached — a silent heads-up, with or without the
    # sound.
    "countdown_warning_colour": True,
    "warning_sound": True,        # play an alert before the answer auto-shows
    "warning_at_percent": 75,     # warn once this % of the delay has elapsed
    "pause_key_enabled": True,    # a key that holds/releases the auto-reveal timer
    "pause_key": "p",             # which key that is
    # The visible "More time" button — the same hold the pause key applies, but
    # discoverable without knowing the key exists. Glutanimate's Speed Focus Mode
    # had one; this is the equivalent.
    "more_time_button": True,
    # Learn my pace (engine/pace.py). Auto-tune scales every delay by a learned
    # multiplier, steering until the timer beats you on about
    # target_timer_wins_percent of cards; calibration fits base / per-word to
    # the same target. The learned pace lives in user_files, not here.
    "auto_tune_enabled": True,
    "target_timer_wins_percent": 10,
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
