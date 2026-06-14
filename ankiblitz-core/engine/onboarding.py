"""First-run wizard.

Shown once per install (gated by config.first_run_pending / mark_first_run_done).
Two jobs: introduce AnkiBlitz Core as a session-discipline suite (Blitz, Pomodoro,
Focus Lock, profiles, music) and warn the user to disable add-ons that double up —
Sprint Mode above all. It also points to the companion add-ons that handle reveal
pacing (aSFM and Progressive Word Reveal), which Core deliberately leaves out.
Standalone-safe: every Qt touch is guarded and any failure still marks the run
done so it can't nag on every restart.
"""

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDialogButtonBox,
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
    dlg = QDialog(mw)
    dlg.setWindowTitle("Welcome to AnkiBlitz Core")
    dlg.setMinimumWidth(440)
    lay = QVBoxLayout(dlg)

    head = QLabel("AnkiBlitz Core")
    head.setStyleSheet("font-size: 20px; font-weight: 700; margin-bottom: 2px;")
    lay.addWidget(head)

    intro = QLabel(
        "Session discipline for Anki: timed <b>Blitz</b> sessions, a "
        "<b>Pomodoro</b> work/break cycle, a <b>Focus Lock</b> that makes bailing "
        "harder, one-click <b>profiles</b>, and an in-app <b>music</b> player. A "
        "couple of things before you start:"
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("color: gray; font-size: 12px; margin-bottom: 8px;")
    lay.addWidget(intro)

    # --- clash warning ---
    clash = QLabel(
        "<b>Disable add-ons that do the same job</b> so timers and counters don't "
        "double up — especially:<br>"
        "&nbsp;&nbsp;• <b>Sprint Mode</b>"
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

    # --- companions ---
    companions = QLabel(
        "<b>Want reveal pacing too?</b> Core leaves the card-reveal timers out so "
        "it stays light. Two companion add-ons add them, and run happily alongside "
        "Core:<br>"
        "&nbsp;&nbsp;• <b>Adaptive Speed Focus (aSFM)</b> — adaptive auto-reveal "
        "timer<br>"
        "&nbsp;&nbsp;• <b>Progressive Word Reveal</b> — fade the answer in word by "
        "word<br>"
        "Or grab the all-in-one <b>AnkiBlitz</b> add-on, which bundles everything."
    )
    companions.setWordWrap(True)
    companions.setStyleSheet("font-size: 11px; color: gray; margin-bottom: 8px;")
    lay.addWidget(companions)

    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    bb.button(QDialogButtonBox.StandardButton.Ok).setText("Get started")
    bb.accepted.connect(dlg.accept)
    lay.addWidget(bb)

    return dlg


def maybe_show_first_run_wizard() -> None:
    """Show the wizard once per install. Best-effort: any failure is swallowed,
    and the run is marked done regardless so a display hiccup doesn't nag on every
    restart."""
    try:
        if not config.first_run_pending():
            return
        dlg = _build_dialog()
        dlg.exec()
    except Exception:
        pass
    finally:
        try:
            config.mark_first_run_done()
        except Exception:
            pass
