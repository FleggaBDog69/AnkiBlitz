"""Profiles (presets): named, whole-config snapshots of AnkiBlitz's *feel*.

A profile is an overlay of behavioural keys across the tunable sections —
reveal speed, auto-reveal timing, anti-pressure, Focus Lock, and the Blitz /
Pomodoro launch defaults — so one click flips the entire feel. It deliberately
leaves collection-specific keys alone (note-type / deck exclusion lists, quick
picks, the music URL and the AnkiBlitz master switch) so switching profiles never
silently wipes them.

Three built-ins ship as code constants (never written into config, so config.json
stays small): **Morning**, **Exam Mode**, **Casual**. User-saved profiles — and
a one-time auto-capture of the user's current setup ("My setup") — live in the
``presets.saved`` config section. A saved profile that shares a built-in's name
shadows it (so a built-in can be customised, and re-appears if the shadow is
deleted).

This module is pure config (no Qt): callers own any tooltips / UI refresh.
Settings are read live per card, so an applied profile takes effect with no extra
refresh — the next card / launch / leave-check reads the new values.
"""

from ..config import get_section, save_section

# Section -> the behavioural keys a profile is allowed to capture / apply. Keys
# NOT listed here are never touched by a profile (exclusion lists, *_quick_picks,
# card_source, music.service/last_url, tts_base_wpm, the PB-tracking toggles, and
# the top-level suite ``enabled`` master switch).
PROFILE_SPEC = {
    "speed_focus": [
        "enabled", "base_seconds", "seconds_per_word", "min_delay_seconds",
        "max_delay_seconds", "unfamiliar_multiplier", "new_multiplier",
        "enable_on_new", "difficulty_weight", "min_post_seconds",
        "show_countdown", "warning_sound", "warning_at_percent",
    ],
    "word_reveal": [
        "enabled", "words_per_second", "reveal_mode", "chunk_words",
        "reveal_on_answer", "tts_auto_match",
    ],
    "sprint": [
        "enabled", "default_mode", "count_mode", "default_target",
        "default_time_minutes", "show_progress_bar", "show_card_counter",
        "show_elapsed_time", "show_live_accuracy", "show_again_count",
        "show_streak_counter", "streak_animations", "show_completion_screen",
        "completion_sound", "show_completion_accuracy", "hide_all_accuracy_stats",
    ],
    "focus": [
        "enabled", "apply_to_reviews", "lock_level", "lock_min_cards",
        "score_enabled", "score_include_accuracy", "idle_threshold_seconds",
        "target_seconds_per_card",
    ],
    "momentum": ["enabled", "near_end_cards", "near_end_seconds"],
    "quick_start": [
        "enabled", "launch_style", "countdown_seconds", "mode", "target",
        "min_due", "relaunch_on_new_day", "relaunch_after_hour",
    ],
    "pomodoro": [
        "enabled", "work_mode", "work_target", "break_minutes",
        "long_break_enabled", "long_break_every", "long_break_minutes", "cycles",
        "auto_return_level", "break_sound", "daily_goal", "end_summary",
        "carry_forward", "break_show_timeline", "break_show_journal",
        "break_show_focus_rating", "break_show_tips", "break_show_browser",
        "break_show_add_kg", "break_allow_extend",
    ],
    "music": ["enabled", "show_on_break", "show_dropdown", "show_on_home"],
}

