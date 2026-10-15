"""AnkiBlitz settings — one tabbed window.

A single ``QDialog`` with a master switch plus one tab per tool. Each tab is a
self-contained panel that reads its own config section on open and writes only
that section on save, so the tools stay decoupled (mirrors the namespaced
config in config.py). Settings are read live per card, so saving takes effect on
the next card with no extra refresh.

Each panel exposes the full option set inherited from the original add-on it
replaces (Sprint Mode, Progressive Word Reveal); Speed Focus uses the redefined
adaptive auto-reveal knobs.
"""

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPalette,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip

from .config import get_section, save_section, suite_enabled, set_suite_enabled
from .engine import adaptive, breathing, pace, presets, tts_sync

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked

# Representative cards for the preview, mapped to adaptive.delay_for primitives.
# "Typical" sits at FSRS difficulty 5, where the difficulty factor is exactly
# 1 — the same footing as the "You" column, whose times have it divided out.
_PREVIEW_CARDS = [
    ("Easy", dict(ease=2500, lapses=0, reps=10, unfamiliar=False, is_new=False, difficulty=3.5)),
    ("Typical", dict(ease=2500, lapses=1, reps=10, unfamiliar=False, is_new=False, difficulty=5.0)),
    ("Hard", dict(ease=1700, lapses=5, reps=15, unfamiliar=False, is_new=False, difficulty=8.5)),
    ("New", dict(ease=0, lapses=0, reps=0, unfamiliar=True, is_new=True, difficulty=None)),
]
_TYPICAL = _PREVIEW_CARDS[1][1]
# Word Reveal's preview rows.
_PREVIEW_WORDS = (15, 25)
# Until aSFM has learned your own lengths: (question words, answer words).
_DEFAULT_LENGTHS = ((8, 10), (12, 10), (16, 15), (24, 20))


def _preview_lengths(cfg: dict):
    """(rows, measured): your commonest lengths with your reveal times, or the
    stock lengths with none."""
    rows = pace.length_rows(cfg)
    if rows:
        return rows, True
    return [{"words": q, "answer_words": a, "reveal_s": None}
            for q, a in _DEFAULT_LENGTHS], False




def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: gray; font-size: 11px;")
    return lbl


