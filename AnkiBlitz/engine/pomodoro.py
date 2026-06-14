"""Pomodoro cycle — chain Blitz work blocks with breaks.

A Pomodoro run is a sequence of work blocks (each an ordinary Blitz, flagged
``is_pomodoro``) separated by breaks. Every Nth break is a longer one. When a
break's countdown ends, ``auto_return_level`` decides how insistently the next
work block is started:

  L0  notify only        — tooltip; the cycle stays "armed" and the next Blitz
                           you start manually resumes it.
  L1  prompt             — ask "start the next Blitz?" and wait.
  L2  auto-start         — start it, but only if Anki is the active window
                           (otherwise the focus-loss watcher would cancel it,
                           so it degrades to L0).
  L3  raise + auto-start — pull Anki to the front, then start it.

The cycle is the single source of truth in this module (``_active``); sprint.py
hands a completed work block to ``on_work_complete`` and reports cancellations to
``abort``. There is no active BlitzSession during a break, so the focus-loss
watcher and state-change cancel paths are dormant — you may leave Anki freely
while on a break.
"""

import importlib.util
import math
import os
import random
from datetime import datetime
from typing import Optional

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QDialogButtonBox, QMessageBox, QApplication, QTimer, Qt,
    QWidget, QStackedWidget, QLineEdit, QPlainTextEdit, QUrl,
)
from aqt.utils import tooltip

from ..config import get_section, suite_enabled
from . import sprint, stats, injection
from .session import MODE_CARDS, MODE_TIME, MODE_FRACTION


class PomodoroState:
    def __init__(self, work_mode, work_target, break_minutes, long_break_enabled,
                 long_break_every, long_break_minutes, cycles, auto_return_level,
                 break_sound, deck_id=None, due_total=0):
        self.work_mode = work_mode
        self.work_target = int(work_target)
        self.break_minutes = int(break_minutes)
        self.long_break_enabled = bool(long_break_enabled)
        self.long_break_every = max(1, int(long_break_every))
        self.long_break_minutes = int(long_break_minutes)
        self.cycles = int(cycles)                # 0 = unlimited
        self.auto_return_level = int(auto_return_level)
        self.break_sound = bool(break_sound)
        self.deck_id = deck_id
        self.completed_blocks = 0
        self.run_cards = 0                       # totals across this run (for the summary)
        self.run_seconds = 0.0
        self.awaiting_resume = False             # break over at L0 — next Blitz resumes

        # Fraction mode: split the due pile ONCE, here, into N equal chunks; each
        # work block then does one fixed-size chunk (shown as k/N), instead of
        # recomputing ceil(due/N) against the shrinking pile every block.
        if work_mode == MODE_FRACTION:
            self.frac_denom = max(2, int(work_target))
            self.frac_total = int(due_total)
            self.frac_chunk = (max(1, math.ceil(self.frac_total / self.frac_denom))
                               if self.frac_total > 0 else 0)
        else:
            self.frac_denom = 0
            self.frac_total = 0
            self.frac_chunk = 0


# ----- Single source of truth -----

_active: Optional[PomodoroState] = None
# Holds the live break dialog so it isn't garbage-collected while shown.
_break_dialog = None


def is_active() -> bool:
    return _active is not None


def _chime() -> None:
    if _active and _active.break_sound:
        try:
            QApplication.beep()
        except Exception:
            pass


def _anki_focused() -> bool:
    """True when our app is the foreground app (any AnkiBlitz/Anki window).

    The break dialog is a modal child window, so it — not ``mw`` — is the active
    *window*; checking the application state instead correctly means "the user is
    in Anki" (so auto-start is safe and the focus-loss watcher won't cancel it)."""
    try:
        return QApplication.applicationState() == Qt.ApplicationState.ApplicationActive
    except Exception:
        return True


# ----- Estimates / preview -----

def _seconds_per_card() -> float:
    """A rough per-card estimate from the all-time best speed (0 if unknown)."""
    try:
        cpm = stats.load_stats().get("best_cards_per_min", 0) or 0
        if cpm > 0:
            return 60.0 / cpm
    except Exception:
        pass
    return 0.0


