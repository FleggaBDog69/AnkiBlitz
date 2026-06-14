"""Blitz session lifecycle.

State lives in session.py (the single source of truth); the progress bar is
rendered by the JS bundle via injection.push_progress(). This module drives the
lifecycle only: the start dialog (card-count / time / fraction-of-due), the
answer/state hooks, the focus-loss watcher, and the end-of-Blitz summary.

A Blitz ends three ways:
  - target reached (cards/fraction) or the clock runs out (time)  -> completed
  - the queue empties before the target                          -> completed
  - the user leaves the reviewer or Anki loses focus             -> cancelled
Cancelled sessions keep no record.
"""

import math

from aqt import mw, gui_hooks
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QComboBox, QDialogButtonBox, QMessageBox, QObject, QEvent, QApplication,
    QStackedWidget, QWidget, QTimer,
)
from aqt.utils import tooltip

from ..config import get_section, suite_enabled
from . import session, injection, stats, focus, presets
from .session import MODE_CARDS, MODE_TIME, MODE_FRACTION
from .stats import record_completed_sprint


# ----- Due-count helpers -----

def _due_total() -> int:
    """New + learning + review cards due in the currently selected deck."""
    try:
        return int(sum(mw.col.sched.counts()))
    except Exception:
        return 0


def _queue_empty() -> bool:
    return _due_total() == 0


def _largest_due_deck_id():
    """The deck whose subtree has the most cards due right now, or None if the
    collection has nothing due. Used by 'Blitz all due cards' so it never no-ops
    just because the deck Anki happens to have selected (e.g. on the deck list)
    is empty."""
    try:
        tree = mw.col.sched.deck_due_tree()
    except Exception:
        return None
    best = [0, None]  # [due, deck_id]

    def node_due(node) -> int:
        return (int(getattr(node, "new_count", 0))
                + int(getattr(node, "learn_count", 0))
                + int(getattr(node, "review_count", 0)))

    def visit(node) -> None:
        for child in getattr(node, "children", []):
            due = node_due(child)
            if due > best[0]:
                best[0], best[1] = due, getattr(child, "deck_id", None)
            visit(child)

    visit(tree)
    return best[1]


# ----- Start dialog -----

def _quick_row(spin, values):
    row = QHBoxLayout()
    for n in values:
        b = QPushButton(str(n))
        b.setMaximumWidth(64)
        b.clicked.connect(lambda _, v=n: spin.setValue(v))
        row.addWidget(b)
    row.addStretch(1)
    return row


