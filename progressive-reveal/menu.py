"""Tools ▸ Progressive Word Reveal menu: Settings and a master Enabled toggle."""

from aqt import mw
from aqt.qt import QAction, QMenu

from .config import enabled, set_enabled
from .settings import open_settings


def build_menu() -> None:
    menu = QMenu("Progressive Word Reveal", mw)

    settings = QAction("Settings…", mw)
    settings.triggered.connect(open_settings)
    menu.addAction(settings)

    on = QAction("Enabled", mw)
    on.setCheckable(True)
    on.setChecked(enabled())
    on.toggled.connect(lambda checked: set_enabled(checked))
    menu.aboutToShow.connect(lambda: on.setChecked(enabled()))
    menu.addAction(on)

    mw.form.menuTools.addMenu(menu)
