"""Unified configuration for AnkiBlitz.

A single Anki add-on config (one JSON) holds a top-level ``enabled`` master
switch plus one namespaced section per feature::

    { "enabled": true,
      "speed_focus": { ... },
      "word_reveal": { ... },
      "sprint":      { ... } }

Each feature reads/writes only its own section via ``get_section`` /
``save_section`` so the three formerly-separate add-ons stay decoupled. A new
feature (e.g. a future Remaining Time bar) just adds another section to
``DEFAULTS`` and a tab to the settings dialog — nothing else changes.
"""

from aqt import mw

# Top-level add-on package name ("focus_suite"), used as the config key.
PACKAGE = __name__.split(".")[0]

# Per-feature defaults. Mirrors each original add-on's config.json.
DEFAULTS = {
    "enabled": True,  # master switch for the whole suite

    # Adaptive auto-REVEAL timer. Never auto-grades. The reveal delay is
    # computed in Python per card (see engine/adaptive.py); these are its knobs.
    "speed_focus": {
        "enabled": True,
        "base_seconds": 2.0,          # fixed thinking budget added to every card
        "seconds_per_word": 0.20,     # reading budget scaled by question length
        "min_delay_seconds": 2.0,     # floor for the computed delay
        "max_delay_seconds": 15.0,    # ceiling for the computed delay
        "unfamiliar_multiplier": 1.2, # extra time for learning / relearning cards
        "new_multiplier": 1.5,        # extra time for genuinely new cards
        "enable_on_new": True,        # run the auto-reveal timer on new cards
        "difficulty_weight": 0.20,    # max ± swing from FSRS difficulty (0 = off)
        "min_post_seconds": 1.0,      # hold answer >= this long after the reveal finishes
        "show_countdown": True,       # show the depleting countdown indicator
        "warning_sound": True,        # play an alert before the answer auto-shows
        "warning_at_percent": 75,     # warn once this % of the delay has elapsed
        "excluded_note_types": [],    # skip the auto-reveal timer for these note types
        "excluded_decks": [],         # skip the auto-reveal timer for these decks
        # Picture / visual cards: ignore word count and familiarity; give a SET
        # reveal time with only difficulty as a modifier (there's nothing to
        # read). Matched by note-type name or deck like the exclusion lists.
        # These three keys live OUTSIDE the profile system, so the choice of
        # which cards are "visual" endures across every profile.
        "fixed_time_enabled": True,
        "fixed_time_base_seconds": 6.0,  # set thinking time for a visual card
        "fixed_time_note_types": [],     # note types treated as picture cards
        "fixed_time_decks": [],          # decks treated as picture cards
    },

    # Progressive reveal: words (or fixed-size word chunks) fade in over time.
    # Standalone — does not depend on the auto-reveal timer.
    "word_reveal": {
        "enabled": True,
        "words_per_second": 6.0,      # reading speed; total time scales with length
        "reveal_mode": "words",       # "words" (one at a time) or "chunks"
        "chunk_words": 3,             # words revealed together per chunk in chunk mode
        "reveal_on_answer": False,
        "reveal_key": "p",            # key (besides click) to reveal instantly
        # TTS sync: keep the progressive reveal in step with native Anki/AnKing
        # {{tts}} playback. macOS `say` runs at (base_wpm × speed), so the reveal
        # rate that matches a card's TTS is (base_wpm × speed / 60) words/sec.
        "tts_auto_match": True,       # per-card: drive reveal speed from the card's active TTS
        "tts_base_wpm": 170,          # `say` base wpm (170 × speed); platform-tunable
        "excluded_note_types": [],
        "excluded_decks": [],
    },

    # Quick Start: auto-launch a Blitz on the first open of the day. Uses its
    # own preset (mode + target), independent of the Start-Blitz dialog defaults.
    "quick_start": {
        "enabled": True,              # opt-in; off until turned on
        "launch_style": "immediate",  # "countdown" (3-2-1, cancelable) | "immediate"
        "countdown_seconds": 3,
        "mode": "cards",              # own preset: "cards" | "time" | "fraction"
        "target": 50,                 # cards / minutes / denominator, per mode
        "min_due": 1,                 # don't auto-launch unless >= this many due
        # If Anki is left open across a day rollover, relaunch the daily Blitz the
        # first time you bring Anki to the foreground on/after relaunch_after_hour.
        # It opens PAUSED (no auto-reveal, clock at 0:00) until your first key/click.
        "relaunch_on_new_day": True,
        "relaunch_after_hour": 5,     # earliest local hour the foreground relaunch may fire
    },

    # Momentum protection: when you leave the reviewer NEAR THE END of a Blitz,
    # intercept with a "you're almost done" prompt instead of silently cancelling.
    "momentum": {
        "enabled": True,
        "near_end_cards": 10,         # cards/fraction: within N of the target
        "near_end_seconds": 120,      # time mode: within N seconds of the deadline
    },

    # Pomodoro: chain work blocks (each a Blitz) with breaks. A longer break lands
    # every Nth block. When a break's countdown ends, auto_return_level decides how
    # insistently you're brought back (notify -> prompt -> auto-start -> raise+start).
    "pomodoro": {
        "enabled": True,              # feature available (menu + widgets show it)
        "work_mode": "fraction",      # work-block Blitz mode: "time"|"cards"|"fraction"
        "work_target": 3,             # minutes / cards / denominator, per work_mode
        "break_minutes": 5,           # short break length
        "long_break_enabled": True,
        "long_break_every": 4,        # long break after every Nth work block
        "long_break_minutes": 25,
        "cycles": 0,                  # 0 = unlimited; else stop after N work blocks
        "auto_return_level": 2,       # 0 notify | 1 prompt | 2 auto | 3 raise+auto
        "break_sound": True,          # chime when a break starts and ends
        "daily_goal": 0,              # blocks/day target shown on the break screen; 0 = off
        "end_summary": True,          # end-of-run summary screen (vs a tooltip)
        "carry_forward": True,        # greet the next block with last break's note
        # Break-screen elements — each can be hidden so the screen stays calm.
        "break_show_timeline": True,  # the past/now/future strip
        "break_show_journal": True,   # the per-break journal box
        "break_show_focus_rating": True,  # the 1-5 focus rating
        "break_show_tips": True,      # rotating micro-break suggestions
        "break_show_browser": True,   # the in-app browser button
        "break_show_add_kg": True,    # the Ankisstant "Add KG" button
        "break_allow_extend": True,   # the +5 min extend button
    },

    # On-screen widgets: AnkiBlitz panels injected into the deck browser (home)
    # and a deck's overview screen, so a Blitz/Pomodoro is one click from where
    # you already are.
    # Music player: keep study music inside Anki. A small in-app browser pointed
    # at a music service (you browse and hit play — no pasting links), shown on
    # the Pomodoro break screen, as a floating window during reviews, and from
    # the deck-list rail. Off by default; nothing shows until `enabled` is on.
    # SoundCloud plays full tracks with no login; YouTube Music depends on the Qt
    # build having the proprietary codecs.
    "music": {
        "enabled": True,              # master: nothing appears until this is on
        "show_on_break": True,        # offer a "♪ Music" panel on the break screen
        "show_dropdown": True,        # allow the floating review window (menu / Ctrl+Shift+M)
        "show_on_home": True,         # add a "♪ Music" button to the deck-list rail
        "service": "youtube",         # quick-jump default: "soundcloud" | "youtube"
        "last_url": "https://music.youtube.com/",  # remembered last page, so it reopens where you left off
    },

    # Focus (Stage 6): discipline + scoring for a study session.
    #  - Focus Lock makes leaving progressively harder (0 none → 3 finish).
    #  - Focus Score is a 0–100 blend of completion, speed, engagement (idle), and
    #    optionally accuracy, shown on the completion screen and in stats.
    # Focus Lock applies to a running Blitz always, and to ordinary review
    # sessions when apply_to_reviews is on. Level meanings:
    #   1 confirm  — a prompt before you may leave.
    #   2 min-cards — trying to leave forces you to clear lock_min_cards MORE
    #                 cards from that point, then asks to confirm leaving.
    #   3 finish   — can't leave until the Blitz target (or all due cards, in a
    #                normal review) is reached.
    # Leaving by alt-tab still cancels a Blitz at levels 0–2 (the discipline
    # penalty); level 3 keeps the session and re-raises Anki to the front.
    "focus": {
        "enabled": True,
        "apply_to_reviews": False,     # also lock ordinary review sessions, not just Blitzes
        "lock_level": 1,               # 0 none | 1 confirm | 2 min-cards | 3 finish
        "lock_min_cards": 10,          # level 2: extra cards forced when you try to leave
        "score_enabled": True,         # compute + show the Focus Score
        "score_include_accuracy": True,  # count accuracy as a score component
        "idle_threshold_seconds": 60,  # a gap between answers beyond this is idle
        "target_seconds_per_card": 8.0,  # reference pace for the speed component
    },

    "home_widget": {
        "enabled": True,              # show the AnkiBlitz panel on the deck browser
        "show_on_overview": True,     # show the "Blitz this deck" panel on overviews
        # Quick-launch buttons on the rail, each {"mode": ..., "value": ...}.
        # Empty -> fall back to the three Blitz defaults (time / cards / fraction).
        "presets": [
            {"mode": "cards", "value": 50},
            {"mode": "cards", "value": 80},
            {"mode": "fraction", "value": 3},
        ],
    },

    "sprint": {
        "enabled": True,
        "default_mode": "cards",      # "cards" | "time" | "fraction"
        "count_mode": "unique",       # "unique" cards or "answers" — the bar's unit
        "default_target": 50,         # cards-mode target
        "quick_picks": [25, 50, 100], # cards-mode quick buttons
        "default_time_minutes": 15,   # time-mode target
        "time_quick_picks": [10, 15, 25],
        "fraction_quick_picks": [2, 3],  # denominators -> 1/2, 1/3
        "card_source": "current_queue",
        "show_progress_bar": True,
        "show_card_counter": True,
        "show_elapsed_time": True,
        "show_live_accuracy": True,
        "show_again_count": True,
        "show_streak_counter": True,
        "streak_animations": False,
        "show_completion_screen": True,
        "completion_sound": False,
        "show_completion_accuracy": True,
        "track_pb_sprints_today": True,
        "track_pb_speed": True,
        "track_pb_total_sprints": True,
        "hide_all_accuracy_stats": False,
    },

    # Profiles (presets): named whole-config snapshots of AnkiBlitz's feel. The
    # three built-ins (Morning / Exam Mode / Casual) live in engine/presets.py as
    # code constants; only user-saved profiles and a one-time auto-capture of the
    # current setup ("My setup") are stored here. Applying is always explicit.
    "presets": {
        "active": "",       # name of the profile last applied ("My setup" after seeding)
        "saved": {},        # name -> snapshot overlay (see engine/presets.PROFILE_SPEC)
    },
}


