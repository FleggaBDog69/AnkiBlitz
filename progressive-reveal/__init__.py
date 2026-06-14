"""Progressive Word Reveal — fade the question in word by word.

Fades the card's question in at a fixed reading pace (optionally locked to the
card's {{tts}} voice), so longer questions take proportionally longer. Click or
the reveal key shows everything at once.

A standalone reworking of Patrick Lee's Progressive Word Reveal
(https://www.patricklee.com.au/). Extracted from the AnkiBlitz suite so it can be
used on its own. Distributed under the GNU AGPLv3 (in keeping with the suite).
"""

from aqt import gui_hooks

from . import config
from .engine import injection
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


gui_hooks.profile_did_open.append(_on_profile_open)