def start_blitz_dialog():
    if not (suite_enabled() and get_section("sprint").get("enabled", True)):
        tooltip("Blitz is turned off in AnkiBlitz settings.")
        return
    if mw.col is None:
        return

    cfg = get_section("sprint")
    due_now = _due_total()
    if due_now <= 0:
        tooltip("Nothing due right now — load a deck first.")
        return

    dlg = QDialog(mw)
    dlg.setWindowTitle("Start Blitz")
    dlg.setMinimumWidth(380)
    lay = QVBoxLayout(dlg)

    lay.addWidget(QLabel(f"<b>{due_now}</b> cards due right now."))

    # One-off launch picker: pre-fill mode + target from a profile WITHOUT
    # applying it (your active profile is unchanged). "Current settings" keeps the
    # Blitz defaults. Full feel (Focus Lock etc.) still follows the active profile.
    launch_combo = QComboBox()
    launch_combo.addItem("Current settings", None)
    for _name in presets.list_profiles():
        launch_combo.addItem(_name, _name)
    lay.addWidget(QLabel("Launch as:"))
    lay.addWidget(launch_combo)

    lay.addWidget(QLabel("Blitz mode:"))
    mode_combo = QComboBox()
    mode_combo.addItem("Card count", MODE_CARDS)
    mode_combo.addItem("Time", MODE_TIME)
    mode_combo.addItem("Fraction of due", MODE_FRACTION)
    lay.addWidget(mode_combo)

    stack = QStackedWidget()

    # --- page 0: card count ---
    cards_page = QWidget()
    cpl = QVBoxLayout(cards_page)
    cpl.setContentsMargins(0, 0, 0, 0)
    card_spin = QSpinBox()
    card_spin.setRange(1, 9999)
    card_spin.setValue(int(cfg.get("default_target", 50)))
    card_spin.setSuffix(" cards")
    cpl.addLayout(_quick_row(card_spin, cfg.get("quick_picks", [25, 50, 100])))
    cpl.addWidget(card_spin)
    stack.addWidget(cards_page)

    # --- page 1: time ---
    time_page = QWidget()
    tpl = QVBoxLayout(time_page)
    tpl.setContentsMargins(0, 0, 0, 0)
    time_spin = QSpinBox()
    time_spin.setRange(1, 600)
    time_spin.setValue(int(cfg.get("default_time_minutes", 15)))
    time_spin.setSuffix(" min")
    tpl.addLayout(_quick_row(time_spin, cfg.get("time_quick_picks", [10, 15, 25])))
    tpl.addWidget(time_spin)
    stack.addWidget(time_page)

    # --- page 2: fraction of due ---
    frac_page = QWidget()
    fpl = QVBoxLayout(frac_page)
    fpl.setContentsMargins(0, 0, 0, 0)
    denom_spin = QSpinBox()
    denom_spin.setRange(2, 50)
    picks = cfg.get("fraction_quick_picks", [2, 3])
    denom_spin.setValue(int(picks[0]) if picks else 2)
    denom_spin.setPrefix("1 / ")
    frac_quick = QHBoxLayout()
    for d in picks:
        b = QPushButton(f"1/{d}")
        b.setMaximumWidth(64)
        b.clicked.connect(lambda _, v=d: denom_spin.setValue(v))
        frac_quick.addWidget(b)
    frac_quick.addStretch(1)
    fpl.addLayout(frac_quick)
    fpl.addWidget(denom_spin)
    frac_preview = QLabel()
    frac_preview.setStyleSheet("color: gray; font-size: 11px;")
    fpl.addWidget(frac_preview)
    stack.addWidget(frac_page)

    def _update_frac():
        d = denom_spin.value()
        frac_preview.setText(f"≈ {max(1, math.ceil(due_now / d))} of {due_now} due cards")
    denom_spin.valueChanged.connect(_update_frac)
    _update_frac()

    lay.addWidget(stack)
    mode_combo.currentIndexChanged.connect(stack.setCurrentIndex)
    start_idx = mode_combo.findData(cfg.get("default_mode", "cards"))
    if start_idx >= 0:
        mode_combo.setCurrentIndex(start_idx)
        stack.setCurrentIndex(start_idx)

    def _prefill_from_profile(idx):
        name = launch_combo.itemData(idx)
        if not name:
            return
        ov = presets.resolve(name) or {}
        sp = ov.get("sprint", {})
        qs = ov.get("quick_start", {})
        if "default_target" in sp:
            card_spin.setValue(int(sp["default_target"]))
        if "default_time_minutes" in sp:
            time_spin.setValue(int(sp["default_time_minutes"]))
        if qs.get("mode") == MODE_FRACTION and qs.get("target"):
            denom_spin.setValue(max(2, int(qs["target"])))
        m = sp.get("default_mode")
        if m:
            mi = mode_combo.findData(m)
            if mi >= 0:
                mode_combo.setCurrentIndex(mi)
    launch_combo.currentIndexChanged.connect(_prefill_from_profile)

    # Counting-rule reminder (the bar's unit).
    count_mode = cfg.get("count_mode", "unique")
    unit_txt = ("distinct cards (re-reviews of the same card don't advance the bar)"
                if count_mode == "unique" else
                "every answer (re-reviews count again)")
    count_hint = QLabel(f"Progress counts {unit_txt}.")
    count_hint.setWordWrap(True)
    count_hint.setStyleSheet("color: gray; font-size: 11px; margin-top: 6px;")
    lay.addWidget(count_hint)

    deck_combo = None
    if cfg.get("card_source") == "pick_deck":
        lay.addWidget(QLabel("Deck:"))
        deck_combo = QComboBox()
        for d in mw.col.decks.all_names_and_ids():
            deck_combo.addItem(d.name, d.id)
        lay.addWidget(deck_combo)

    note = QLabel(
        "Switching screens or losing focus cancels the Blitz with no record.\n"
        "Grade honestly — pressing Again when you should is more valuable than streaks."
    )
    note.setWordWrap(True)
    note.setStyleSheet("color: gray; font-size: 11px; margin-top: 8px;")
    lay.addWidget(note)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Start")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return

    mode = mode_combo.currentData()
    if mode == MODE_TIME:
        value = time_spin.value()
    elif mode == MODE_FRACTION:
        value = denom_spin.value()
    else:
        value = card_spin.value()
    deck_id = deck_combo.currentData() if deck_combo else None
    _begin_blitz(mode, value, deck_id, cfg)


