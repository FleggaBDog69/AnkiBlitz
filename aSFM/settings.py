"""Adaptive Speed Focus settings — one dialog.

A single ``QDialog`` exposing the adaptive auto-reveal knobs, with a live preview
table that always agrees with the runtime (both call ``adaptive.delay_for``).
Settings are read live per card, so saving takes effect on the next card.
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
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPalette,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .config import get_config, save_config
from .engine import adaptive, pace

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
_ANKIWEB_URL = "https://ankiweb.net/shared/info/1148593203"
_ISSUES_URL = "https://github.com/FleggaBDog69/AnkiBlitz/issues"
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


def _double(lo, hi, step, decimals, suffix=""):
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setSingleStep(step)
    sb.setDecimals(decimals)
    if suffix:
        sb.setSuffix(suffix)
    return sb


def _section(title: str, sub: str = "") -> QLabel:
    """A section heading, with an optional one-line explanation under it."""
    html = f"<div style='font-size: 13px; font-weight: 600;'>{title}</div>"
    if sub:
        html += f"<div style='color: gray; font-size: 11px;'>{sub}</div>"
    lbl = QLabel(html)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setWordWrap(True)
    lbl.setContentsMargins(0, 8, 0, 2)
    return lbl


def _form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setHorizontalSpacing(12)
    return form


def _tab(tabs: QTabWidget, name: str) -> QVBoxLayout:
    """A scrolling tab page; returns the layout to fill."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(4, 4, 12, 4)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(page)
    tabs.addTab(area, name)
    return layout


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
        heading = QLabel(title)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumHeight(110)
        self.list.setMaximumHeight(170)
        checked_set = set(checked_items or [])
        for name in all_items:
            item = QListWidgetItem(name)
            item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(_CHECKED if name in checked_set else _UNCHECKED)
            self.list.addItem(item)
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


