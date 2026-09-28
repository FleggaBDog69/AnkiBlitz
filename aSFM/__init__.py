"""Adaptive Speed Focus (aSFM) — an auto-REVEAL timer for Anki.

After the question shows, it waits a delay computed from the card's length and
FSRS difficulty, then reveals the answer automatically. It NEVER grades the card.

A standalone reworking of the auto-reveal idea from Glutanimate's Speed Focus
Mode (AGPL). Extracted from the AnkiBlitz suite so it can be used on its own.
"""

from aqt import gui_hooks

from . import config
from .engine import injection, pace
from .menu import build_menu

_initialized = False


def _on_profile_open() -> None:
    global _initialized
    if _initialized:
        return
    config.ensure_defaults()
    injection.register()
    build_menu()
    _initialized = True


def _on_profile_close() -> None:
    try:
        pace.end_session()
    except Exception:
        pass


gui_hooks.profile_did_open.append(_on_profile_open)
gui_hooks.profile_will_close.append(_on_profile_close)