def _double(lo: float, hi: float, step: float, decimals: int, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    if suffix:
        sb.setSuffix(suffix)
    return sb


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _section(title: str, sub: str = "") -> QLabel:
    """A section heading, with an optional one-line explanation under it."""
    html = f"<div style='font-size: 13px; font-weight: 600;'>{title}</div>"
    if sub:
        html += f"<div style='color: gray; font-size: 11px;'>{sub}</div>"
    lbl = QLabel(html)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    lbl.setContentsMargins(0, 10, 0, 2)
    return lbl


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setHorizontalSpacing(12)
    return form


def _preview_card(title: str, sub: str):
    """The bordered panel a live preview sits in; returns (frame, layout)."""
    card = QFrame()
    card.setObjectName("abPreview")
    card.setStyleSheet(
        "#abPreview { border: 1px solid palette(mid); border-radius: 8px;"
        " background: palette(base); }")
    inner = QVBoxLayout(card)
    inner.setContentsMargins(14, 12, 14, 12)
    lbl = _section(title, sub)
    lbl.setContentsMargins(0, 0, 0, 2)
    inner.addWidget(lbl)
    return card, inner


def _table_style(widget: QWidget):
    """(band colour, header-cell attributes) for a gridless preview table in
    the theme's own colours, so it reads the same in light and dark mode."""
    pal = widget.palette()
    band = pal.color(QPalette.ColorRole.AlternateBase).name()
    rule = pal.color(QPalette.ColorRole.Mid).name()
    th = (f"style='color: gray; font-size: 11px; font-weight: 600;"
          f" border-bottom: 1px solid {rule};'")
    return band, th


def _scroll(inner: QWidget) -> QScrollArea:
    """Wrap a tall panel so dense tabs stay usable on small screens."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area


class _KeyCaptureEdit(QLineEdit):
    """Read-only field that records the next printable key the user presses."""

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaxLength(1)
        self.setFixedWidth(56)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText("key")
        self.setToolTip("Click here, then press the key you want")
        self.setText(str(key or ""))

    def keyPressEvent(self, event):
        text = event.text()
        # Esc and other control keys carry a one-character text too ("\x1b"),
        # so test for a printable, non-space character rather than any text.
        if len(text) == 1 and text.isprintable() and not text.isspace():
            self.setText(text)
        else:
            super().keyPressEvent(event)

    def key_value(self):
        return (self.text() or "p").lower()


class _FilterList(QWidget):
    """A labelled, searchable list of checkable items."""

    def __init__(self, title, all_items, checked_items, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setMinimumHeight(140)
        checked_set = set(checked_items or [])
        for name in all_items:
            item = QListWidgetItem(name)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(_CHECKED if name in checked_set else _UNCHECKED)
            self.list.addItem(item)
        # Preserve any saved entries that no longer exist in the collection.
        for name in checked_set:
            if name not in set(all_items):
                item = QListWidgetItem(name)
                item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item.setCheckState(_CHECKED)
                self.list.addItem(item)
        layout.addWidget(self.list)

    def _filter(self, text):
        text = (text or "").lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(text not in item.text().lower())

    def tick(self, names):
        wanted = set(names)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.text() in wanted:
                item.setCheckState(_CHECKED)

    def checked(self):
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == _CHECKED:
                out.append(item.text())
        return out


def _collect_names():
    notetypes, decks = [], []
    if mw.col is not None:
        try:
            notetypes = sorted(nt.name for nt in mw.col.models.all_names_and_ids())
        except Exception:
            notetypes = []
        try:
            decks = sorted(d.name for d in mw.col.decks.all_names_and_ids())
        except Exception:
            decks = []
    return notetypes, decks


# --------------------------------------------------------------------------- #
#  Speed Focus (adaptive auto-reveal) panel
# --------------------------------------------------------------------------- #

class SpeedFocusPanel(QWidget):
    SECTION = "speed_focus"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)

        # The knobs scroll in their own column, so the preview beside them
        # stays in view however far down you are. (The dialog doesn't wrap
        # this tab in a scroll area of its own — see SettingsDialog.)
        outer = QHBoxLayout(self)
        outer.setSpacing(14)
        knobs = QWidget()
        layout = QVBoxLayout(knobs)   # left column: the knobs
        layout.setContentsMargins(0, 0, 10, 0)
        outer.addWidget(_scroll(knobs), 1)

        self.enabled = QCheckBox("Enable adaptive auto-reveal")
        font = self.enabled.font()
        font.setBold(True)
        self.enabled.setFont(font)
        self.enabled.setChecked(bool(cfg["enabled"]))
        layout.addWidget(self.enabled)
        layout.addWidget(_hint(
            "After the question finishes revealing, AnkiBlitz waits a computed "
            "delay, then shows the answer automatically. It never grades the "
            "card for you."))

        layout.addWidget(_section("How long to wait",
                                  "Base time plus reading time, then clamped."))
        form = _form()

        self.base = _double(0.0, 60.0, 0.5, 1, " s")
        self.base.setValue(float(cfg["base_seconds"]))
        form.addRow("Base time:", self.base)

        self.per_word = _double(0.0, 5.0, 0.05, 2, " s")
        self.per_word.setValue(float(cfg["seconds_per_word"]))
        form.addRow("Per question word:", self.per_word)

        # --- answer length: 0 s per answer word is the off switch ---
        self.per_answer_word = _double(0.0, 5.0, 0.05, 2, " s")
        self.per_answer_word.setValue(float(cfg["seconds_per_answer_word"]))
        form.addRow("Per answer word:", self.per_answer_word)

        self.max_answer = _double(0.0, 60.0, 0.5, 1, " s")
        self.max_answer.setValue(float(cfg["max_answer_seconds"]))
        form.addRow("Answer time cap:", self.max_answer)

        self.min_delay = _double(0.0, 120.0, 0.5, 1, " s")
        self.min_delay.setValue(float(cfg["min_delay_seconds"]))
        form.addRow("Shortest wait:", self.min_delay)

        self.max_delay = _double(0.0, 300.0, 1.0, 1, " s")
        self.max_delay.setValue(float(cfg["max_delay_seconds"]))
        form.addRow("Longest wait:", self.max_delay)
        # A maximum under the minimum is clamped up to it at runtime anyway, so
        # don't let the spin box show a number that never applies.
        self.min_delay.valueChanged.connect(self.max_delay.setMinimum)
        self.max_delay.setMinimum(self.min_delay.value())
        self.per_answer_word.valueChanged.connect(
            lambda v: self.max_answer.setEnabled(v > 0))
        self.max_answer.setEnabled(self.per_answer_word.value() > 0)

        layout.addLayout(form)

        layout.addWidget(_hint(
            "Only words you can see count — hidden fields and tags don't. Answer "
            "words are the answer side's (on cloze, the hidden text); the cap is "
            "the most they can add, and 0 s per answer word turns them off."))

        layout.addWidget(_section("Adjustments",
                                  "Extra time for cards you don't know well yet."))
        mod = _form()
        self.unfamiliar = _double(1.0, 5.0, 0.1, 2, "×")
        self.unfamiliar.setValue(float(cfg["unfamiliar_multiplier"]))
        mod.addRow("Learning / relearning:", self.unfamiliar)

        # New-card multiplier with its own enable toggle right beside it.
        self.new_mult = _double(1.0, 5.0, 0.1, 2, "×")
        self.new_mult.setValue(float(cfg["new_multiplier"]))
        self.enable_on_new = QCheckBox("Run on new cards")
        self.enable_on_new.setChecked(bool(cfg["enable_on_new"]))
        new_row = QHBoxLayout()
        new_row.setContentsMargins(0, 0, 0, 0)
        new_row.addWidget(self.new_mult)
        new_row.addWidget(self.enable_on_new)
        new_row.addStretch(1)
        mod.addRow("New cards:", new_row)
        self.enable_on_new.toggled.connect(self.new_mult.setEnabled)
        self.new_mult.setEnabled(self.enable_on_new.isChecked())

        self.difficulty = _double(0.0, 1.0, 0.05, 2, "")
        self.difficulty.setValue(float(cfg["difficulty_weight"]))
        mod.addRow("Difficulty weight:", self.difficulty)
        layout.addLayout(mod)
        layout.addWidget(_hint(
            "Time = base + per word × question words + answer time, × the new or "
            "learning modifier, nudged by up to ± the difficulty weight (0 = "
            "ignore difficulty), then clamped to the shortest and longest wait. "
            "Difficulty comes from FSRS, or from ease and lapses on SM-2."))

        self._build_kinds(layout, cfg)

        layout.addWidget(_section("Countdown and heads-up"))
        self.show_countdown = QCheckBox("Show a countdown bar along the bottom")
        self.show_countdown.setChecked(bool(cfg["show_countdown"]))
        layout.addWidget(self.show_countdown)

        self.warn_colour = QCheckBox("Turn the bar red at the warning point")
        self.warn_colour.setChecked(bool(cfg["countdown_warning_colour"]))
        layout.addWidget(self.warn_colour)
        self.show_countdown.toggled.connect(self.warn_colour.setEnabled)
        self.warn_colour.setEnabled(self.show_countdown.isChecked())

        self.warning_sound = QCheckBox("Play a warning sound before revealing")
        self.warning_sound.setChecked(bool(cfg["warning_sound"]))
        layout.addWidget(self.warning_sound)

        warn_form = _form()
        self.warn_pct = QSpinBox()
        self.warn_pct.setRange(5, 95)
        self.warn_pct.setSuffix(" % of the wait")
        self.warn_pct.setValue(int(cfg["warning_at_percent"]))
        warn_form.addRow("Warning point:", self.warn_pct)

        def _sync_warn(*_):
            colour = self.show_countdown.isChecked() and self.warn_colour.isChecked()
            self.warn_pct.setEnabled(self.warning_sound.isChecked() or colour)
        for box in (self.show_countdown, self.warn_colour, self.warning_sound):
            box.toggled.connect(_sync_warn)
        _sync_warn()

        self.min_post = _double(0.0, 30.0, 0.5, 1, " s")
        self.min_post.setValue(float(cfg["min_post_seconds"]))
        warn_form.addRow("Hold after reveal:", self.min_post)
        layout.addLayout(warn_form)
        layout.addWidget(_hint(
            "The sound plays, and the bar turns red, once this much of the wait "
            "has passed. For your own sound, put alert.flac/.ogg/.opus/.wav in "
            "user_files.\n\n“Hold after reveal”: the answer never shows sooner "
            "than this after the words finish revealing."))

        layout.addWidget(_section("Need longer on a card?",
                                  "Hold the timer, then carry on where it stopped."))
        self.more_time_button = QCheckBox("Show a “More time” button on the card")
        self.more_time_button.setChecked(bool(cfg["more_time_button"]))
        layout.addWidget(self.more_time_button)
        layout.addWidget(_hint(
            "Faint until you hover it. While the timer is held, a “paused” badge "
            "takes its place — click it to resume."))

        self.pause_key_enabled = QCheckBox("Pause key")
        self.pause_key_enabled.setChecked(bool(cfg["pause_key_enabled"]))
        self.pause_key = _KeyCaptureEdit(cfg["pause_key"])
        key_row = QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.addWidget(self.pause_key_enabled)
        key_row.addWidget(self.pause_key)
        key_row.addStretch(1)
        layout.addLayout(key_row)
        self.pause_key_enabled.toggled.connect(self.pause_key.setEnabled)
        self.pause_key.setEnabled(self.pause_key_enabled.isChecked())
        layout.addWidget(_hint(
            "Press once to hold, again to carry on. The hold sticks across cards "
            "until you release it. It can share the reveal key: the first press "
            "finishes the reveal, the next one pauses."))

        layout.addWidget(_section("Learn my pace",
                                  "Let AnkiBlitz fit the timer to how fast you really are."))
        self.learn = QCheckBox("Learn my pace from my reviews")
        self.learn.setChecked(bool(cfg["learn_my_pace"]))
        layout.addWidget(self.learn)
        layout.addWidget(_hint(
            "Off until you tick it. When on, AnkiBlitz keeps a small tally of how "
            "quickly you reveal cards — counts and timings by card length, never "
            "which cards — in one file on this computer. It's never sent "
            "anywhere. Turning it off stops recording straight away."))

        target_form = _form()
        self.target = QSpinBox()
        self.target.setRange(5, 50)
        self.target.setSuffix(" % of cards")
        self.target.setValue(int(cfg["target_timer_wins_percent"]))
        target_form.addRow("Timer beats me on:", self.target)
        layout.addLayout(target_form)

        self.auto_tune = QCheckBox("Auto-tune the timer to how fast I reveal cards")
        self.auto_tune.setChecked(bool(cfg["auto_tune_enabled"]))
        layout.addWidget(self.auto_tune)

        self.pace_label = QLabel()
        layout.addWidget(self.pace_label)

        # The detail lives in pop-ups, so this tab stays a handful of controls.
        btn_row = QHBoxLayout()
        self.calibrate_btn = QPushButton("Calibrate…")
        self.calibrate_btn.setToolTip("Suggest timings from your own reveals")
        self.calibrate_btn.clicked.connect(self._on_calibrate)
        btn_row.addWidget(self.calibrate_btn)
        self.details_btn = QPushButton("Details…")
        self.details_btn.setToolTip("Each kind of card's pace, and recent sessions")
        self.details_btn.clicked.connect(self._on_details)
        btn_row.addWidget(self.details_btn)
        self.reset_pace_btn = QPushButton("Reset")
        self.reset_pace_btn.setToolTip("Put every learned pace back to 1.00×")
        self.reset_pace_btn.clicked.connect(self._on_reset_pace)
        btn_row.addWidget(self.reset_pace_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addWidget(_hint(
            "“Timer beats me on” is how often the answer should show before you "
            "reveal it. Auto-tune nudges the timer after every card; Calibrate "
            "fits your settings to your reveals in one go, and shows you the "
            "numbers first."))
        self._pace_reset_pending = None    # None | "all" (Reset) | "rebase" (Calibrate)
        self._pace_refitted = set()        # kinds whose own setting Calibrate refitted
        self.auto_tune.toggled.connect(self._refresh_pace)
        self.learn.toggled.connect(self._refresh_pace)

        layout.addStretch(1)

        # --- live preview: right column, pinned to the top so it stays in
        # view while you adjust the knobs on the left ---
        card, side = _preview_card("Preview", "Seconds until the answer shows")
        card.setFixedWidth(340)
        outer.addWidget(card, 0)
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.preview)
        self.preview_hint = _hint("")
        side.addWidget(self.preview_hint)
        side.addStretch(1)

        for w in (self.base, self.per_word, self.min_delay, self.max_delay,
                  self.unfamiliar, self.new_mult, self.difficulty,
                  self.per_answer_word, self.max_answer):
            w.valueChanged.connect(self._update_preview)
        self.enable_on_new.toggled.connect(self._update_preview)
        self.target.valueChanged.connect(self._update_preview)
        self._refresh_pace()


    def _build_kinds(self, layout, cfg):
        """The "Kinds of card" section. Not part of profiles."""
        # --- Kinds of card: skipped, picture, one-by-one. The deck / note-type
        # lists live in a pop-up (_PickDialog); the tab only shows a summary.
        self._names = _collect_names()
        self._skip = {"nt": list(cfg["excluded_note_types"]),
                      "decks": list(cfg["excluded_decks"])}
        self._picture = {"nt": list(cfg["fixed_time_note_types"]),
                         "decks": list(cfg["fixed_time_decks"])}
        layout.addWidget(_section("Kinds of card",
                                  "What skips the timer, and how pictures and "
                                  "one-by-one clozes are timed."))
        kinds = _form()
        self.skip_btn = QPushButton()
        self.skip_btn.clicked.connect(lambda: self._pick("skip"))
        kinds.addRow("No timer on:", self.skip_btn)

        self.fixed_enabled = QCheckBox("Set time")
        self.fixed_enabled.setChecked(bool(cfg["fixed_time_enabled"]))
        self.fixed_base = _double(0.5, 60.0, 0.5, 1, " s")
        self.fixed_base.setValue(float(cfg["fixed_time_base_seconds"]))
        self.picture_btn = QPushButton()
        self.picture_btn.clicked.connect(lambda: self._pick("picture"))
        pic_row = QHBoxLayout()
        pic_row.setContentsMargins(0, 0, 0, 0)
        for w in (self.fixed_enabled, self.fixed_base, self.picture_btn):
            pic_row.addWidget(w)
        pic_row.addStretch(1)
        kinds.addRow("Picture cards:", pic_row)
        for w in (self.fixed_base, self.picture_btn):
            self.fixed_enabled.toggled.connect(w.setEnabled)
            w.setEnabled(self.fixed_enabled.isChecked())

        self.obo_mode = QComboBox()
        for label, value in (("A timer per cloze", "per_cloze"),
                             ("Whole card × multiplier", "multiplier"),
                             ("Off — time like any card", "off")):
            self.obo_mode.addItem(label, value)
        idx = self.obo_mode.findData(adaptive.one_by_one_mode(cfg))
        self.obo_mode.setCurrentIndex(max(0, idx))
        kinds.addRow("One-by-one:", self.obo_mode)
        self.obo_per_cloze = _double(0.0, 30.0, 0.5, 1, " s")
        self.obo_per_cloze.setValue(float(cfg["one_by_one_seconds_per_cloze"]))
        self.obo_per_word = _double(0.0, 5.0, 0.05, 2, " s")
        self.obo_per_word.setValue(float(cfg["one_by_one_seconds_per_word"]))
        self.obo_max = _double(0.5, 60.0, 0.5, 1, " s")
        self.obo_max.setValue(float(cfg["one_by_one_max_cloze_seconds"]))
        self.obo_mult = _double(0.5, 5.0, 0.05, 2, "×")
        self.obo_mult.setValue(float(cfg["one_by_one_multiplier"]))
        # One line per mode, so the form stays short.
        self.obo_cloze_row = QWidget()
        cl = QHBoxLayout(self.obo_cloze_row)
        cl.setContentsMargins(0, 0, 0, 0)
        for w in (self.obo_per_cloze, QLabel("+"), self.obo_per_word,
                  QLabel("per word, up to"), self.obo_max):
            cl.addWidget(w)
        cl.addStretch(1)
        kinds.addRow("Each cloze:", self.obo_cloze_row)
        kinds.addRow("Multiplier:", self.obo_mult)
        layout.addLayout(kinds)
        layout.addWidget(_hint(
            "Picture cards get a set time instead of a word count. One-by-one "
            "cards (the AnKing “One by one” field) get a timer per cloze, each "
            "uncovering the next; the first cloze also gets the question's "
            "reading time. Needs the AnKing template doing one-by-one on the "
            "front."))

        def _obo_mode_changed(*_):
            mode = self.obo_mode.currentData()
            for w in (self.obo_per_cloze, self.obo_per_word, self.obo_max):
                w.setEnabled(mode == "per_cloze")
            self.obo_mult.setEnabled(mode == "multiplier")
            # Show only the row the chosen mode uses (Qt 6.4+; older Qt just
            # greys the other out, above).
            if hasattr(kinds, "setRowVisible"):
                kinds.setRowVisible(self.obo_cloze_row, mode == "per_cloze")
                kinds.setRowVisible(self.obo_mult, mode == "multiplier")
        self.obo_mode.currentIndexChanged.connect(_obo_mode_changed)
        _obo_mode_changed()
        self._refresh_pick_buttons()

    def _current_cfg(self):
        return {
            "base_seconds": self.base.value(),
            "seconds_per_word": self.per_word.value(),
            "seconds_per_answer_word": self.per_answer_word.value(),
            "max_answer_seconds": self.max_answer.value(),
            "min_delay_seconds": self.min_delay.value(),
            "max_delay_seconds": self.max_delay.value(),
            "unfamiliar_multiplier": self.unfamiliar.value(),
            "new_multiplier": self.new_mult.value(),
            "difficulty_weight": self.difficulty.value(),
        }

    def _update_preview(self):
        cfg = self._current_cfg()
        p = self._preview_pace()
        p_new = self._preview_pace("new")
        rows, measured = _preview_lengths(
            {**cfg, "learn_my_pace": self.learn.isChecked(),
             "target_timer_wins_percent": self.target.value()})
        answers_on = self.per_answer_word.value() > 0
        new_on = self.enable_on_new.isChecked()
        cards = [(n, c) for n, c in _PREVIEW_CARDS if new_on or not c["is_new"]]
        # No grid: a quiet header and banded rows, in the theme's own colours
        # so it reads the same in light and dark mode.
        pal = self.palette()
        band = pal.color(QPalette.ColorRole.AlternateBase).name()
        rule = pal.color(QPalette.ColorRole.Mid).name()
        th = (f"style='color: gray; font-size: 11px; font-weight: 600;"
              f" border-bottom: 1px solid {rule};'")
        heads = ["Words"] + [n for n, _ in cards] + (["You"] if measured else [])
        header = "<tr>" + "".join(
            f"<th align='{'left' if i == 0 else 'right'}' {th}>{h}</th>"
            for i, h in enumerate(heads)) + "</tr>"
        body = ""
        for i, r in enumerate(rows):
            label = str(r["words"])
            if answers_on:
                label += (f" <span style='color: gray; font-size: 11px;'>"
                          f"+{r['answer_words']}</span>")
            cells = ""
            for name, card in cards:
                d = adaptive.delay_for(cfg, words=r["words"],
                                       answer_words=r["answer_words"],
                                       pace=p_new if card["is_new"] else p, **card)
                weight = "<b>{:.1f}</b>" if name == "Typical" else "{:.1f}"
                cells += f"<td align='right'>{weight.format(d)}</td>"
            if measured:
                cells += f"<td align='right'><i>{r['reveal_s']:.1f}</i></td>"
            bg = f" bgcolor='{band}'" if i % 2 else ""
            body += f"<tr{bg}><td>{label}</td>{cells}</tr>"

        share = 100 - self.target.value()
        notes = []
        if measured:
            notes.append("Rows are your most common card lengths.")
        else:
            notes.append("Rows are example card lengths.")
        if answers_on:
            notes.append("Grey +N is the answer's words.")
        notes.append("Typical = average difficulty; Easy = familiar; Hard = lapsed.")
        if measured:
            notes.append(f"<b>You</b> = when you'd revealed {share}% of those "
                         "cards yourself, at average difficulty. Compare it with "
                         "Typical: higher means the timer is quicker than you.")
        elif not self.learn.isChecked():
            notes.append("Turn on “Learn my pace” to see your own reveal times "
                         "and lengths here.")
        if not new_on:
            notes.append("New cards are off.")
        if abs(p - 1.0) >= 0.005:
            notes.append(f"Includes your learned pace ({p:.2f}×).")
        self.preview_hint.setText(" ".join(notes))
        self.preview.setText(
            "<table width='100%' cellspacing='0' cellpadding='5'>"
            f"{header}{body}</table>")

    def save(self):
        cfg = get_section(self.SECTION)
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "base_seconds": round(self.base.value(), 2),
            "seconds_per_word": round(self.per_word.value(), 2),
            "seconds_per_answer_word": round(self.per_answer_word.value(), 2),
            "max_answer_seconds": round(self.max_answer.value(), 2),
            "min_delay_seconds": round(self.min_delay.value(), 2),
            "max_delay_seconds": round(self.max_delay.value(), 2),
            "unfamiliar_multiplier": round(self.unfamiliar.value(), 2),
            "new_multiplier": round(self.new_mult.value(), 2),
            "enable_on_new": self.enable_on_new.isChecked(),
            "difficulty_weight": round(self.difficulty.value(), 2),
            "min_post_seconds": round(self.min_post.value(), 2),
            "show_countdown": self.show_countdown.isChecked(),
            "countdown_warning_colour": self.warn_colour.isChecked(),
            "warning_sound": self.warning_sound.isChecked(),
            "warning_at_percent": self.warn_pct.value(),
            "pause_key_enabled": self.pause_key_enabled.isChecked(),
            "pause_key": self.pause_key.key_value(),
            "more_time_button": self.more_time_button.isChecked(),
            "learn_my_pace": self.learn.isChecked(),
            "auto_tune_enabled": self.auto_tune.isChecked(),
            "target_timer_wins_percent": self.target.value(),
            "excluded_note_types": list(self._skip["nt"]),
            "excluded_decks": list(self._skip["decks"]),
            "fixed_time_enabled": self.fixed_enabled.isChecked(),
            "fixed_time_base_seconds": round(self.fixed_base.value(), 2),
            "fixed_time_note_types": list(self._picture["nt"]),
            "fixed_time_decks": list(self._picture["decks"]),
            "one_by_one_mode": self.obo_mode.currentData(),
            "one_by_one_seconds_per_cloze": round(self.obo_per_cloze.value(), 2),
            "one_by_one_seconds_per_word": round(self.obo_per_word.value(), 2),
            "one_by_one_max_cloze_seconds": round(self.obo_max.value(), 2),
            "one_by_one_multiplier": round(self.obo_mult.value(), 2),
        })
        save_section(self.SECTION, cfg)
        if self._pace_reset_pending == "all":
            pace.reset_pace()
        elif self._pace_reset_pending == "rebase":
            pace.rebase_pace(self._pace_refitted)

    # ----- learn my pace -----

    def _preview_pace(self, cat: str = "review") -> float:
        """The pace the next card of this kind would get once you save."""
        pending = self._pace_reset_pending
        if (not self.learn.isChecked() or not self.auto_tune.isChecked()
                or pending == "all"):
            return 1.0
        if pending == "rebase":
            if cat == "review" or cat in self._pace_refitted:
                return 1.0
            if cat in pace.FORMULA_BASED:
                return pace._clamp(pace.pace_of(cat) / pace.pace_of("review"))
        return pace.pace_of(cat)

    def _refresh_pace(self, *_):
        n = pace.count_of("review")
        learning = self.learn.isChecked()
        for w in (self.auto_tune, self.reset_pace_btn, self.details_btn):
            w.setEnabled(learning)
        if not learning:
            text = "Not learning: nothing about your reviews is recorded."
        elif self._pace_reset_pending == "all":
            text = "Pace: 1.00× (reset when you save)"
        elif self._pace_reset_pending == "rebase":
            text = "Pace: 1.00× (calibrated, applies when you save)"
        elif not self.auto_tune.isChecked():
            text = f"Auto-tune off. Learned pace {pace.pace_of():.2f}× is kept."
        elif n == 0:
            text = "Pace: 1.00× (nothing learned yet)"
        else:
            text = f"Pace: {pace.pace_of():.2f}× · learned from {n} cards"
        self.pace_label.setText(text)
        self._update_preview()

    # ----- the deck / note-type pickers -----

    @staticmethod
    def _summary(sel) -> str:
        parts = []
        for key, one, many in (("decks", "deck", "decks"),
                               ("nt", "note type", "note types")):
            n = len(sel[key])
            if n:
                parts.append(f"{n} {one if n == 1 else many}")
        return " · ".join(parts) + " — change…" if parts else "Choose…"

    def _refresh_pick_buttons(self):
        self.skip_btn.setText(self._summary(self._skip))
        self.picture_btn.setText(self._summary(self._picture))

    def _pick(self, which: str):
        sel = self._skip if which == "skip" else self._picture
        title, intro = (("No timer on these",
                         "Cards from these decks or note types are reviewed "
                         "normally, with no auto-reveal.")
                        if which == "skip" else
                        ("Picture cards",
                         "These decks or note types get the set time instead "
                         "of a word count — there's nothing to read."))
        suggest = None
        if which == "picture":
            from .engine.notetypes import picture_notetypes
            suggest = picture_notetypes(mw.col)
        dlg = _PickDialog(self, title, intro, self._names, sel, suggest)
        if dlg.exec():
            sel["nt"], sel["decks"] = dlg.chosen()
            self._refresh_pick_buttons()

    def _on_details(self):
        _PaceDetailsDialog(self).exec()

    def _on_reset_pace(self):
        self._pace_reset_pending = "all"
        self._pace_refitted = set()
        self._refresh_pace()

    # Calibratable settings beyond base / per word -> the spin box holding each.

    def _extra_boxes(self):
        return {"difficulty_weight": self.difficulty,
                "unfamiliar_multiplier": self.unfamiliar,
                "new_multiplier": self.new_mult,
                "fixed_time_base_seconds": self.fixed_base,
                "one_by_one_seconds_per_cloze": self.obo_per_cloze,
                "one_by_one_seconds_per_word": self.obo_per_word,
                "one_by_one_multiplier": self.obo_mult}

    def _on_calibrate(self):
        # The whole config as it stands in the dialog, not just the timing
        # knobs: calibration has to skip picture cards the same way the timer
        # does, and fits the other settings against what's on screen.
        cfg = {**get_section(self.SECTION), **self._current_cfg(),
               "target_timer_wins_percent": self.target.value(),
               "learn_my_pace": self.learn.isChecked(),
               "enable_on_new": self.enable_on_new.isChecked(),
               "fixed_time_enabled": self.fixed_enabled.isChecked(),
               "one_by_one_mode": self.obo_mode.currentData(),
               **{k: box.value() for k, box in self._extra_boxes().items()}}
        dlg = _CalibrateDialog(self, cfg)
        if dlg.exec() and dlg.result_values:
            r = dlg.result_values
            self.base.setValue(r["base_seconds"])
            self.per_word.setValue(r["seconds_per_word"])
            if self.per_answer_word.value() > 0:
                self.per_answer_word.setValue(r["seconds_per_answer_word"])
            boxes = self._extra_boxes()
            for key, value in dlg.extras_chosen.items():
                boxes[key].setValue(value)
                if key in pace.SETTING_KIND:
                    self._pace_refitted.add(pace.SETTING_KIND[key])
            # The new values already reflect your pace, so the multiplier
            # starts again from 1 rather than being applied twice.
            if self._pace_reset_pending != "all":
                self._pace_reset_pending = "rebase"
            self._refresh_pace()


def _fit_to_content(dlg: QDialog) -> None:
    """Size a dialog to everything it holds. Qt's adjustSize() stops at two
    thirds of the screen, which on a laptop clips these; cap at the screen's
    usable area instead."""
    want = dlg.sizeHint()
    screen = dlg.screen() or (mw.screen() if mw else None)
    if screen is not None:
        want = want.boundedTo(screen.availableGeometry().size() * 0.9)
    dlg.resize(want)


def _grid(headers, rows) -> QWidget:
    """A small table as a grid of labels. (A rich-text <table> in a QLabel
    gets its height measured wrong inside a dialog and loses rows.) First
    column left-aligned, the rest right; a cell may be (text, "note") to show
    it grey and left-aligned."""
    box = QWidget()
    grid = QGridLayout(box)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(6)
    right, left = Qt.AlignmentFlag.AlignRight, Qt.AlignmentFlag.AlignLeft
    for c, h in enumerate(headers):
        lbl = QLabel(f"<b>{h}</b>")
        lbl.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(lbl, 0, c, left if c == 0 else right)
    for r, row in enumerate(rows, start=1):
        for c, cell in enumerate(row):
            note = isinstance(cell, tuple)
            text = cell[0] if note else cell
            lbl = QLabel(text)
            if note:
                lbl.setStyleSheet("color: gray;")
            grid.addWidget(lbl, r, c, left if (c == 0 or note) else right)
    grid.setColumnStretch(len(headers), 1)
    return box


def _session_rows() -> list:
    rows = list(pace.summary().get("sessions", []))[-8:]
    live = pace.session_so_far()
    if live and live["cards"]:
        t = sorted(live["reveal_s"])
        rows.append({"date": "now", "cards": live["cards"], "self": live["self"],
                     "median_s": t[len(t) // 2] if t else None, "pace": None})
    out = []
    for r in reversed(rows):
        out.append([
            str(r["date"]), str(r["cards"]),
            f"{round(100 * r['self'] / r['cards'])}%" if r["cards"] else "–",
            f"{r['median_s']:.1f} s" if r.get("median_s") else "–",
            f"{r['pace']:.2f}×" if r.get("pace") else "–"])
    return out


class _PickDialog(QDialog):
    """Choose decks and note types, in a pop-up so the tab stays short."""

    def __init__(self, parent, title, intro, names, sel, suggest=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Wide enough for long shared-deck note-type names without a
        # sideways scroll bar.
        self.setMinimumSize(820, 420)
        notetypes, decks = names
        layout = QVBoxLayout(self)
        layout.addWidget(_hint(intro))
        lists = QHBoxLayout()
        self.decks = _FilterList("Decks (a parent also covers its subdecks)",
                                 decks, sel["decks"])
        self.nts = _FilterList("Note types", notetypes, sel["nt"])
        for fl in (self.decks, self.nts):
            fl.list.setMaximumHeight(16777215)    # use the pop-up's height
            lists.addWidget(fl, 1)
        layout.addLayout(lists, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        if suggest:
            # Ticks the likely picture types; never unticks anything.
            add = buttons.addButton(f"Tick picture types ({len(suggest)})",
                                    QDialogButtonBox.ButtonRole.ResetRole)
            add.setToolTip("Image occlusion and similar: " + ", ".join(suggest))
            add.clicked.connect(lambda: self.nts.tick(suggest))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen(self):
        return self.nts.checked(), self.decks.checked()


class _PaceDetailsDialog(QDialog):
    """Read-only: each kind's pace, recent sessions, and how it all works.
    Kept off the tab so the tab stays simple."""

    _KINDS = (("review", "Review"), ("learning", "Learning / relearning"),
              ("new", "New"), ("picture", "Picture"),
              ("one_by_one", "One-by-one (clozes)"),
              ("one_by_one_whole", "One-by-one (whole card)"))

    def __init__(self, panel):
        super().__init__(panel)
        self.setWindowTitle("Your pace — details")
        self.setMinimumWidth(500)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 12)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 14, 18, 6)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(page)
        outer.addWidget(area, 1)

        layout.addWidget(_section("Each kind of card",
                                  "Paces as they'll be after you save."))
        tallied = pace.tally_counts()
        kinds = []
        for cat, name in self._KINDS:
            if cat == "one_by_one_whole" and not tallied.get(cat):
                continue      # only when a template skips the per-cloze timers
            note = ""
            if cat in pace.TUNED:
                pc = f"{panel._preview_pace(cat):.2f}×"
                if cat != "review" and not pace.count_of(cat):
                    note = "follows review"
            else:
                pc, note = "–", "uses the one-by-one pace"
            kinds.append([name, pc, str(int(tallied.get(cat, 0))), (note, "note")])
        layout.addWidget(_grid(["Kind", "Pace", "Cards measured", ""], kinds))

        layout.addWidget(_section("Recent sessions"))
        sessions = _session_rows()
        if sessions:
            layout.addWidget(_grid(["Session", "Cards", "You revealed", "Median",
                                    "Pace"], sessions))
        else:
            layout.addWidget(_hint("No sessions yet."))

        layout.addWidget(_section("How it works"))
        layout.addWidget(_hint(
            "Auto-tune: each card you reveal first shortens that kind's timer "
            "about 0.5%; each timeout or More time lengthens it about 5%. It "
            "settles where the timer beats you on your target share of cards, "
            "and never goes more than 15% quicker than your settings. Review, "
            "learning, new, picture and one-by-one cards each keep their own "
            "pace (one-by-one is nudged per cloze), so one kind can't drag "
            "another; a kind with nothing learned yet follows your review pace."))
        layout.addWidget(_hint(
            "Calibrate: fits base and per word to the time you'd revealed your "
            "target share of review cards by, at each length. Once there's "
            "enough data it also suggests the learning and new multipliers, "
            "the difficulty weight, the picture time and the one-by-one "
            "timings, each from that kind's own cards. Applying resets the "
            "paces those settings now carry. It can also work from Anki's own "
            "review history, so it's useful from day one: those times run "
            "until you graded, so the time you spend on the answer comes off "
            "each (measured from your reveals once there are enough)."))
        layout.addWidget(_hint(
            "What's kept: counts and timings by card length and difficulty, "
            "and how long the answer is up before you grade, never which "
            "cards, in one file per profile on this computer. "
            "Nothing is sent anywhere."))

        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.setContentsMargins(18, 0, 18, 0)
        outer.addWidget(buttons)
        # A scroll area reports a small size hint; size to the page instead.
        hint = page.sizeHint()
        self.setMinimumHeight(0)
        self.resize(max(500, hint.width() + 24), hint.height() + 70)
        screen = self.screen() or (mw.screen() if mw else None)
        if screen is not None:
            self.resize(self.size().boundedTo(screen.availableGeometry().size() * 0.9))


class _CalibrateDialog(QDialog):
    """Works out suggested timings, shows them next to the current ones, and
    hands them back only if you press Apply. Nothing is saved from here — the
    settings dialog's own Save does that."""

    def __init__(self, parent, cfg, saves_directly=False):
        super().__init__(parent)
        self.setWindowTitle("Calibrate from my reviews")
        self.saves_directly = saves_directly
        self.setMinimumWidth(460)
        self.cfg = cfg
        self.result_values = None
        self.extras_chosen = {}
        self._extra_checks = {}
        layout = QVBoxLayout(self)
        # Rich-text tables in a word-wrapped QLabel get measured short as the
        # content grows; never let the dialog shrink below what it holds.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.body = QLabel("Working…")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.body)
        # The other settings: one tickable row each, filled in by _fill.
        self.extras_box = QWidget()
        self.extras_grid = QGridLayout(self.extras_box)
        self.extras_grid.setContentsMargins(0, 0, 0, 6)
        self.extras_grid.setHorizontalSpacing(14)
        self.extras_box.hide()
        layout.addWidget(self.extras_box)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_btn = self.buttons.addButton(
            "Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_btn.setEnabled(False)
        self.buttons.accepted.connect(self._on_apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        # Where the numbers come from: the reveals AnkiBlitz has watched (exact,
        # once there are enough), or Anki's review history (works from day one).
        ready = pace.reveal_data_ready(cfg)
        self._run_id = 0
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("From:"))
        self.src_reveals = QRadioButton(self._reveals_label(ready))
        self.src_history = QRadioButton("Anki's review history")
        self.src_reveals.setEnabled(ready)
        src_row.addWidget(self.src_reveals)
        src_row.addWidget(self.src_history)
        src_row.addStretch(1)
        layout.insertLayout(0, src_row)
        (self.src_reveals if ready else self.src_history).setChecked(True)
        self.src_reveals.toggled.connect(lambda on: on and self._run(True))
        self.src_history.toggled.connect(lambda on: on and self._run(False))
        self._run(ready)

    def _reveals_label(self, ready: bool) -> str:
        if ready:
            n = int(pace.summary().get("self_n", 0.0))
            return f"What AnkiBlitz has seen ({n} cards)"
        if pace.learning(self.cfg):
            n = int(pace.summary().get("self_n", 0.0))
            return f"What AnkiBlitz has seen (needs {pace.MIN_CALIBRATION}, {n} so far)"
        return "What AnkiBlitz has seen (turn on Learn my pace)"

    def _run(self, measured: bool):
        """Work out suggestions from the chosen source. A history read runs in
        the background; if you switch source meanwhile, its result is dropped."""
        self._run_id += 1
        run = self._run_id
        self.result_values = None
        self.apply_btn.setEnabled(False)
        cancel = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel:
            cancel.setText("Cancel")
        self._clear_extras()
        self.body.setText("Working…")
        if measured:
            self._show(pace.fit_from_reveals(self.cfg), True, run=run)
            return
        if mw.col is None:
            self._show(None, False, run=run)
            return
        from aqt.operations import QueryOp
        cfg = self.cfg

        def progress(n):
            mw.taskman.run_on_main(lambda: mw.progress.update(
                label=f"Reading your review history… {n} cards"))

        QueryOp(
            parent=self,
            op=lambda col: pace.fit_from_history(col, cfg, progress),
            success=lambda r: self._show(r, False, run=run),
        ).failure(
            lambda _exc: self._show(None, False, failed=True, run=run)
        ).with_progress("Reading your review history…").run_in_background()

    def _show(self, r, measured: bool, failed: bool = False, run=None):
        if run is not None and run != self._run_id:
            return      # you switched source while this one was working
        try:
            self._fill(r, measured, failed)
        except RuntimeError:
            pass    # the dialog was closed before the history read finished

    def _clear_extras(self):
        self._extra_checks = {}
        while self.extras_grid.count():
            w = self.extras_grid.takeAt(0).widget()
            if w:
                w.hide()            # gone now, not when Qt gets round to it
                w.setParent(None)
                w.deleteLater()
        self.extras_box.hide()

    def _fill(self, r, measured: bool, failed: bool):
        target = int(self.cfg["target_timer_wins_percent"])
        if not r:
            cancel = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel:
                cancel.setText("Close")
            if failed:
                self.body.setText(
                    "<b>Couldn't read your review history.</b><br><br>Nothing "
                    "was changed. Try again in a moment.")
                return
            self.body.setText(
                "<b>Not enough data yet.</b><br><br>Calibration needs about "
                f"{pace.MIN_CALIBRATION} cards you revealed yourself, or a few "
                f"hundred reviews in Anki's history (the last "
                f"{pace.HISTORY_DAYS} days). Keep reviewing and try again.")
            return
        rows = [("Base time", "base_seconds", "s"),
                ("Per word", "seconds_per_word", "s")]
        if float(self.cfg["seconds_per_answer_word"]) > 0:
            rows.append(("Per answer word", "seconds_per_answer_word", "s"))
        table = "".join(
            f"<tr><td>{label}</td><td align='right'>{float(self.cfg[key]):.2f} {u}</td>"
            f"<td align='right'><b>{r[key]:.2f} {u}</b></td></tr>"
            for label, key, u in rows)
        if measured:
            source = (f"From <b>{r['cards']}</b> cards AnkiBlitz watched you answer. "
                      "Timed so the answer shows before you've revealed it on "
                      f"about {target}% of cards.")
        else:
            hist = r["source"]
            allowance = (f"{hist['gap']:.1f} s, measured from your own reveals,"
                         if hist["gap_measured"] else
                         "a typical allowance (about 1.5 s plus 0.1 s per answer "
                         "word)")
            source = (f"From <b>{hist['reviews']}</b> reviews of "
                      f"{hist['cards']} cards in Anki's history (the last "
                      f"{hist['days']} days). Anki times each review until you "
                      f"grade it, so {allowance} is taken off each for reading "
                      "the answer. Timed so the answer shows before you'd have "
                      f"revealed it on about {target}% of cards. If you've been "
                      "reviewing with an auto-reveal timer on, those times "
                      "partly reflect that timer.")
        reset = (" and resets the learned pace to 1.00×"
                 if pace.learning(self.cfg) else "")
        if self.saves_directly:
            outro = (f"Apply saves these{reset}. "
                     "You can change them any time in Settings.")
        else:
            outro = (f"Apply fills these, and any you tick below, into "
                     f"Settings{reset}. Nothing changes until you save.")
        self.body.setText(
            source + "<br><br><table cellspacing='0' cellpadding='4'>"
            "<tr><th></th><th>Now</th><th>Suggested</th></tr>" + table +
            "</table><br>" + self._seconds_table(r) + outro)
        self.result_values = r
        self.apply_btn.setEnabled(True)
        _fit_to_content(self)
        self._fill_extras(pace.fit_kinds(self.cfg, r, None if measured else r["source"]))

    _FORMATS = {"difficulty_weight": "{:.2f}", "unfamiliar_multiplier": "{:.2f}×",
                "new_multiplier": "{:.2f}×", "fixed_time_base_seconds": "{:.1f} s",
                "one_by_one_seconds_per_cloze": "{:.1f} s",
                "one_by_one_seconds_per_word": "{:.2f} s",
                "one_by_one_multiplier": "{:.2f}×"}

    def _fill_extras(self, extras: dict):
        """One row per other setting: tick it to apply, or why it can't be
        suggested yet. Each comes from that kind's own cards."""
        if not extras:
            return
        grid = self.extras_grid
        head = QLabel("<b>Other settings</b> <span style='color: gray;'>— from "
                      "each kind's own cards; tick the ones to apply</span>")
        head.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(head, 0, 0, 1, 3)
        for col, text in ((1, "Now"), (2, "Suggested")):
            lbl = QLabel(f"<span style='color: gray;'>{text}</span>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            grid.addWidget(lbl, 1, col, Qt.AlignmentFlag.AlignRight)
        row = 2
        for key, info in extras.items():
            fmt = self._FORMATS.get(key, "{}")
            now = fmt.format(float(self.cfg.get(key, 0.0)))
            if info["value"] is not None:
                box = QCheckBox(info["label"])
                box.setChecked(True)
                self._extra_checks[key] = (box, info["value"])
                grid.addWidget(box, row, 0)
                grid.addWidget(QLabel(now), row, 1, Qt.AlignmentFlag.AlignRight)
                sug = QLabel(f"<b>{fmt.format(info['value'])}</b>")
                sug.setTextFormat(Qt.TextFormat.RichText)
                grid.addWidget(sug, row, 2, Qt.AlignmentFlag.AlignRight)
            else:
                why = info.get("reason") or (
                    f"needs {info['need']} {info['unit']} ({info['cards']} so far)")
                name = QLabel(f"<span style='color: gray;'>{info['label']}</span>")
                name.setTextFormat(Qt.TextFormat.RichText)
                grid.addWidget(name, row, 0)
                grid.addWidget(QLabel(now), row, 1, Qt.AlignmentFlag.AlignRight)
                why_lbl = QLabel(why)
                why_lbl.setStyleSheet("color: gray; font-size: 11px;")
                grid.addWidget(why_lbl, row, 2, Qt.AlignmentFlag.AlignRight)
            row += 1
        self.extras_box.show()
        _fit_to_content(self)

    def _on_apply(self):
        self.extras_chosen = {key: value for key, (box, value)
                              in self._extra_checks.items() if box.isChecked()}
        self.accept()


    def _seconds_table(self, r) -> str:
        """The settings rows above can mislead: "Now" leaves out the learned
        pace, and a reshape (base up, per word down) reads as "longer" when it
        is quicker on most cards. So also show real seconds, per length."""
        after_cfg = {**self.cfg, "base_seconds": r["base_seconds"],
                     "seconds_per_word": r["seconds_per_word"]}
        if float(self.cfg["seconds_per_answer_word"]) > 0:
            after_cfg["seconds_per_answer_word"] = r["seconds_per_answer_word"]
        now_pace = pace.current(self.cfg)
        rows, measured = _preview_lengths(self.cfg)
        body = ""
        for row in rows:
            kw = dict(words=row["words"], answer_words=row["answer_words"], **_TYPICAL)
            now = adaptive.delay_for(self.cfg, pace=now_pace, **kw)
            after = adaptive.delay_for(after_cfg, pace=1.0, **kw)
            you = (f"<td align='right'><i>{row['reveal_s']:.1f}</i></td>"
                   if measured else "")
            body += (f"<tr><td>{row['words']} words</td>"
                     f"<td align='right'>{now:.1f} s</td>"
                     f"<td align='right'><b>{after:.1f} s</b></td>{you}</tr>")
        you_head = "<th>You</th>" if measured else ""
        return ("<b>In seconds</b>, for a card of average difficulty"
                + (f" (your pace {now_pace:.2f}× included in Now)"
                   if abs(now_pace - 1.0) >= 0.005 else "") + ":"
                "<table cellspacing='0' cellpadding='4'>"
                f"<tr><th></th><th>Now</th><th>After</th>{you_head}</tr>"
                + body + "</table><br>")


# --------------------------------------------------------------------------- #
#  Word Reveal panel  (full Progressive Word Reveal option set)
# --------------------------------------------------------------------------- #

class WordRevealPanel(QWidget):
    SECTION = "word_reveal"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)

        layout = QVBoxLayout(self)

        self.enabled = QCheckBox("Enable progressive word reveal")
        self.enabled.setChecked(bool(cfg.get("enabled", True)))
        layout.addWidget(self.enabled)

        self.reveal_on_answer = QCheckBox("Also reveal on the answer side")
        self.reveal_on_answer.setChecked(bool(cfg.get("reveal_on_answer", False)))
        layout.addWidget(self.reveal_on_answer)
        layout.addWidget(_hint(
            "Fades the question in at a fixed reading rate, so longer questions "
            "take proportionally longer. Click or press the reveal key to show "
            "everything at once. (Left unticked, the answer side shows at once.)"))

        form = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem("One word at a time", "words")
        self.mode.addItem("In chunks of N words", "chunks")
        midx = self.mode.findData(cfg.get("reveal_mode", "words"))
        if midx >= 0:
            self.mode.setCurrentIndex(midx)
        form.addRow("Reveal mode:", self.mode)

        self.chunk_words = QSpinBox()
        self.chunk_words.setRange(1, 20)
        self.chunk_words.setValue(int(cfg.get("chunk_words", 3)))
        self.chunk_words.setSuffix(" words")
        form.addRow("Chunk size:", self.chunk_words)

        self.wps = _double(1.0, 30.0, 0.5, 1, " w/s")
        self.wps.setValue(float(cfg.get("words_per_second", 6.0)))
        form.addRow("Reading speed:", self.wps)

        self.reveal_key = _KeyCaptureEdit(cfg.get("reveal_key", "p"))
        form.addRow("Reveal-all key:", self.reveal_key)

        self.stop_audio = QCheckBox("Stop the card's audio when you reveal early")
        self.stop_audio.setChecked(bool(cfg.get("stop_audio_on_reveal", True)))

        # Chunk size only matters in chunk mode.
        def _toggle_chunk():
            self.chunk_words.setEnabled(self.mode.currentData() == "chunks")
        self.mode.currentIndexChanged.connect(_toggle_chunk)
        _toggle_chunk()

        # Reading-speed knob on the left, live reveal-time table on the right.
        speed_row = QHBoxLayout()
        speed_row.addLayout(form, 1)
        card, side = _preview_card("Preview", "Time to fully reveal the question")
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.preview)
        side.addStretch(1)
        speed_row.addWidget(card, 1)
        layout.addLayout(speed_row)

        layout.addWidget(self.stop_audio)
        layout.addWidget(_hint(
            "Revealing everything (key or click) also cuts the card's TTS / "
            "[sound:] playback — you've read it, so the voice reading it to you "
            "is just noise. The audio stops rather than pausing; the next card "
            "plays normally."))

        self.wps.valueChanged.connect(self._update_preview)
        self._update_preview()

        # --- TTS sync ---
        self._base_wpm = int(cfg.get("tts_base_wpm", tts_sync.DEFAULT_BASE_WPM)) or tts_sync.DEFAULT_BASE_WPM
        layout.addWidget(self._build_tts_group(cfg))

        layout.addWidget(_hline())
        layout.addWidget(QLabel("Tick anything that should skip the reveal (show instantly):"))

        notetypes, decks = _collect_names()
        self.nt_list = _FilterList("Note types", notetypes, cfg.get("excluded_note_types", []))
        self.deck_list = _FilterList(
            "Decks (a parent also covers its subdecks)", decks, cfg.get("excluded_decks", []))
        lists_row = QHBoxLayout()
        lists_row.addWidget(self.nt_list)
        lists_row.addWidget(self.deck_list)
        layout.addLayout(lists_row)

    def _build_tts_group(self, cfg):
        box = QGroupBox("TTS sync")
        v = QVBoxLayout(box)
        v.addWidget(_hint(
            "Keep the word reveal in step with native Anki / AnKing {{tts}} "
            "playback. On macOS the voice runs at 170 × speed words/min, so "
            "the matching reveal rate is exact — no guessing."))

        self.tts_readout = QLabel()
        self.tts_readout.setTextFormat(Qt.TextFormat.RichText)
        self.tts_readout.setWordWrap(True)
        v.addWidget(self.tts_readout)
        self.wps.valueChanged.connect(self._update_tts_readout)
        self._update_tts_readout()

        # What's actually in the collection.
        found = tts_sync.scan_collection_tts()
        if found:
            parts = []
            for name, speed, active in found:
                wps = tts_sync.wps_for_speed(speed, self._base_wpm)
                tag = "" if active else " <i>(disabled)</i>"
                parts.append(f"&bull; {name}: speed {speed:g} → {wps:.1f} w/s{tag}")
            detected = QLabel(
                "<b>Detected in your collection:</b><br>" + "<br>".join(parts))
            detected.setTextFormat(Qt.TextFormat.RichText)
            detected.setWordWrap(True)
            v.addWidget(detected)

        self.tts_auto_match = QCheckBox(
            "Auto-match reveal speed to each card's TTS")
        self.tts_auto_match.setChecked(bool(cfg.get("tts_auto_match", True)))
        v.addWidget(self.tts_auto_match)
        v.addWidget(_hint(
            "When on, any card with active TTS overrides the reading speed above "
            "so the words finish in step with the voice. Cards without TTS (e.g. "
            "AnKing's commented-out default) use your reading speed unchanged."))
        return box

    def _update_tts_readout(self):
        wps = self.wps.value() or 6.0
        speed = tts_sync.ideal_speed(wps, self._base_wpm)
        self.tts_readout.setText(
            f"At <b>{wps:g} w/s</b>, set your AnKing TTS "
            f"<code>speed=</code> to about <b>{speed:.2f}</b> to stay in sync.")

    def _update_preview(self):
        wps = self.wps.value() or 6.0
        band, th = _table_style(self)
        rows = ""
        for i, words in enumerate(_PREVIEW_WORDS):
            bg = f" bgcolor='{band}'" if i % 2 else ""
            rows += (
                f"<tr{bg}><td>{words} words</td>"
                f"<td align='right'><b>{words / wps:.1f}</b> s</td></tr>"
            )
        self.preview.setText(
            "<table width='100%' cellspacing='0' cellpadding='6'>"
            f"<tr><th align='left' {th}>Words</th>"
            f"<th align='right' {th}>Reveal time</th></tr>"
            f"{rows}</table>"
        )

    def save(self):
        cfg = get_section(self.SECTION)
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "reveal_on_answer": self.reveal_on_answer.isChecked(),
            "reveal_mode": self.mode.currentData(),
            "chunk_words": self.chunk_words.value(),
            "words_per_second": round(self.wps.value(), 2),
            "reveal_key": self.reveal_key.key_value(),
            "stop_audio_on_reveal": self.stop_audio.isChecked(),
            "tts_auto_match": self.tts_auto_match.isChecked(),
            "excluded_note_types": self.nt_list.checked(),
            "excluded_decks": self.deck_list.checked(),
        })
        save_section(self.SECTION, cfg)