def _begin_blitz(mode, value, deck_id, cfg, is_quick_start=False, is_pomodoro=False,
                 paused=False, label_override=None):
    if session.is_running():
        ok = QMessageBox.question(
            mw, "Blitz already active",
            "A Blitz is already in progress. Cancel it and start a new one?",
        )
        if ok != QMessageBox.StandardButton.Yes:
            return
        session.clear()

    if deck_id is not None:
        mw.col.decks.select(deck_id)

    # Recompute due against the (possibly just-selected) deck.
    due = _due_total()
    if due <= 0:
        tooltip("Nothing due in that deck.")
        return

    count_mode = cfg.get("count_mode", "unique")
    target_cards = 0
    target_seconds = 0.0

    if mode == MODE_TIME:
        minutes = max(1, int(value))
        target_seconds = minutes * 60
        label = f"{minutes} min"
    elif mode == MODE_FRACTION:
        denom = max(2, int(value))
        target_cards = max(1, math.ceil(due / denom))
        label = f"1/{denom} of due ({target_cards} cards)"
    else:  # cards
        target_cards = max(1, int(value))
        if target_cards > due:
            target_cards = due
            tooltip(f"Only {due} cards due — blitzing all of them.", period=2500)
        label = f"{target_cards} cards"

    if label_override:
        label = label_override

    session.start(
        mode,
        target_cards=target_cards,
        target_seconds=target_seconds,
        count_mode=count_mode,
        deck_id=deck_id,
        label=label,
        is_quick_start=is_quick_start,
        is_pomodoro=is_pomodoro,
        idle_threshold=float(get_section("focus").get("idle_threshold_seconds", 60)),
        paused=paused,
    )
    # A Blitz takes over from any normal-review Focus Lock guard.
    global _review_guard
    _review_guard = None
    # An "armed" Pomodoro (break over at notify-level) resumes on any Blitz the
    # user starts manually — flag this one as the next work block if so.
    if not is_pomodoro:
        from . import pomodoro
        pomodoro.note_manual_blitz_started(session.get_active())
    mw.moveToState("review")
    injection.push_progress()


def start_quick_start(paused: bool = False) -> bool:
    """Launch a Blitz from the Quick Start preset. Returns whether it started.

    ``paused`` opens it on the first card but holds the auto-reveal and the
    session clock until the first key/click (the overnight relaunch path)."""
    if not (suite_enabled() and get_section("sprint").get("enabled", True)):
        return False
    if mw.col is None or session.is_running():
        return False
    if _due_total() <= 0:
        return False

    qs = get_section("quick_start")
    sprint_cfg = get_section("sprint")
    mode = qs.get("mode", "cards")
    if mode == MODE_TIME:
        value = max(1, int(qs.get("target", 15)))
    elif mode == MODE_FRACTION:
        value = max(2, int(qs.get("target", 2)))
    else:
        mode = MODE_CARDS
        value = max(1, int(qs.get("target", 50)))
    _begin_blitz(mode, value, None, sprint_cfg, is_quick_start=True, paused=paused)
    return True


