# AnkiBlitz Core engine.
#
# One session of truth, one reviewer injection point, one JS/CSS bundle.
# (Card-reveal pacing — adaptive auto-reveal and progressive word reveal — lives
# in the separate aSFM and Progressive Word Reveal add-ons, so it's absent here.)
# Submodules:
#   session.py    - the single source-of-truth Blitz session
#   injection.py  - the ONE webview injection + per-card eval bridge
#   sprint.py     - Blitz lifecycle (start, hooks, completion, momentum) and the
#                   ambient due-pile bar for ordinary (non-Blitz) review
#   breathing.py  - guided breathing pacer widget for the break screen
#   quickstart.py - daily auto-launch + 3-2-1 countdown
#   pomodoro.py   - Pomodoro cycle: work blocks + break screen + auto-return
#   music.py      - embedded SoundCloud/YouTube player: break panel + review dock
#   widgets.py    - deck-browser / overview on-screen launch panels
#   stats.py      - persistent Blitz stats
