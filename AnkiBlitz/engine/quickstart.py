"""Quick Start — auto-launch a Blitz on the first open of the day.

On profile open (deferred so the deck browser has settled), if Quick Start is
enabled and cards are due, this either shows a cancelable 3-2-1 countdown or
jumps straight into a Blitz, depending on ``quick_start.launch_style``. The Blitz
itself is owned by sprint.py (``start_quick_start``); this module only decides
*whether* and *how* to trigger it. Launching is gated to once per day via the
stats store, so cancelling the countdown won't re-nag on a same-day reopen.
"""

from datetime import datetime

from aqt import mw
from aqt.qt import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTimer, Qt,
)

from ..config import get_section, suite_enabled
from . import session, sprint, stats

# Holds the live countdown dialog so it isn't garbage-collected while shown.
_active_countdown = None

# Foreground-return relaunch: True once Anki has lost focus, so the next time it
# becomes the foreground app we know it's a "came back to it" (not startup).
_was_inactive = False


class CountdownDialog(QDialog):
    """A 3-2-1 screen with Cancel / Start now; fires ``on_done`` when it ends."""

    def __init__(self, seconds: int, on_done, parent=None):
        super().__init__(parent or mw)
        self.on_done = on_done
        self._remaining = max(1, int(seconds))
        self._fired = False

        self.setWindowTitle("Quick Start")
        self.setModal(True)
        self.setMinimumWidth(280)
        lay = QVBoxLayout(self)

        head = QLabel("Daily Blitz starting…")
        head.setAlignment(Qt.AlignmentFlag.AlignCenter)
        head.setStyleSheet("font-size: 14px; color: gray;")
        lay.addWidget(head)

        self.num = QLabel(str(self._remaining))
        self.num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.num.setStyleSheet("font-size: 64px; font-weight: 700; margin: 12px;")
        lay.addWidget(self.num)

        btn_row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        start_now = QPushButton("Start now")
        start_now.clicked.connect(self._fire)
        btn_row.addWidget(cancel)
        btn_row.addWidget(start_now)
        lay.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self._fire()
        else:
            self.num.setText(str(self._remaining))

    def _fire(self):
        if self._fired:
            return
        self._fired = True
        self._timer.stop()
        self.accept()
        try:
            self.on_done()
        except Exception:
            pass


def maybe_autostart(paused: bool = False) -> None:
    """Auto-launch the daily Blitz if the gates pass. Best-effort, never raises.

    ``paused`` (the overnight foreground-return path) opens the Blitz on the first
    card but holds the auto-reveal and clock until the first key/click — and skips
    the 3-2-1 countdown, since you've only just come back to Anki."""
    try:
        if not suite_enabled():
            return
        qs = get_section("quick_start")
        if not qs.get("enabled", False):
            return
        if mw.col is None:
            return
        # Only from the home screens, never if the user already started reviewing.
        if getattr(mw, "state", None) not in ("deckBrowser", "overview"):
            return
        if session.is_running():
            return
        if stats.quick_start_launched_today():
            return
        if sprint._due_total() < int(qs.get("min_due", 1)):
            return

        # Mark launched now so a cancelled countdown doesn't re-nag later today.
        stats.mark_quick_start_launched()

        if paused:
            sprint.start_quick_start(paused=True)
        elif qs.get("launch_style", "countdown") == "immediate":
            sprint.start_quick_start()
        else:
            global _active_countdown
            _active_countdown = CountdownDialog(
                int(qs.get("countdown_seconds", 3)), sprint.start_quick_start, mw)
            _active_countdown.finished.connect(_clear_countdown)
            _active_countdown.show()
    except Exception:
        pass


def _clear_countdown(*_):
    global _active_countdown
    _active_countdown = None


# ----- Foreground-return relaunch (Anki left open across a day rollover) -----

def _on_app_state_changed(state) -> None:
    """Anki gained/lost foreground. The first time it becomes active again after
    having been inactive (you tabbed away and came back), try a paused relaunch."""
    global _was_inactive
    try:
        if state == Qt.ApplicationState.ApplicationActive:
            if _was_inactive:
                _was_inactive = False
                _maybe_relaunch_on_foreground()
        else:
            _was_inactive = True
    except Exception:
        pass


def _maybe_relaunch_on_foreground() -> None:
    try:
        qs = get_section("quick_start")
        if not qs.get("relaunch_on_new_day", True):
            return
        if datetime.now().hour < int(qs.get("relaunch_after_hour", 5)):
            return
        maybe_autostart(paused=True)
    except Exception:
        pass


def register() -> None:
    # Deferred so the deck browser has settled and the collection is ready.
    mw.progress.single_shot(800, maybe_autostart, True)
    # Relaunch when you return to an Anki that was left open across midnight.
    try:
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(_on_app_state_changed)
    except Exception:
        pass
