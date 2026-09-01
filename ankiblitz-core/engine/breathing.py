"""Guided breathing pacer for the Pomodoro break screen.

A break is only restful if you actually down-shift, and "look away from the
screen" advice doesn't pace anything. This draws a circle that expands and
contracts on a fixed rhythm, with the phase named underneath and a per-phase
count, so there is something concrete to follow for a minute or two.

Two pieces:

  - ``BreathingPacer`` — the animation itself. A plain ``QWidget`` with a
    ``paintEvent``; no QML, no web view, no external assets. It advances a
    single 0–1 phase progress on a ~33 ms timer and repaints.
  - ``BreathingPanel`` — what the break screen actually embeds: a collapsed
    "Breathe" button that expands into the pacer and collapses again, so the
    break screen looks exactly as it always did until you ask for it.

Nothing here touches the Pomodoro cycle, the break countdown, or any config
value: the pacer is decorative and entirely self-contained. It stops its timer
when hidden or destroyed so a stepped-away break isn't repainting behind your
back.

Patterns are (phase, seconds) sequences. A phase of "hold" is drawn at whatever
size the preceding phase ended on, so a box pattern reads as a real square
rather than a circle that twitches at the corners.
"""

import math

from aqt.qt import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTimer,
    QPainter, QColor, QPen, Qt, QSize,
)

# Phase kinds.
IN = "in"
HOLD_FULL = "hold_full"
OUT = "out"
HOLD_EMPTY = "hold_empty"

_PHASE_TEXT = {
    IN: "Breathe in",
    HOLD_FULL: "Hold",
    OUT: "Breathe out",
    HOLD_EMPTY: "Hold",
}

# Each pattern is a list of (phase, seconds). Keep them short and even — this is
# a study break, not a breathwork session.
PATTERNS = {
    "box": {
        "label": "Box · 4-4-4-4",
        "hint": "Even square breathing — steadies you without making you sleepy.",
        "phases": [(IN, 4), (HOLD_FULL, 4), (OUT, 4), (HOLD_EMPTY, 4)],
    },
    "44": {
        "label": "Simple · 4-4",
        "hint": "In for four, out for four. Nothing to hold, nothing to count wrong.",
        "phases": [(IN, 4), (OUT, 4)],
    },
    "coherent": {
        "label": "Coherent · 5-5",
        "hint": "Six breaths a minute — the classic slow-breathing pace.",
        "phases": [(IN, 5), (OUT, 5)],
    },
    "478": {
        "label": "Calming · 4-7-8",
        "hint": "Long exhale. Best for a long break — it will make you drowsy.",
        "phases": [(IN, 4), (HOLD_FULL, 7), (OUT, 8)],
    },
}

PATTERN_ORDER = ["box", "44", "coherent", "478"]

DEFAULT_PATTERN = "box"

_TICK_MS = 33  # ~30 fps: smooth enough for a slow circle, cheap enough to ignore


def pattern_or_default(key: str) -> dict:
    return PATTERNS.get(key) or PATTERNS[DEFAULT_PATTERN]


