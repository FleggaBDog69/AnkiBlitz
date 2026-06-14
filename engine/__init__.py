# AnkiBlitz engine.
#
# One session of truth, one reviewer injection point, one JS/CSS bundle.
# Submodules:
#   session.py    - the single source-of-truth Blitz session
#   adaptive.py   - Python adaptive auto-reveal delay calculator
#   reveal.py     - builds the per-card payload pushed to the JS bundle
#   tts_sync.py   - matches reveal speed to native/AnKing {{tts}} playback rate
#   injection.py  - the ONE webview injection + per-card eval bridge + pycmd
#   sprint.py     - Blitz lifecycle (start, hooks, completion, momentum)
#   quickstart.py - daily auto-launch + 3-2-1 countdown
#   pomodoro.py   - Pomodoro cycle: work blocks + break screen + auto-return
#   music.py      - embedded SoundCloud/YouTube player: break panel + review dock
#   widgets.py    - deck-browser / overview on-screen launch panels
#   stats.py      - persistent Blitz stats