def _next_preview_text(state: PomodoroState) -> str:
    due = sprint._due_total()
    n = state.completed_blocks + 1
    if state.work_mode == MODE_FRACTION:
        denom = max(2, state.frac_denom or state.work_target)
        cards = min(state.frac_chunk, due) if state.frac_chunk else (
            max(1, math.ceil(due / denom)) if due > 0 else 0)
        bits = [f"Next: Fraction {n}/{denom}",
                f"{due} card{'s' if due != 1 else ''} due now"]
        if cards:
            label = f"{cards} card target"
            spc = _seconds_per_card()
            if spc > 0:
                label += f" · ~{max(1, round(cards * spc / 60))} min"
            bits.append(label)
        return " · ".join(bits)

    bits = [f"Next: Blitz #{n}", f"{due} card{'s' if due != 1 else ''} due now"]
    if state.work_mode == MODE_TIME:
        bits.append(f"~{max(1, state.work_target)} min")
    else:
        cards = max(1, state.work_target)
        if due > 0:
            cards = min(cards, due)
        if cards:
            label = f"{cards} card target"
            spc = _seconds_per_card()
            if spc > 0:
                label += f" · ~{max(1, round(cards * spc / 60))} min"
            bits.append(label)
    return " · ".join(bits)


# ----- Lifecycle -----

def start_pomodoro(deck_id=None, use_defaults=False) -> None:
    """Start a Pomodoro run. With ``use_defaults`` it skips the start dialog and
    builds the cycle straight from the saved preset (the widget quick-launch)."""
    global _active
    if not (suite_enabled() and get_section("pomodoro").get("enabled", True)):
        tooltip("Pomodoro is turned off in AnkiBlitz settings.")
        return
    if mw.col is None:
        return
    if is_active():
        # An "armed" cycle (L0 break over, waiting to resume) shouldn't lock out a
        # fresh start — replace it. A genuinely in-progress cycle is left alone.
        if _active.awaiting_resume:
            abort("restarted")
        else:
            tooltip("A Pomodoro is already running.")
            return
    if sprint.session.is_running():
        tooltip("Finish or cancel the current Blitz first.")
        return
    if sprint._due_total() <= 0:
        tooltip("Nothing due right now — load a deck first.")
        return

    cfg = get_section("pomodoro")
    state = _state_from_cfg(cfg, deck_id) if use_defaults else _show_start_dialog(cfg, deck_id)
    if state is None:
        return
    _active = state
    if not _begin_work():
        _active = None
        tooltip("Couldn't start the Pomodoro.")


def _begin_work() -> bool:
    if _active is None:
        return False
    ok = sprint.begin_pomodoro_work(_active)
    # Carry-forward: greet a block that follows a break with the note you just
    # wrote, so your intention rolls into the next session.
    if ok and _active.completed_blocks >= 1 and get_section("pomodoro").get("carry_forward", True):
        note = _last_entry_text(_read_journal())
        if note:
            tooltip("📝 From your break: " + note.replace("\n", " ")[:120], period=5000)
    return ok


def on_work_complete(snapshot, stats_after, cfg) -> None:
    """A work block finished — advance the cycle into a break (or finish)."""
    if _active is None:
        return
    _active.completed_blocks += 1
    _active.run_cards += snapshot.unique_cards
    _active.run_seconds += snapshot.elapsed_seconds()
    try:
        stats.record_pomodoro_block(snapshot.unique_cards, snapshot.elapsed_seconds())
    except Exception:
        pass
    if _active.cycles > 0 and _active.completed_blocks >= _active.cycles:
        finish(summary=True)
        return
    # Fraction cycles run exactly N blocks (one per chunk) — stop after the last
    # chunk, or early if the due pile is already cleared.
    if _active.work_mode == MODE_FRACTION:
        if ((_active.frac_denom > 0 and _active.completed_blocks >= _active.frac_denom)
                or sprint._due_total() <= 0):
            finish(summary=True)
            return
    is_long = (_active.long_break_enabled
               and _active.completed_blocks % _active.long_break_every == 0)
    minutes = _active.long_break_minutes if is_long else _active.break_minutes
    start_break(max(1, int(minutes)), is_long, _last_block_text(snapshot))


def _last_block_text(snapshot) -> str:
    """A neutral one-line recap of the work block that just finished."""
    try:
        secs = snapshot.elapsed_seconds()
        bits = [f"{snapshot.unique_cards} card{'s' if snapshot.unique_cards != 1 else ''}",
                f"{secs / 60:.1f} min"]
        cpm = snapshot.cards_per_min()
        if cpm > 0:
            bits.append(f"{cpm:.1f} cards/min")
        return " · ".join(bits)
    except Exception:
        return ""


