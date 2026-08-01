"""First-run wizard.

Shown once per install (gated by config.first_run_pending / mark_first_run_done).
Two jobs: warn the user to disable add-ons that double up with AnkiBlitz — Speed
Focus Mode (SFM) above all — and let them set the progressive-reveal speed before
they start. Standalone-safe: every Qt touch is guarded and any failure still
marks the run done so it can't nag on every restart.
"""

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, Qt,
)

from .. import config


def _open_addons() -> None:
    """Open Tools ▸ Add-ons so the user can disable clashers. Best-effort."""
    try:
        mw.onAddonManager()
    except Exception:
        try:
            from aqt.addons import AddonsDialog
            AddonsDialog(mw.addonManager).exec()
        except Exception:
            pass


def _build_dialog() -> QDialog:
    wr = config.get_section("word_reveal")

    dlg = QDialog(mw)
    dlg.setWindowTitle("Welcome to AnkiBlitz")
    dlg.setMinimumWidth(440)
    lay = QVBoxLayout(dlg)

    head = QLabel("AnkiBlitz")
    head.setStyleSheet("font-size: 20px; font-weight: 700; margin-bottom: 2px;")
    lay.addWidget(head)

    intro = QLabel(
        "Adaptive auto-reveal, progressive word reveal, and timed Blitz "
        "sessions — all in one. A couple of things before you start:"
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("color: gray; font-size: 12px; margin-bottom: 8px;")
    lay.addWidget(intro)

    # --- clash warning ---
    clash = QLabel(
        "<b>Disable add-ons that do the same job</b> so timers don't double up — "
        "especially:<br>"
        "&nbsp;&nbsp;• <b>Speed Focus Mode (SFM)</b><br>"
        "&nbsp;&nbsp;• Progressive Word Reveal<br>"
        "&nbsp;&nbsp;• Sprint Mode<br>"
        "&nbsp;&nbsp;• <b>SynapsePro</b> — keep it, but turn <i>its</i> Pomodoro "
        "off in its settings if you want to use AnkiBlitz's. AnkiBlitz already "
        "steps aside for SynapsePro's music player."
    )
    clash.setWordWrap(True)
    clash.setStyleSheet("font-size: 12px; margin-bottom: 6px;")
    lay.addWidget(clash)

    addons_row = QHBoxLayout()
    addons_btn = QPushButton("Open Add-ons…")
    addons_btn.clicked.connect(_open_addons)
    addons_row.addWidget(addons_btn)
    addons_row.addStretch(1)
    lay.addLayout(addons_row)

    note = QLabel("Disable them in Tools ▸ Add-ons, then restart Anki.")
    note.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 10px;")
    lay.addWidget(note)

    # --- progressive-reveal speed ---
    speed_lbl = QLabel("<b>Progressive reveal speed</b>")
    speed_lbl.setStyleSheet("font-size: 12px;")
    lay.addWidget(speed_lbl)

    speed_row = QHBoxLayout()
    spin = QDoubleSpinBox()
    spin.setRange(1.0, 20.0)
    spin.setSingleStep(0.5)
    spin.setDecimals(1)
    spin.setSuffix(" words/sec")
    spin.setValue(float(wr.get("words_per_second", 6.0)))
    speed_row.addWidget(spin)
    speed_row.addStretch(1)
    lay.addLayout(speed_row)

    speed_hint = QLabel(
        "How fast the question fades in — lower is slower/calmer, higher is "
        "snappier. You can change this any time in Tools ▸ AnkiBlitz ▸ Settings."
    )
    speed_hint.setWordWrap(True)
    speed_hint.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 8px;")
    lay.addWidget(speed_hint)

    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Get started")
    bb.accepted.connect(dlg.accept)
    lay.addWidget(bb)

    dlg._fs_spin = spin  # keep a handle for save
    return dlg


def maybe_show_first_run_wizard() -> None:
    """Show the wizard once per install, then persist the chosen reveal speed.
    Best-effort: any failure is swallowed, and the run is marked done regardless
    so a display hiccup doesn't nag on every restart."""
    try:
        if not config.first_run_pending():
            return
        dlg = _build_dialog()
        dlg.exec()
        try:
            wr = config.get_section("word_reveal")
            wr["words_per_second"] = float(dlg._fs_spin.value())
            config.save_section("word_reveal", wr)  # additive: only this section
        except Exception:
            pass
    except Exception:
        pass
    finally:
        try:
            config.mark_first_run_done()
        except Exception:
            pass