# --------------------------------------------------------------------------- #
#  Quick Start + Momentum panel
# --------------------------------------------------------------------------- #

class QuickStartPanel(QWidget):
    """Daily Quick Start, Momentum protection, and the on-screen widgets.

    Saves the ``quick_start``, ``momentum`` and ``home_widget`` config sections.
    """

    SECTION = "quick_start"
    SECTION_MOMENTUM = "momentum"
    SECTION_WIDGET = "home_widget"

    def __init__(self):
        super().__init__()
        qs = get_section(self.SECTION)
        mo = get_section(self.SECTION_MOMENTUM)
        wi = get_section(self.SECTION_WIDGET)

        layout = QVBoxLayout(self)

        # --- Daily Quick Start ---
        qbox = QGroupBox("Daily Quick Start")
        ql = QVBoxLayout(qbox)

        self.enabled = QCheckBox("Auto-launch a Blitz on the first open of the day")
        self.enabled.setChecked(bool(qs.get("enabled", False)))
        ql.addWidget(self.enabled)
        ql.addWidget(_hint(
            "On the first time you open Anki each day with cards due, AnkiBlitz "
            "starts a Blitz for you, using the preset below."))

        qf = QFormLayout()

        self.launch_style = QComboBox()
        self.launch_style.addItem("Show 3-2-1 countdown (cancelable)", "countdown")
        self.launch_style.addItem("Jump straight in (no prompt)", "immediate")
        sidx = self.launch_style.findData(qs.get("launch_style", "countdown"))
        if sidx >= 0:
            self.launch_style.setCurrentIndex(sidx)
        qf.addRow("Launch style:", self.launch_style)

        self.countdown = QSpinBox()
        self.countdown.setRange(1, 10)
        self.countdown.setSuffix(" s")
        self.countdown.setValue(int(qs.get("countdown_seconds", 3)))
        qf.addRow("Countdown length:", self.countdown)

        self.mode = QComboBox()
        self.mode.addItem("Card count", "cards")
        self.mode.addItem("Time", "time")
        self.mode.addItem("Fraction of due", "fraction")
        midx = self.mode.findData(qs.get("mode", "cards"))
        if midx >= 0:
            self.mode.setCurrentIndex(midx)
        qf.addRow("Preset mode:", self.mode)

        self.target = QSpinBox()
        qf.addRow("Preset amount:", self.target)

        self.min_due = QSpinBox()
        self.min_due.setRange(1, 9999)
        self.min_due.setSuffix(" cards")
        self.min_due.setValue(int(qs.get("min_due", 1)))
        qf.addRow("Only if at least:", self.min_due)

        self.relaunch_hour = QSpinBox()
        self.relaunch_hour.setRange(0, 23)
        self.relaunch_hour.setSuffix(":00")
        self.relaunch_hour.setValue(int(qs.get("relaunch_after_hour", 5)))
        qf.addRow("Overnight relaunch after:", self.relaunch_hour)

        ql.addLayout(qf)

        self.relaunch = QCheckBox(
            "Left open overnight? Relaunch (paused) when I next return to Anki")
        self.relaunch.setChecked(bool(qs.get("relaunch_on_new_day", True)))
        ql.addWidget(self.relaunch)
        ql.addWidget(_hint(
            "If Anki was left running across midnight, the daily Blitz starts the "
            "first time you bring Anki to the front on/after the hour above. It "
            "opens paused on the first card until your first key or click."))
        self.relaunch.toggled.connect(self.relaunch_hour.setEnabled)
        self.relaunch_hour.setEnabled(self.relaunch.isChecked())

        layout.addWidget(qbox)

        # Countdown length only matters for the countdown style.
        def _toggle_countdown():
            self.countdown.setEnabled(self.launch_style.currentData() == "countdown")
        self.launch_style.currentIndexChanged.connect(_toggle_countdown)
        _toggle_countdown()

        # The preset amount's units/range follow the chosen mode.
        self.mode.currentIndexChanged.connect(self._sync_target)
        self._sync_target()
        self.target.setValue(int(qs.get("target", 50)))  # clamp into the synced range

        # --- Momentum protection ---
        mbox = QGroupBox("Momentum protection")
        ml = QVBoxLayout(mbox)
        self.mo_enabled = QCheckBox("Ask before quitting near the end of a Blitz")
        self.mo_enabled.setChecked(bool(mo.get("enabled", True)))
        ml.addWidget(self.mo_enabled)
        ml.addWidget(_hint(
            "If you leave the reviewer when you're close to finishing, AnkiBlitz "
            "shows a time estimate and asks whether to keep going. Leaving when "
            "you're not near the end still cancels with no record."))

        mf = QFormLayout()
        self.near_cards = QSpinBox()
        self.near_cards.setRange(1, 999)
        self.near_cards.setSuffix(" cards")
        self.near_cards.setValue(int(mo.get("near_end_cards", 10)))
        mf.addRow("Near end (card/fraction):", self.near_cards)

        self.near_secs = QSpinBox()
        self.near_secs.setRange(5, 3600)
        self.near_secs.setSuffix(" s")
        self.near_secs.setValue(int(mo.get("near_end_seconds", 120)))
        mf.addRow("Near end (time):", self.near_secs)
        ml.addLayout(mf)
        layout.addWidget(mbox)

        # --- On-screen widgets ---
        wbox = QGroupBox("On-screen widgets")
        wl = QVBoxLayout(wbox)
        self.widget_home = QCheckBox("Show the AnkiBlitz panel on the deck list (home)")
        self.widget_home.setChecked(bool(wi.get("enabled", True)))
        self.widget_overview = QCheckBox("Show a 'Blitz this deck' panel on a deck's overview")
        self.widget_overview.setChecked(bool(wi.get("show_on_overview", True)))
        wl.addWidget(self.widget_home)
        wl.addWidget(self.widget_overview)
        wl.addWidget(_hint(
            "A rail beside the deck list with one-click Blitz / Pomodoro launch, "
            "right where you already are."))
        wl.addWidget(QLabel("Quick-launch Blitz buttons on the rail:"))
        self.presets = _BlitzPresetEditor(wi.get("presets", []))
        wl.addWidget(self.presets)
        wl.addWidget(_hint(
            "Each button starts that Blitz immediately. Mix modes however you "
            "like — e.g. all card counts, or all timers."))
        layout.addWidget(wbox)

        layout.addStretch(1)

    def _sync_target(self):
        mode = self.mode.currentData()
        keep = self.target.value()
        if mode == "time":
            self.target.setPrefix("")
            self.target.setSuffix(" min")
            self.target.setRange(1, 600)
        elif mode == "fraction":
            self.target.setSuffix("")
            self.target.setPrefix("1 / ")
            self.target.setRange(2, 50)
        else:
            self.target.setPrefix("")
            self.target.setSuffix(" cards")
            self.target.setRange(1, 9999)
        self.target.setValue(keep)  # re-clamped into the new range

    def save(self):
        qs = get_section(self.SECTION)
        qs.update({
            "enabled": self.enabled.isChecked(),
            "launch_style": self.launch_style.currentData(),
            "countdown_seconds": self.countdown.value(),
            "mode": self.mode.currentData(),
            "target": self.target.value(),
            "min_due": self.min_due.value(),
            "relaunch_on_new_day": self.relaunch.isChecked(),
            "relaunch_after_hour": self.relaunch_hour.value(),
        })
        save_section(self.SECTION, qs)

        mo = get_section(self.SECTION_MOMENTUM)
        mo.update({
            "enabled": self.mo_enabled.isChecked(),
            "near_end_cards": self.near_cards.value(),
            "near_end_seconds": self.near_secs.value(),
        })
        save_section(self.SECTION_MOMENTUM, mo)

        wi = get_section(self.SECTION_WIDGET)
        wi.update({
            "enabled": self.widget_home.isChecked(),
            "show_on_overview": self.widget_overview.isChecked(),
            "presets": self.presets.values(),
        })
        save_section(self.SECTION_WIDGET, wi)