# Built-in archetypes. Each is a {section: {key: value}} overlay; keys must fall
# within PROFILE_SPEC (enforced on apply). They needn't be exhaustive — any key a
# profile omits is left at its current value.
BUILTINS = {
    # Calm daily driver: gentle adaptive reveal, anti-pressure on, light lock,
    # momentum on, fraction Pomodoro, Quick Start a third of the pile.
    "Morning": {
        "speed_focus": {
            "enabled": True, "base_seconds": 2.0, "seconds_per_word": 0.20,
            "min_delay_seconds": 2.0, "max_delay_seconds": 15.0,
            "unfamiliar_multiplier": 1.2, "new_multiplier": 1.5,
            "enable_on_new": True, "difficulty_weight": 0.20,
            "show_countdown": True, "warning_sound": True, "warning_at_percent": 75,
        },
        "word_reveal": {
            "enabled": True, "words_per_second": 6.0, "reveal_mode": "words",
            "reveal_on_answer": False, "tts_auto_match": True,
        },
        "sprint": {
            "enabled": True, "default_mode": "cards", "count_mode": "unique",
            "default_target": 50, "hide_all_accuracy_stats": True,
            "show_progress_bar": True, "show_card_counter": True,
            "show_elapsed_time": True, "show_completion_screen": True,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 1,
            "score_enabled": True,
        },
        "momentum": {"enabled": True, "near_end_cards": 10, "near_end_seconds": 120},
        "quick_start": {
            "enabled": True, "launch_style": "immediate", "mode": "fraction",
            "target": 3, "min_due": 1, "relaunch_on_new_day": True,
        },
        "pomodoro": {
            "enabled": True, "work_mode": "fraction", "work_target": 3,
            "break_minutes": 5, "long_break_enabled": True, "long_break_every": 4,
            "long_break_minutes": 25, "auto_return_level": 2,
        },
        "music": {"enabled": True, "show_on_break": True},
    },

    # Intense: tight auto-reveal, faster reveal, lock to FINISH (reviews too),
    # 25-min time blocks that pull you back, big Quick Start, music minimised.
    "Exam Mode": {
        "speed_focus": {
            "enabled": True, "base_seconds": 1.5, "seconds_per_word": 0.15,
            "min_delay_seconds": 1.5, "max_delay_seconds": 8.0,
            "unfamiliar_multiplier": 1.15, "new_multiplier": 1.3,
            "enable_on_new": True, "difficulty_weight": 0.25,
            "show_countdown": True, "warning_sound": True, "warning_at_percent": 70,
        },
        "word_reveal": {
            "enabled": True, "words_per_second": 8.0, "reveal_mode": "words",
            "reveal_on_answer": False, "tts_auto_match": True,
        },
        "sprint": {
            "enabled": True, "default_mode": "cards", "count_mode": "unique",
            "default_target": 100, "default_time_minutes": 25,
            "hide_all_accuracy_stats": True, "show_progress_bar": True,
            "show_card_counter": True, "show_elapsed_time": True,
            "show_completion_screen": True,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": True, "lock_level": 3,
            "lock_min_cards": 15, "score_enabled": True,
            "target_seconds_per_card": 6.0,
        },
        "momentum": {"enabled": True, "near_end_cards": 15, "near_end_seconds": 180},
        "quick_start": {
            "enabled": True, "launch_style": "immediate", "mode": "cards",
            "target": 100, "min_due": 1,
        },
        "pomodoro": {
            "enabled": True, "work_mode": "time", "work_target": 25,
            "break_minutes": 5, "long_break_enabled": True, "long_break_every": 4,
            "long_break_minutes": 15, "auto_return_level": 3,
        },
        "music": {"enabled": True, "show_on_break": True, "show_dropdown": False,
                  "show_on_home": False},
    },

    # Low friction: generous reveal, no warning sound, no new-card timer, no lock,
    # no Quick Start, relaxed Pomodoro, music everywhere.
    "Casual": {
        "speed_focus": {
            "enabled": True, "base_seconds": 3.0, "seconds_per_word": 0.30,
            "min_delay_seconds": 3.0, "max_delay_seconds": 30.0,
            "unfamiliar_multiplier": 1.3, "new_multiplier": 2.0,
            "enable_on_new": False, "difficulty_weight": 0.15,
            "show_countdown": False, "warning_sound": False, "warning_at_percent": 80,
        },
        "word_reveal": {
            "enabled": True, "words_per_second": 5.0, "reveal_mode": "words",
            "reveal_on_answer": False, "tts_auto_match": True,
        },
        "sprint": {
            "enabled": True, "default_mode": "cards", "count_mode": "unique",
            "default_target": 25, "hide_all_accuracy_stats": True,
            "show_progress_bar": True, "show_card_counter": True,
            "show_elapsed_time": False, "show_completion_screen": True,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 0,
            "score_enabled": True,
        },
        "momentum": {"enabled": False},
        "quick_start": {"enabled": False},
        "pomodoro": {
            "enabled": True, "work_mode": "cards", "work_target": 20,
            "break_minutes": 10, "long_break_enabled": True, "long_break_every": 3,
            "long_break_minutes": 20, "auto_return_level": 1,
        },
        "music": {"enabled": True, "show_on_break": True, "show_dropdown": True,
                  "show_on_home": True},
    },

    # The default "I'm doing a Blitz" feel: brisk auto-reveal, fast word reveal,
    # progress + completion on, a confirm-to-leave Focus Lock, momentum on.
    "Blitz": {
        "speed_focus": {
            "enabled": True, "base_seconds": 1.5, "seconds_per_word": 0.15,
            "min_delay_seconds": 1.5, "max_delay_seconds": 9.0,
            "unfamiliar_multiplier": 1.15, "new_multiplier": 1.3,
            "enable_on_new": True, "difficulty_weight": 0.15,
            "show_countdown": True, "warning_sound": True, "warning_at_percent": 75,
        },
        "word_reveal": {
            "enabled": True, "words_per_second": 8.0, "reveal_mode": "words",
            "reveal_on_answer": False, "tts_auto_match": True,
        },
        "sprint": {
            "enabled": True, "default_mode": "cards", "count_mode": "unique",
            "default_target": 50, "hide_all_accuracy_stats": True,
            "show_progress_bar": True, "show_card_counter": True,
            "show_elapsed_time": True, "show_completion_screen": True,
            "completion_sound": True,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 2,
            "lock_min_cards": 10, "score_enabled": True,
        },
        "momentum": {"enabled": True, "near_end_cards": 10, "near_end_seconds": 120},
        "quick_start": {"enabled": False},
        "pomodoro": {
            "enabled": True, "work_mode": "cards", "work_target": 40,
            "break_minutes": 5, "auto_return_level": 2,
        },
        "music": {"enabled": True, "show_on_break": True},
    },

    # A plain, unpressured review: gentle auto-reveal + word reveal as quality-of-
    # life only — no Blitz chrome, no Focus Lock, no momentum, no Quick Start.
    "Standard review": {
        "speed_focus": {
            "enabled": True, "base_seconds": 3.0, "seconds_per_word": 0.30,
            "min_delay_seconds": 2.0, "max_delay_seconds": 20.0,
            "unfamiliar_multiplier": 1.3, "new_multiplier": 1.8,
            "enable_on_new": True, "difficulty_weight": 0.20,
            "show_countdown": False, "warning_sound": False, "warning_at_percent": 80,
        },
        "word_reveal": {
            "enabled": True, "words_per_second": 6.0, "reveal_mode": "words",
            "reveal_on_answer": False, "tts_auto_match": True,
        },
        "sprint": {
            "enabled": True, "default_mode": "cards", "count_mode": "unique",
            "default_target": 50, "hide_all_accuracy_stats": True,
            "show_progress_bar": False, "show_card_counter": False,
            "show_elapsed_time": False, "show_completion_screen": False,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 0,
            "score_enabled": False,
        },
        "momentum": {"enabled": False},
        "quick_start": {"enabled": False},
        "pomodoro": {"enabled": False},
        "music": {"enabled": True, "show_on_break": True},
    },
}

