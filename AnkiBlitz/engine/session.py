"""The single source-of-truth Blitz session for AnkiBlitz.

There is at most one active session at a time, held in the module-level
``_active``. Everything else in the engine reads session state from here rather
than keeping its own copy:

  - the progress bar reflects ``progress_fraction()`` (cards or time)
  - the elapsed clock reflects ``started_at``
  - completion / cancellation flip ``completed`` / clear ``_active``

Three modes (Stage 2):
  - ``cards``    — finish a target number of cards
  - ``time``     — study for a fixed number of minutes
  - ``fraction`` — finish a fraction of what is currently due (a card target
                   computed from the due count when the session starts)

Counting rule ("the bar must not lie"): learning cards that Again-requeue come
back within the session. ``count_mode`` decides what the bar counts:
  - ``unique``  — distinct cards touched (a re-review of the same card does not
                  move the bar; reaching the target means that many *different*
                  cards were seen). This is the honest default for a volume goal.
  - ``answers`` — every grade press (re-reviews included).
The progress bar is always labelled with the matching unit so the number on
screen can never be misread.
"""

import time
from typing import Optional, Set

MODE_CARDS = "cards"
MODE_TIME = "time"
MODE_FRACTION = "fraction"


class BlitzSession:
    def __init__(self, mode: str, target_cards: int = 0, target_seconds: float = 0.0,
                 count_mode: str = "unique", deck_id: Optional[int] = None,
                 label: str = "", is_quick_start: bool = False,
                 is_pomodoro: bool = False, idle_threshold: float = 60.0,
                 paused: bool = False):
        self.mode = mode
        self.target_cards = int(target_cards)        # cards / fraction modes
        self.target_seconds = float(target_seconds)  # time mode
        self.count_mode = count_mode if count_mode in ("unique", "answers") else "unique"
        self.deck_id = deck_id
        self.label = label                           # e.g. "50 cards", "15 min", "½ of due"
        self.is_quick_start = bool(is_quick_start)   # launched by the daily Quick Start
        self.is_pomodoro = bool(is_pomodoro)         # a Pomodoro work block

        self.started_at = time.time()
        # Paused launch (overnight relaunch): the Blitz opens on the first card but
        # holds the auto-reveal and doesn't count time until the first key/click.
        # begin_engagement() then rebases started_at so the away gap isn't counted.
        self.paused = bool(paused)
        # Time mode: the countdown clock doesn't start until the first card is
        # flipped (its answer shown), so the gap before you engage isn't counted.
        self.clock_started_at: Optional[float] = None
        self.first_answer_at: Optional[float] = None  # for the launch -> first-answer metric
        self.answers = 0                             # total grade presses
        self.again_count = 0
        self.correct_count = 0                       # graded > 1 (Hard/Good/Easy)
        self._seen_ids: Set[int] = set()             # distinct cards touched
        self.completed = False
        self.end_reason = ""                         # "target" | "time" | "exhausted"

        # Focus metrics (Stage 6). Idle = time spent away between answers beyond
        # the threshold (a proxy for distraction, computed purely on grade events).
        self.idle_threshold = max(0.0, float(idle_threshold))
        self.idle_seconds = 0.0
        self.last_answer_at: Optional[float] = None
        self.current_streak = 0                      # consecutive non-Again answers
        self.best_streak = 0

        # Focus Lock (Stage 6). Level 2 sets a "leave penalty" target the first
        # time you try to leave (cards_done + lock_min_cards); cleared when you
        # confirm/keep-going. None means no leave attempt is pending.
        self.leave_target: Optional[int] = None
        self.finish_msg = "Finish the Blitz before you can leave."

    # ----- counting -----

    def record_answer(self, card_id, ease: int) -> None:
        now = time.time()
        if self.last_answer_at is not None:
            gap = now - self.last_answer_at
            if gap > self.idle_threshold:
                self.idle_seconds += gap - self.idle_threshold
        self.last_answer_at = now
        if self.first_answer_at is None:
            self.first_answer_at = now
        self.answers += 1
        if card_id is not None:
            self._seen_ids.add(int(card_id))
        if ease == 1:
            self.again_count += 1
            self.current_streak = 0
        else:
            self.correct_count += 1
            self.current_streak += 1
            if self.current_streak > self.best_streak:
                self.best_streak = self.current_streak

    @property
    def unique_cards(self) -> int:
        return len(self._seen_ids)

    @property
    def cards_done(self) -> int:
        """The counted value the bar shows, in the configured unit."""
        return self.unique_cards if self.count_mode == "unique" else self.answers

    @property
    def unit(self) -> str:
        return "cards" if self.count_mode == "unique" else "answers"

    # ----- time -----

    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    def active_seconds(self) -> float:
        """Elapsed time minus the idle stretches between answers."""
        return max(0.0, self.elapsed_seconds() - self.idle_seconds)

    def begin_engagement(self) -> None:
        """First interaction on a paused launch: clear the pause and rebase the
        elapsed clock to now, so the overnight idle gap isn't counted. No-op once
        engaged or for a normal (non-paused) launch."""
        if self.paused:
            self.paused = False
            self.started_at = time.time()

    def start_clock(self) -> None:
        """Begin the time-mode countdown (called on the first card flip). No-op
        after the first call or for non-time modes."""
        if self.mode == MODE_TIME and self.clock_started_at is None:
            self.clock_started_at = time.time()

    def clock_running(self) -> bool:
        return self.mode == MODE_TIME and self.clock_started_at is not None

    def target_ms(self) -> int:
        return int(self.target_seconds * 1000)

    def launch_to_first_ms(self) -> int:
        """Time from launch to the first graded answer (0 until one lands)."""
        if self.first_answer_at is None:
            return 0
        return int((self.first_answer_at - self.started_at) * 1000)

    def started_at_ms(self) -> int:
        # Time mode uses the flip-time clock base once it's running; everything
        # else (the card-mode elapsed clock) counts from the session start.
        base = self.clock_started_at if self.clock_started_at is not None else self.started_at
        return int(base * 1000)

    def deadline_ms(self) -> int:
        if self.mode == MODE_TIME and self.target_seconds > 0 and self.clock_started_at is not None:
            return int((self.clock_started_at + self.target_seconds) * 1000)
        return 0

    def remaining_seconds(self) -> float:
        if self.mode != MODE_TIME or self.target_seconds <= 0:
            return 0.0
        if self.clock_started_at is None:
            return self.target_seconds          # not started yet — full time
        return max(0.0, self.target_seconds - (time.time() - self.clock_started_at))

    # ----- derived stats -----

    def cards_per_min(self) -> float:
        s = self.elapsed_seconds()
        return self.cards_done / (s / 60.0) if s > 0 else 0.0

    def avg_seconds_per_card(self) -> float:
        c = self.unique_cards
        return self.elapsed_seconds() / c if c else 0.0

    def accuracy(self) -> float:
        if self.answers == 0:
            return 100.0
        return (self.correct_count / self.answers) * 100

    def progress_fraction(self) -> float:
        if self.mode == MODE_TIME:
            if self.target_seconds <= 0 or self.clock_started_at is None:
                return 0.0
            return min(1.0, (time.time() - self.clock_started_at) / self.target_seconds)
        if self.target_cards <= 0:
            return 0.0
        return min(1.0, self.cards_done / self.target_cards)

    def target_reached(self) -> bool:
        if self.mode == MODE_TIME:
            return (self.target_seconds > 0 and self.clock_started_at is not None
                    and (time.time() - self.clock_started_at) >= self.target_seconds)
        return self.target_cards > 0 and self.cards_done >= self.target_cards


# ----- Module-level single source of truth -----

_active: Optional[BlitzSession] = None


def get_active() -> Optional[BlitzSession]:
    return _active


def is_running() -> bool:
    return _active is not None and not _active.completed


def start(mode: str, **kwargs) -> BlitzSession:
    global _active
    _active = BlitzSession(mode, **kwargs)
    return _active


def clear() -> None:
    global _active
    _active = None
