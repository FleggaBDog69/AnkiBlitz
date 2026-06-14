"""Profiles (presets): named snapshots of AnkiBlitz's *feel*.

A profile flips the **feel** of reviewing in one click — the adaptive auto-reveal
pace, the Focus Lock, the near-end momentum nudge, and the anti-pressure / HUD
display toggles. It deliberately **does not** touch:

  * the **session shape** you pick each launch (Blitz mode / target / count mode,
    Quick Start, Pomodoro work blocks) — you choose that in the Start dialog, every
    time, regardless of profile;
  * the **word-reveal speed** (one reading pace, the same across every profile);
  * the **music** player (your station/visibility stay put);
  * collection-specific keys (note-type / deck exclusion lists, quick picks, the
    fixed-time picture lists, the music URL) and the AnkiBlitz master switch.

So switching profiles never silently changes how a session is launched, how fast
words fade in, what's playing, or which decks are excluded.

Three built-ins ship as code constants: **Default** (the everyday review feel),
**Blitz** (a committed, locked-in run), **Relaxed** (low friction — studying with
mates or half-distracted). User-saved profiles — and a one-time auto-capture of
the user's current setup ("My setup") — live in the ``presets.saved`` config
section. A saved profile that shares a built-in's name shadows it (so a built-in
can be customised, and re-appears if the shadow is deleted).

This module is pure config (no Qt): callers own any tooltips / UI refresh.
Settings are read live per card, so an applied profile takes effect with no extra
refresh — the next card / launch / leave-check reads the new values.
"""

from ..config import get_section, save_section

# Section -> the behavioural keys a profile is allowed to capture / apply. Keys
# NOT listed here are never touched by a profile. By design this whitelist covers
# only the *feel*: auto-reveal pace, the in-session HUD / anti-pressure display,
# Focus Lock, and momentum. It deliberately omits the whole ``word_reveal``,
# ``quick_start``, ``pomodoro`` and ``music`` sections, plus ``sprint``'s launch
# keys (mode / target / count_mode / time) — those are session-shape, reading
# pace and playback choices the user owns globally, not per profile.
PROFILE_SPEC = {
    "speed_focus": [
        "enabled", "base_seconds", "seconds_per_word", "min_delay_seconds",
        "max_delay_seconds", "unfamiliar_multiplier", "new_multiplier",
        "enable_on_new", "difficulty_weight", "min_post_seconds",
        "show_countdown", "warning_sound", "warning_at_percent",
    ],
    # Only the in-session display / anti-pressure toggles — NOT default_mode,
    # default_target, count_mode or default_time_minutes (those are session shape,
    # chosen per launch and left alone by profiles).
    "sprint": [
        "show_progress_bar", "show_card_counter", "show_elapsed_time",
        "show_live_accuracy", "show_again_count", "show_streak_counter",
        "streak_animations", "show_completion_screen", "completion_sound",
        "show_completion_accuracy", "hide_all_accuracy_stats",
    ],
    "focus": [
        "enabled", "apply_to_reviews", "lock_level", "lock_min_cards",
        "score_enabled", "score_include_accuracy", "idle_threshold_seconds",
        "target_seconds_per_card",
    ],
    "momentum": ["enabled", "near_end_cards", "near_end_seconds"],
}

# Built-in archetypes. Each is a {section: {key: value}} overlay; keys must fall
# within PROFILE_SPEC (enforced on apply). They needn't be exhaustive — any key a
# profile omits is left at its current value. Profiles govern *feel* only: the
# auto-reveal pace, the in-session HUD / anti-pressure, Focus Lock and momentum.
# They never set the session shape (you pick that each launch), the word-reveal
# speed, or the music — those endure across every profile.
BUILTINS = {
    # The everyday review feel and the active profile out of the box: a relaxed
    # ~7s auto-reveal on a typical card (base 3s + length + difficulty), a quiet
    # countdown, no Focus Lock, a gentle near-end nudge. Use this for normal daily
    # reviews — it's the "standard review session" feel.
    "Default": {
        "speed_focus": {
            "enabled": True, "base_seconds": 3.0, "seconds_per_word": 0.30,
            "min_delay_seconds": 2.0, "max_delay_seconds": 20.0,
            "unfamiliar_multiplier": 1.2, "new_multiplier": 1.5,
            "enable_on_new": True, "difficulty_weight": 0.20,
            "show_countdown": True, "warning_sound": False, "warning_at_percent": 75,
        },
        "sprint": {
            "hide_all_accuracy_stats": True, "show_progress_bar": True,
            "show_card_counter": True, "show_elapsed_time": True,
            "show_completion_screen": True, "completion_sound": False,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 0,
            "score_enabled": True,
        },
        "momentum": {"enabled": True, "near_end_cards": 10, "near_end_seconds": 120},
    },

    # A committed, locked-in run — what you switch to when you start a real Blitz:
    # brisk auto-reveal (base 1.5s), countdown + pre-reveal warning, a penalty
    # Focus Lock (level 2) so bailing costs Focus Score, full HUD with a completion
    # chime, momentum on.
    "Blitz": {
        "speed_focus": {
            "enabled": True, "base_seconds": 1.5, "seconds_per_word": 0.15,
            "min_delay_seconds": 1.5, "max_delay_seconds": 9.0,
            "unfamiliar_multiplier": 1.15, "new_multiplier": 1.3,
            "enable_on_new": True, "difficulty_weight": 0.15,
            "show_countdown": True, "warning_sound": True, "warning_at_percent": 75,
        },
        "sprint": {
            "hide_all_accuracy_stats": True, "show_progress_bar": True,
            "show_card_counter": True, "show_elapsed_time": True,
            "show_completion_screen": True, "completion_sound": True,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 2,
            "lock_min_cards": 10, "score_enabled": True,
        },
        "momentum": {"enabled": True, "near_end_cards": 10, "near_end_seconds": 120},
    },

    # Low friction for studying with mates or half-distracted: generous auto-reveal
    # (base 3s, long ceiling), no countdown/warning pressure, no Focus Lock, no
    # near-end nagging, a minimal HUD.
    "Relaxed": {
        "speed_focus": {
            "enabled": True, "base_seconds": 3.0, "seconds_per_word": 0.35,
            "min_delay_seconds": 3.0, "max_delay_seconds": 30.0,
            "unfamiliar_multiplier": 1.3, "new_multiplier": 1.8,
            "enable_on_new": False, "difficulty_weight": 0.15,
            "show_countdown": False, "warning_sound": False, "warning_at_percent": 80,
        },
        "sprint": {
            "hide_all_accuracy_stats": True, "show_progress_bar": False,
            "show_card_counter": True, "show_elapsed_time": False,
            "show_completion_screen": True, "completion_sound": False,
        },
        "focus": {
            "enabled": True, "apply_to_reviews": False, "lock_level": 0,
            "score_enabled": False,
        },
        "momentum": {"enabled": False},
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
    fc = ov.get("focus", {})
    if "lock_level" in fc:
        lvl = _LOCK_NAMES.get(int(fc.get("lock_level", 0)), str(fc.get("lock_level")))
        scope = " incl. reviews" if fc.get("apply_to_reviews") else ""
        lines.append(f"Focus Lock: {lvl}{scope}")
    mo = ov.get("momentum", {})
    if "enabled" in mo:
        lines.append("Momentum nudge: " + ("on" if mo.get("enabled") else "off"))
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
