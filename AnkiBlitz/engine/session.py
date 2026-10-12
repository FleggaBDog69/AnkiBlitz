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

Alongside the Blitz there is an ``AmbientSession`` (``_ambient``): the tracker
for an ordinary review session with no Blitz running, so the bar can still show
how far through the due pile you are. It records nothing and completes nothing —
see the class docstring.

Both trackers share ``_PaceStats``, which carries the two things the bar needs
beyond a raw count: the **grade split** (how much of the work done so far was
clean vs. had to be repeated, drawn as the green/red segments) and the session's
**press gaps**, which the time estimate (``forecast.py``) blends with your
history for its seconds-per-press.
"""

import time
from collections import deque
from typing import Optional, Set

# The last few answer-to-answer gaps, kept for a band's width when a card was
# graded without a flip we saw.
PACE_WINDOW = 10
# Each gap is clamped rather than dropped, so a genuinely hard card still counts
# as a slow card while a walk-away can't count as a 20-minute one.
PACE_CAP = 120.0

# Segment widths are clamped against the session's OWN median rather than
# against absolute seconds, so the bar reads the same whether you're doing
# 3-second clozes or 40-second cases: twice your typical card is twice as wide,
# and no single card can swallow the bar.
SEG_MIN_RATIO = 0.25
SEG_MAX_RATIO = 4.0
# Ceiling on how many bands to ship and draw. Adjacent same-grade cards merge
# first, which costs nothing to look at — two touching bands of one colour are
# already indistinguishable from one.
MAX_SEGMENTS = 240

MODE_CARDS = "cards"
MODE_TIME = "time"
MODE_FRACTION = "fraction"


class _PaceStats:
    """The grade split and the rolling pace, shared by both trackers.

    Subclasses supply ``count_mode``, ``cards_done`` and ``_seen_ids``; this
    supplies what the bar draws on top of them. Call ``_init_pace()`` from
    ``__init__`` and ``_note_pace()`` from ``record_answer``.
    """

    def _init_pace(self) -> None:
        self._gaps = deque(maxlen=PACE_WINDOW)
        self._pace_last: Optional[float] = None
        self.again_count = 0
        self.correct_count = 0
        self._lapsed_ids: Set[int] = set()   # cards that got Again at least once
        # One [seconds, is_again] per answer, in the order you did them — the
        # bar's texture. See segment_weights().
        self.segments: list = []
        self._q_shown_at: Optional[float] = None
        self._pending_think: Optional[float] = None
        # Every gap this session (clamped like the pace), for the estimate's
        # seconds-per-press — see forecast.seconds_per_press.
        self.gap_sum = 0.0
        self.gap_n = 0

    # ----- the thinking window (what a segment's width measures) -----

    def note_question_shown(self) -> None:
        self._q_shown_at = time.time()

    def note_answer_shown(self) -> None:
        """Close the thinking window: question shown -> answer shown.

        Only the question side counts toward a card's width. The answer side is
        reading, not working — it's where you sit with a card you already knew,
        or where you go and make a coffee — so counting it would make the widest
        bands the ones you thought about least.
        """
        if self._q_shown_at is not None:
            self._pending_think = min(time.time() - self._q_shown_at, PACE_CAP)
            self._q_shown_at = None

    def _note_pace(self, card_id, ease: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        if self._pace_last is not None:
            gap = min(now - self._pace_last, PACE_CAP)
            self._gaps.append(gap)
            self.gap_sum += gap
            self.gap_n += 1
        self._pace_last = now
        if ease == 1:
            self.again_count += 1
            if card_id is not None:
                self._lapsed_ids.add(int(card_id))
        else:
            self.correct_count += 1
        think = self._pending_think
        self._pending_think = None
        if think is None:
            # Graded without a flip we saw — the bar armed mid-card, or an undo.
            # Fall back to the answer-to-answer gap so the band still has a
            # width rather than collapsing to nothing.
            think = self._gaps[-1] if self._gaps else 0.0
        self.segments.append([think, 1 if ease == 1 else 0])

    def segment_weights(self, limit: int = MAX_SEGMENTS) -> list:
        """The bar's texture as ``[[weight, is_again], ...]``, oldest first.

        Weights are clamped into [SEG_MIN_RATIO, SEG_MAX_RATIO] × the session's
        own median, so a fast card can't vanish and a slow one can't take the
        bar over. The caller normalises them across the filled region — the fill
        edge keeps meaning "this much of the pile is done"; the texture inside
        it is the rhythm of how it went.
        """
        segs = self.segments
        if not segs:
            return []
        ordered = sorted(s[0] for s in segs)
        med = ordered[len(ordered) // 2] or 1.0
        lo, hi = med * SEG_MIN_RATIO, med * SEG_MAX_RATIO
        out = [[min(max(s[0], lo), hi), s[1]] for s in segs]
        if len(out) > limit:
            merged: list = []
            for w, a in out:
                if merged and merged[-1][1] == a:
                    merged[-1][0] += w
                else:
                    merged.append([w, a])
            out = merged
        if len(out) > limit:
            # Still too many colour changes to draw honestly. Roll the oldest
            # into one band — the near past is what you can still act on.
            cut = len(out) - limit + 1
            head = out[:cut]
            out = [[sum(w for w, _ in head), head[-1][1]]] + out[cut:]
        return [[round(w, 2), a] for w, a in out]

    # ----- the grade split (the red / green segments) -----
    #
    # Both parts are in the unit the counter shows, and they always sum to
    # exactly cards_done — the bar must not lie applies to its colours too.

    @property
    def done_again(self) -> int:
        """The red part: in `unique` mode, cards that needed a repeat at all;
        in `answers` mode, the Again presses themselves.

        A card that lapsed and was later got right stays red. It cost the extra
        pass and it is the reason the estimate moved, so folding it back into
        the green would hide exactly what the split is there to show.
        """
        if getattr(self, "count_mode", "unique") == "unique":
            return len(self._lapsed_ids)
        return self.again_count

    @property
    def done_good(self) -> int:
        return max(0, self.cards_done - self.done_again)


class BlitzSession(_PaceStats):
    def __init__(self, mode: str, target_cards: int = 0, target_seconds: float = 0.0,
                 count_mode: str = "unique", deck_id: Optional[int] = None,
                 label: str = "", is_quick_start: bool = False,
                 is_pomodoro: bool = False, idle_threshold: float = 60.0,
                 paused: bool = False, lock_level: Optional[int] = None):
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
        self._seen_ids: Set[int] = set()             # distinct cards touched
        # again_count / correct_count / the rolling pace / the lapsed set.
        self._init_pace()
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
        # Focus Lock level chosen for THIS Blitz in the Start dialog. None means
        # "use the configured level"; focus.effective_level reads it. Never
        # written back to config — one Blitz's choice is not a new default.
        self.lock_level_override: Optional[int] = (
            None if lock_level is None else max(0, min(3, int(lock_level))))

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
        self._note_pace(card_id, ease, now)
        if ease == 1:
            self.current_streak = 0
        else:
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
            # The card has been on screen since before you engaged; start its
            # thinking window now rather than banking the away time into it.
            self._q_shown_at = time.time()

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


class AmbientSession(_PaceStats):
    """The whole-pile tracker for an ordinary review session — no Blitz running.

    This is deliberately NOT a Blitz: nothing is recorded, nothing completes,
    no Focus Lock hangs off it, and it never reaches stats. It exists so that
    just working through your dues still gets an honest progress bar instead of
    a blank screen.

    It does keep the grade split and the pace (via ``_PaceStats``) — the bar's
    red/green segments and its time estimate are the same on an ordinary session
    as in a Blitz, because the question "how long is this pile going to take" is
    the same question either way. Those live only for the session; nothing is
    written anywhere.

    The target is live rather than snapshotted: ``cards_done + remaining_due``,
    with ``remaining_due`` refreshed from the scheduler on every push. A
    learning card that Again-requeues therefore pushes the target out by one
    instead of letting the bar claim progress it hasn't made — the same "the bar
    must not lie" rule the Blitz bar follows. The bar reaches 100% exactly when
    the queue empties.
    """

    def __init__(self, count_mode: str = "unique"):
        self.count_mode = count_mode if count_mode in ("unique", "answers") else "unique"
        self.started_at = time.time()
        self.answers = 0
        self.remaining_due = 0
        self._seen_ids: Set[int] = set()
        self._init_pace()

    def record_answer(self, card_id, ease: int = 0) -> None:
        self.answers += 1
        if card_id is not None:
            self._seen_ids.add(int(card_id))
        self._note_pace(card_id, ease)

    def set_remaining(self, n: int) -> None:
        self.remaining_due = max(0, int(n))

    @property
    def cards_done(self) -> int:
        return len(self._seen_ids) if self.count_mode == "unique" else self.answers

    @property
    def target(self) -> int:
        return self.cards_done + self.remaining_due

    @property
    def unit(self) -> str:
        return "cards" if self.count_mode == "unique" else "answers"

    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    def started_at_ms(self) -> int:
        return int(self.started_at * 1000)


# ----- Module-level single source of truth -----

_active: Optional[BlitzSession] = None
_ambient: Optional[AmbientSession] = None


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


# ----- Ambient (non-Blitz) review tracker -----

def get_ambient() -> Optional[AmbientSession]:
    return _ambient


def start_ambient(count_mode: str = "unique") -> AmbientSession:
    global _ambient
    _ambient = AmbientSession(count_mode)
    return _ambient


def clear_ambient() -> None:
    global _ambient
    _ambient = None