_SECTION = "presets"

# Human labels for the Focus Lock levels, used in profile summaries.
_LOCK_NAMES = {0: "off", 1: "confirm", 2: "penalty", 3: "finish"}


def summary_lines(name: str) -> list:
    """The handful of *defining* settings for a profile, as short human strings —
    so the picker can show what each profile actually does. Reads the resolved
    overlay (a saved profile shadows a same-named built-in); only reports keys the
    profile actually sets."""
    ov = resolve(name)
    if not isinstance(ov, dict):
        return []
    lines = []
    sf = ov.get("speed_focus", {})
    if sf:
        if sf.get("enabled", True):
            parts = []
            if "base_seconds" in sf:
                parts.append(f"base {sf['base_seconds']:g}s")
            if "min_delay_seconds" in sf and "max_delay_seconds" in sf:
                parts.append(f"{sf['min_delay_seconds']:g}–{sf['max_delay_seconds']:g}s")
            lines.append("Auto-reveal: " + (", ".join(parts) if parts else "on"))
        else:
            lines.append("Auto-reveal: off")
    wr = ov.get("word_reveal", {})
    if wr:
        if wr.get("enabled", True):
            wps = wr.get("words_per_second")
            lines.append(f"Word reveal: {wps:g} words/s" if wps is not None else "Word reveal: on")
        else:
            lines.append("Word reveal: off")
    fc = ov.get("focus", {})
    if "lock_level" in fc:
        lvl = _LOCK_NAMES.get(int(fc.get("lock_level", 0)), str(fc.get("lock_level")))
        scope = " incl. reviews" if fc.get("apply_to_reviews") else ""
        lines.append(f"Focus Lock: {lvl}{scope}")
    qs = ov.get("quick_start", {})
    if "enabled" in qs:
        lines.append("Quick Start: " + ("on" if qs.get("enabled") else "off"))
    pm = ov.get("pomodoro", {})
    if "enabled" in pm:
        lines.append(f"Pomodoro: {pm.get('work_mode', 'cards')} blocks"
                     if pm.get("enabled") else "Pomodoro: off")
    if ov.get("sprint", {}).get("hide_all_accuracy_stats"):
        lines.append("Anti-pressure: accuracy hidden")
    return lines