# --------------------------------------------------------------------------- #
#  Widget quick-launch preset editor
# --------------------------------------------------------------------------- #

class _BlitzPresetEditor(QWidget):
    """An editable list of rail quick-launch presets — each a mode + amount, so
    the user can have e.g. all card counts or all timers."""

    _MODES = [("Timer", "time"), ("Card count", "cards"), ("Fraction of due", "fraction")]

    def __init__(self, presets):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._rows_box = QVBoxLayout()
        outer.addLayout(self._rows_box)
        add = QPushButton("+ Add button")
        add.clicked.connect(lambda: self._add_row("cards", 50))
        outer.addWidget(add)

        self._rows = []
        seed = presets or [
            {"mode": "time", "value": 25},
            {"mode": "cards", "value": 50},
            {"mode": "fraction", "value": 2},
        ]
        for p in seed:
            self._add_row(p.get("mode", "cards"), int(p.get("value", 50) or 50))

    def _add_row(self, mode, value):
        row = QHBoxLayout()
        combo = QComboBox()
        for label, key in self._MODES:
            combo.addItem(label, key)
        idx = combo.findData(mode)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        spin = QSpinBox()
        remove = QPushButton("✕")
        remove.setMaximumWidth(34)

        def _sync():
            keep = spin.value()
            m = combo.currentData()
            if m == "time":
                spin.setPrefix(""); spin.setSuffix(" min"); spin.setRange(1, 600)
            elif m == "fraction":
                spin.setSuffix(""); spin.setPrefix("1 / "); spin.setRange(2, 50)
            else:
                spin.setPrefix(""); spin.setSuffix(" cards"); spin.setRange(1, 9999)
            spin.setValue(keep)
        combo.currentIndexChanged.connect(_sync)
        _sync()
        spin.setValue(value)

        entry = {"combo": combo, "spin": spin, "layout": row}
        remove.clicked.connect(lambda: self._remove_row(entry))

        row.addWidget(combo, 1)
        row.addWidget(spin, 1)
        row.addWidget(remove)
        self._rows_box.addLayout(row)
        self._rows.append(entry)

    def _remove_row(self, entry):
        if entry not in self._rows:
            return
        self._rows.remove(entry)
        lay = entry["layout"]
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._rows_box.removeItem(lay)

    def values(self):
        return [{"mode": e["combo"].currentData(), "value": e["spin"].value()}
                for e in self._rows]


