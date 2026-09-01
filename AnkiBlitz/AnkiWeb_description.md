# AnkiBlitz

**Pace your reviews, not your grades.**

AnkiBlitz rolls three review-pacing ideas into one engine, one menu and one settings window — plus the session structure to hold them together.

## What it does

- **Adaptive auto-reveal** — after the question shows, AnkiBlitz waits a delay computed from the card's length and its FSRS difficulty, then reveals the answer. It **never grades for you** — you still press the button. Picture or visual note types and decks can use a set time instead, since there's nothing to read.
- **Progressive word reveal** — the question fades in word by word at a reading pace you set, optionally locked to the card's `{{tts}}` voice. Skipping ahead stops the card's audio too: you've read it, so the voice still reading it to you is just noise.
- **Blitz sessions** — focused, timed runs by card count, time, or a fraction of what's due, with a progress bar and a completion screen. The bar stays up **outside** a Blitz too, dimmed and labelled *All due*, filling against everything you have due — so plain reviewing isn't a blank screen.
- **Pomodoro** — work blocks chained with short and long breaks, a break screen with journaling, focus ratings and a guided breathing pacer, and configurable auto-return.
- **Focus Lock** — make leaving a session progressively harder (confirm → clear more cards → finish), with an optional Focus Score. Pick the level per Blitz in the Start dialog without touching your saved default.
- **Hold the timer whenever you like** — a **“More time”** button on the card, or a **pause key** (default `P`). Either stops the countdown where it stands and picks it up where it stopped.
- **In-app music** — a SoundCloud / YouTube Music player on the break screen, as a floating review dock, and on the deck list.

## Profiles

Three built-ins — **Default** (everyday), **Blitz** (a committed, locked-in run) and **Relaxed** (low friction) — flip the *feel* in one click: auto-reveal pace, Focus Lock, the near-end nudge, the anti-pressure display.

They deliberately leave your session shape alone (you pick mode and target at each launch), along with word-reveal speed and music. The picker shows each profile's key settings before you apply it. Save your own too — your current setup is kept as a *My setup* profile, so nothing is lost.

## New in 1.2.0

- **A “More time” button** on the card, by request. The pause key already did this, but a keypress is invisible — now you can see that it's there. Click to stop the countdown, click again (or click the “paused” badge) to carry on.
- **A pause key** (default `P`) for the same hold, from the keyboard.
- **The progress bar now stays up outside a Blitz**, dimmed and labelled *All due*, filling against your whole due pile. Its target is **live**: a card that comes back in learning pushes it out by one, so the bar fills exactly as your queue empties and never before. It shows no accuracy, Again count or streak — a bar you didn't opt into is the wrong place for grading pressure.
- **Per-Blitz Focus Lock.** *Start Blitz…* now has a Focus lock picker: commit hard to a session you need to finish, or let yourself off for a tired one, without changing your saved default.
- **A guided breathing pacer on the break screen** — a circle that expands and contracts with the phase named and counted underneath, so there's something to follow rather than just being told to relax. Collapsed as a **Breathe** button until you press it. Box 4-4-4-4, Simple 4-4, Coherent 5-5, or Calming 4-7-8.
- **Skipping the word reveal stops the card's TTS and `[sound:]` playback.**
- **SynapsePro theming** — matches SynapsePro's palette when that add-on is installed, and looks exactly as before when it isn't.
- **Fixed:** the reveal key no longer fires while you're typing in Anki's type-in-the-answer box, or with Ctrl/Cmd/Alt held.
- **Fixed:** *Finish all due* on the deck-list panel no longer swallows the click.

## Before you start

AnkiBlitz bundles its own version of each of these, so **disable them** to avoid double timers (Tools ▸ Add-ons):

- Speed Focus Mode
- Progressive Word Reveal
- Sprint Mode

A one-time welcome wizard reminds you on first launch.

## Shortcuts

Under **Tools ▸ AnkiBlitz**:

- Start Blitz — `Ctrl+Shift+S`
- Start Pomodoro — `Ctrl+Shift+P`
- Music player — `Ctrl+Shift+M`

## Only want one piece?

Each half ships on its own, and they run happily alongside each other:

- [AnkiBlitz Core](https://ankiweb.net/shared/info/1174429600) — sessions, Pomodoro, Focus Lock, profiles and music **without** the two reveal timers.
- [Adaptive Speed Focus (aSFM)](https://ankiweb.net/shared/info/1148593203) — the auto-reveal timer alone.
- [Progressive Word Reveal](https://ankiweb.net/shared/info/972193513) — the word-by-word fade alone.

Core + aSFM + Progressive Word Reveal together equal this add-on. Don't run any of them alongside AnkiBlitz — it already contains all three, and the timers would double up.

## Notes

- Works standalone. Your stats and settings are preserved across updates.
- Word-count timing counts only the text you actually see — hidden fields and tag chips on AnKing-style notes don't inflate the timer.
- Bundles concepts from **Glutanimate's Speed Focus Mode** (Copyright © 2017-2021 Aristotelis P., [glutanimate.com](https://glutanimate.com/)) and from **Patrick Lee's** Progressive Word Reveal and Sprint Mode ([patricklee.com.au](https://www.patricklee.com.au/)). Licensed under the GNU AGPLv3 **with** Glutanimate's Section 7 additional terms — preserve attribution, don't misrepresent origin, no use of the Glutanimate name for endorsement. Full terms in `LICENSE`.
- Tested on Anki 2.1.50+ (Qt6).
