# Adaptive Speed Focus (aSFM)

**An auto-REVEAL timer that never grades.**

After the question shows, aSFM waits a delay computed from the card's length and its FSRS difficulty, then reveals the answer automatically. It **never grades the card for you** — you still press the button yourself.

## What it does

- Waits `(base + per-word × words) × familiarity × difficulty`, clamped between a minimum and a maximum, then auto-reveals.
- Counts only the text you actually **see** — hidden fields and AnKing-style tag chips don't inflate the timer.
- Gives new and learning/relearning cards more time (tunable).
- Nudges the delay by the card's **FSRS difficulty** — harder cards get longer, bounded so it stays a gentle shift rather than a cliff.
- Optional thin **countdown bar** and a **warning sound** before the reveal.
- A **“More time” button** on the card, and a **pause key** (default `P`) — either one holds the countdown where it stands so you can sit on a card, then picks it up where it stopped. The hold sticks across cards, and every card it applies to says so on screen. The button stays faint until you hover it.
- **Picture-card mode:** chosen note types or decks use a set time instead of a word count, since there's nothing to read.

## New in 1.2.0

- **A visible “More time” button**, by request. The pause key already did this, but a keypress is invisible — you only find it if you read the settings. Now you can see that it's there: click to stop the countdown, click again (or click the “paused” badge) to carry on. Turn it off in Settings if you'd rather keep the card clear.
- **A pause key** (default `P`) for the same hold, if you prefer the keyboard. Give it a different key from Progressive Word Reveal's if you run both.

## Before you start

If you run **Glutanimate's Speed Focus Mode**, disable it so the two timers don't double up. If you run the full **AnkiBlitz** suite, this feature is already in it — don't install both.

## Using it

**Tools ▸ Adaptive Speed Focus ▸ Settings…** — every timing knob, the exclusions, picture-card mode, and a live preview table that always agrees with the runtime.

## The AnkiBlitz suite

- [AnkiBlitz](https://ankiweb.net/shared/info/178722601) — all four features in one add-on.
- [AnkiBlitz Core](https://ankiweb.net/shared/info/1174429600) — sessions, Pomodoro, Focus Lock, profiles, music.
- [Adaptive Speed Focus (aSFM)](https://ankiweb.net/shared/info/1148593203) — this add-on: the auto-reveal timer alone.
- [Progressive Word Reveal](https://ankiweb.net/shared/info/972193513) — the word-by-word fade alone.

Core + aSFM + Progressive Word Reveal together equal the full AnkiBlitz. Don't run AnkiBlitz alongside any of the other three — it already contains them.

## Notes

- Reworks the auto-reveal concept from **Glutanimate's Speed Focus Mode** (Copyright © 2017-2021 Aristotelis P., [glutanimate.com](https://glutanimate.com/)); the “More time” button is his idea too. Licensed under the GNU AGPLv3 **with** Glutanimate's Section 7 additional terms — preserve attribution, don't misrepresent origin, no use of the Glutanimate name for endorsement. Full terms in `LICENSE`.
- To change the warning sound, drop your own `alert.mp3` into the add-on's `user_files/` folder.
- Tested on Anki 2.1.50+ (Qt6).