# --------------------------------------------------------------------------- #
#  Pomodoro + on-screen widgets panel
# --------------------------------------------------------------------------- #

class PomodoroPanel(QWidget):
    """Pomodoro cycle settings (the on-screen widget settings live on the Quick
    Start tab). Saves the ``pomodoro`` section."""

    SECTION = "pomodoro"

    _LEVELS = [
        (0, "Notify me only"),
        (1, "Prompt me to start"),
        (2, "Auto-start next Blitz (if Anki focused)"),
        (3, "Raise Anki + auto-start"),
    ]

    def __init__(self):
        super().__init__()
        po = get_section(self.SECTION)

        layout = QVBoxLayout(self)

        # --- Pomodoro ---
        pbox = QGroupBox("Pomodoro cycle")
        pl = QVBoxLayout(pbox)

        self.enabled = QCheckBox("Enable Pomodoro (work blocks paired with breaks)")
        self.enabled.setChecked(bool(po.get("enabled", True)))
        pl.addWidget(self.enabled)
        pl.addWidget(_hint(
            "A work block is a Blitz; when it finishes you get a break screen "
            "with a countdown, then the next block. Start one from the AnkiBlitz "
            "menu (Ctrl+Shift+P) or the on-screen widget."))

        pf = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem("Time", "time")
        self.mode.addItem("Card count", "cards")
        self.mode.addItem("Fraction of due", "fraction")
        midx = self.mode.findData(po.get("work_mode", "time"))
        if midx >= 0:
            self.mode.setCurrentIndex(midx)
        pf.addRow("Work block mode:", self.mode)

        self.work_target = QSpinBox()
        pf.addRow("Work block amount:", self.work_target)

        self.break_min = QSpinBox()
        self.break_min.setRange(1, 120)
        self.break_min.setSuffix(" min")
        self.break_min.setValue(int(po.get("break_minutes", 5)))
        pf.addRow("Break length:", self.break_min)

        self.cycles = QSpinBox()
        self.cycles.setRange(0, 99)
        self.cycles.setSpecialValueText("Unlimited")
        self.cycles.setSuffix(" blocks")
        self.cycles.setValue(int(po.get("cycles", 0)))
        pf.addRow("Stop after:", self.cycles)

        self.level = QComboBox()
        for value, label in self._LEVELS:
            self.level.addItem(label, value)
        lidx = self.level.findData(int(po.get("auto_return_level", 2)))
        if lidx >= 0:
            self.level.setCurrentIndex(lidx)
        pf.addRow("When a break ends:", self.level)

        pl.addLayout(pf)

        # Work amount units follow the mode.
        self.mode.currentIndexChanged.connect(self._sync_target)
        self._sync_target()
        self.work_target.setValue(int(po.get("work_target", 25)))

        # Long break sub-group.
        self.long_enabled = QCheckBox("Take a longer break every few blocks")
        self.long_enabled.setChecked(bool(po.get("long_break_enabled", True)))
        pl.addWidget(self.long_enabled)

        lf = QFormLayout()
        self.long_every = QSpinBox()
        self.long_every.setRange(2, 12)
        self.long_every.setSuffix(" blocks")
        self.long_every.setValue(int(po.get("long_break_every", 4)))
        lf.addRow("Long break every:", self.long_every)

        self.long_min = QSpinBox()
        self.long_min.setRange(1, 180)
        self.long_min.setSuffix(" min")
        self.long_min.setValue(int(po.get("long_break_minutes", 15)))
        lf.addRow("Long break length:", self.long_min)
        pl.addLayout(lf)

        def _toggle_long():
            on = self.long_enabled.isChecked()
            self.long_every.setEnabled(on)
            self.long_min.setEnabled(on)
        self.long_enabled.toggled.connect(_toggle_long)
        _toggle_long()

        self.break_sound = QCheckBox("Chime when a break starts and ends")
        self.break_sound.setChecked(bool(po.get("break_sound", True)))
        pl.addWidget(self.break_sound)
        pl.addWidget(_hint(
            "Notify only: a reminder, then your next manual Blitz resumes the "
            "cycle. Prompt: ask before starting. Auto-start only fires when Anki "
            "is the active window (otherwise leaving focus would cancel it); "
            "Raise + auto-start brings Anki to the front first."))

        self.break_mute_audio = QCheckBox("Silence card audio during a break")
        self.break_mute_audio.setChecked(bool(po.get("break_mute_audio", True)))
        pl.addWidget(self.break_mute_audio)
        pl.addWidget(_hint(
            "A block ends on an answer, so Anki renders the next card behind the "
            "break screen and plays its sound / TTS at you. This mutes it until "
            "the break is over; the card is replayed when the reviewer returns."))

        gf = QFormLayout()
        self.daily_goal = QSpinBox()
        self.daily_goal.setRange(0, 99)
        self.daily_goal.setSpecialValueText("Off")
        self.daily_goal.setSuffix(" blocks/day")
        self.daily_goal.setValue(int(po.get("daily_goal", 0)))
        gf.addRow("Daily goal:", self.daily_goal)
        pl.addLayout(gf)

        self.end_summary = QCheckBox("Show an end-of-run summary screen")
        self.end_summary.setChecked(bool(po.get("end_summary", True)))
        pl.addWidget(self.end_summary)
        self.carry_forward = QCheckBox("Carry your last break note into the next block")
        self.carry_forward.setChecked(bool(po.get("carry_forward", True)))
        pl.addWidget(self.carry_forward)

        self.resume_same_day = QCheckBox("Offer to resume an unfinished run from earlier today")
        self.resume_same_day.setChecked(bool(po.get("resume_same_day", True)))
        pl.addWidget(self.resume_same_day)
        pl.addWidget(_hint(
            "Stopped after 2 of 3 blocks? Starting a Pomodoro later the same day "
            "offers to pick up at block 3 — same cycle, same fraction split — "
            "instead of beginning again. The widget button says “Resume” when "
            "there's one waiting."))

        layout.addWidget(pbox)

        # --- Break screen elements (hide any to keep the screen calm) ---
        bbox = QGroupBox("Break screen elements")
        bl = QVBoxLayout(bbox)
        bl.addWidget(_hint("Show or hide each part of the break screen."))
        self.br_timeline = QCheckBox("Timeline (past · now · upcoming + long break)")
        self.br_journal = QCheckBox("Break journal")
        self.br_focus = QCheckBox("Focus rating (1–5)")
        self.br_tips = QCheckBox("Micro-break suggestions")
        self.br_breathing = QCheckBox("Guided breathing pacer")
        self.br_browser = QCheckBox("In-app browser button")
        self.br_addkg = QCheckBox("Add KG button (Ankisstant)")
        self.br_extend = QCheckBox("+5 min extend button")
        self.br_away = QCheckBox("“Step away” button (and Esc) — leave without ending the run")
        self.br_pill = QCheckBox("Floating countdown while you're stepped away")
        self._break_toggles = [
            (self.br_timeline, "break_show_timeline"),
            (self.br_journal, "break_show_journal"),
            (self.br_focus, "break_show_focus_rating"),
            (self.br_tips, "break_show_tips"),
            (self.br_breathing, "break_show_breathing"),
            (self.br_browser, "break_show_browser"),
            (self.br_addkg, "break_show_add_kg"),
            (self.br_extend, "break_allow_extend"),
            (self.br_away, "break_allow_step_away"),
            (self.br_pill, "break_pill"),
        ]
        for cb, key in self._break_toggles:
            cb.setChecked(bool(po.get(key, True)))
            bl.addWidget(cb)

        # Which rhythm the pacer opens on (you can still switch it on the break
        # screen itself, for that break only).
        bf = QFormLayout()
        self.br_pattern = QComboBox()
        for key in breathing.PATTERN_ORDER:
            self.br_pattern.addItem(breathing.PATTERNS[key]["label"], key)
        bi = self.br_pattern.findData(
            po.get("break_breathing_pattern", breathing.DEFAULT_PATTERN))
        if bi >= 0:
            self.br_pattern.setCurrentIndex(bi)
        bf.addRow("Breathing pattern:", self.br_pattern)
        bl.addLayout(bf)
        self.br_breathing.toggled.connect(self.br_pattern.setEnabled)
        self.br_pattern.setEnabled(self.br_breathing.isChecked())
        bl.addWidget(_hint(
            "The pacer sits collapsed as a “Breathe” button next to the tip — "
            "press it and a circle expands and contracts for you to breathe "
            "along with. 4-7-8 is the drowsy one; save it for long breaks."))

        bl.addWidget(_hint(
            "Stepping away hides the break screen with its countdown still "
            "running, so you can check your calendar or step outside — the "
            "screen comes back when you return to Anki. With it off, Esc ends "
            "the Pomodoro."))
        layout.addWidget(bbox)

        layout.addStretch(1)

    def _sync_target(self):
        mode = self.mode.currentData()
        keep = self.work_target.value()
        if mode == "time":
            self.work_target.setPrefix("")
            self.work_target.setSuffix(" min")
            self.work_target.setRange(1, 600)
        elif mode == "fraction":
            self.work_target.setSuffix("")
            self.work_target.setPrefix("1 / ")
            self.work_target.setRange(2, 50)
        else:
            self.work_target.setPrefix("")
            self.work_target.setSuffix(" cards")
            self.work_target.setRange(1, 9999)
        self.work_target.setValue(keep)

    def save(self):
        po = get_section(self.SECTION)
        po.update({
            "enabled": self.enabled.isChecked(),
            "work_mode": self.mode.currentData(),
            "work_target": self.work_target.value(),
            "break_minutes": self.break_min.value(),
            "long_break_enabled": self.long_enabled.isChecked(),
            "long_break_every": self.long_every.value(),
            "long_break_minutes": self.long_min.value(),
            "cycles": self.cycles.value(),
            "auto_return_level": self.level.currentData(),
            "break_sound": self.break_sound.isChecked(),
            "break_mute_audio": self.break_mute_audio.isChecked(),
            "daily_goal": self.daily_goal.value(),
            "end_summary": self.end_summary.isChecked(),
            "carry_forward": self.carry_forward.isChecked(),
            "resume_same_day": self.resume_same_day.isChecked(),
        })
        for cb, key in self._break_toggles:
            po[key] = cb.isChecked()
        po["break_breathing_pattern"] = self.br_pattern.currentData()
        save_section(self.SECTION, po)