class _Panel(QWidget):
    """Everything in the dialog above the Save row: a header with the master
    switch, the settings split into tabs, and the preview pinned beside them so
    it stays in view whichever tab you're changing."""

    def __init__(self):
        super().__init__()
        cfg = get_config()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # --- header: what this is, and the one switch that matters most ---
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Adaptive Speed Focus")
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.45)
        font.setBold(True)
        title.setFont(font)
        titles.addWidget(title)
        titles.addWidget(_hint(
            "Waits a delay matched to the card, then shows the answer. It never "
            "grades the card for you — you still press the button."))
        header.addLayout(titles, 1)
        self.enabled = QCheckBox("Enabled")
        self.enabled.setChecked(bool(cfg["enabled"]))
        header.addWidget(self.enabled, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        body.addWidget(self.tabs, 1)

        # ===== Timing =====
        layout = _tab(self.tabs, "Timing")
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
        layout.addStretch(1)

        # ===== On screen: the countdown, the heads-up, holding the timer =====
        layout = _tab(self.tabs, "On screen")
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
        layout.addLayout(warn_form)
        layout.addWidget(_hint(
            "The sound plays, and the bar turns red, once this much of the wait "
            "has passed. For your own sound, put alert.flac/.ogg/.opus/.wav in "
            "user_files."))

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
            "until you release it. It can share Progressive Word Reveal's key: "
            "the first press finishes the fade, the next one pauses."))
        layout.addStretch(1)

        # ===== Your pace =====
        layout = _tab(self.tabs, "Your pace")
        layout.addWidget(_section("Learn my pace",
                                  "Let aSFM fit the timer to how fast you really are."))
        self.learn = QCheckBox("Learn my pace from my reviews")
        self.learn.setChecked(bool(cfg["learn_my_pace"]))
        layout.addWidget(self.learn)
        layout.addWidget(_hint(
            "Off until you tick it. When on, aSFM keeps a small tally of how "
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
        layout.addStretch(1)
        self._pace_reset_pending = None    # None | "all" (Reset) | "rebase" (Calibrate)
        self._pace_refitted = set()        # kinds whose own setting Calibrate refitted
        self.auto_tune.toggled.connect(self._refresh_pace)
        self.learn.toggled.connect(self._refresh_pace)

        # ===== Cards: what to skip, picture cards, one-by-one clozes =====
        layout = _tab(self.tabs, "Cards")
        layout.addWidget(_section("Skip these",
                                  "No timer at all — review them normally."))
        notetypes, decks = _collect_names()
        self.nt_list = _FilterList("Note types", notetypes, cfg["excluded_note_types"])
        self.deck_list = _FilterList(
            "Decks (a parent also covers its subdecks)", decks, cfg["excluded_decks"])
        sf_lists = QHBoxLayout()
        sf_lists.addWidget(self.nt_list, 1)
        sf_lists.addWidget(self.deck_list, 1)
        layout.addLayout(sf_lists)

        layout.addWidget(_section("Picture cards",
                                  "Nothing to read, so a set time instead of a word count."))
        self.fixed_enabled = QCheckBox("Use a set time for these note types and decks")
        self.fixed_enabled.setChecked(bool(cfg["fixed_time_enabled"]))
        layout.addWidget(self.fixed_enabled)
        fixed_form = _form()
        self.fixed_base = _double(0.5, 60.0, 0.5, 1, " s")
        self.fixed_base.setValue(float(cfg["fixed_time_base_seconds"]))
        fixed_form.addRow("Set time:", self.fixed_base)
        layout.addLayout(fixed_form)
        layout.addWidget(_hint("Only the difficulty weight still applies."))
        self.fixed_nt_list = _FilterList(
            "Picture note types", notetypes, cfg["fixed_time_note_types"])
        self.fixed_deck_list = _FilterList(
            "Picture decks (a parent also covers its subdecks)",
            decks, cfg["fixed_time_decks"])
        fixed_lists = QHBoxLayout()
        fixed_lists.addWidget(self.fixed_nt_list, 1)
        fixed_lists.addWidget(self.fixed_deck_list, 1)
        layout.addLayout(fixed_lists)
        for w in (self.fixed_base, self.fixed_nt_list, self.fixed_deck_list):
            self.fixed_enabled.toggled.connect(w.setEnabled)
            w.setEnabled(self.fixed_enabled.isChecked())

        # --- Cloze one-by-one cards: per-cloze timers or a multiplier ---
        layout.addWidget(_section("One-by-one cloze cards",
                                  "Cards with the AnKing “One by one” field filled."))
        obo_form = _form()
        self.obo_mode = QComboBox()
        for label, value in (("A timer per cloze", "per_cloze"),
                             ("Whole card × multiplier", "multiplier"),
                             ("Off — time like any card", "off")):
            self.obo_mode.addItem(label, value)
        idx = self.obo_mode.findData(adaptive.one_by_one_mode(cfg))
        self.obo_mode.setCurrentIndex(max(0, idx))
        obo_form.addRow("Timing:", self.obo_mode)
        self.obo_per_cloze = _double(0.0, 30.0, 0.5, 1, " s")
        self.obo_per_cloze.setValue(float(cfg["one_by_one_seconds_per_cloze"]))
        obo_form.addRow("Per cloze:", self.obo_per_cloze)
        self.obo_per_word = _double(0.0, 5.0, 0.05, 2, " s")
        self.obo_per_word.setValue(float(cfg["one_by_one_seconds_per_word"]))
        obo_form.addRow("Per answer word:", self.obo_per_word)
        self.obo_max = _double(0.5, 60.0, 0.5, 1, " s")
        self.obo_max.setValue(float(cfg["one_by_one_max_cloze_seconds"]))
        obo_form.addRow("Longest per cloze:", self.obo_max)
        self.obo_mult = _double(0.5, 5.0, 0.05, 2, "×")
        self.obo_mult.setValue(float(cfg["one_by_one_multiplier"]))
        obo_form.addRow("Multiplier:", self.obo_mult)
        layout.addLayout(obo_form)
        layout.addWidget(_hint(
            "A timer per cloze uncovers the next cloze each time it runs out; "
            "uncovering one yourself starts the next. The first cloze also gets "
            "the normal question-reading time. Needs the AnKing template doing "
            "one-by-one on the front."))

        def _obo_mode_changed(*_):
            mode = self.obo_mode.currentData()
            for w in (self.obo_per_cloze, self.obo_per_word, self.obo_max):
                w.setEnabled(mode == "per_cloze")
            self.obo_mult.setEnabled(mode == "multiplier")
        self.obo_mode.currentIndexChanged.connect(_obo_mode_changed)
        _obo_mode_changed()
        layout.addStretch(1)

        # ===== the preview, pinned beside the tabs =====
        card = QFrame()
        card.setObjectName("asfmPreview")
        card.setFixedWidth(340)
        card.setStyleSheet(
            "#asfmPreview { border: 1px solid palette(mid); border-radius: 8px;"
            " background: palette(base); }")
        side = QVBoxLayout(card)
        side.setContentsMargins(14, 12, 14, 12)
        side.addWidget(_section("Preview", "Seconds until the answer shows"))
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.preview)
        self.preview_hint = _hint("")
        side.addWidget(self.preview_hint)
        side.addStretch(1)
        body.addWidget(card, 0)

        for w in (self.base, self.per_word, self.min_delay, self.max_delay,
                  self.unfamiliar, self.new_mult, self.difficulty,
                  self.per_answer_word, self.max_answer):
            w.valueChanged.connect(self._update_preview)
        self.enable_on_new.toggled.connect(self._update_preview)
        self.target.valueChanged.connect(self._update_preview)
        self._refresh_pace()

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
        cfg = get_config()
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
            "excluded_note_types": self.nt_list.checked(),
            "excluded_decks": self.deck_list.checked(),
            "fixed_time_enabled": self.fixed_enabled.isChecked(),
            "fixed_time_base_seconds": round(self.fixed_base.value(), 2),
            "fixed_time_note_types": self.fixed_nt_list.checked(),
            "fixed_time_decks": self.fixed_deck_list.checked(),
            "one_by_one_mode": self.obo_mode.currentData(),
            "one_by_one_seconds_per_cloze": round(self.obo_per_cloze.value(), 2),
            "one_by_one_seconds_per_word": round(self.obo_per_word.value(), 2),
            "one_by_one_max_cloze_seconds": round(self.obo_max.value(), 2),
            "one_by_one_multiplier": round(self.obo_mult.value(), 2),
        })
        save_config(cfg)
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
        cfg = {**get_config(), **self._current_cfg(),
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


class _PaceDetailsDialog(QDialog):
    """Read-only: each kind's pace, recent sessions, and how it all works.
    Kept off the tab so the tab stays simple."""

    _KINDS = (("review", "Review"), ("learning", "Learning / relearning"),
              ("new", "New"), ("picture", "Picture"), ("one_by_one", "One-by-one"))

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
            note = ""
            if cat in pace.TUNED:
                pc = f"{panel._preview_pace(cat):.2f}×"
                if cat != "review" and not pace.count_of(cat):
                    note = "follows review"
            else:
                pc, note = "–", "not auto-tuned"
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
            "learning, new and picture cards each keep their own pace, so one "
            "kind can't drag another; a kind with nothing learned yet follows "
            "your review pace."))
        layout.addWidget(_hint(
            "Calibrate: fits base and per word to the time you'd revealed your "
            "target share of review cards by, at each length. Once there's "
            "enough data it also suggests the learning and new multipliers, "
            "the difficulty weight, the picture time and the one-by-one "
            "timings, each from that kind's own cards. Applying resets the "
            "paces those settings now carry. Without enough of your own "
            "reveals it makes a rough estimate from Anki's review history."))
        layout.addWidget(_hint(
            "What's kept: counts and timings by card length and difficulty, "
            "never which cards, in one file per profile on this computer. "
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

        if pace.reveal_data_ready(cfg):
            self._show(pace.fit_from_reveals(cfg), measured=True)
        elif mw.col is not None:
            from aqt.operations import QueryOp
            QueryOp(
                parent=self,
                op=lambda col: pace.fit_from_revlog(col, cfg),
                success=lambda r: self._show(r, measured=False),
            ).failure(
                lambda _exc: self._show(None, measured=False, failed=True)
            ).with_progress("Reading your review history…").run_in_background()
        else:
            self._show(None, measured=False)

    def _show(self, r, measured: bool, failed: bool = False):
        try:
            self._fill(r, measured, failed)
        except RuntimeError:
            pass    # the dialog was closed before the history read finished

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
                "hundred passed reviews in Anki's history. Keep reviewing with "
                "the timer on and try again.")
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
            source = (f"From <b>{r['cards']}</b> cards aSFM watched you answer. "
                      "Timed so the answer shows before you've revealed it on "
                      f"about {target}% of cards.")
        else:
            source = (f"A <b>rough estimate</b> from Anki's review history "
                      f"({r.get('cards_seen', r['cards'])} cards). That history "
                      "times the answer side too, so an allowance is taken off, "
                      "and if you've been reviewing with a timer it partly "
                      "reflects that timer. "
                      + (f"Once aSFM has watched {pace.MIN_CALIBRATION} cards "
                         "you reveal yourself, calibrating again uses those "
                         "instead." if pace.learning(self.cfg) else
                         "Turn on “Learn my pace” for a measured fit instead."))
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
        if measured:
            self._fill_extras(pace.fit_kinds(self.cfg, r))

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
                    f"needs {info['need']} cards ({info['cards']} so far)")
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


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Adaptive Speed Focus — Settings")
        self.setMinimumSize(720, 520)
        self.resize(880, 640)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 12)

        # Each tab scrolls on its own, so the header and the preview stay put.
        self.panel = _Panel()
        layout.addWidget(self.panel, 1)

        footer = QHBoxLayout()
        links = QLabel(
            f"<a href='{_ANKIWEB_URL}'>Enjoying aSFM? Rate it on AnkiWeb</a>"
            f" · <a href='{_ISSUES_URL}'>Report a problem</a>")
        links.setTextFormat(Qt.TextFormat.RichText)
        links.setOpenExternalLinks(True)
        footer.addWidget(links)
        footer.addStretch(1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)

    def _on_save(self):
        self.panel.save()
        self.accept()


def open_settings() -> None:
    SettingsDialog(mw).exec()
