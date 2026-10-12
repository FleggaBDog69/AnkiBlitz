"""First-run welcome for aSFM: what it does, and a one-click calibration.

Shown once, shortly after the first profile load with ``show_welcome`` still
true, then never again unless reopened from Tools ▸ Adaptive Speed Focus.
Existing users get it once on the update that adds the key — on purpose, since
calibration is new to them too.

Calibration reuses the settings dialog's ``_CalibrateDialog``. The difference
is that Apply here saves straight away: there is no Settings dialog behind it
whose Save button would otherwise do that.
"""

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QTimer,
    QVBoxLayout,
)

from .config import get_config, save_config
from .engine import pace


def _label(html: str) -> QLabel:
    lbl = QLabel(html)
    lbl.setWordWrap(True)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    return lbl


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Welcome to Adaptive Speed Focus")
        self.setMinimumWidth(480)
        cfg = get_config()
        key = str(cfg.get("pause_key") or "p").upper()
        layout = QVBoxLayout(self)

        layout.addWidget(_label(
            "<h3>aSFM is on</h3>"
            "When a question shows, aSFM waits a delay based on how long the "
            "card is and how hard it is for you, then shows the answer. "
            "<b>It never grades the card</b>, so you still press the button "
            "yourself.<br><br>"
            f"• Need longer on a card? Press <b>{key}</b> or click "
            "<b>More time</b> to hold the timer, and do the same again to carry on.<br>"
            "• A thin bar at the top counts down to the reveal.<br>"
            "• Everything is under <b>Tools ▸ Adaptive Speed Focus</b>."))

        self.on_new = QCheckBox("Also run the timer on new cards")
        self.on_new.setChecked(bool(cfg["enable_on_new"]))
        layout.addWidget(self.on_new)
        layout.addWidget(_label(
            "<span style='color: gray; font-size: 11px;'>Off by default: new "
            "cards usually need time to read, not just to recall. Leave this "
            "off and the timer starts on cards you've already seen.</span>"))

        layout.addWidget(_label("<h3>Tune it to your speed</h3>"
                                "aSFM can set its timings from your own review "
                                "history, so the answer shows just after you'd "
                                "usually have got there. It takes a few seconds, "
                                "and you can see the numbers before anything changes."))
        row = QHBoxLayout()
        self.calibrate_btn = QPushButton("Calibrate to my speed…")
        self.calibrate_btn.clicked.connect(self._on_calibrate)
        row.addWidget(self.calibrate_btn)
        row.addStretch(1)
        layout.addLayout(row)
        self.calib_result = _label("")
        layout.addWidget(self.calib_result)
        if cfg["auto_tune_enabled"]:
            layout.addWidget(_label(
                "<span style='color: gray; font-size: 11px;'>Skipping this is "
                "fine too: aSFM also adjusts itself a little as you review.</span>"))

        buttons = QDialogButtonBox()
        settings_btn = buttons.addButton(
            "Open Settings…", QDialogButtonBox.ButtonRole.ActionRole)
        settings_btn.clicked.connect(self._on_settings)
        done = buttons.addButton("Done", QDialogButtonBox.ButtonRole.AcceptRole)
        done.setDefault(True)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _save_on_new(self) -> None:
        cfg = get_config()
        if bool(cfg["enable_on_new"]) != self.on_new.isChecked():
            cfg["enable_on_new"] = self.on_new.isChecked()
            save_config(cfg)

    def _on_calibrate(self) -> None:
        from .settings import _CalibrateDialog

        dlg = _CalibrateDialog(self, get_config(), saves_directly=True)
        if not (dlg.exec() and dlg.result_values):
            return
        r = dlg.result_values
        cfg = get_config()
        cfg["base_seconds"] = round(r["base_seconds"], 2)
        cfg["seconds_per_word"] = round(r["seconds_per_word"], 2)
        if float(cfg["seconds_per_answer_word"]) > 0:
            cfg["seconds_per_answer_word"] = round(r["seconds_per_answer_word"], 2)
        save_config(cfg)
        # The new timings already reflect your speed; don't apply it twice.
        pace.reset_pace()
        self.calib_result.setText(
            f"✓ Saved: base {cfg['base_seconds']:.2f} s, "
            f"{cfg['seconds_per_word']:.2f} s per word.")
        self.calibrate_btn.setText("Calibrate again…")

    def _on_settings(self) -> None:
        from .settings import open_settings

        self._save_on_new()
        self.accept()
        open_settings()

    def accept(self) -> None:
        self._save_on_new()
        super().accept()

    def done(self, r) -> None:
        # Closing the window any way counts as having seen it.
        _mark_shown()
        super().done(r)


def _mark_shown() -> None:
    cfg = get_config()
    if cfg.get("show_welcome"):
        cfg["show_welcome"] = False
        save_config(cfg)


def open_welcome() -> None:
    WelcomeDialog(mw).exec()


def maybe_show_welcome() -> None:
    """Called on profile open. Waits a moment so it lands on the main window
    rather than racing Anki's own start-up dialogs."""
    if not get_config().get("show_welcome"):
        return

    def show():
        if mw.col is None or not get_config().get("show_welcome"):
            return
        open_welcome()

    QTimer.singleShot(1500, show)