def start_break(minutes: int, is_long: bool, last_text: str = "") -> None:
    if _active is None:
        return
    _chime()
    # Defer presentation so we're clear of the just-finished block's answer hook.
    # The break is a fullscreen modal over the *reviewer* (we don't leave the
    # cards screen) — no deck list, no distraction; the reviewer behind is hidden
    # and input-blocked by the modal.
    QTimer.singleShot(0, lambda: _present_break(minutes, is_long, last_text))


def _present_break(minutes: int, is_long: bool, last_text: str) -> None:
    global _break_dialog
    if _active is None:
        return
    # Stop Speed Focus on the card hidden behind the break so it doesn't
    # auto-reveal or chime mid-break.
    try:
        injection.pause_auto_reveal()
    except Exception:
        pass
    _break_dialog = BreakDialog(minutes, is_long, _active, last_text)
    _break_dialog.finished.connect(lambda *_: _clear_break_dialog())
    _break_dialog.show()


def on_break_over() -> None:
    """The break countdown reached 0 (or was skipped) — apply the return level."""
    if _active is None:
        return
    _chime()
    level = _active.auto_return_level

    if level >= 3:
        _close_break_dialog()
        try:
            mw.raise_()
            mw.activateWindow()
        except Exception:
            pass
        _begin_work()
        return

    if level == 2:
        # Only auto-start if Anki is focused; else the focus watcher would cancel
        # the new Blitz the instant it starts. Degrade to notify + armed.
        if _anki_focused():
            _close_break_dialog()
            _begin_work()
            return
        _notify_and_arm()
        return

    if level == 1:
        _close_break_dialog()
        n = _active.completed_blocks + 1
        box = QMessageBox(mw)
        box.setWindowTitle("Break over")
        box.setText(f"Break's over — start Blitz #{n}?")
        start = box.addButton("Start now", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("End Pomodoro", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(start)
        box.exec()
        if _active is None:
            return
        if box.clickedButton() is start:
            _begin_work()
        else:
            finish(summary=True)
        return

    # level 0
    _notify_and_arm()


def _notify_and_arm() -> None:
    _close_break_dialog()
    if _active is None:
        return
    _active.awaiting_resume = True
    tooltip("Break's over — start a Blitz when you're ready.", period=4000)


def note_manual_blitz_started(sess) -> None:
    """If a cycle is armed (L0 break over), the next manual Blitz resumes it."""
    if _active is None or sess is None or not _active.awaiting_resume:
        return
    _active.awaiting_resume = False
    sess.is_pomodoro = True


def abort(reason: str = "") -> None:
    global _active
    if _active is None:
        return
    _active = None
    _close_break_dialog()


def finish(summary: bool = False) -> None:
    global _active
    if _active is None:
        return
    state = _active
    _active = None
    _close_break_dialog()
    if not summary:
        return
    if state.completed_blocks > 0 and get_section("pomodoro").get("end_summary", True):
        _show_run_summary(state)
    else:
        blocks = state.completed_blocks
        tooltip(
            f"Pomodoro complete — {blocks} block{'s' if blocks != 1 else ''} done. 🍅",
            period=4000,
        )


def _show_run_summary(state: PomodoroState) -> None:
    dlg = QDialog(mw)
    dlg.setWindowTitle("Pomodoro complete")
    dlg.setMinimumWidth(360)
    lay = QVBoxLayout(dlg)

    title = QLabel(f"🍅 Pomodoro complete — {state.completed_blocks} "
                   f"block{'s' if state.completed_blocks != 1 else ''}")
    title.setStyleSheet("font-size: 17px; font-weight: 700; margin-bottom: 4px;")
    lay.addWidget(title)

    def add(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 13px; margin: 2px 0;")
        lay.addWidget(lbl)

    add(f"Cards: {state.run_cards}")
    add(f"Focus time: {state.run_seconds / 60:.0f} min")
    try:
        pt = stats.pomodoro_today_summary()
        add(f"Today so far: {pt['blocks']} blocks · {pt['seconds'] / 60:.0f} min")
        if pt["avg_focus"]:
            add(f"Avg focus today: {pt['avg_focus']:.1f} / 5")
    except Exception:
        pass

    btn_row = QHBoxLayout()
    journal_btn = QPushButton("Open journal")
    journal_btn.clicked.connect(lambda: (dlg.accept(), open_journal_viewer()))
    done = QPushButton("Done")
    done.clicked.connect(dlg.accept)
    btn_row.addWidget(journal_btn)
    btn_row.addWidget(done)
    lay.addLayout(btn_row)
    dlg.exec()


def _clear_break_dialog() -> None:
    global _break_dialog
    _break_dialog = None


def _close_break_dialog() -> None:
    global _break_dialog
    dlg = _break_dialog
    _break_dialog = None
    if dlg is not None:
        try:
            dlg.accept()  # accept() so it isn't treated as a window-close "End"
        except Exception:
            pass


# ----- Break screen -----

def _journal_path() -> str:
    suite_dir = os.path.dirname(os.path.dirname(__file__))
    uf = os.path.join(suite_dir, "user_files")
    os.makedirs(uf, exist_ok=True)
    return os.path.join(uf, "break_journal.md")


def _read_journal() -> str:
    try:
        with open(_journal_path(), "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_journal(text: str) -> None:
    try:
        with open(_journal_path(), "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _last_entry_text(journal: str) -> str:
    """Body of the most recent journal entry (for the 'last break' reminder)."""
    if not journal.strip():
        return ""
    last = journal.split("\n## ")[-1]
    lines = last.splitlines()
    return "\n".join(lines[1:]).strip()  # drop the header line


def open_journal_viewer() -> None:
    """Read-only viewer for the whole break journal (newest first)."""
    text = _read_journal().strip()
    dlg = QDialog(mw)
    dlg.setWindowTitle("Break journal")
    dlg.setMinimumSize(520, 480)
    lay = QVBoxLayout(dlg)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    if text:
        # Newest entry first for quick reference.
        entries = text.split("\n## ")
        entries = [e if e.startswith("## ") else "## " + e for e in entries if e.strip()]
        view.setPlainText("\n\n".join(reversed(entries)))
    else:
        view.setPlainText("No break-journal entries yet. Jot something on your next break.")
    lay.addWidget(view)
    close = QPushButton("Close")
    close.clicked.connect(dlg.accept)
    lay.addWidget(close)
    dlg.exec()


# Rotating micro-break suggestions. Long breaks lean toward getting up and moving.
_SHORT_TIPS = [
    "Stand up and stretch", "Hydrate 💧", "Look 20 ft away for 20 s 👀",
    "Roll your shoulders", "Breathe — 4 in, 4 out", "Rest your eyes",
]
_LONG_TIPS = [
    "Go for a short walk 🚶", "Step outside for fresh air",
    "Get a proper drink or snack", "Move — a lap of the house",
    "Stretch your legs and back", "Look out a window, let your eyes relax",
]


def _break_tip(is_long: bool) -> str:
    return random.choice(_LONG_TIPS if is_long else _SHORT_TIPS)


def _kg_available() -> bool:
    try:
        return importlib.util.find_spec("ankisstant") is not None
    except Exception:
        return False


def _open_add_kg() -> None:
    # Soft cross-add-on bridge — AnkiBlitz works fine without Ankisstant.
    try:
        from ankisstant.tools.knowledge_gaps import open_add_kg_dialog
        open_add_kg_dialog()
    except Exception:
        tooltip("Couldn't open Ankisstant Knowledge Gaps.")


def _next_long_break_block(state: PomodoroState) -> Optional[int]:
    """The block number after which the next long break falls (None if off)."""
    every = state.long_break_every if state.long_break_enabled else 0
    if every <= 0:
        return None
    n = state.completed_blocks
    return ((n // every) + 1) * every


def _remaining_text(state: PomodoroState) -> str:
    n = state.completed_blocks
    # Fraction cycles: report progress through the fixed N chunks.
    if state.work_mode == MODE_FRACTION and state.frac_denom > 0:
        left = max(0, state.frac_denom - n)
        if left <= 0:
            return ""
        return f"{n}/{state.frac_denom} fractions done · {left} to go"
    if state.cycles > 0:
        left = max(0, state.cycles - n)
        if left <= 0:
            return ""
        if state.work_mode == MODE_TIME:
            mins = left * (max(1, state.work_target) + max(1, state.break_minutes))
            return f"≈ {mins} min left · {left} block{'s' if left != 1 else ''} to go"
        return f"{left} block{'s' if left != 1 else ''} to go"
    # Unlimited cycles: estimate the time to clear the current due pile.
    due = sprint._due_total()
    spc = _seconds_per_card()
    if due > 0 and spc > 0:
        mins = max(1, round(due * spc / 60))
        return f"≈ {mins} min to clear {due} due · block {n + 1} next"
    if due > 0:
        return f"{due} cards still due · block {n + 1} next"
    return f"Block {n + 1} next · keep it going"


def _pill(text: str, style: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


# Pill styles for the timeline.
_PILL_DONE = ("background:#2e7d32;color:#fff;border-radius:7px;"
              "padding:4px 9px;font-size:12px;font-weight:600;")
_PILL_NOW = ("background:#e0883c;color:#fff;border-radius:7px;"
             "padding:4px 9px;font-size:12px;font-weight:700;")
_PILL_NOW_LONG = ("background:#7e57c2;color:#fff;border-radius:7px;"
                  "padding:4px 9px;font-size:12px;font-weight:700;")
_PILL_NEXT = ("border:1px dashed rgba(150,150,150,.7);border-radius:7px;"
              "padding:4px 9px;font-size:12px;")
_PILL_LONG = ("border:1px solid #7e57c2;color:#b39ddb;border-radius:7px;"
              "padding:4px 9px;font-size:12px;font-weight:600;")


def _timeline_widget(state: PomodoroState) -> QWidget:
    """Past → now → future: today's done blocks, this break, what's coming
    (upcoming blocks and when the next long break lands)."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(5)
    h.addStretch(1)

    try:
        blocks = stats.pomodoro_blocks_today()
    except Exception:
        blocks = []
    for blk in blocks[-6:]:                        # recent past (capped)
        h.addWidget(_pill(f"✓ {blk.get('c', 0)}", _PILL_DONE))

    n = state.completed_blocks
    every = state.long_break_every if state.long_break_enabled else 0
    is_long_now = every > 0 and n > 0 and n % every == 0
    h.addWidget(_pill("🌙 now" if is_long_now else "☕ now",
                      _PILL_NOW_LONG if is_long_now else _PILL_NOW))

    # Future: upcoming work blocks (capped to the cycle limit if set).
    long_block = _next_long_break_block(state)
    upto = long_block if long_block is not None else n + 3
    if state.cycles > 0:
        upto = min(upto, state.cycles)
    upcoming = [i for i in range(n + 1, upto + 1)]
    for i in upcoming[:4]:
        h.addWidget(_pill(f"▶ #{i}", _PILL_NEXT))
    if len(upcoming) > 4:
        h.addWidget(_pill("…", "font-size:12px;opacity:.5;"))
    # Mark the next long break (if it actually falls within this run).
    if long_block is not None and (state.cycles == 0 or long_block <= state.cycles):
        away = long_block - n
        h.addWidget(_pill(f"🌙 long break in {away}", _PILL_LONG))

    h.addStretch(1)
    return row


class BreakDialog(QDialog):
    """A fullscreen break page over the reviewer: big mm:ss countdown, a timeline
    of today's blocks, the last block's recap + what's next, and actions
    (End / Browse in-app / Add KG / Skip). The countdown runs on every page."""

    def __init__(self, minutes: int, is_long: bool, state: PomodoroState,
                 last_text: str = "", parent=None):
        super().__init__(parent or mw)
        self._remaining = max(1, int(minutes)) * 60
        self._fired = False
        self._state = state
        self._browser = None
        self._view = None
        self._music = None

        self.setWindowTitle("Break")
        # Frameless + modal, sized over the Anki window: a distraction-free
        # fullscreen break page that hides the reviewer behind it.
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        try:
            self.setGeometry(mw.frameGeometry())
        except Exception:
            self.setMinimumSize(560, 460)

        # Per-break journal: this break appends one dated entry to the running
        # journal. Capture the prior journal + a stable header for this entry.
        self.notes = None
        self._journal_prior = _read_journal()
        n = state.completed_blocks
        self._entry_header = (
            "## " + datetime.now().strftime("%Y-%m-%d %H:%M")
            + (f" — after block {n}" if n else " — break"))
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._save_notes_now)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.stack.addWidget(self._build_break_page(minutes, is_long, last_text))

        # Closing the window (Esc) ends the Pomodoro.
        self.rejected.connect(self._on_rejected)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _build_break_page(self, minutes, is_long, last_text) -> QWidget:
        po = get_section("pomodoro")
        page = QWidget()
        # Outer split: break content (and its action buttons) on the left, the
        # music player docked as a fixed panel on the right so it can never push
        # the End/Skip buttons off the page.
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(40, 22, 40, 22)
        lay.addStretch(2)

        # Long breaks get a distinct "step away" framing.
        if is_long:
            head_text = f"🌙 Long break — {minutes} min · step away"
        else:
            head_text = f"☕ Break — {minutes} min"
        head = QLabel(head_text)
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet("font-size: 22px; opacity: 0.75;")
        lay.addWidget(head)

        self.clock = QLabel(self._fmt())
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setStyleSheet("font-size: 88px; font-weight: 800; margin: 6px;")
        lay.addWidget(self.clock)

        if po.get("break_show_tips", True):
            tip = QLabel("💡 " + _break_tip(is_long))
            tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tip.setStyleSheet("font-size: 13px; opacity: 0.65; margin-bottom: 2px;")
            lay.addWidget(tip)

        if po.get("break_show_timeline", True):
            lay.addWidget(_timeline_widget(self._state))

        # Daily goal + completion estimate on one line.
        info_bits = []
        goal = int(po.get("daily_goal", 0))
        if goal > 0:
            done = stats.pomodoro_today_summary()["blocks"]
            info_bits.append(f"Goal {done}/{goal}" + (" ✓" if done >= goal else ""))
        rem = _remaining_text(self._state)
        if rem:
            info_bits.append(rem)
        if info_bits:
            rl = QLabel("  ·  ".join(info_bits))
            rl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.setStyleSheet("font-size: 13px; opacity: 0.6; margin-top: 4px;")
            lay.addWidget(rl)

        if last_text:
            last = QLabel("Just finished: " + last_text)
            last.setAlignment(Qt.AlignmentFlag.AlignCenter)
            last.setStyleSheet("font-size: 12px; opacity: 0.55;")
            lay.addWidget(last)

        preview = QLabel(_next_preview_text(self._state))
        preview.setWordWrap(True)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setStyleSheet("font-size: 12px; opacity: 0.5; margin-bottom: 8px;")
        lay.addWidget(preview)

        if po.get("break_show_focus_rating", True) and self._state.completed_blocks > 0:
            lay.addLayout(self._build_focus_row())

        if po.get("break_show_journal", True):
            lay.addLayout(self._build_journal())

        # --- action buttons (each gated) ---
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        end = QPushButton("End Pomodoro")
        end.clicked.connect(self._end)
        btn_row.addWidget(end)
        if po.get("break_allow_extend", True):
            ext = QPushButton("+5 min")
            ext.clicked.connect(self._extend)
            btn_row.addWidget(ext)
        if po.get("break_show_browser", True):
            browse = QPushButton("🌐 Browse")
            browse.clicked.connect(self._open_browser)
            btn_row.addWidget(browse)
        if po.get("break_show_add_kg", True) and _kg_available():
            kg = QPushButton("＋ Add KG")
            kg.clicked.connect(lambda: _open_add_kg())
            btn_row.addWidget(kg)
        skip = QPushButton("Skip break →")
        skip.setDefault(True)
        skip.clicked.connect(self._skip)
        btn_row.addWidget(skip)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        lay.addStretch(3)

        outer.addWidget(content, 1)
        # Music docked to the right edge (only when enabled for breaks).
        mu = get_section("music")
        if mu.get("enabled", False) and mu.get("show_on_break", True):
            outer.addWidget(self._build_music_panel())
        return page

    def _build_focus_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        lbl = QLabel("Focus this block:")
        lbl.setStyleSheet("font-size: 12px; opacity: 0.6;")
        row.addWidget(lbl)
        self._focus_btns = []
        for n in range(1, 6):
            b = QPushButton(str(n))
            b.setMaximumWidth(38)
            b.clicked.connect(lambda _, v=n: self._rate_focus(v))
            row.addWidget(b)
            self._focus_btns.append(b)
        row.addStretch(1)
        return row

    def _build_journal(self) -> QHBoxLayout:
        # A fresh, always-visible entry box (out in the open to encourage a jot),
        # with the previous entry shown for continuity.
        notes_row = QHBoxLayout()
        notes_row.addStretch(1)
        notes_col = QVBoxLayout()
        notes_lbl = QLabel("Break journal — this entry")
        notes_lbl.setStyleSheet("font-size: 12px; opacity: 0.6; margin-bottom: 2px;")
        notes_col.addWidget(notes_lbl)

        last = _last_entry_text(self._journal_prior)
        if last:
            short = last.replace("\n", "  ")
            if len(short) > 150:
                short = short[:150] + "…"
            prev = QLabel("Last break: " + short)
            prev.setWordWrap(True)
            prev.setFixedWidth(640)
            prev.setStyleSheet("font-size: 11px; opacity: 0.45; margin-bottom: 4px;")
            notes_col.addWidget(prev)

        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "Knowledge gaps · thoughts & feelings · what to tackle next session · "
            "how's your focus today · anything…")
        self.notes.setFixedWidth(640)
        self.notes.setFixedHeight(120)
        self.notes.textChanged.connect(lambda: self._notes_timer.start(700))
        notes_col.addWidget(self.notes)
        notes_row.addLayout(notes_col)
        notes_row.addStretch(1)
        return notes_row

    def _rate_focus(self, n: int) -> None:
        try:
            stats.set_last_block_focus(n)
        except Exception:
            pass
        for i, b in enumerate(self._focus_btns, start=1):
            b.setStyleSheet("background:#3b82f6;color:#fff;font-weight:700;" if i <= n else "")
        tooltip(f"Focus {n}/5 logged", period=1200)

    def _extend(self) -> None:
        if self._fired:
            return
        self._remaining += 300
        self.clock.setText(self._fmt())
        tooltip("+5 min added to the break", period=1200)

    # ----- in-app browser (keeps the break inside Anki) -----

    def _open_browser(self) -> None:
        if self._browser is None:
            self._browser = self._make_browser()
            if self._browser is None:
                tooltip("Web browser isn't available in this Anki build.")
                return
            self.stack.addWidget(self._browser)
        self.stack.setCurrentWidget(self._browser)

    # ----- in-app music player (its own little box on the break screen) -----

    def _build_music_panel(self) -> QWidget:
        """The music player as a fixed panel pinned to the right of the break
        screen (player at top, stretch below) — keeps it out of the content
        column so it never displaces the action buttons."""
        from . import music as music_mod
        panel = QWidget()
        col = QVBoxLayout(panel)
        col.setContentsMargins(10, 22, 16, 22)
        self._music = music_mod.build_player_widget(self)
        # Fixed, narrow size to match the home/review player (width is set inside
        # the widget); only the height needs pinning here.
        self._music.setFixedHeight(music_mod.PLAYER_H)
        col.addWidget(self._music)
        col.addStretch(1)
        return panel

    def _make_browser(self):
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
        except Exception:
            try:
                from PyQt5.QtWebEngineWidgets import QWebEngineView
            except Exception:
                return None
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 6, 6, 6)

        bar = QHBoxLayout()
        back_break = QPushButton("← Break")
        back_break.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        b = QPushButton("◀")
        fwd = QPushButton("▶")
        rl = QPushButton("⟳")
        for btn in (back_break, b, fwd, rl):
            btn.setMaximumWidth(78)
        addr = QLineEdit()
        addr.setPlaceholderText("Search or type a URL…")

        view = QWebEngineView(w)
        b.clicked.connect(view.back)
        fwd.clicked.connect(view.forward)
        rl.clicked.connect(view.reload)

        def navigate():
            t = addr.text().strip()
            if not t:
                return
            if " " in t or "." not in t:
                from urllib.parse import quote
                url = "https://www.google.com/search?q=" + quote(t)
            elif not t.startswith(("http://", "https://")):
                url = "https://" + t
            else:
                url = t
            view.setUrl(QUrl(url))
        addr.returnPressed.connect(navigate)

        def _sync(u):
            if not addr.hasFocus():
                addr.setText(u.toString())
        view.urlChanged.connect(_sync)

        bar.addWidget(back_break)
        bar.addWidget(b)
        bar.addWidget(fwd)
        bar.addWidget(rl)
        bar.addWidget(addr, 1)
        v.addLayout(bar)
        v.addWidget(view, 1)
        view.setUrl(QUrl("https://www.google.com"))
        self._view = view
        return w

    # ----- notes -----

    def _save_notes_now(self) -> None:
        if self.notes is None:
            return
        body = self.notes.toPlainText().strip()
        prior = self._journal_prior.rstrip()
        # Rewrite = prior journal + this break's dated entry (idempotent on every
        # autosave; empty entries add nothing).
        if body:
            text = (prior + "\n\n" if prior else "") + self._entry_header + "\n" + body + "\n"
        else:
            text = (prior + "\n" if prior else "")
        _write_journal(text)

    # ----- countdown -----

    def _fmt(self) -> str:
        m, s = divmod(max(0, self._remaining), 60)
        return f"{m:d}:{s:02d}"

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining <= 0:
            self._fire()
        else:
            self.clock.setText(self._fmt())

    def _fire(self) -> None:
        if self._fired:
            return
        self._fired = True
        self._timer.stop()
        self._save_notes_now()
        on_break_over()

    def _skip(self) -> None:
        self._fire()

    def _end(self) -> None:
        if self._fired:
            return
        self._fired = True
        self._timer.stop()
        self._save_notes_now()
        finish(summary=True)

    def _on_rejected(self) -> None:
        # accept()-driven programmatic close won't reach here; only X / Esc does.
        if not self._fired:
            self._fired = True
            self._timer.stop()
            self._save_notes_now()
            abort("ended during break")


# ----- Start dialog -----

_LEVELS = [
    (0, "Notify me only"),
    (1, "Prompt me to start"),
    (2, "Auto-start next Blitz"),
    (3, "Raise Anki + auto-start"),
]


def _show_start_dialog(cfg, deck_id) -> Optional[PomodoroState]:
    dlg = QDialog(mw)
    dlg.setWindowTitle("Start Pomodoro")
    dlg.setMinimumWidth(360)
    lay = QVBoxLayout(dlg)

    cur = {"mode": cfg.get("work_mode", "time")}

    summary_lbl = QLabel(_work_summary(cur["mode"]))
    lay.addWidget(summary_lbl)

    form = QFormLayout()

    target = QSpinBox()
    _apply_target_units(target, cur["mode"])
    target.setValue(int(cfg.get("work_target", 25)))
    form.addRow("Work block:", target)

    brk = QSpinBox()
    brk.setRange(1, 120)
    brk.setSuffix(" min")
    brk.setValue(int(cfg.get("break_minutes", 5)))
    form.addRow("Break:", brk)

    cycles = QSpinBox()
    cycles.setRange(0, 99)
    cycles.setSpecialValueText("Unlimited")
    cycles.setSuffix(" blocks")
    cycles.setValue(int(cfg.get("cycles", 0)))
    form.addRow("Stop after:", cycles)

    level = QComboBox()
    for value, label in _LEVELS:
        level.addItem(label, value)
    lidx = level.findData(int(cfg.get("auto_return_level", 2)))
    if lidx >= 0:
        level.setCurrentIndex(lidx)
    form.addRow("When break ends:", level)

    lay.addLayout(form)

    long_txt = ""
    if cfg.get("long_break_enabled", True):
        long_txt = (f"Longer break ({int(cfg.get('long_break_minutes', 15))} min) "
                    f"every {int(cfg.get('long_break_every', 4))} blocks.")
    note = QLabel(
        (long_txt + "\n" if long_txt else "")
        + "Leaving review during a work block ends the Pomodoro."
    )
    note.setWordWrap(True)
    note.setStyleSheet("color: gray; font-size: 11px; margin-top: 6px;")
    lay.addWidget(note)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Start")
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None

    return PomodoroState(
        work_mode=cur["mode"],
        work_target=target.value(),
        break_minutes=brk.value(),
        long_break_enabled=cfg.get("long_break_enabled", True),
        long_break_every=cfg.get("long_break_every", 4),
        long_break_minutes=cfg.get("long_break_minutes", 15),
        cycles=cycles.value(),
        auto_return_level=level.currentData(),
        break_sound=cfg.get("break_sound", True),
        deck_id=deck_id,
        due_total=sprint._due_total(),
    )


def _state_from_cfg(cfg, deck_id) -> PomodoroState:
    return PomodoroState(
        work_mode=cfg.get("work_mode", "time"),
        work_target=cfg.get("work_target", 25),
        break_minutes=cfg.get("break_minutes", 5),
        long_break_enabled=cfg.get("long_break_enabled", True),
        long_break_every=cfg.get("long_break_every", 4),
        long_break_minutes=cfg.get("long_break_minutes", 15),
        cycles=cfg.get("cycles", 0),
        auto_return_level=cfg.get("auto_return_level", 2),
        break_sound=cfg.get("break_sound", True),
        deck_id=deck_id,
        due_total=sprint._due_total(),
    )


def _work_summary(work_mode: str) -> str:
    if work_mode == MODE_TIME:
        return "Each work block is a timed Blitz."
    if work_mode == MODE_FRACTION:
        return "Each work block blitzes a fraction of what's due."
    return "Each work block is a card-count Blitz."


def _apply_target_units(spin: QSpinBox, work_mode: str) -> None:
    if work_mode == MODE_TIME:
        spin.setSuffix(" min")
        spin.setRange(1, 600)
    elif work_mode == MODE_FRACTION:
        spin.setPrefix("1 / ")
        spin.setRange(2, 50)
    else:
        spin.setSuffix(" cards")
        spin.setRange(1, 9999)
