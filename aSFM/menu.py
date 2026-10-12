"""Tools ▸ Adaptive Speed Focus menu: Settings, a master Enabled toggle, and
the welcome / calibration window."""

from aqt import mw
from aqt.qt import QAction, QMenu

from .config import enabled, set_enabled
from .settings import open_settings
from .welcome import open_welcome


def build_menu() -> None:
    menu = QMenu("Adaptive Speed Focus", mw)

    settings = QAction("Settings…", mw)
    settings.triggered.connect(open_settings)
    menu.addAction(settings)

    on = QAction("Enabled", mw)
    on.setCheckable(True)
    on.setChecked(enabled())
    on.toggled.connect(lambda checked: set_enabled(checked))
    menu.aboutToShow.connect(lambda: on.setChecked(enabled()))
    menu.addAction(on)

    welcome = QAction("Welcome && calibration…", mw)
    welcome.triggered.connect(open_welcome)
    menu.addAction(welcome)

    mw.form.menuTools.addMenu(menu)
