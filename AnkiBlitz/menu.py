"""Tools ▸ AnkiBlitz menu.

Start/stats, the tabbed Settings window, and a master Enabled toggle.
"""

from aqt import mw
from aqt.qt import QAction, QInputDialog, QMenu
from aqt.utils import tooltip

from .config import suite_enabled, set_suite_enabled
from .engine import presets
from .engine.sprint import start_blitz_dialog, start_blitz_all_due
from .engine.pomodoro import start_pomodoro, open_journal_viewer
from .engine.stats import open_stats_window
from .engine.music import toggle_dock
from .settings import open_settings


def _toggle_enabled(checked: bool) -> None:
    set_suite_enabled(checked)


def _apply_profile(name: str) -> None:
    if presets.apply_profile(name):
        tooltip(f"Switched to “{name}”.")


def _save_profile_as() -> None:
    name, ok = QInputDialog.getText(mw, "Save profile", "Profile name:")
    name = (name or "").strip()
    if ok and name:
        presets.save_current_as(name)
        tooltip(f"Saved profile “{name}”.")


def _build_profile_menu(profile_menu: QMenu) -> None:
    """(Re)populate the Profile submenu — done on aboutToShow so newly-saved
    profiles and the active mark stay current."""
    profile_menu.clear()
    profile_menu.setToolTipsVisible(True)
    active = presets.active_name()
    for name in presets.list_profiles():
        act = QAction(name, mw)
        act.setCheckable(True)
        act.setChecked(name == active)
        summary = presets.summary_text(name, sep="\n")
        if summary:
            act.setToolTip(summary)
        act.triggered.connect(lambda _checked=False, n=name: _apply_profile(n))
        profile_menu.addAction(act)
    profile_menu.addSeparator()
    save = QAction("Save current settings as…", mw)
    save.triggered.connect(lambda: _save_profile_as())
    profile_menu.addAction(save)


def build_menu() -> None:
    menu = QMenu("AnkiBlitz", mw)

    start = QAction("Start Blitz…", mw)
    start.setShortcut("Ctrl+Shift+S")
    start.triggered.connect(start_blitz_dialog)
    menu.addAction(start)

    all_due = QAction("Blitz all due cards", mw)
    all_due.triggered.connect(lambda: start_blitz_all_due())
    menu.addAction(all_due)

    pomodoro = QAction("Start Pomodoro…", mw)
    pomodoro.setShortcut("Ctrl+Shift+P")
    # Wrap so QAction.triggered's `checked` bool isn't passed as deck_id.
    pomodoro.triggered.connect(lambda: start_pomodoro())
    menu.addAction(pomodoro)

    stats = QAction("Blitz stats", mw)
    stats.triggered.connect(open_stats_window)
    menu.addAction(stats)

    journal = QAction("Break journal…", mw)
    journal.triggered.connect(lambda: open_journal_viewer())
    menu.addAction(journal)

    music = QAction("Music player", mw)
    music.setShortcut("Ctrl+Shift+M")
    music.triggered.connect(lambda: toggle_dock())
    menu.addAction(music)

    # SynapsePro ships a music player of its own, so AnkiBlitz's entry steps
    # aside when it's installed. Decided each time the menu opens rather than
    # once at build time, so toggling the setting takes effect immediately.
    def _sync_music_visibility() -> None:
        try:
            from .engine import theme_bridge
            music.setVisible(not theme_bridge.music_deferred())
        except Exception:
            pass

    menu.aboutToShow.connect(_sync_music_visibility)
    _sync_music_visibility()

    menu.addSeparator()

    profile_menu = QMenu("Profile", mw)
    profile_menu.aboutToShow.connect(lambda: _build_profile_menu(profile_menu))
    _build_profile_menu(profile_menu)
    menu.addMenu(profile_menu)

    settings = QAction("Settings…", mw)
    settings.triggered.connect(open_settings)
    menu.addAction(settings)

    enabled = QAction("Enabled", mw)
    enabled.setCheckable(True)
    enabled.setChecked(suite_enabled())
    enabled.toggled.connect(_toggle_enabled)
    menu.aboutToShow.connect(lambda: enabled.setChecked(suite_enabled()))
    menu.addAction(enabled)

    mw.form.menuTools.addMenu(menu)