# --------------------------------------------------------------------------- #
#  Sprint panel  (full Sprint Mode option set)
# --------------------------------------------------------------------------- #

class SprintPanel(QWidget):
    SECTION = "sprint"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)

        layout = QVBoxLayout(self)

        self.enabled = QCheckBox("Enable Blitz mode")
        self.enabled.setChecked(bool(cfg.get("enabled", True)))
        layout.addWidget(self.enabled)
        layout.addWidget(_hint(
            "Focused review sessions — by card count, time, or a fraction of "
            "what's due — with a progress bar. Start one from the AnkiBlitz "
            "menu (Ctrl+Shift+S)."))

        # --- Anti-pressure master ---
        anti = QGroupBox("Anti-pressure")
        al = QVBoxLayout(anti)
        self.hide_acc = QCheckBox("Hide all accuracy stats (overrides everything below)")
        self.hide_acc.setChecked(bool(cfg.get("hide_all_accuracy_stats", True)))
        self.hide_acc.setStyleSheet("font-weight: 600;")
        al.addWidget(self.hide_acc)
        al.addWidget(_hint(
            "When on, no accuracy / streak / again-count is shown anywhere — "
            "during or after Blitz sessions. Recommended."))
        layout.addWidget(anti)

        # --- Defaults ---
        sd = QGroupBox("Blitz defaults")
        f = QFormLayout(sd)

        self.mode = QComboBox()
        self.mode.addItem("Card count", "cards")
        self.mode.addItem("Time", "time")
        self.mode.addItem("Fraction of due", "fraction")
        midx = self.mode.findData(cfg.get("default_mode", "cards"))
        if midx >= 0:
            self.mode.setCurrentIndex(midx)
        f.addRow("Default mode:", self.mode)

        self.count = QComboBox()
        self.count.addItem("Distinct cards (recommended)", "unique")
        self.count.addItem("Every answer (re-reviews count again)", "answers")
        cidx = self.count.findData(cfg.get("count_mode", "unique"))
        if cidx >= 0:
            self.count.setCurrentIndex(cidx)
        f.addRow("Progress counts:", self.count)

        self.target = QSpinBox()
        self.target.setRange(1, 9999)
        self.target.setValue(int(cfg.get("default_target", 50)))
        f.addRow("Default card count:", self.target)

        self.quick = QLineEdit(", ".join(str(x) for x in cfg.get("quick_picks", [25, 50, 100])))
        f.addRow("Card quick-picks:", self.quick)

        self.time_default = QSpinBox()
        self.time_default.setRange(1, 600)
        self.time_default.setSuffix(" min")
        self.time_default.setValue(int(cfg.get("default_time_minutes", 15)))
        f.addRow("Default time:", self.time_default)

        self.time_quick = QLineEdit(
            ", ".join(str(x) for x in cfg.get("time_quick_picks", [10, 15, 25])))
        f.addRow("Time quick-picks (min):", self.time_quick)

        self.frac_quick = QLineEdit(
            ", ".join(str(x) for x in cfg.get("fraction_quick_picks", [2, 3])))
        f.addRow("Fraction quick-picks (1/n):", self.frac_quick)

        self.source = QComboBox()
        self.source.addItem("Current queue (whatever Anki has loaded)", "current_queue")
        self.source.addItem("Ask me to pick a deck each time", "pick_deck")
        idx = self.source.findData(cfg.get("card_source", "current_queue"))
        if idx >= 0:
            self.source.setCurrentIndex(idx)
        f.addRow("Card source:", self.source)
        layout.addWidget(sd)
        layout.addWidget(_hint(
            "“Distinct cards” means an Again-requeued card is counted once, so "
            "the bar reflects unique cards covered. “Every answer” counts each "
            "grade press. The bar is labelled with whichever unit you pick."))

        # --- During Blitz (neutral) ---
        dn = QGroupBox("Show during Blitz (neutral)")
        dnl = QVBoxLayout(dn)
        self.show_bar = QCheckBox("Progress bar")
        self.show_bar.setChecked(bool(cfg.get("show_progress_bar", True)))
        self.show_counter = QCheckBox("Card counter (e.g. 23 / 80)")
        self.show_counter.setChecked(bool(cfg.get("show_card_counter", True)))
        self.show_elapsed = QCheckBox("Elapsed time")
        self.show_elapsed.setChecked(bool(cfg.get("show_elapsed_time", True)))
        self.overlay_stats = QCheckBox("Thick bar with the counters on it")
        self.overlay_stats.setChecked(bool(cfg.get("overlay_stats_on_bar", True)))
        self.flush_top = QCheckBox("Sit the bar at the very top of the window")
        self.flush_top.setChecked(bool(cfg.get("bar_flush_with_top", True)))
        self.split_bar = QCheckBox("Colour the bar by grade (green done, red to repeat)")
        self.split_bar.setChecked(bool(cfg.get("split_bar_by_grade", True)))
        self.show_eta = QCheckBox("Estimated time left (cards left, in a timed Blitz)")
        self.show_eta.setChecked(bool(cfg.get("show_eta", True)))
        self.show_pace = QCheckBox("Current pace (cards/min)")
        self.show_pace.setChecked(bool(cfg.get("show_pace", False)))
        for w in (self.show_bar, self.show_counter, self.show_elapsed,
                  self.overlay_stats, self.flush_top, self.split_bar,
                  self.show_eta, self.show_pace):
            dnl.addWidget(w)
        dnl.addWidget(_hint(
            "The bar is a single thick band with the counters sitting on it, "
            "rather than a row of text stacked above a thin bar — same numbers, "
            "less of the screen spent on the gap between them. Turn it off for "
            "the stacked layout.\n\n"
            "With Anki set to hide the top bar during review it doesn't remove "
            "the toolbar, only fade it out — the empty band it leaves is why the "
            "bar can look like it's floating below the top of the screen. Turned "
            "on, that band is closed up while the bar is showing and given back "
            "the moment you move the mouse to the top of the window (or leave "
            "the reviewer). Nothing happens if you keep the top bar visible.\n\n"
            "The filled part of the bar splits into what you got through cleanly "
            "and what you pressed Again on and will see again — both named in "
            "words next to it, so you never have to guess what a colour means. "
            "(It's an accuracy display, so the anti-pressure switch below hides "
            "it with the rest.)\n\n"
            "The estimate prices what's left off your own review history: how "
            "many presses a new card, a review and a card mid-step have "
            "actually cost you (misses and learning steps included), times your "
            "usual time per press, nudged toward today's pace as you go. It "
            "shows from the first card, one slow card barely moves it, and "
            "learning cards waiting on a step timer are counted even before "
            "Anki's counts show them."))
        self.bar_outside = QCheckBox("Keep the bar up outside a Blitz (all due cards)")
        self.bar_outside.setChecked(bool(cfg.get("show_bar_outside_blitz", True)))
        dnl.addWidget(self.bar_outside)
        dnl.addWidget(_hint(
            "During an ordinary review session the same bar stays up, dimmed, "
            "filling against everything you have due rather than a Blitz target. "
            "It counts down live — a card that comes back in learning pushes the "
            "target out by one — so it reaches the end exactly when your queue "
            "empties. It gets the grade colours and the time estimate too; the "
            "accuracy %, Again tally and streak are never shown on it."))
        layout.addWidget(dn)

        # --- During Blitz (pressure) ---
        dp = QGroupBox("Show during Blitz (may pressure grading)")
        dpl = QVBoxLayout(dp)
        self.show_acc = QCheckBox("Live accuracy %")
        self.show_acc.setChecked(bool(cfg.get("show_live_accuracy", False)))
        self.show_again = QCheckBox("Again count")
        self.show_again.setChecked(bool(cfg.get("show_again_count", False)))
        self.show_streak = QCheckBox("Again-free streak counter")
        self.show_streak.setChecked(bool(cfg.get("show_streak_counter", False)))
        self.streak_anim = QCheckBox("Streak glow/animation effects")
        self.streak_anim.setChecked(bool(cfg.get("streak_animations", False)))
        for w in (self.show_acc, self.show_again, self.show_streak, self.streak_anim):
            dpl.addWidget(w)
        dpl.addWidget(_hint(
            "These can incentivize avoiding Again when you should press it. Off by default."))
        layout.addWidget(dp)

        # --- Completion ---
        cp = QGroupBox("Completion screen")
        cpl = QVBoxLayout(cp)
        self.show_completion = QCheckBox("Show completion screen")
        self.show_completion.setChecked(bool(cfg.get("show_completion_screen", True)))
        self.completion_sound = QCheckBox("Play sound on completion")
        self.completion_sound.setChecked(bool(cfg.get("completion_sound", False)))
        self.completion_acc = QCheckBox("Show accuracy in completion recap")
        self.completion_acc.setChecked(bool(cfg.get("show_completion_accuracy", False)))
        for w in (self.show_completion, self.completion_sound, self.completion_acc):
            cpl.addWidget(w)
        layout.addWidget(cp)

        # --- Personal bests ---
        pb = QGroupBox("Personal bests to track")
        pbl = QVBoxLayout(pb)
        self.pb_today = QCheckBox("Blitzes completed today")
        self.pb_today.setChecked(bool(cfg.get("track_pb_sprints_today", True)))
        self.pb_speed = QCheckBox("Best cards/min")
        self.pb_speed.setChecked(bool(cfg.get("track_pb_speed", True)))
        self.pb_total = QCheckBox("Total Blitzes all-time")
        self.pb_total.setChecked(bool(cfg.get("track_pb_total_sprints", True)))
        for w in (self.pb_today, self.pb_speed, self.pb_total):
            pbl.addWidget(w)
        layout.addWidget(pb)

        layout.addStretch(1)

    @staticmethod
    def _parse_picks(text, fallback, minimum=1):
        try:
            picks = [int(x.strip()) for x in text.split(",") if x.strip()]
            picks = [p for p in picks if p >= minimum]
        except ValueError:
            picks = []
        return picks or fallback

    def save(self):
        picks = self._parse_picks(self.quick.text(), [25, 50, 100])
        time_picks = self._parse_picks(self.time_quick.text(), [10, 15, 25])
        frac_picks = self._parse_picks(self.frac_quick.text(), [2, 3], minimum=2)

        cfg = get_section(self.SECTION)
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "hide_all_accuracy_stats": self.hide_acc.isChecked(),
            "default_mode": self.mode.currentData(),
            "count_mode": self.count.currentData(),
            "default_target": self.target.value(),
            "quick_picks": picks,
            "default_time_minutes": self.time_default.value(),
            "time_quick_picks": time_picks,
            "fraction_quick_picks": frac_picks,
            "card_source": self.source.currentData(),
            "show_progress_bar": self.show_bar.isChecked(),
            "show_bar_outside_blitz": self.bar_outside.isChecked(),
            "show_card_counter": self.show_counter.isChecked(),
            "show_elapsed_time": self.show_elapsed.isChecked(),
            "overlay_stats_on_bar": self.overlay_stats.isChecked(),
            "bar_flush_with_top": self.flush_top.isChecked(),
            "split_bar_by_grade": self.split_bar.isChecked(),
            "show_eta": self.show_eta.isChecked(),
            "show_pace": self.show_pace.isChecked(),
            "show_live_accuracy": self.show_acc.isChecked(),
            "show_again_count": self.show_again.isChecked(),
            "show_streak_counter": self.show_streak.isChecked(),
            "streak_animations": self.streak_anim.isChecked(),
            "show_completion_screen": self.show_completion.isChecked(),
            "completion_sound": self.completion_sound.isChecked(),
            "show_completion_accuracy": self.completion_acc.isChecked(),
            "track_pb_sprints_today": self.pb_today.isChecked(),
            "track_pb_speed": self.pb_speed.isChecked(),
            "track_pb_total_sprints": self.pb_total.isChecked(),
        })
        save_section(self.SECTION, cfg)


