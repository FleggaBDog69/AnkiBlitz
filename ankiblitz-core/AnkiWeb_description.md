# AnkiBlitz Core

**Session discipline, without the reveal timers.**

AnkiBlitz Core is the lean build of AnkiBlitz: focused, timed study with real structure, but **without** the card-reveal timers. One engine, one menu, one settings window.

## What it does

- **Blitz sessions** — focused, timed runs by card count, time, or a fraction of what's due, with a progress bar and a completion screen. The bar stays up **outside** a Blitz too, dimmed and labelled *All due*, filling against everything you have due — so plain reviewing isn't a blank screen.
- **Pomodoro** — work blocks chained with short and long breaks, a break screen with journaling, focus ratings and a guided breathing pacer, and configurable auto-return.
- **Focus Lock** — make leaving a session progressively harder (confirm → clear more cards → finish), with an optional Focus Score. Pick the level per Blitz in the Start dialog without touching your saved default.
- **In-app music** — a SoundCloud / YouTube Music player on the break screen, as a floating review dock, and on the deck list.

## Profiles

Three built-ins — **Default** (everyday), **Blitz** (a committed, locked-in run) and **Relaxed** (low friction) — flip the *feel* in one click: Focus Lock, the near-end nudge, the anti-pressure display.

They deliberately leave your session shape alone (you pick mode and target at each launch), and your music too. Save your own as well — your current setup is kept as a *My setup* profile, so nothing is lost.

## New in 1.2.0

- **The progress bar now stays up outside a Blitz**, dimmed and labelled *All due*, filling against your whole due pile. Its target is **live**: a card that comes back in learning pushes it out by one, so the bar fills exactly as your queue empties and never before. It shows no accuracy, Again count or streak — a bar you didn't opt into is the wrong place for grading pressure.
- **Per-Blitz Focus Lock.** *Start Blitz…* now has a Focus lock picker: commit hard to a session you need to finish, or let yourself off for a tired one, without changing your saved default.
- **A guided breathing pacer on the break screen** — a circle that expands and contracts with the phase named and counted underneath, so there's something to follow rather than just being told to relax. Collapsed as a **Breathe** button until you press it. Box 4-4-4-4, Simple 4-4, Coherent 5-5, or Calming 4-7-8.
- **A break you can walk away from** — a *Step away* button with a floating countdown, muted card audio during the break, and the option to resume an unfinished run from earlier the same day.
- **Fixed:** Focus Lock level 3 now keeps a Blitz alive on focus loss based on the level that Blitz was *started* with, rather than whatever is configured right now.
- **Fixed:** *Finish all due* on the deck-list panel no longer swallows the click.

## Want reveal pacing too?

Core leaves the card-reveal timers out on purpose. Two companion add-ons put them back, and both run alongside Core:

- [Adaptive Speed Focus (aSFM)](https://ankiweb.net/shared/info/1148593203) — adaptive auto-reveal timer, with a “More time” button.
- [Progressive Word Reveal](https://ankiweb.net/shared/info/972193513) — fades the question in word by word.

Or install the all-in-one [AnkiBlitz](https://ankiweb.net/shared/info/178722601), which bundles everything.

## Before you start

**Disable these** to avoid double timers and counters (Tools ▸ Add-ons):

- Sprint Mode
- the full [AnkiBlitz](https://ankiweb.net/shared/info/178722601) add-on — it already includes Core

A one-time welcome wizard reminds you on first launch.

## Shortcuts

Under **Tools ▸ AnkiBlitz Core**:

- Start Blitz — `Ctrl+Shift+S`
- Start Pomodoro — `Ctrl+Shift+P`
- Music player — `Ctrl+Shift+M`

## Notes

- Works standalone. Your stats and settings are preserved across updates.
- Builds on the idea of **Patrick Lee's Sprint Mode** ([patricklee.com.au](https://www.patricklee.com.au/)); licensed under the GNU AGPLv3.
- Tested on Anki 2.1.50+ (Qt6).