class BreathingPacer(QWidget):
    """The expanding/contracting circle, its phase name, and the phase count."""

    def __init__(self, pattern_key: str = DEFAULT_PATTERN, parent=None):
        super().__init__(parent)
        self._phases = pattern_or_default(pattern_key)["phases"]
        self._index = 0          # which phase we're in
        self._elapsed = 0.0      # seconds into that phase
        self._cycles = 0         # completed full rounds, for the count under the circle
        self.setMinimumHeight(210)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ----- lifecycle -----

    def set_pattern(self, pattern_key: str) -> None:
        self._phases = pattern_or_default(pattern_key)["phases"]
        self.reset()

    def reset(self) -> None:
        self._index = 0
        self._elapsed = 0.0
        self._cycles = 0
        self.update()

    def start(self) -> None:
        self.reset()
        if not self._timer.isActive():
            self._timer.start(_TICK_MS)

    def stop(self) -> None:
        self._timer.stop()

    # Qt calls these when the panel collapses/expands or the dialog closes, so
    # the timer can never outlive what it's animating.
    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(_TICK_MS)

    def sizeHint(self) -> QSize:
        return QSize(260, 210)

    def _tick(self) -> None:
        self._elapsed += _TICK_MS / 1000.0
        # while, not if: a stalled event loop (a slow repaint elsewhere) can hand
        # us a jump bigger than one whole phase.
        while self._elapsed >= self._phases[self._index][1]:
            self._elapsed -= self._phases[self._index][1]
            self._index = (self._index + 1) % len(self._phases)
            if self._index == 0:
                self._cycles += 1
        self.update()

    # ----- drawing -----

    def _phase(self):
        return self._phases[self._index]

    def _fill(self) -> float:
        """How "full" the lungs are, 0–1, for the current instant.

        In/out phases ease between the two with a raised cosine so the circle
        doesn't snap direction at the turn; holds sit still at the end of
        whichever phase preceded them.
        """
        kind, secs = self._phase()
        t = min(1.0, self._elapsed / secs) if secs > 0 else 1.0
        eased = (1.0 - math.cos(math.pi * t)) / 2.0
        if kind == IN:
            return eased
        if kind == OUT:
            return 1.0 - eased
        return 1.0 if kind == HOLD_FULL else 0.0

    def _count_text(self) -> str:
        """Seconds remaining in this phase, counted down like you'd say them."""
        _, secs = self._phase()
        return str(max(1, int(math.ceil(secs - self._elapsed))))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        circle_box = min(w, h - 58)          # leave room for the labels below
        cx, cy = w / 2.0, (circle_box / 2.0) + 6
        outer = max(24.0, circle_box / 2.0 - 8)
        inner = outer * 0.34                  # smallest the circle ever gets
        radius = inner + (outer - inner) * self._fill()

        accent = QColor("#3b82f6")
        text_col = self.palette().text().color()

        # Track: where a full breath reaches, so the circle has something to
        # grow into rather than floating in space.
        track = QColor(text_col)
        track.setAlpha(38)
        painter.setPen(QPen(track, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(cx - outer), int(cy - outer),
                            int(outer * 2), int(outer * 2))

        # The breath itself: a soft disc with a firmer rim.
        fill = QColor(accent)
        fill.setAlpha(58)
        painter.setBrush(fill)
        rim = QColor(accent)
        rim.setAlpha(190)
        painter.setPen(QPen(rim, 2.0))
        painter.drawEllipse(int(cx - radius), int(cy - radius),
                            int(radius * 2), int(radius * 2))

        # Count, inside the circle.
        painter.setPen(QPen(text_col))
        font = painter.font()
        font.setPointSize(22)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            int(cx - outer), int(cy - outer), int(outer * 2), int(outer * 2),
            int(Qt.AlignmentFlag.AlignCenter), self._count_text())

        # Phase name + rounds, under the circle.
        font.setPointSize(13)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(0, int(cy + outer + 6), w, 22,
                         int(Qt.AlignmentFlag.AlignCenter),
                         _PHASE_TEXT[self._phase()[0]])

        if self._cycles:
            faint = QColor(text_col)
            faint.setAlpha(120)
            painter.setPen(QPen(faint))
            font.setPointSize(11)
            painter.setFont(font)
            painter.drawText(
                0, int(cy + outer + 28), w, 20,
                int(Qt.AlignmentFlag.AlignCenter),
                f"{self._cycles} breath{'s' if self._cycles != 1 else ''}")
        painter.end()


class BreathingPanel(QWidget):
    """Collapsed "Breathe" button that expands into the pacer.

    Collapsed is the resting state: the break screen keeps its usual shape and
    the animation only exists once you've asked for it. Expanding reveals the
    pacer, a pattern picker, and a close button.
    """

    def __init__(self, pattern_key: str = DEFAULT_PATTERN, parent=None):
        super().__init__(parent)
        self._pattern_key = pattern_key if pattern_key in PATTERNS else DEFAULT_PATTERN

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # --- collapsed ---
        open_row = QHBoxLayout()
        open_row.addStretch(1)
        self._open_btn = QPushButton("🫁 Breathe")
        self._open_btn.setToolTip("A guided breathing pacer to follow while you rest.")
        self._open_btn.setMaximumWidth(140)
        self._open_btn.clicked.connect(self._expand)
        open_row.addWidget(self._open_btn)
        open_row.addStretch(1)
        lay.addLayout(open_row)

        # --- expanded ---
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 2, 0, 0)
        body.setSpacing(2)

        self._pacer = BreathingPacer(self._pattern_key)
        body.addWidget(self._pacer)

        self._hint = QLabel(pattern_or_default(self._pattern_key)["hint"])
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("font-size: 11px; opacity: 0.5;")
        body.addWidget(self._hint)

        ctl = QHBoxLayout()
        ctl.addStretch(1)
        close = QPushButton("✕")
        close.setMaximumWidth(36)
        close.setToolTip("Hide the pacer")
        close.clicked.connect(self._collapse)
        ctl.addWidget(close)
        self._picker = QComboBox()
        for key in PATTERN_ORDER:
            self._picker.addItem(PATTERNS[key]["label"], key)
        pi = self._picker.findData(self._pattern_key)
        if pi >= 0:
            self._picker.setCurrentIndex(pi)
        self._picker.currentIndexChanged.connect(self._change_pattern)
        ctl.addWidget(self._picker)
        ctl.addStretch(1)
        body.addLayout(ctl)

        self._body.setVisible(False)
        lay.addWidget(self._body)

    def _expand(self) -> None:
        self._open_btn.setVisible(False)
        self._body.setVisible(True)
        self._pacer.start()

    def _collapse(self) -> None:
        self._pacer.stop()
        self._body.setVisible(False)
        self._open_btn.setVisible(True)

    def _change_pattern(self) -> None:
        key = self._picker.currentData()
        if not key:
            return
        self._pattern_key = key
        self._hint.setText(pattern_or_default(key)["hint"])
        self._pacer.set_pattern(key)

    def stop(self) -> None:
        """Called when the break screen goes away."""
        self._pacer.stop()