def start_blitz_now(mode=None, value=None, deck_id=None) -> bool:
    """Start a Blitz immediately — no start dialog.

    ``mode`` picks the mode (time / cards / fraction); when omitted the
    configured ``default_mode`` is used. ``value`` is the target (minutes / cards
    / denominator); when omitted it's taken from the Blitz defaults. Backs the
    home/overview widget quick-launch buttons.
    """
    if not (suite_enabled() and get_section("sprint").get("enabled", True)):
        tooltip("Blitz is turned off in AnkiBlitz settings.")
        return False
    if mw.col is None:
        return False
    if _due_total() <= 0:
        tooltip("Nothing due right now — load a deck first.")
        return False

    cfg = get_section("sprint")
    mode = mode or cfg.get("default_mode", "cards")
    if mode == MODE_TIME:
        value = int(value) if value else int(cfg.get("default_time_minutes", 15))
        value = max(1, value)
    elif mode == MODE_FRACTION:
        if value:
            value = max(2, int(value))
        else:
            picks = cfg.get("fraction_quick_picks", [2, 3])
            value = max(2, int(picks[0]) if picks else 2)
    else:
        mode = MODE_CARDS
        value = max(1, int(value) if value else int(cfg.get("default_target", 50)))
    _begin_blitz(mode, value, deck_id, cfg)
    return session.is_running()


def start_blitz_all_due() -> bool:
    """Blitz every card currently due — a cards-mode Blitz whose target is the
    whole due pile, so it finishes when you've cleared your dues (or the queue
    empties first). Backs the 'Finish all due' button."""
    if not (suite_enabled() and get_section("sprint").get("enabled", True)):
        tooltip("Blitz is turned off in AnkiBlitz settings.")
        return False
    if mw.col is None:
        return False
    # If the deck Anki currently has selected is empty (common when launched from
    # the deck list / home widget), switch to the deck with the most due so this
    # never silently does nothing.
    deck_id = None
    if _due_total() <= 0:
        deck_id = _largest_due_deck_id()
        if deck_id is None:
            tooltip("Nothing due anywhere right now.")
            return False
        mw.col.decks.select(deck_id)
    due = _due_total()
    if due <= 0:
        tooltip("Nothing due anywhere right now.")
        return False
    cfg = get_section("sprint")
    _begin_blitz(MODE_CARDS, due, deck_id, cfg,
                 label_override=f"All due ({due} cards)")
    return session.is_running()


def begin_pomodoro_work(state) -> bool:
    """Start a Blitz as a Pomodoro work block, using the cycle's preset."""
    if mw.col is None or session.is_running():
        return False
    sprint_cfg = get_section("sprint")
    mode = state.work_mode
    label_override = None
    if mode == MODE_TIME:
        value = max(1, int(state.work_target))
    elif mode == MODE_FRACTION:
        # Fixed split: the due pile was divided ONCE into N equal chunks at the
        # start of the run (PomodoroState.frac_chunk / frac_denom). Each block is
        # a fixed card-count Blitz for one chunk, labelled k/N.
        k = state.completed_blocks + 1
        mode = MODE_CARDS
        value = max(1, int(getattr(state, "frac_chunk", 0)) or max(2, int(state.work_target)))
        label_override = f"Fraction {k}/{max(2, int(getattr(state, 'frac_denom', state.work_target)))}"
    else:
        mode = MODE_CARDS
        value = max(1, int(state.work_target))
    _begin_blitz(mode, value, state.deck_id, sprint_cfg, is_pomodoro=True,
                 label_override=label_override)
    return session.is_running()


# ----- Hooks -----

def on_review_did_answer(reviewer, card, ease):
    """ease: 1=Again, 2=Hard, 3=Good, 4=Easy"""
    s = session.get_active()
    if s is None or s.completed:
        # No Blitz: feed the normal-review Focus Lock counter if one is armed.
        if _review_guard is not None:
            _review_guard.cards_done += 1
        return
    s.record_answer(getattr(card, "id", None), ease)
    if s.is_quick_start and s.answers == 1:
        stats.record_launch_to_first(s.launch_to_first_ms())
    if s.target_reached():
        _complete("time" if s.mode == MODE_TIME else "target")
    else:
        injection.push_progress()


def on_time_up():
    """The JS clock crossed the deadline (time mode).

    Don't cut the user off mid-card: if a card is in progress, let them finish
    it — the next graded answer trips ``target_reached()`` and completes the
    Blitz (see on_review_did_answer). Only end here if no card is in progress.
    """
    s = session.get_active()
    if not (s and not s.completed and s.mode == MODE_TIME):
        return
    if mw.reviewer and mw.reviewer.card:
        return
    _complete("time")


