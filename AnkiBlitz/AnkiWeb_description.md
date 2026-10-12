# AnkiBlitz

**Pace your reviews, not your grades.**

AnkiBlitz rolls three review-pacing ideas into one engine, one menu and one settings window — plus the session structure to hold them together.

## What it does

- **Adaptive auto-reveal** — after the question shows, AnkiBlitz waits a delay computed from the card's length and its FSRS difficulty, then reveals the answer. The delay can count the **answer's** length as well as the question's, so a one-line question with a five-item answer gets the time it needs. It **never grades for you** — you still press the button. Picture or visual note types and decks can use a set time instead, since there's nothing to read.
- **Progressive word reveal** — the question fades in word by word at a reading pace you set, optionally locked to the card's `{{tts}}` voice. Skipping ahead stops the card's audio too: you've read it, so the voice still reading it to you is just noise.
- **Blitz sessions** — focused, timed runs by card count, time, or a fraction of what's due, with a progress bar and a completion screen. The bar stays up **outside** a Blitz too, dimmed and labelled *All due*, filling against everything you have due — so plain reviewing isn't a blank screen.
- **Know how long it's going to take** — the bar's fill is coloured card by card in the order you did them (green for a clean pass, red for an Again), each band as wide as the time that card took, named in words beside it, and it estimates the time left from your own review history — what new cards, reviews and learning steps have actually cost you, misses included — pulled toward today's pace as you go. In a timed Blitz it runs the other way and tells you how many cards you should get through. Works on ordinary review sessions, not just Blitzes.
- **Pomodoro** — work blocks chained with short and long breaks, a break screen with journaling, focus ratings and a guided breathing pacer, and configurable auto-return.
- **Focus Lock** — make leaving a session progressively harder (confirm → clear more cards → finish), with an optional Focus Score. Pick the level per Blitz in the Start dialog without touching your saved default.
- **Hold the timer whenever you like** — a **“More time”** button on the card, or a **pause key** (default `P`). Either stops the countdown where it stands and picks it up where it stopped.
- **In-app music** — a SoundCloud / YouTube Music player on the break screen, as a floating review dock, and on the deck list.

## Profiles

Three built-ins — **Default** (everyday), **Blitz** (a committed, locked-in run) and **Relaxed** (low friction) — flip the *feel* in one click: auto-reveal pace, Focus Lock, the near-end nudge, the anti-pressure display.

They deliberately leave your session shape alone (you pick mode and target at each launch), along with word-reveal speed and music. The picker shows each profile's key settings before you apply it. Save your own too — your current setup is kept as a *My setup* profile, so nothing is lost.

## New in this update

- **A fresh look on the card.** The auto-reveal countdown now has a soft glow, and the More time button and paused badge are a redesigned frosted pill that shows the pause key as a keycap.
- **Tidier Speed Focus settings.** Clear section headings and plainer labels, and the live preview stays in view while you scroll.
- **Fixed:** pressing Esc in a key box (pause key, reveal key) no longer sets Esc as the key.

## New in 1.3.0

- **Long answers can get more time.** The delay now also scales with the **answer's** length, not just the question's — for the cards where the question is one line but the answer is a list of five things. Works on cloze and front/back alike. Set *Per answer word* to `0.0` to switch it off.
- **Fixed: the warning sound now plays.** It had been silent on some setups. The reviewer plays it itself now, rather than handing it to Anki's external media player, so it works even where that player fails to start.
- **Fixed: multi-line cards were being timed short.** Text either side of a line break was glued together, losing one word per line — a four-line cloze counted 27 words instead of 29, and got a shorter timer than it should have.
- **Retuned defaults** for new installs: a slightly longer base time, auto-reveal off on new cards, and Quick Start off until you turn it on.

Existing setups are untouched — an update only fills in settings you don't already have, so nothing you've tuned is rewritten.

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
- To change the warning sound, drop your own `alert.flac`, `.ogg`, `.opus` or `.wav` into the add-on's `user_files/` folder. An `alert.mp3` works too, but only where Anki's external media player is running — the reviewer can't decode MP3 by itself.
- Word-count timing counts only the text you actually see — hidden fields and tag chips on AnKing-style notes don't inflate the timer.
- Bundles concepts from **Glutanimate's Speed Focus Mode** (Copyright © 2017-2021 Aristotelis P., [glutanimate.com](https://glutanimate.com/)) and from **Patrick Lee's** Progressive Word Reveal and Sprint Mode ([patricklee.com.au](https://www.patricklee.com.au/)). Licensed under the GNU AGPLv3 **with** Glutanimate's Section 7 additional terms — preserve attribution, don't misrepresent origin, no use of the Glutanimate name for endorsement. Full terms in `LICENSE`.
- Tested on Anki 2.1.50+ (Qt6).