def _all() -> dict:
    return mw.addonManager.getConfig(PACKAGE) or {}


def _write_all(cfg: dict) -> None:
    mw.addonManager.writeConfig(PACKAGE, cfg)


def ensure_defaults() -> None:
    """Backfill any missing top-level or per-section keys, then persist."""
    cfg = _all()
    changed = False
    for key, default in DEFAULTS.items():
        if isinstance(default, dict):
            section = cfg.get(key)
            if not isinstance(section, dict):
                cfg[key] = dict(default)
                changed = True
            else:
                for sk, sv in default.items():
                    if sk not in section:
                        section[sk] = sv
                        changed = True
        elif key not in cfg:
            cfg[key] = default
            changed = True
    if changed:
        _write_all(cfg)


def migrate() -> None:
    """One-time, additive value migrations. Runs via writeConfig (the add-on's
    normal channel), guarded by flags so a later deliberate change is never
    re-applied. Never hand-edits meta.json."""
    cfg = _all()
    flags = cfg.get("_migrations")
    if not isinstance(flags, dict):
        flags = {}
        cfg["_migrations"] = flags
    changed = False

    # v5.x: the Pomodoro auto-return default moved from "prompt" (1) to
    # "auto-start" (2). Bump only the value that still equals the old default.
    if not flags.get("pomodoro_autoreturn_v2"):
        po = cfg.get("pomodoro")
        if isinstance(po, dict) and int(po.get("auto_return_level", 2)) == 1:
            po["auto_return_level"] = 2
        flags["pomodoro_autoreturn_v2"] = True
        changed = True

    # v6.x: the music player's first cut stored a pasted link per service; the
    # browser version replaced that with a single `last_url`. Drop the two dead
    # keys if a stale config still carries them.
    if not flags.get("music_drop_url_keys"):
        mu = cfg.get("music")
        if isinstance(mu, dict):
            for dead in ("soundcloud_url", "youtube_url"):
                if dead in mu:
                    mu.pop(dead, None)
                    changed = True
        flags["music_drop_url_keys"] = True
        changed = True

    if changed:
        _write_all(cfg)

    # One-time capture of the user's current config into a saved "My setup"
    # profile (so adopting Stage 7 profiles never loses their tuning). Idempotent
    # and additive; local import avoids a circular dependency (presets imports
    # config). Runs after the additive backfill above so the section exists.
    try:
        from .engine import presets
        presets.seed_user_setup_once()
    except Exception:
        pass


def first_run_pending() -> bool:
    """True until the one-time first-run notice has been acknowledged. The flag
    is stored as a top-level key via the add-on's normal config channel (never a
    hand-edit of meta.json); ensure_defaults leaves unknown keys untouched."""
    return not bool(_all().get("_first_run_warned", False))


def mark_first_run_done() -> None:
    cfg = _all()
    cfg["_first_run_warned"] = True
    _write_all(cfg)


def suite_enabled() -> bool:
    """The master switch. When False, every feature is inert."""
    return bool(_all().get("enabled", DEFAULTS["enabled"]))


def set_suite_enabled(value: bool) -> None:
    cfg = _all()
    cfg["enabled"] = bool(value)
    _write_all(cfg)


def get_section(name: str) -> dict:
    """A feature's settings, with defaults filled in for any missing keys."""
    base = dict(DEFAULTS.get(name, {}))
    saved = _all().get(name)
    if isinstance(saved, dict):
        base.update(saved)
    return base


def save_section(name: str, data: dict) -> None:
    cfg = _all()
    cfg[name] = data
    _write_all(cfg)
