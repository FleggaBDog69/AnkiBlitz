"""AnkiBlitz — review-pacing engine for Anki.

One source-of-truth session, one reviewer injection point, one CSS/JS bundle.
Features: Blitz progress bar, progressive word reveal, and an adaptive
auto-REVEAL timer (never auto-grades).

Bundles concepts from Glutanimate's Speed Focus Mode (AGPL) and from Patrick Lee's
Progressive Word Reveal and Sprint Mode (https://www.patricklee.com.au/).
"""

from aqt import gui_hooks

from . import config
from .engine import (
    injection, sprint, quickstart, widgets, music, onboarding, pomodoro,
    synapse_sidebar,
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
    pomodoro.register()
    quickstart.register()
    widgets.register()
    music.register()
    # Adds AnkiBlitz's buttons to SynapsePro's icon strip. A no-op without it —
    # registered unconditionally so installing SynapsePro later just works.
    synapse_sidebar.register()
    build_menu()
    _initialized = True


gui_hooks.profile_did_open.append(_on_profile_open)
