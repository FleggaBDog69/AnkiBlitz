# AnkiBlitz Core engine.
#
# One session of truth, one reviewer injection point, one JS/CSS bundle.
# (Card-reveal pacing — adaptive auto-reveal and progressive word reveal — lives
# in the separate aSFM and Progressive Word Reveal add-ons, so it's absent here.)
# Submodules:
#   session.py    - the single source-of-truth Blitz session
#   forecast.py   - the bar's time estimate, priced off your review history
#   injection.py  - the ONE webview injection + per-card eval bridge
#   topbar.py     - reclaims the blank band Anki leaves above the reviewer
#                   when it hides the top bar, so the strip sits at the very top
#   sprint.py     - Blitz lifecycle (start, hooks, completion, momentum) and the
#                   ambient due-pile bar for ordinary (non-Blitz) review
#   breathing.py  - guided breathing pacer widget for the break screen
#   quickstart.py - daily auto-launch + 3-2-1 countdown
#   pomodoro.py   - Pomodoro cycle: work blocks + break screen + auto-return
#   music.py      - embedded SoundCloud/YouTube player: break panel + review dock
#   widgets.py    - deck-browser / overview on-screen launch panels
#   stats.py      - persistent Blitz stats
#   focus.py      - Focus Lock (how hard leaving is) and the Focus Score
#   presets.py    - profiles: named snapshots of the whole config
#   onboarding.py - one-time first-run wizard