def on_state_change(new_state: str, old_state: str):
    entering = new_state == "review" and old_state != "review"
    leaving = new_state != "review" and old_state == "review"

    if entering:
        _maybe_arm_review_guard()
        return
    if not leaving:
        return

    # --- Leaving the reviewer ---
    if session.is_running():
        # Running out of due cards is success, not a bail-out.
        if _queue_empty():
            _complete("exhausted")
            return
        s = session.get_active()
        # Focus Lock takes precedence over momentum: it decides whether leaving
        # is allowed at all (block), needs confirming (confirm), or is free.
        decision, msg = focus.leave_decision(s, get_section("focus"))
        if decision == "block":
            _bounce_back(msg)
            return
        if decision == "confirm":
            _confirm_leave_intercept()
            return
        # Free to leave. Momentum protection: if you bail NEAR the end, offer to
        # keep going instead of silently cancelling.
        if get_section("momentum").get("enabled", True) and _near_end(s):
            _momentum_intercept(s)
        else:
            cancel_if_active(reason="left review screen")
        return

    # --- No Blitz: normal-review Focus Lock (if armed) ---
    global _review_guard
    if _review_guard is not None:
        decision, msg = focus.leave_decision(_review_guard, get_section("focus"))
        if decision == "block":
            _bounce_back(msg)
            return
        if decision == "confirm":
            _confirm_review_leave()
            return
        _review_guard = None  # free to go


# ----- Focus Lock -----

# A lightweight stand-in for a Blitz session so ordinary reviews can reuse
# focus.leave_decision. Counts answers since the review session was armed.
class _ReviewGuard:
    def __init__(self):
        self.cards_done = 0
        self.unit = "cards"
        self.leave_target = None
        self.finish_msg = "Clear all your due cards before you can leave."

    def target_reached(self) -> bool:
        return _queue_empty()


# The active normal-review guard, or None when reviews aren't locked.
_review_guard = None


def _maybe_arm_review_guard():
    """On entering the reviewer with no Blitz, arm a guard if reviews are locked.
    A bounce-back re-enters review with the guard already set — keep it (so its
    card count and any pending leave-penalty survive)."""
    global _review_guard
    if session.is_running():
        _review_guard = None
        return
    fcfg = get_section("focus")
    if focus.applies_to_reviews(fcfg) and focus.lock_level(fcfg) > 0:
        if _review_guard is None:
            _review_guard = _ReviewGuard()
    else:
        _review_guard = None


def _locked() -> bool:
    """A lock is in force right now — a running Blitz, or an armed review guard."""
    return session.is_running() or _review_guard is not None


def _bounce_back(msg: str):
    """Refuse to leave: return to the reviewer and explain why. Works for a Blitz
    (keeps the bar) or a locked review.

    Leaving the reviewer renders the destination screen into the web view
    asynchronously, and that render can land AFTER an immediate moveToState back —
    repainting the reviewer with the deck list and letting the user slip out
    (the visible "stutter"). So we bounce immediately, then force the reviewer to
    re-render once the leave transition has settled, guaranteeing it paints last.
    """
    def go(force: bool):
        if not _locked():
            return
        if force or mw.state != "review":
            mw.moveToState("review")
            if session.is_running():
                injection.push_progress()
    QTimer.singleShot(0, lambda: go(False))
    QTimer.singleShot(120, lambda: go(False))
    QTimer.singleShot(350, lambda: go(True))   # final word: reviewer renders last
    if msg:
        QTimer.singleShot(0, lambda: tooltip(msg, period=2500))


def _confirm_leave_intercept():
    QTimer.singleShot(0, _show_leave_confirm)


