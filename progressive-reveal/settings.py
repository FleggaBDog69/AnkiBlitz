"""Progressive Word Reveal settings — one dialog.

The full reveal option set: speed, mode, chunk size, reveal-all key, optional
TTS-sync, and per-note-type / per-deck exclusions. A live preview shows the time
to fully reveal questions of a couple of lengths. Read live per card.
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
    QGroupBox,
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

from .config import get_config, save_config
from .engine import tts_sync

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked
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
        layout = QVBoxLayout(self)

        self.enabled = QCheckBox("Enable progressive word reveal")
        self.enabled.setChecked(bool(cfg.get("enabled", True)))
        layout.addWidget(self.enabled)

        self.reveal_on_answer = QCheckBox("Also reveal on the answer side")
        self.reveal_on_answer.setChecked(bool(cfg.get("reveal_on_answer", False)))
        layout.addWidget(self.reveal_on_answer)
        layout.addWidget(_hint(
            "Fades the question in at a fixed reading rate, so longer questions take "
            "proportionally longer. Click or press the reveal key to show everything "
            "at once. (Left unticked, the answer side shows at once.)"))

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

        def _toggle_chunk():
            self.chunk_words.setEnabled(self.mode.currentData() == "chunks")
        self.mode.currentIndexChanged.connect(_toggle_chunk)
        _toggle_chunk()

        speed_row = QHBoxLayout()
        speed_row.addLayout(form, 1)
        side = QVBoxLayout()
        side.addWidget(QLabel("<b>Preview</b>"))
        side.addWidget(_hint("Time to fully reveal the question:"))
        self.preview = QLabel()
        self.preview.setTextFormat(Qt.TextFormat.RichText)
        side.addWidget(self.preview)
        side.addStretch(1)
        speed_row.addLayout(side, 1)
        layout.addLayout(speed_row)

        layout.addWidget(self.stop_audio)
        layout.addWidget(_hint(
            "Revealing everything (key or click) also cuts the card's TTS / "
            "[sound:] playback — you've read it, so the voice reading it to you "
            "is just noise. The audio stops rather than pausing; the next card "
            "plays normally."))

        self.wps.valueChanged.connect(self._update_preview)
        self._update_preview()

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
        layout.addStretch(1)

    def _build_tts_group(self, cfg):
        box = QGroupBox("TTS sync")
        v = QVBoxLayout(box)
        v.addWidget(_hint(
            "Keep the word reveal in step with native Anki / AnKing {{tts}} "
            "playback. On macOS the voice runs at 170 × speed words/min, so the "
            "matching reveal rate is exact — no guessing."))

        self.tts_readout = QLabel()
        self.tts_readout.setTextFormat(Qt.TextFormat.RichText)
        self.tts_readout.setWordWrap(True)
        v.addWidget(self.tts_readout)
        self.wps.valueChanged.connect(self._update_tts_readout)
        self._update_tts_readout()

        found = tts_sync.scan_collection_tts()
        if found:
            parts = []
            for name, speed, active in found:
                wps = tts_sync.wps_for_speed(speed, self._base_wpm)
                tag = "" if active else " <i>(disabled)</i>"
                parts.append(f"&bull; {name}: speed {speed:g} → {wps:.1f} w/s{tag}")
            detected = QLabel("<b>Detected in your collection:</b><br>" + "<br>".join(parts))
            detected.setTextFormat(Qt.TextFormat.RichText)
            detected.setWordWrap(True)
            v.addWidget(detected)

        self.tts_auto_match = QCheckBox("Auto-match reveal speed to each card's TTS")
        self.tts_auto_match.setChecked(bool(cfg.get("tts_auto_match", True)))
        v.addWidget(self.tts_auto_match)
        v.addWidget(_hint(
            "When on, any card with active TTS overrides the reading speed above so "
            "the words finish in step with the voice. Cards without TTS (e.g. "
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
        rows = ""
        for words in _PREVIEW_WORDS:
            rows += (
                f"<tr><td>{words} words</td>"
                f"<td align='center'>{words / wps:.1f} s</td></tr>")
        self.preview.setText(
            "<table border='1' cellspacing='0' cellpadding='5'>"
            "<tr><th>Card</th><th>Reveal time</th></tr>"
            f"{rows}</table>")

    def save(self):
        cfg = get_config()
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
        save_config(cfg)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Progressive Word Reveal — Settings")
        self.setMinimumSize(520, 560)
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
