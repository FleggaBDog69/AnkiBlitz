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
    QHBoxLayout,
    QLabel,
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
_PREVIEW_CARDS = [
    ("Easy", dict(ease=2500, lapses=0, reps=10, unfamiliar=False, is_new=False, difficulty=3.5)),
    ("Hard", dict(ease=1700, lapses=5, reps=15, unfamiliar=False, is_new=False, difficulty=8.5)),
    ("New", dict(ease=0, lapses=0, reps=0, unfamiliar=True, is_new=True, difficulty=None)),
]
_PREVIEW_WORDS = (15, 25)
_ANKIWEB_URL = "https://ankiweb.net/shared/info/1148593203"
_ISSUES_URL = "https://github.com/FleggaBDog69/AnkiBlitz/issues"
_PREVIEW_ANSWERS = (5, 40)   # answer-side words, for the answer-length rows


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

        pace_row = QHBoxLayout()
        self.pace_label = QLabel()
        pace_row.addWidget(self.pace_label, 1)
        self.reset_pace_btn = QPushButton("Reset")
        self.reset_pace_btn.clicked.connect(self._on_reset_pace)
        pace_row.addWidget(self.reset_pace_btn)
        layout.addLayout(pace_row)

        calib_row = QHBoxLayout()
        calibrate = QPushButton("Calibrate from my reviews…")
        calibrate.clicked.connect(self._on_calibrate)
        calib_row.addWidget(calibrate)
        calib_row.addStretch(1)
        layout.addLayout(calib_row)
        layout.addWidget(_hint(
            "“Timer beats me on” is how often the answer should show before you "
            "reveal it. Auto-tune adjusts gently: about −0.5% when you reveal "
            "first, +5% on a timeout or More time, and never more than 15% "
            "quicker. Calibrate suggests timings from your own reveals (a rough "
            "estimate from review history at first); nothing changes until you "
            "apply and save. Saved per profile, numbers only."))

        self.sessions_title = _section("Recent sessions")
        layout.addWidget(self.sessions_title)
        self.sessions_label = QLabel()
        self.sessions_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.sessions_label)
        layout.addStretch(1)
        self._pace_reset_pending = False
        self.auto_tune.toggled.connect(self._refresh_pace)

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
        card.setFixedWidth(300)
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

    def _preview_rows(self):
        """(label, question words, answer words) per preview row. The answer
        column only appears while the answer-length term is on — otherwise every
        pair of rows would print the same number twice."""
        if self.per_answer_word.value() > 0:
            return [(f"{q} + {a} words", q, a)
                    for q in _PREVIEW_WORDS for a in _PREVIEW_ANSWERS]
        return [(f"{q} words", q, 0) for q in _PREVIEW_WORDS]

    def _update_preview(self):
        cfg = self._current_cfg()
        p = self._preview_pace()
        # No grid: a quiet header and banded rows, in the theme's own colours
        # so it reads the same in light and dark mode.
        pal = self.palette()
        band = pal.color(QPalette.ColorRole.AlternateBase).name()
        rule = pal.color(QPalette.ColorRole.Mid).name()
        th = (f"style='color: gray; font-size: 11px; font-weight: 600;"
              f" border-bottom: 1px solid {rule};'")
        header = f"<tr><th align='left' {th}>Words</th>" + "".join(
            f"<th align='right' {th}>{name}</th>" for name, _ in _PREVIEW_CARDS) + "</tr>"
        rows = ""
        new_on = self.enable_on_new.isChecked()

        def cell(card, words, answer_words):
            if card["is_new"] and not new_on:
                return "<td align='right' style='color: gray;'>off</td>"
            d = adaptive.delay_for(cfg, words=words, answer_words=answer_words,
                                   pace=p, **card)
            return f"<td align='right'><b>{d:.1f}</b> s</td>"

        for i, (label, words, answer_words) in enumerate(self._preview_rows()):
            cells = "".join(cell(card, words, answer_words)
                            for _, card in _PREVIEW_CARDS)
            bg = f" bgcolor='{band}'" if i % 2 else ""
            rows += f"<tr{bg}><td>{label}</td>{cells}</tr>"
        self.preview_hint.setText(
            ("Rows are question + answer words. " if self.per_answer_word.value() > 0
             else "Rows are question words. ")
            + "Easy = a familiar review card; Hard = a lapsed card."
            + ("" if new_on else " New cards are off (see “Run on new cards”).")
            + (f" Includes your learned pace ({p:.2f}×)." if abs(p - 1.0) >= 0.005
               else ""))
        self.preview.setText(
            "<table width='100%' cellspacing='0' cellpadding='6'>"
            f"{header}{rows}</table>")

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
        if self._pace_reset_pending:
            pace.reset_pace()

    # ----- learn my pace -----

    def _preview_pace(self) -> float:
        if not self.auto_tune.isChecked() or self._pace_reset_pending:
            return 1.0
        return pace.current({"auto_tune_enabled": True})

    def _refresh_pace(self, *_):
        data = pace.summary()
        n = int(data.get("pace_cards", 0))
        if self._pace_reset_pending:
            text = "Current pace: 1.00× (resets when you save)"
        elif not self.auto_tune.isChecked():
            text = f"Auto-tune off. Learned pace {float(data.get('pace', 1.0)):.2f}× is kept."
        elif n == 0:
            text = "Current pace: 1.00× (nothing learned yet)"
        else:
            text = (f"Current pace: {float(data.get('pace', 1.0)):.2f}× "
                    f"· learned from {n} cards")
        self.pace_label.setText(text)
        self._refresh_sessions(data)
        self._update_preview()

    def _refresh_sessions(self, data):
        rows = list(data.get("sessions", []))[-5:]
        live = pace.session_so_far()
        if live and live["cards"]:
            t = sorted(live["reveal_s"])
            rows.append({"date": "now", "cards": live["cards"], "self": live["self"],
                         "median_s": t[len(t) // 2] if t else None, "pace": None})
        # Hidden while empty, so a blank label doesn't leave a gap in the panel.
        self.sessions_label.setVisible(bool(rows))
        self.sessions_title.setVisible(bool(rows))
        if not rows:
            self.sessions_label.setText("")
            return
        body = ""
        for r in reversed(rows):
            share = f"{round(100 * r['self'] / r['cards'])}%" if r["cards"] else "–"
            med = f"{r['median_s']:.1f} s" if r.get("median_s") else "–"
            pc = f"{r['pace']:.2f}×" if r.get("pace") else "–"
            body += (f"<tr><td>{r['date']}</td><td align='right'>{r['cards']}</td>"
                     f"<td align='right'>{share}</td><td align='right'>{med}</td>"
                     f"<td align='right'>{pc}</td></tr>")
        self.sessions_label.setText(
            "<table cellspacing='0' cellpadding='3'>"
            "<tr><th align='left'>Session</th><th>Cards</th><th>You revealed</th>"
            "<th>Median</th><th>Pace</th></tr>" + body + "</table>")

    def _on_reset_pace(self):
        self._pace_reset_pending = True
        self._refresh_pace()

    def _on_calibrate(self):
        # The whole config, not just the timing knobs: calibration has to skip
        # picture cards the same way the timer does.
        cfg = {**get_config(), **self._current_cfg(),
               "target_timer_wins_percent": self.target.value()}
        dlg = _CalibrateDialog(self, cfg)
        if dlg.exec() and dlg.result_values:
            r = dlg.result_values
            self.base.setValue(r["base_seconds"])
            self.per_word.setValue(r["seconds_per_word"])
            if self.per_answer_word.value() > 0:
                self.per_answer_word.setValue(r["seconds_per_answer_word"])
            # The new values already reflect your pace, so the multiplier
            # starts again from 1 rather than being applied twice.
            self._pace_reset_pending = True
            self._refresh_pace()


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
        layout = QVBoxLayout(self)
        self.body = QLabel("Working…")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.body)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_btn = self.buttons.addButton(
            "Apply", QDialogButtonBox.ButtonRole.AcceptRole)
        self.apply_btn.setEnabled(False)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        if pace.reveal_data_ready():
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
                      "reflects that timer. Once aSFM has watched "
                      f"{pace.MIN_CALIBRATION} cards you reveal yourself, "
                      "calibrating again uses those instead.")
        if self.saves_directly:
            outro = ("Apply saves these and resets the learned pace to 1.00×. "
                     "You can change them any time in Settings.")
        else:
            outro = ("Apply fills these into Settings and resets the learned "
                     "pace to 1.00×. Nothing changes until you save.")
        self.body.setText(
            source + "<br><br><table cellspacing='0' cellpadding='4'>"
            "<tr><th></th><th>Now</th><th>Suggested</th></tr>" + table +
            "</table><br>" + outro)
        self.result_values = r
        self.apply_btn.setEnabled(True)


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