def _show_leave_confirm():
    global _intercepting
    s = session.get_active()
    if s is None or s.completed:
        return
    _intercepting = True
    try:
        box = QMessageBox(mw)
        box.setWindowTitle("Leave Blitz?")
        box.setText("Leaving now cancels this Blitz.")
        box.setInformativeText("Your progress won't be recorded. Leave anyway?")
        stay = box.addButton("Keep going", QMessageBox.ButtonRole.RejectRole)
        leave = box.addButton("Leave Blitz", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(stay)
        box.exec()
        clicked = box.clickedButton()
    finally:
        _intercepting = False

    if not session.is_running():
        return
    if clicked is leave:
        cancel_if_active(reason="left review screen")
    else:
        # Keeping going clears any level-2 leave penalty (a later leave starts
        # a fresh lap).
        s.leave_target = None
        mw.moveToState("review")
        injection.push_progress()


def _confirm_review_leave():
    QTimer.singleShot(0, _show_review_leave_confirm)


def _show_review_leave_confirm():
    """Normal-review counterpart to _show_leave_confirm: nothing to cancel, so
    leaving simply disarms the guard and lets the navigation stand."""
    global _intercepting, _review_guard
    if _review_guard is None:
        return
    _intercepting = True
    try:
        box = QMessageBox(mw)
        box.setWindowTitle("Leave review?")
        box.setText("Leave this review session?")
        stay = box.addButton("Keep studying", QMessageBox.ButtonRole.RejectRole)
        leave = box.addButton("Leave", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(stay)
        box.exec()
        clicked = box.clickedButton()
    finally:
        _intercepting = False

    if clicked is leave:
        _review_guard = None  # let the navigation away from review stand
    else:
        if _review_guard is not None:
            _review_guard.leave_target = None  # fresh lap next time
        mw.moveToState("review")


# ----- Momentum protection -----

# True while the keep-going prompt is open, so the focus watcher doesn't treat
# the dialog as "leaving the Blitz" and cancel it out from under us.
_intercepting = False


def _near_end(s) -> bool:
    if s.mode == MODE_TIME:
        within = float(get_section("momentum").get("near_end_seconds", 120))
        remaining = s.remaining_seconds()
        return 0 < remaining <= within
    within = int(get_section("momentum").get("near_end_cards", 10))
    remaining = s.target_cards - s.cards_done
    return 0 < remaining <= within


def _estimate_remaining_text(s) -> str:
    if s.mode == MODE_TIME:
        secs = s.remaining_seconds()
        cards_left = None
    else:
        cards_left = s.target_cards - s.cards_done
        avg = s.avg_seconds_per_card()
        secs = cards_left * avg if avg > 0 else 0.0
    bits = []
    if cards_left is not None:
        bits.append(f"{cards_left} card{'s' if cards_left != 1 else ''} from finishing")
    if secs > 0:
        if secs < 90:
            bits.append(f"~{int(round(secs))} s left")
        else:
            bits.append(f"~{secs / 60:.0f} min left")
    elif cards_left is None:
        bits.append("almost out of time")
    return " · ".join(bits) if bits else "almost done"


def _momentum_intercept(s):
    # The state has already flipped away from review; defer the dialog so we're
    # clear of the state-change hook before re-entering review.
    QTimer.singleShot(0, _show_momentum_dialog)


def _show_momentum_dialog():
    global _intercepting
    s = session.get_active()
    if s is None or s.completed:
        return
    _intercepting = True
    try:
        box = QMessageBox(mw)
        box.setWindowTitle("Almost done")
        box.setText("You're " + _estimate_remaining_text(s) + ".")
        box.setInformativeText("Keep going and finish this Blitz?")
        keep = box.addButton("Keep going", QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton("Quit Blitz", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(keep)
        box.exec()
        clicked = box.clickedButton()
    finally:
        _intercepting = False

    if not session.is_running():
        return
    if clicked is quit_btn:
        cancel_if_active(reason="left near the end")
    else:
        mw.moveToState("review")
        injection.push_progress()


def cancel_if_active(reason: str = ""):
    if not session.is_running():
        return
    was_pomodoro = session.get_active().is_pomodoro
    session.clear()
    injection.clear_progress()
    # Bailing out of a work block ends the whole Pomodoro cycle.
    if was_pomodoro:
        from . import pomodoro
        pomodoro.abort(reason)
    msg = "Blitz cancelled"
    if reason:
        msg += f" — {reason}"
    msg += ". No record kept."
    tooltip(msg, period=2500)


# ----- Completion -----

_REASON_TEXT = {
    "target": "Target reached",
    "time": "Time's up",
    "exhausted": "All due cards done",
}


def _complete(reason: str):
    s = session.get_active()
    if s is None or s.completed:
        return
    s.completed = True
    s.end_reason = reason
    cfg = get_section("sprint")

    fcfg = get_section("focus")
    score = focus.compute_score(s, fcfg) if fcfg.get("score_enabled", True) else None
    stats_after = record_completed_sprint(
        s.unique_cards, s.elapsed_seconds(),
        focus_score=(score["score"] if score else 0),
        idle_seconds=s.idle_seconds,
    )
    if s.is_quick_start:
        stats.record_quick_start_completed()
    snapshot = s
    session.clear()
    injection.clear_progress()

    # A Pomodoro work block hands off to the break screen instead of the usual
    # completion screen — the cycle continues.
    if snapshot.is_pomodoro:
        from . import pomodoro
        if pomodoro.is_active():
            pomodoro.on_work_complete(snapshot, stats_after, cfg)
            return

    if cfg.get("show_completion_screen", True):
        _show_completion(snapshot, stats_after, cfg, score)
    else:
        tooltip(f"Blitz complete: {snapshot.unique_cards} cards.", period=3000)


def _show_completion(s, stats_after, cfg, score=None):
    dlg = QDialog(mw)
    dlg.setWindowTitle("Blitz complete")
    dlg.setMinimumWidth(360)
    lay = QVBoxLayout(dlg)

    title = QLabel(f"✓ Blitz complete — {s.unique_cards} cards")
    title.setStyleSheet("font-size: 18px; font-weight: 600; margin-bottom: 2px;")
    lay.addWidget(title)

    reason = _REASON_TEXT.get(s.end_reason, "")
    sub = QLabel(f"{reason} · {s.label}" if reason else s.label)
    sub.setStyleSheet("color: gray; font-size: 12px; margin-bottom: 6px;")
    lay.addWidget(sub)

    secs = s.elapsed_seconds()

    def add(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 13px; margin: 2px 0;")
        lay.addWidget(lbl)

    # Focus Score headline (Stage 6) — with a one-line component breakdown.
    if score:
        sc = QLabel(f"⚡ Focus Score: {score['score']} / 100")
        sc.setStyleSheet("font-size: 15px; font-weight: 700; margin: 4px 0 1px;")
        lay.addWidget(sc)
        _names = {"completion": "completion", "speed": "speed",
                  "engagement": "focus", "accuracy": "accuracy"}
        parts = score.get("parts", {})
        bits = [f"{_names[k]} {parts[k]}" for k in
                ("completion", "speed", "engagement", "accuracy") if k in parts]
        if bits:
            br = QLabel(" · ".join(bits))
            br.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 4px;")
            lay.addWidget(br)

    # Core summary: cards, avg time, (accuracy below if allowed).
    add(f"Time: {secs / 60:.1f} min ({int(secs)} sec)")
    add(f"Average: {s.avg_seconds_per_card():.1f} s / card")
    add(f"Speed: {s.cards_per_min():.1f} cards/min")
    if s.idle_seconds >= 1:
        add(f"Idle: {s.idle_seconds / 60:.1f} min" if s.idle_seconds >= 60
            else f"Idle: {int(s.idle_seconds)} sec")
    if s.answers != s.unique_cards:
        add(f"Answers: {s.answers} ({s.answers - s.unique_cards} were re-reviews)")

    # Accuracy is opt-in: anti-pressure hide overrides it (see settings).
    if not cfg.get("hide_all_accuracy_stats", True) and cfg.get("show_completion_accuracy"):
        add(f"Accuracy: {s.accuracy():.0f}% (Again pressed {s.again_count}×)")

    cpm = s.cards_per_min()
    pb_lines = []
    if s.is_quick_start:
        streak = stats.current_quick_start_streak()
        if streak > 0:
            pb_lines.append(f"Quick Start streak: {streak} day{'s' if streak != 1 else ''} 🔥")
    if cfg.get("track_pb_sprints_today", True):
        from datetime import date
        today_key = date.today().isoformat()
        today_sprints = stats_after["by_day"].get(today_key, {}).get("sprints", 0)
        pb_lines.append(f"Blitzes today: {today_sprints}")
    if cfg.get("track_pb_total_sprints", True):
        pb_lines.append(f"Total Blitzes all-time: {stats_after['total_sprints']}")
    if cfg.get("track_pb_speed", True) and stats_after["best_cards_per_min"] > 0:
        is_new_pb = (
            abs(stats_after["best_cards_per_min"] - cpm) < 0.01
            and stats_after["best_cards_per_min_size"] == s.unique_cards
        )
        line = f"Best speed: {stats_after['best_cards_per_min']:.1f} cards/min"
        if is_new_pb:
            line += "  🏆 new PB!"
        pb_lines.append(line)

    if pb_lines:
        sep = QLabel(""); sep.setStyleSheet("margin-top: 6px;"); lay.addWidget(sep)
        for line in pb_lines:
            add(line)

    if cfg.get("completion_sound"):
        try:
            QApplication.beep()
        except Exception:
            pass

    btn_row = QHBoxLayout()
    close_btn = QPushButton("Done")
    close_btn.clicked.connect(dlg.accept)
    again_btn = QPushButton("Next Blitz")
    again_btn.clicked.connect(lambda: (dlg.accept(), start_blitz_dialog()))
    btn_row.addWidget(close_btn)
    btn_row.addWidget(again_btn)
    lay.addLayout(btn_row)

    dlg.exec()


# ----- Focus-loss watcher -----

class _FocusWatcher(QObject):
    def eventFilter(self, obj, event):
        # ApplicationDeactivate fires when Anki loses focus to ANOTHER app
        # (alt-tab). WindowDeactivate would also fire for in-app dialogs, which
        # we don't want to treat as leaving the Blitz.
        if event.type() == QEvent.Type.ApplicationDeactivate and not _intercepting:
            fcfg = get_section("focus")
            if session.is_running():
                if focus.keeps_session_on_focus_loss(fcfg):
                    # Focus Lock level 3: don't lose the Blitz — pull Anki back.
                    _reraise_anki()
                else:
                    cancel_if_active(reason="Anki lost focus")
            elif (_review_guard is not None
                  and focus.applies_to_reviews(fcfg)
                  and focus.keeps_session_on_focus_loss(fcfg)):
                # Level 3 on a normal review: keep them in — pull Anki back.
                _reraise_anki()
        return False


def _reraise_anki():
    """Best-effort pull of the Anki window back to the front (lock level 3)."""
    def go():
        try:
            mw.raise_()
            mw.activateWindow()
        except Exception:
            pass
    QTimer.singleShot(0, go)


_focus_watcher = _FocusWatcher()


# ----- Escape-window blocking (Browse / Add / Stats) -----
#
# These open as their own windows WITHOUT changing the main state, so the
# leave-trap in on_state_change never sees them. While a hard lock (level 2–3)
# is in force we close them again and pull Anki back to the reviewer. Soft modes
# (level 0–1) leave them alone.

def _hard_locked() -> bool:
    return _locked() and focus.lock_level(get_section("focus")) >= focus.LOCK_MIN_CARDS


def _block_escape_window(win, what: str):
    if not _hard_locked():
        return

    def shut():
        if not _hard_locked():
            return
        try:
            win.close()
        except Exception:
            pass
        _reraise_anki()
        tooltip(f"Focus Lock is on — stay on the cards before opening {what}.",
                period=2500)
    QTimer.singleShot(0, shut)


def _on_browser_will_show(browser):
    _block_escape_window(browser, "the Browser")


def _on_add_cards_did_init(addcards):
    _block_escape_window(addcards, "Add")


def _on_stats_will_show(dialog):
    _block_escape_window(dialog, "Stats")


def register():
    gui_hooks.state_did_change.append(on_state_change)
    gui_hooks.reviewer_did_answer_card.append(on_review_did_answer)
    QApplication.instance().installEventFilter(_focus_watcher)
    # Close the side windows that otherwise bypass the leave-trap (guarded so a
    # missing hook on an older Anki can't break startup).
    for name, fn in (("browser_will_show", _on_browser_will_show),
                     ("add_cards_did_init", _on_add_cards_did_init),
                     ("stats_dialog_will_show", _on_stats_will_show),
                     ("stats_dialog_old_will_show", _on_stats_will_show)):
        hook = getattr(gui_hooks, name, None)
        if hook is not None:
            try:
                hook.append(fn)
            except Exception:
                pass
