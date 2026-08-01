"""Adaptive Speed Focus settings — one dialog.

A single ``QDialog`` exposing the adaptive auto-reveal knobs, with a live preview
table that always agrees with the runtime (both call ``adaptive.delay_for``).
Settings are read live per card, so saving takes effect on the next card.
"""

from aqt import mw
from aqt.qt import (
    QCheckBox,
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
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .config import get_config, save_config, enabled, set_enabled
from .engine import adaptive

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked

# Representative cards for the preview, mapped to adaptive.delay_for primitives.
_PREVIEW_CARDS = [
    ("Easy", dict(ease=2500, lapses=0, reps=10, unfamiliar=False, is_new=False, difficulty=3.5)),
    ("Hard", dict(ease=1700, lapses=5, reps=15, unfamiliar=False, is_new=False, difficulty=8.5)),
    ("New", dict(ease=0, lapses=0, reps=0, unfamiliar=True, is_new=True, difficulty=None)),
]
_PREVIEW_WORDS = (15, 25)


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


def _hline():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class _KeyCaptureEdit(QLineEdit):
    """Read-only field that records the next printable key the user presses."""

    def __init__(self, key, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaxLength(1)
        self.setFixedWidth(140)
        self.setPlaceholderText("click, then press a key")
        self.setText(str(key or ""))

    def keyPressEvent(self, event):
        text = event.text()
        if text and text.strip() and len(text) == 1:
            self.setText(text)

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
        self.list.setMinimumHeight(120)
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
    def __init__(self):
        super().__init__()
        cfg = get_config()

        outer = QHBoxLayout(self)
        layout = QVBoxLayout()
        outer.addLayout(layout, 3)
        side = QVBoxLayout()
        outer.addLayout(side, 2)

        self.enabled = QCheckBox("Enable adaptive auto-reveal")
        self.enabled.setChecked(bool(cfg.get("enabled", True)))
        layout.addWidget(self.enabled)
        layout.addWidget(_hint(
            "After the question shows, aSFM waits a computed delay, then shows the "
            "answer automatically. It never grades the card for you — you still "
            "press the button."))

        form = QFormLayout()
        self.base = _double(0.0, 60.0, 0.5, 1, " s")
        self.base.setValue(float(cfg.get("base_seconds", 3.0)))
        form.addRow("Base time:", self.base)

        self.per_word = _double(0.0, 5.0, 0.05, 2, " s")
        self.per_word.setValue(float(cfg.get("seconds_per_word", 0.30)))
        form.addRow("Per word:", self.per_word)

        self.min_delay = _double(0.0, 120.0, 0.5, 1, " s")
        self.min_delay.setValue(float(cfg.get("min_delay_seconds", 2.0)))
        form.addRow("Minimum delay:", self.min_delay)

        self.max_delay = _double(0.0, 300.0, 1.0, 1, " s")
        self.max_delay.setValue(float(cfg.get("max_delay_seconds", 20.0)))
        form.addRow("Maximum delay:", self.max_delay)
        layout.addLayout(form)

        layout.addWidget(_hline())
        layout.addWidget(QLabel("<b>Modifiers (weighted)</b>"))
        mod = QFormLayout()
        self.unfamiliar = _double(1.0, 5.0, 0.1, 2, "×")
        self.unfamiliar.setValue(float(cfg.get("unfamiliar_multiplier", 1.2)))
        mod.addRow("Learning / relearning cards:", self.unfamiliar)

        self.new_mult = _double(1.0, 5.0, 0.1, 2, "×")
        self.new_mult.setValue(float(cfg.get("new_multiplier", 1.5)))
        self.enable_on_new = QCheckBox("Run on new cards")
        self.enable_on_new.setChecked(bool(cfg.get("enable_on_new", True)))
        new_row = QHBoxLayout()
        new_row.setContentsMargins(0, 0, 0, 0)
        new_row.addWidget(self.new_mult)
        new_row.addWidget(self.enable_on_new)
        new_row.addStretch(1)
        mod.addRow("New cards:", new_row)

        self.difficulty = _double(0.0, 1.0, 0.05, 2, "")
        self.difficulty.setValue(float(cfg.get("difficulty_weight", 0.20)))
        mod.addRow("Difficulty weight:", self.difficulty)
        layout.addLayout(mod)
        layout.addWidget(_hint(
            "Time = (base + per-word × words). New cards multiply by the new-card "
            "modifier; learning/relearning cards by the learning modifier. The "
            "card’s FSRS difficulty then nudges the delay by at most ± the "
            "difficulty weight (0 = ignore difficulty). The result is clamped "
            "between the minimum and maximum delay. Untick “Run on new cards” to "
            "leave new cards with no auto-reveal timer at all."))

        layout.addWidget(_hline())
        self.show_countdown = QCheckBox("Show countdown bar while waiting")
        self.show_countdown.setChecked(bool(cfg.get("show_countdown", True)))
        layout.addWidget(self.show_countdown)

        self.warning_sound = QCheckBox("Play a warning sound before revealing")
        self.warning_sound.setChecked(bool(cfg.get("warning_sound", True)))
        layout.addWidget(self.warning_sound)

        warn_form = QFormLayout()
        self.warn_pct = QSpinBox()
        self.warn_pct.setRange(5, 95)
        self.warn_pct.setSuffix(" %")
        self.warn_pct.setValue(int(cfg.get("warning_at_percent", 75)))
        warn_form.addRow("Warn after:", self.warn_pct)
        layout.addLayout(warn_form)
        layout.addWidget(_hint(
            "The alert plays once this share of the auto-reveal delay has elapsed — "
            "e.g. 75% leaves the final 25% as a heads-up before the answer shows. "
            "(Replace sounds/alert.mp3, or drop alert.mp3 in user_files, to change "
            "the sound.)"))

        layout.addWidget(_hline())
        self.pause_key_enabled = QCheckBox(
            "Pause key: hold the timer on the current card")
        self.pause_key_enabled.setChecked(bool(cfg.get("pause_key_enabled", True)))
        layout.addWidget(self.pause_key_enabled)

        pause_form = QFormLayout()
        self.pause_key = _KeyCaptureEdit(cfg.get("pause_key", "p"))
        pause_form.addRow("Pause key:", self.pause_key)
        layout.addLayout(pause_form)
        self.pause_key_enabled.toggled.connect(self.pause_key.setEnabled)
        self.pause_key.setEnabled(self.pause_key_enabled.isChecked())
        layout.addWidget(_hint(
            "Press it to freeze the auto-reveal countdown (and its warning) so "
            "you can sit on a card; press again to pick up where it stopped. The "
            "pause sticks across cards, and every card it applies to says so on "
            "screen.\n\n"
            "If you also run Progressive Word Reveal, give the two different "
            "keys — they both default to “p”, and as separate add-ons they can't "
            "take turns on one press the way they do inside AnkiBlitz."))

        layout.addWidget(_hline())
        layout.addWidget(QLabel("Skip the auto-reveal timer for these (review normally):"))
        notetypes, decks = _collect_names()
        self.nt_list = _FilterList("Note types", notetypes, cfg.get("excluded_note_types", []))
        self.deck_list = _FilterList(
            "Decks (a parent also covers its subdecks)", decks, cfg.get("excluded_decks", []))
        sf_lists = QHBoxLayout()
        sf_lists.addWidget(self.nt_list)
        sf_lists.addWidget(self.deck_list)
        layout.addLayout(sf_lists)

        layout.addWidget(_hline())
        self.fixed_enabled = QCheckBox("Picture cards: use a set time (ignore word count)")
        self.fixed_enabled.setChecked(bool(cfg.get("fixed_time_enabled", True)))
        layout.addWidget(self.fixed_enabled)
        fixed_form = QFormLayout()
        self.fixed_base = _double(0.5, 60.0, 0.5, 1, " s")
        self.fixed_base.setValue(float(cfg.get("fixed_time_base_seconds", 6.0)))
        fixed_form.addRow("Set time:", self.fixed_base)
        layout.addLayout(fixed_form)
        layout.addWidget(_hint(
            "For image / visual cards there's nothing to read, so word count is "
            "meaningless. Cards matching the note types or decks below get this set "
            "time instead, with only the difficulty weight as a modifier."))
        self.fixed_nt_list = _FilterList(
            "Picture note types", notetypes, cfg.get("fixed_time_note_types", []))
        self.fixed_deck_list = _FilterList(
            "Picture decks (a parent also covers its subdecks)",
            decks, cfg.get("fixed_time_decks", []))
        fixed_lists = QHBoxLayout()
        fixed_lists.addWidget(self.fixed_nt_list)
        fixed_lists.addWidget(self.fixed_deck_list)
        layout.addLayout(fixed_lists)
        layout.addStretch(1)

        side.addWidget(QLabel("<b>Preview</b>"))
        side.addWidget(_hint("Seconds until the answer auto-shows:"))
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.preview)
        side.addWidget(_hint(
            "Easy = a familiar review card; Hard = a lapsed card (low ease, several "
            "lapses). Updates live as you change the knobs."))
        side.addStretch(1)

        for w in (self.base, self.per_word, self.min_delay, self.max_delay,
                  self.unfamiliar, self.new_mult, self.difficulty):
            w.valueChanged.connect(self._update_preview)
        self._update_preview()

    def _current_cfg(self):
        return {
            "base_seconds": self.base.value(),
            "seconds_per_word": self.per_word.value(),
            "min_delay_seconds": self.min_delay.value(),
            "max_delay_seconds": self.max_delay.value(),
            "unfamiliar_multiplier": self.unfamiliar.value(),
            "new_multiplier": self.new_mult.value(),
            "difficulty_weight": self.difficulty.value(),
        }

    def _update_preview(self):
        cfg = self._current_cfg()
        header = "<tr><th>Card</th>" + "".join(
            f"<th>{name}</th>" for name, _ in _PREVIEW_CARDS) + "</tr>"
        rows = ""
        for words in _PREVIEW_WORDS:
            cells = "".join(
                f"<td align='center'>{adaptive.delay_for(cfg, words=words, **card):.1f} s</td>"
                for _, card in _PREVIEW_CARDS
            )
            rows += f"<tr><td>{words} words</td>{cells}</tr>"
        self.preview.setText(
            "<table border='1' cellspacing='0' cellpadding='5'>"
            f"{header}{rows}</table>")

    def save(self):
        cfg = get_config()
        cfg.update({
            "enabled": self.enabled.isChecked(),
            "base_seconds": round(self.base.value(), 2),
            "seconds_per_word": round(self.per_word.value(), 2),
            "min_delay_seconds": round(self.min_delay.value(), 2),
            "max_delay_seconds": round(self.max_delay.value(), 2),
            "unfamiliar_multiplier": round(self.unfamiliar.value(), 2),
            "new_multiplier": round(self.new_mult.value(), 2),
            "enable_on_new": self.enable_on_new.isChecked(),
            "difficulty_weight": round(self.difficulty.value(), 2),
            "show_countdown": self.show_countdown.isChecked(),
            "warning_sound": self.warning_sound.isChecked(),
            "warning_at_percent": self.warn_pct.value(),
            "pause_key_enabled": self.pause_key_enabled.isChecked(),
            "pause_key": self.pause_key.key_value(),
            "excluded_note_types": self.nt_list.checked(),
            "excluded_decks": self.deck_list.checked(),
            "fixed_time_enabled": self.fixed_enabled.isChecked(),
            "fixed_time_base_seconds": round(self.fixed_base.value(), 2),
            "fixed_time_note_types": self.fixed_nt_list.checked(),
            "fixed_time_decks": self.fixed_deck_list.checked(),
        })
        save_config(cfg)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Adaptive Speed Focus — Settings")
        self.setMinimumSize(560, 560)
        layout = QVBoxLayout(self)

        self.panel = _Panel()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(self.panel)
        layout.addWidget(area)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        self.panel.save()
        self.accept()


def open_settings() -> None:
    SettingsDialog(mw).exec()
