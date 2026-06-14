"""AnkiBlitz Core settings — one tabbed window.

A single ``QDialog`` with a master switch plus one tab per tool (Profiles, Blitz,
Focus, Quick Start, Pomodoro, Music). Each tab is a self-contained panel that
reads its own config section on open and writes only that section on save, so the
tools stay decoupled (mirrors the namespaced config in config.py). Settings are
read live per card, so saving takes effect on the next card with no extra refresh.
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
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    Qt,
)
from aqt.utils import tooltip

from .config import get_section, save_section, suite_enabled, set_suite_enabled
from .engine import presets

_CHECKED = Qt.CheckState.Checked
_UNCHECKED = Qt.CheckState.Unchecked


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


def _scroll(inner: QWidget) -> QScrollArea:
    """Wrap a tall panel so dense tabs stay usable on small screens."""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area


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

        layout.addWidget(pbox)

        # --- Break screen elements (hide any to keep the screen calm) ---
        bbox = QGroupBox("Break screen elements")
        bl = QVBoxLayout(bbox)
        bl.addWidget(_hint("Show or hide each part of the break screen."))
        self.br_timeline = QCheckBox("Timeline (past · now · upcoming + long break)")
        self.br_journal = QCheckBox("Break journal")
        self.br_focus = QCheckBox("Focus rating (1–5)")
        self.br_tips = QCheckBox("Micro-break suggestions")
        self.br_browser = QCheckBox("In-app browser button")
        self.br_addkg = QCheckBox("Add KG button (Ankisstant)")
        self.br_extend = QCheckBox("+5 min extend button")
        self._break_toggles = [
            (self.br_timeline, "break_show_timeline"),
            (self.br_journal, "break_show_journal"),
            (self.br_focus, "break_show_focus_rating"),
            (self.br_tips, "break_show_tips"),
            (self.br_browser, "break_show_browser"),
            (self.br_addkg, "break_show_add_kg"),
            (self.br_extend, "break_allow_extend"),
        ]
        for cb, key in self._break_toggles:
            cb.setChecked(bool(po.get(key, True)))
            bl.addWidget(cb)
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
            "daily_goal": self.daily_goal.value(),
            "end_summary": self.end_summary.isChecked(),
            "carry_forward": self.carry_forward.isChecked(),
        })
        for cb, key in self._break_toggles:
            po[key] = cb.isChecked()
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
        for w in (self.show_bar, self.show_counter, self.show_elapsed):
            dnl.addWidget(w)
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
            "show_card_counter": self.show_counter.isChecked(),
            "show_elapsed_time": self.show_elapsed.isChecked(),
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
            "A profile flips the <i>feel</i> of a session in one click: Focus "
            "Lock, the near-end nudge, and the anti-pressure / progress display. "
            "It deliberately leaves alone how you launch a session (Blitz mode / "
            "target, Pomodoro blocks — you pick those each time), the music, and "
            "your note-type / deck exclusions. Built-ins: <b>Default</b> (everyday), "
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
        self.setWindowTitle("AnkiBlitz Core Settings")
        self.setMinimumSize(480, 560)

        layout = QVBoxLayout(self)

        master_row = QHBoxLayout()
        self.master = QCheckBox("Enable AnkiBlitz Core")
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
        self.sprint = SprintPanel()
        self.focus = FocusPanel()
        self.quick_start = QuickStartPanel()
        self.pomodoro = PomodoroPanel()
        self.music = MusicPanel()
        # Profiles front-and-centre, then the per-feature tabs.
        self.tabs.addTab(_scroll(self.presets), "Profiles")
        self.tabs.addTab(_scroll(self.sprint), "Blitz")
        self.tabs.addTab(_scroll(self.focus), "Focus")
        self.tabs.addTab(_scroll(self.quick_start), "Quick Start")
        self.tabs.addTab(_scroll(self.pomodoro), "Pomodoro")
        self.tabs.addTab(_scroll(self.music), "Music")
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
        self.sprint.save()
        self.focus.save()
        self.quick_start.save()
        self.pomodoro.save()
        self.music.save()

    def _on_save(self):
        self._save_open_panels()
        self.accept()

    def _applied_and_close(self, name):
        """A profile was applied from the Profiles tab: close WITHOUT running
        _on_save, so the now-stale feature panels can't overwrite the profile."""
        tooltip(f"Switched to “{name}”.")
        self.accept()


def open_settings() -> None:
    SettingsDialog(mw).exec()