# --------------------------------------------------------------------------- #
#  Music panel
# --------------------------------------------------------------------------- #

class FocusPanel(QWidget):
    """Focus Lock (how hard it is to leave a Blitz) + the Focus Score."""

    SECTION = "focus"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)
        layout = QVBoxLayout(self)

        self.enabled = QCheckBox("Enable Focus features")
        self.enabled.setChecked(cfg.get("enabled", True))
        layout.addWidget(self.enabled)
        layout.addWidget(_hint(
            "Focus Lock makes it harder to bail out of studying; the Focus Score "
            "rates each finished Blitz out of 100."))

        layout.addWidget(_hline())

        # --- Focus Lock ---
        lock_title = QLabel("Focus Lock")
        lock_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(lock_title)

        self.apply_to_reviews = QCheckBox("Also lock ordinary review sessions (not just Blitzes)")
        self.apply_to_reviews.setChecked(cfg.get("apply_to_reviews", True))
        layout.addWidget(self.apply_to_reviews)

        form = QFormLayout()
        self.lock_level = QComboBox()
        self.lock_level.addItem("Off — leaving is free", 0)
        self.lock_level.addItem("Confirm before leaving", 1)
        self.lock_level.addItem("Clear extra cards, then confirm", 2)
        self.lock_level.addItem("Can’t leave until finished", 3)
        li = self.lock_level.findData(int(cfg.get("lock_level", 0)))
        if li >= 0:
            self.lock_level.setCurrentIndex(li)
        form.addRow("Lock level", self.lock_level)

        self.lock_min_cards = QSpinBox()
        self.lock_min_cards.setRange(1, 9999)
        self.lock_min_cards.setValue(int(cfg.get("lock_min_cards", 10)))
        self.lock_min_cards.setSuffix(" cards")
        form.addRow("Extra cards when you try to leave", self.lock_min_cards)
        layout.addLayout(form)

        layout.addWidget(_hint(
            "Level 2: trying to leave forces you to clear this many MORE cards "
            "first, then asks you to confirm. Level 3: ‘finished’ means the Blitz "
            "target (or, in a normal review, all your due cards). Alt-tabbing to "
            "another app still cancels a Blitz at levels 1–2; at level 3 the "
            "session is kept and Anki is pulled back to the front."))

        def _sync_lock():
            self.lock_min_cards.setEnabled(self.lock_level.currentData() == 2)
        self.lock_level.currentIndexChanged.connect(_sync_lock)
        _sync_lock()

        layout.addWidget(_hline())

        # --- Focus Score ---
        score_title = QLabel("Focus Score")
        score_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(score_title)

        self.score_enabled = QCheckBox("Show a Focus Score on the completion screen")
        self.score_enabled.setChecked(cfg.get("score_enabled", True))
        layout.addWidget(self.score_enabled)

        self.score_include_accuracy = QCheckBox("Count accuracy as part of the score")
        self.score_include_accuracy.setChecked(cfg.get("score_include_accuracy", True))
        layout.addWidget(self.score_include_accuracy)
        layout.addWidget(_hint(
            "The score blends completion, speed and engagement (time not idle). "
            "Accuracy is optional and is ignored anyway while the Blitz tab’s "
            "‘hide all accuracy stats’ switch is on."))

        form2 = QFormLayout()
        self.idle_threshold = QSpinBox()
        self.idle_threshold.setRange(5, 3600)
        self.idle_threshold.setValue(int(cfg.get("idle_threshold_seconds", 60)))
        self.idle_threshold.setSuffix(" sec")
        form2.addRow("Idle after a gap of", self.idle_threshold)

        self.target_spc = _double(1.0, 120.0, 0.5, 1, " sec")
        self.target_spc.setValue(float(cfg.get("target_seconds_per_card", 8.0)))
        form2.addRow("Target pace per card", self.target_spc)
        layout.addLayout(form2)
        layout.addWidget(_hint(
            "A pause longer than the idle threshold counts the extra time as idle "
            "(and lowers engagement). Hitting the target pace or faster scores "
            "full marks on speed."))
        layout.addStretch(1)

    def save(self):
        cfg = get_section(self.SECTION)
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "apply_to_reviews": self.apply_to_reviews.isChecked(),
            "lock_level": int(self.lock_level.currentData()),
            "lock_min_cards": self.lock_min_cards.value(),
            "score_enabled": self.score_enabled.isChecked(),
            "score_include_accuracy": self.score_include_accuracy.isChecked(),
            "idle_threshold_seconds": self.idle_threshold.value(),
            "target_seconds_per_card": self.target_spc.value(),
        })
        save_section(self.SECTION, cfg)