def summary_text(name: str, sep: str = " · ") -> str:
    return sep.join(summary_lines(name))


def _presets() -> dict:
    """The presets section, with ``saved`` guaranteed a dict."""
    p = get_section(_SECTION)
    if not isinstance(p.get("saved"), dict):
        p["saved"] = {}
    return p


def _saved() -> dict:
    return _presets().get("saved", {})


def list_profiles() -> list:
    """Built-in names (fixed order) then user-saved names not shadowing a built-in."""
    names = list(BUILTINS.keys())
    for n in _saved():
        if n not in BUILTINS:
            names.append(n)
    return names


def is_builtin(name: str) -> bool:
    return name in BUILTINS and name not in _saved()


def active_name() -> str:
    p = _presets()
    name = p.get("active")
    if name and (name in BUILTINS or name in p.get("saved", {})):
        return name
    return next(iter(BUILTINS), "")


def resolve(name: str):
    """The overlay for ``name`` — a user-saved profile shadows a same-named
    built-in. Returns None if the name is unknown."""
    saved = _saved()
    if name in saved:
        return saved[name]
    return BUILTINS.get(name)


def snapshot_current() -> dict:
    """Project the live config down to the whitelisted profile keys."""
    snap = {}
    for section, keys in PROFILE_SPEC.items():
        cfg = get_section(section)
        sub = {k: cfg[k] for k in keys if k in cfg}
        if sub:
            snap[section] = sub
    return snap


def apply_profile(name: str) -> bool:
    """Overlay a profile onto the live config (whitelisted keys only) and mark it
    active. Returns False for an unknown name. An explicit, user-initiated
    overwrite — never auto-applied."""
    overlay = resolve(name)
    if not isinstance(overlay, dict):
        return False
    for section, allowed in PROFILE_SPEC.items():
        sub = overlay.get(section)
        if not isinstance(sub, dict):
            continue
        cfg = get_section(section)
        for k, v in sub.items():
            if k in allowed:
                cfg[k] = v
        save_section(section, cfg)
    p = _presets()
    p["active"] = name
    save_section(_SECTION, p)
    return True


def save_current_as(name: str) -> bool:
    """Snapshot the live config into a named saved profile and make it active."""
    name = (name or "").strip()
    if not name:
        return False
    p = _presets()
    saved = p.get("saved")
    if not isinstance(saved, dict):
        saved = {}
    saved[name] = snapshot_current()
    p["saved"] = saved
    p["active"] = name
    save_section(_SECTION, p)
    return True


def delete_profile(name: str) -> bool:
    """Delete a saved profile (built-ins can't be deleted; deleting a shadow
    restores the built-in). Returns whether anything was removed."""
    p = _presets()
    saved = p.get("saved")
    if not isinstance(saved, dict) or name not in saved:
        return False
    del saved[name]
    p["saved"] = saved
    if p.get("active") == name:
        p["active"] = name if name in BUILTINS else next(iter(BUILTINS), "")
    save_section(_SECTION, p)
    return True


def seed_user_setup_once() -> None:
    """Once, capture the user's current config into a saved 'My setup' profile and
    make it active — so adopting profiles never loses their existing tuning. Idem-
    potent via a ``_seeded`` flag; additive (adds a saved profile, mutates no
    feature section); writes through the add-on's normal config channel only."""
    p = _presets()
    if p.get("_seeded"):
        return
    saved = p.get("saved")
    if not isinstance(saved, dict):
        saved = {}
    if "My setup" not in saved:
        saved["My setup"] = snapshot_current()
    p["saved"] = saved
    if not p.get("active"):
        p["active"] = "My setup"
    p["_seeded"] = True
    save_section(_SECTION, p)
