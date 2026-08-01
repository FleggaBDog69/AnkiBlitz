"""AnkiBlitz Core — session-discipline engine for Anki.

One source-of-truth session, one reviewer injection point, one CSS/JS bundle.
Features: timed Blitz sessions (progress bar), a Pomodoro work/break cycle, a
Focus Lock, one-click profiles, and an in-app music player. Card-reveal pacing
(adaptive auto-reveal and progressive word reveal) lives in the companion aSFM
and Progressive Word Reveal add-ons.

Builds on concepts from Patrick Lee's Sprint Mode (https://www.patricklee.com.au/).
"""

from aqt import gui_hooks

from . import config
from .engine import (
    injection, sprint, quickstart, widgets, music, onboarding, pomodoro,
)
from .menu import build_menu

_initialized = False


def _on_profile_open() -> None:
    # profile_did_open can fire again on profile switch; only wire up once.
    global _initialized
    if _initialized:
        return
    config.ensure_defaults()
    config.migrate()
    # Show the one-time first-run wizard (modal) BEFORE registering features, so
    # Quick Start's deferred auto-launch can't fire while the dialog is open.
    onboarding.maybe_show_first_run_wizard()
    injection.register()
    sprint.register()
    quickstart.register()
    widgets.register()
    music.register()
    # Registers the av_player hook that silences card audio during a break.
    pomodoro.register()
    build_menu()
    _initialized = True


gui_hooks.profile_did_open.append(_on_profile_open)