class MusicPanel(QWidget):
    """Keep study music inside Anki — an embedded SoundCloud / YouTube player on
    the break screen and/or a floating mini-dock during reviews."""

    SECTION = "music"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)
        layout = QVBoxLayout(self)

        self.enabled = QCheckBox("Enable the music player")
        self.enabled.setChecked(cfg.get("enabled", False))
        layout.addWidget(self.enabled)
        layout.addWidget(_hint(
            "Off by default. A small embedded player so you can keep your study "
            "music inside Anki instead of switching apps."))

        layout.addWidget(_hline())

        self.show_on_break = QCheckBox("Show a built-in music box on the break screen")
        self.show_on_break.setChecked(cfg.get("show_on_break", True))
        layout.addWidget(self.show_on_break)

        self.show_dropdown = QCheckBox("Allow the floating mini-player during reviews")
        self.show_dropdown.setChecked(cfg.get("show_dropdown", True))
        layout.addWidget(self.show_dropdown)
        layout.addWidget(_hint(
            "Toggle the floating player with Tools ▸ AnkiBlitz ▸ Music player "
            "(Ctrl+Shift+M). It’s its own window, so it keeps playing as you move "
            "through cards."))

        self.show_on_home = QCheckBox("Show a built-in music box on the deck list (below the rail)")
        self.show_on_home.setChecked(cfg.get("show_on_home", True))
        layout.addWidget(self.show_on_home)
        layout.addWidget(_hint(
            "A small player pinned to the right of the deck list while you pick a "
            "deck; it tucks away once you start reviewing."))

        layout.addWidget(_hline())

        form = QFormLayout()
        self.service = QComboBox()
        self.service.addItem("SoundCloud", "soundcloud")
        self.service.addItem("YouTube Music", "youtube")
        si = self.service.findData(cfg.get("service", "soundcloud"))
        if si >= 0:
            self.service.setCurrentIndex(si)
        form.addRow("Opens on", self.service)
        layout.addLayout(form)

        layout.addWidget(_hint(
            "Browse and hit play, or use the ⏮ ⏯ ⏭ buttons to skip and pause "
            "without opening the page. Sign in (logins persist), and use — to "
            "minimise to just the toolbar while music keeps playing. Stays on the "
            "music sites; YouTube Music can’t wander off to regular YouTube. "
            "SoundCloud plays full tracks (login optional) and is the reliable "
            "one. YouTube Music needs your Anki build to ship the proprietary "
            "codecs (H.264/AAC). It reopens on the last page you left."))
        layout.addStretch(1)

    def save(self):
        cfg = get_section(self.SECTION)
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "show_on_break": self.show_on_break.isChecked(),
            "show_dropdown": self.show_dropdown.isChecked(),
            "show_on_home": self.show_on_home.isChecked(),
            "service": self.service.currentData(),
        })
        save_section(self.SECTION, cfg)


# --------------------------------------------------------------------------- #
#  SynapsePro panel
# --------------------------------------------------------------------------- #

class SynapsePanel(QWidget):
    """Living alongside the SynapsePro add-on: share its colours, and don't run
    two of the things you only need one of."""

    SECTION = "synapse"

    def __init__(self):
        super().__init__()
        cfg = get_section(self.SECTION)
        from .engine import theme_bridge
        layout = QVBoxLayout(self)

        # Say it in words rather than colouring something green — the whole tab
        # is meaningless if the add-on isn't there, and that shouldn't be a
        # guessing game.
        found = False
        try:
            found = theme_bridge.synapse_available()
        except Exception:
            pass
        status = QLabel(
            "<b>SynapsePro detected.</b> The settings below are active."
            if found else
            "<b>SynapsePro not detected.</b> Everything below is inert — "
            "AnkiBlitz looks and behaves exactly as it does on its own. "
            "The settings are kept so they take effect if you install it later."
        )
        status.setWordWrap(True)
        status.setStyleSheet("font-size: 12px; margin-bottom: 6px;")
        layout.addWidget(status)

        layout.addWidget(_hline())

        self.sidebar_buttons = QCheckBox("Put AnkiBlitz in SynapsePro's sidebar")
        self.sidebar_buttons.setChecked(cfg.get("sidebar_buttons", True))
        layout.addWidget(self.sidebar_buttons)
        layout.addWidget(_hint(
            "Adds three icons to SynapsePro's strip: start/resume a Pomodoro, "
            "open the AnkiBlitz panel (Blitz presets, stats, journal), and these "
            "settings. SynapsePro itself isn't modified — if it rebuilds its "
            "sidebar the buttons are put back automatically."))

        self.hide_rail = QCheckBox("Drop the deck-list rail once it's in the sidebar")
        self.hide_rail.setChecked(cfg.get("hide_rail", True))
        layout.addWidget(self.hide_rail)
        layout.addWidget(_hint(
            "One AnkiBlitz, one place. Uncheck to keep the floating rail on the "
            "deck list as well as the sidebar buttons."))

        layout.addWidget(_hline())

        self.theme_bridge = QCheckBox("Match SynapsePro's colours")
        self.theme_bridge.setChecked(cfg.get("theme_bridge", True))
        layout.addWidget(self.theme_bridge)
        layout.addWidget(_hint(
            "AnkiBlitz's rail, reveal overlay and break screen borrow SynapsePro's "
            "palette so the two read as one product — and follow along when you "
            "change its colour theme. Layout and behaviour don't change. Turn this "
            "off to keep AnkiBlitz's own colours."))

        self.theme_settings = QCheckBox("Match this Settings window too")
        self.theme_settings.setChecked(cfg.get("theme_settings", True))
        layout.addWidget(self.theme_settings)
        layout.addWidget(_hint(
            "Recolours the tabs, inputs and buttons here from SynapsePro's "
            "palette. Checkboxes keep Anki's native look on purpose — a "
            "restyled tick is the easiest thing in a stylesheet to get wrong. "
            "Takes effect next time you open Settings."))

        self.match_font = QCheckBox("Match SynapsePro's font as well")
        self.match_font.setChecked(cfg.get("match_font", False))
        layout.addWidget(self.match_font)
        layout.addWidget(_hint(
            "Off by default — colours usually carry the resemblance on their own, "
            "and Anki's own font is tuned for the reviewer."))

        layout.addWidget(_hline())

        self.defer_music = QCheckBox("Let SynapsePro handle the music")
        self.defer_music.setChecked(cfg.get("defer_music", True))
        layout.addWidget(self.defer_music)
        layout.addWidget(_hint(
            "SynapsePro ships a background music player, so AnkiBlitz hides its "
            "own — the rail button, the break-screen box and Ctrl+Shift+M all step "
            "aside. Nothing is removed: uncheck this (or uninstall SynapsePro) and "
            "AnkiBlitz's player comes straight back."))

        self.pomodoro_notice = QCheckBox("Warn me if two Pomodoro timers are running")
        self.pomodoro_notice.setChecked(cfg.get("pomodoro_notice", True))
        layout.addWidget(self.pomodoro_notice)
        layout.addWidget(_hint(
            "SynapsePro has a Pomodoro of its own. AnkiBlitz won't touch another "
            "add-on's settings, so if both are on it says so once and opens "
            "SynapsePro's settings for you — turning its timer off there leaves "
            "AnkiBlitz's in charge."))

        layout.addStretch(1)

    def save(self):
        cfg = get_section(self.SECTION)
        cfg.update({
            "sidebar_buttons": self.sidebar_buttons.isChecked(),
            "hide_rail": self.hide_rail.isChecked(),
            "theme_bridge": self.theme_bridge.isChecked(),
            "theme_settings": self.theme_settings.isChecked(),
            "match_font": self.match_font.isChecked(),
            "defer_music": self.defer_music.isChecked(),
            "pomodoro_notice": self.pomodoro_notice.isChecked(),
        })
        save_section(self.SECTION, cfg)


# --------------------------------------------------------------------------- #
#  Presets (profiles) panel
# --------------------------------------------------------------------------- #

class PresetsPanel(QWidget):
    """Whole-config profiles: apply / save / delete. Drives engine/presets
    directly rather than a single config section, so it has no ``save()`` the
    dialog's Save button calls — applying happens inline and closes the dialog."""

    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Profiles</b>"))
        layout.addWidget(_hint(
            "A profile flips the <i>feel</i> of reviewing in one click: the "
            "auto-reveal pace, Focus Lock, the near-end nudge, and the "
            "anti-pressure / progress display. It deliberately leaves alone how "
            "you launch a session (Blitz mode / target, Pomodoro blocks — you pick "
            "those each time), your word-reveal speed, the music, and your "
            "note-type / deck exclusions. Built-ins: <b>Default</b> (everyday), "
            "<b>Blitz</b> (committed run), <b>Relaxed</b> (low friction). Applying "
            "overwrites the feel settings on the other tabs; your settings as they "
            "were are kept as the “My setup” profile."))

        self.active_lbl = QLabel()
        self.active_lbl.setStyleSheet("font-size: 12px; margin: 4px 0;")
        layout.addWidget(self.active_lbl)

        self.listw = QListWidget()
        self.listw.setMinimumHeight(180)
        self.listw.itemSelectionChanged.connect(self._sync_buttons)
        self.listw.itemDoubleClicked.connect(lambda _: self._apply())
        layout.addWidget(self.listw)

        # Key settings of the highlighted profile, so you can see what each does
        # before applying it.
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setStyleSheet("font-size: 11px; margin: 2px 4px 6px 4px;")
        layout.addWidget(self.details)

        row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply)
        self.save_btn = QPushButton("Save current as…")
        self.save_btn.clicked.connect(self._save_as)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        row.addWidget(self.apply_btn)
        row.addWidget(self.save_btn)
        row.addWidget(self.delete_btn)
        row.addStretch(1)
        layout.addLayout(row)

        layout.addWidget(_hint(
            "Apply closes Settings (so the other tabs can't write back over the "
            "profile you just applied) — reopen to fine-tune. “Save current as…” "
            "captures exactly what's on the tabs right now. Built-ins can't be "
            "deleted; deleting a custom copy of a built-in restores the original."))
        layout.addStretch(1)

        self._reload_list()

    def _reload_list(self):
        self.listw.clear()
        active = presets.active_name()
        for name in presets.list_profiles():
            tag = "   ·   built-in" if presets.is_builtin(name) else ""
            item = QListWidgetItem(name + tag)
            item.setData(Qt.ItemDataRole.UserRole, name)
            if name == active:
                f = item.font(); f.setBold(True); item.setFont(f)
            self.listw.addItem(item)
        self.active_lbl.setText(f"Active profile: <b>{active or '—'}</b>")
        self._sync_buttons()

    def _selected_name(self):
        it = self.listw.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _sync_buttons(self):
        name = self._selected_name()
        self.apply_btn.setEnabled(bool(name))
        self.delete_btn.setEnabled(bool(name) and not presets.is_builtin(name))
        lines = presets.summary_lines(name) if name else []
        if lines:
            self.details.setText(
                "<b>Key settings</b><br>• " + "<br>• ".join(lines))
        else:
            self.details.setText("")

    def _apply(self):
        name = self._selected_name()
        if name and presets.apply_profile(name):
            self._dialog._applied_and_close(name)

    def _save_as(self):
        name, ok = QInputDialog.getText(self, "Save profile", "Profile name:")
        name = (name or "").strip()
        if not ok or not name:
            return
        # Snapshot what's on the tabs right now, not just the last-saved config.
        self._dialog._save_open_panels()
        presets.save_current_as(name)
        self._reload_list()
        tooltip(f"Saved profile “{name}”.")

    def _delete(self):
        name = self._selected_name()
        if name and not presets.is_builtin(name) and presets.delete_profile(name):
            self._reload_list()
            tooltip(f"Deleted profile “{name}”.")


# --------------------------------------------------------------------------- #
#  The dialog
# --------------------------------------------------------------------------- #

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("AnkiBlitz Settings")
        self.setMinimumSize(480, 560)

        # Match SynapsePro's own dialogs when it's installed; empty string
        # otherwise, which leaves Anki's native styling untouched.
        try:
            from .engine import theme_bridge
            qss = theme_bridge.qt_stylesheet()
            if qss:
                self.setStyleSheet(qss)
        except Exception:
            pass

        layout = QVBoxLayout(self)

        master_row = QHBoxLayout()
        self.master = QCheckBox("Enable AnkiBlitz")
        self.master.setChecked(suite_enabled())
        font = self.master.font()
        font.setBold(True)
        self.master.setFont(font)
        master_row.addWidget(self.master)
        master_row.addStretch(1)
        layout.addLayout(master_row)
        layout.addWidget(_hint(
            "Master switch. When off, every tool below is inactive regardless "
            "of its own setting."))

        self.tabs = QTabWidget()
        self.presets = PresetsPanel(self)
        self.speed_focus = SpeedFocusPanel()
        self.word_reveal = WordRevealPanel()
        self.sprint = SprintPanel()
        self.focus = FocusPanel()
        self.quick_start = QuickStartPanel()
        self.pomodoro = PomodoroPanel()
        self.music = MusicPanel()
        self.synapse = SynapsePanel()
        # Profiles front-and-centre, then the per-feature tabs.
        self.tabs.addTab(_scroll(self.presets), "Profiles")
        self.tabs.addTab(_scroll(self.sprint), "Blitz")
        # Not wrapped: the panel scrolls its own knobs so its preview stays put.
        self.tabs.addTab(self.speed_focus, "Speed Focus")
        self.tabs.addTab(_scroll(self.word_reveal), "Word Reveal")
        self.tabs.addTab(_scroll(self.focus), "Focus")
        self.tabs.addTab(_scroll(self.quick_start), "Quick Start")
        self.tabs.addTab(_scroll(self.pomodoro), "Pomodoro")
        self.tabs.addTab(_scroll(self.music), "Music")
        self.tabs.addTab(_scroll(self.synapse), "SynapsePro")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save_open_panels(self):
        """Persist every feature panel + the master switch (no close). Shared by
        Save and by the Profiles tab's 'Save current as…' so a snapshot reflects
        unsaved on-screen edits. The Profiles tab itself has no save()."""
        set_suite_enabled(self.master.isChecked())
        self.speed_focus.save()
        self.word_reveal.save()
        self.sprint.save()
        self.focus.save()
        self.quick_start.save()
        self.pomodoro.save()
        self.music.save()
        self.synapse.save()

    def _on_save(self):
        self._save_open_panels()
        # The rail bakes SynapsePro's colours into its HTML at render time, so a
        # theme-bridge change only shows on the next redraw. Force one.
        self.accept()
        try:
            from .engine import widgets, synapse_sidebar
            widgets.refresh_home()
            synapse_sidebar.apply_settings_change()
        except Exception:
            pass

    def _applied_and_close(self, name):
        """A profile was applied from the Profiles tab: close WITHOUT running
        _on_save, so the now-stale feature panels can't overwrite the profile."""
        tooltip(f"Switched to “{name}”.")
        self.accept()


def open_settings() -> None:
    SettingsDialog(mw).exec()
