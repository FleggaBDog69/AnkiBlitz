# Adaptive Speed Focus (aSFM)

An auto-**reveal** timer for Anki. After the question shows, aSFM waits a delay
computed from the card's length and FSRS difficulty, then reveals the answer
automatically. **It never grades the card for you** — you still press the button.

It's a standalone reworking of the auto-reveal idea from Glutanimate's *Speed
Focus Mode*, extracted from the **AnkiBlitz** suite so you can use just this piece.

---

## What it does

- Waits `(base + per-word × question words + per-answer-word × answer words) ×
  familiarity × difficulty`, clamped between a min and max, then auto-reveals.
  The answer term is capped; set it to `0` to time from the question alone.
- Counts only the words you actually **see** — hidden fields and AnKing-style tag
  chips don't inflate the timer.
- Treats new and learning/relearning cards as needing more time (tunable).
- Nudges the delay by the card's **FSRS difficulty** (harder = longer), bounded.
  Not on FSRS? It works with the classic SM-2 scheduler too, reading the
  card's ease and lapses instead; calibration works with either.
- Optional thin **countdown bar** and a **warning sound** before the reveal. The
  bar can also turn from blue to red at the warning point — a silent heads-up.
- A **“More time” button** on the card (showing its key as a keycap), and a **pause key** (default `p`) — both
  freeze the countdown on the card you're on and pick it up where it stopped. The
  hold sticks across cards, and every card it applies to says so on screen. The
  button stays faint until you hover it; the “paused” badge is clickable to
  resume, so whatever you paused with can start you again.
- **Learns your pace, if you let it.** Opt-in (off until you tick it on the
  welcome screen or in Settings), local only, never sent anywhere. Auto-tune gently adjusts the timer to how fast you
  actually reveal cards (never more than 15% quicker; timeouts back it off
  fast), and **Calibrate from my reviews…** suggests base / per-word timings
  from your own data, shown side by side before anything changes.
- **Picture-card mode:** chosen note types / decks use a set time instead of a
  word count (there's nothing to read).
- **A welcome window on first run** that explains the basics and can
  calibrate the timer to your speed in one click. Reopen it any time from
  **Tools ▸ Adaptive Speed Focus ▸ Welcome & calibration…**.

## Install

- **From AnkiWeb (recommended — you get updates):** Anki ▸ Tools ▸ Add-ons ▸
  Get Add-ons… ▸ paste the code **`1148593203`**, then restart.
  <https://ankiweb.net/shared/info/1148593203>
- **From file:** Anki ▸ Tools ▸ Add-ons ▸ Install from file… ▸ pick
  `aSFM.ankiaddon`, then restart.
- **Manually:** drop the `asfm` folder into your Anki `addons21/` directory and
  restart.

If you also run **Glutanimate's Speed Focus Mode**, disable it so the two timers
don't double up. (If you run the full **AnkiBlitz** suite, you already have this
feature — don't install both.)

**Pairs with Progressive Word Reveal.** Install both and they cooperate: the
answer waits for the question to finish fading in, the two can share the `p`
key (first press finishes the fade, the next one pauses), and clicking **More
time** never skips the fade.

## Using it

Everything is under **Tools ▸ Adaptive Speed Focus**:

| Item | What it does |
|------|--------------|
| Settings… | Four tabs — **Timing**, **On screen**, **Your pace**, **Cards** — with a live preview beside them. |
| Enabled | Master on/off. |
| Welcome & calibration… | The first-run window again, with one-click calibration. |

The live preview table in Settings always agrees with the runtime — both compute
the delay the same way.

## Credits & acknowledgements

- **Glutanimate's _Speed Focus Mode_** — Copyright (C) 2017-2021 Aristotelis P.
  (Glutanimate), <https://glutanimate.com/> — the original auto-reveal-timer idea
  that aSFM reworks, and the source of the **More time** button. aSFM
  deliberately differs: it **never grades**, computes the delay from question
  length **and FSRS difficulty**, and times new vs learning cards separately.
- **The AnKing team** — their note types and `{{tts}}` conventions drove the
  visible-word-count handling (hidden tag chips and hint/Extra chrome don't
  inflate the timer) and the set-time picture-card mode.
- **Anki** and its community — the platform this runs on.

aSFM is one of four add-ons split out of the **AnkiBlitz** suite — the full
integrated version of this feature and more:
<https://github.com/FleggaBDog69/AnkiBlitz>

## Licence

aSFM reworks Glutanimate's Speed Focus Mode, which is licensed under the **GNU
Affero General Public License v3.0 (AGPLv3)** **with additional terms under AGPL
Section 7**, so aSFM is distributed under those same terms. You may use, study,
modify and share it; if you distribute a modified version (or run it as a network
service) you must release your source under the same licence. In addition, per
Glutanimate's Section 7 terms you must **preserve all copyright and author
attributions**, **not misrepresent the origin** of the work, and you are **not
granted any right to use the "Glutanimate" name or logo** for endorsement. The
full licence text, including the additional terms, is in [LICENSE](LICENSE).
