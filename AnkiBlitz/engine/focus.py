"""Focus features (Stage 6).

Two independent pieces, both keyed off the ``focus`` config section:

  - **Focus Lock** — how hard it is to leave (0 none → 3 finish). Governs a
    running Blitz always, and ordinary review sessions when ``apply_to_reviews``
    is on. The leave decision lives in ``leave_decision``; sprint.py acts on it.
  - **Focus Score** — a 0–100 blend of completion, speed, engagement (idle), and
    optionally accuracy, computed by ``compute_score`` (Blitz sessions only).

Everything here is pure and defensive: a malformed session or config yields a
sane default rather than raising into the reviewer.
"""

from ..config import get_section

# Lock levels.
LOCK_NONE = 0
LOCK_CONFIRM = 1     # confirm prompt before leaving
LOCK_MIN_CARDS = 2   # can't leave until lock_min_cards are done
LOCK_FINISH = 3      # can't leave until the Blitz is finished

# Focus Score component weights (renormalised over whichever are enabled).
_WEIGHTS = {
    "completion": 0.35,
    "engagement": 0.25,
    "speed": 0.20,
    "accuracy": 0.20,
}


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def lock_level(cfg: dict) -> int:
    """The active lock level, or 0 when Focus is off entirely."""
    if not cfg.get("enabled", True):
        return LOCK_NONE
    try:
        return max(0, min(3, int(cfg.get("lock_level", 0))))
    except (TypeError, ValueError):
        return LOCK_NONE


def applies_to_reviews(cfg: dict) -> bool:
    """Whether Focus Lock also governs ordinary (non-Blitz) review sessions."""
    return bool(cfg.get("enabled", True)) and bool(cfg.get("apply_to_reviews", True))


def leave_decision(s, cfg: dict):
    """Decide what happens when the user tries to leave a locked session.

    ``s`` is a Blitz session or a normal-review guard; both expose ``cards_done``,
    ``unit``, ``target_reached()`` and a mutable ``leave_target`` attribute.

    Returns one of:
      - ``("free", "")``       — let the normal cancel/momentum path run.
      - ``("confirm", "")``    — ask before leaving.
      - ``("block", msg)``     — refuse: bounce back to review, show ``msg``.
    """
    level = lock_level(cfg)
    if level == LOCK_CONFIRM:
        return ("confirm", "")
    if level == LOCK_MIN_CARDS:
        # Trying to leave imposes a "penalty lap": clear lock_min_cards MORE
        # cards from this point, then (once cleared) confirm before leaving.
        n = max(1, int(cfg.get("lock_min_cards", 10)))
        if getattr(s, "leave_target", None) is None:
            s.leave_target = s.cards_done + n
        remaining = int(s.leave_target) - s.cards_done
        if remaining > 0:
            return ("block", f"{remaining} more {s.unit} before you can leave.")
        return ("confirm", "")
    if level == LOCK_FINISH:
        if not s.target_reached():
            return ("block", getattr(s, "finish_msg", "Finish before you can leave."))
        return ("free", "")
    return ("free", "")


def keeps_session_on_focus_loss(cfg: dict) -> bool:
    """Level 3 keeps the session alive (and re-raises Anki) when focus is lost to
    another app; lower levels let the focus-loss cancel stand."""
    return lock_level(cfg) == LOCK_FINISH


def compute_score(s, cfg: dict) -> dict:
    """A 0–100 Focus Score for a (usually completed) session.

    Returns ``{"score": int, "parts": {name: int_0_100, ...}}``. ``parts`` holds
    only the components that were counted, each as a 0–100 percentage.
    """
    if s.answers == 0:
        return {"score": 0, "parts": {}}

    elapsed = s.elapsed_seconds()
    comps = {}

    # Completion — how far toward the target (capped at 100%).
    comps["completion"] = _clamp01(s.progress_fraction())

    # Engagement — share of time actually spent answering (not idle).
    if elapsed > 0:
        comps["engagement"] = _clamp01(1.0 - (s.idle_seconds / elapsed))
    else:
        comps["engagement"] = 1.0

    # Speed — pace vs the configured reference; at/under target ⇒ full marks.
    try:
        target_spc = float(cfg.get("target_seconds_per_card", 8.0))
    except (TypeError, ValueError):
        target_spc = 8.0
    avg = s.avg_seconds_per_card()
    if avg > 0 and target_spc > 0:
        comps["speed"] = _clamp01(target_spc / avg)
    elif s.unique_cards == 0:
        comps["speed"] = 0.0
    else:
        comps["speed"] = 1.0

    # Accuracy — opt-in, and never shown when the anti-pressure switch is on.
    hide_acc = get_section("sprint").get("hide_all_accuracy_stats", True)
    if cfg.get("score_include_accuracy", True) and not hide_acc and s.answers > 0:
        comps["accuracy"] = _clamp01(s.correct_count / s.answers)

    # Weighted mean over whatever components are present.
    total_w = sum(_WEIGHTS[k] for k in comps)
    if total_w <= 0:
        return {"score": 0, "parts": {}}
    score = sum(comps[k] * _WEIGHTS[k] for k in comps) / total_w

    return {
        "score": int(round(score * 100)),
        "parts": {k: int(round(v * 100)) for k, v in comps.items()},
    }
