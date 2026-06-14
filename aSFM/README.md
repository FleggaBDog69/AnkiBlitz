# Adaptive Speed Focus (aSFM)

An auto-**reveal** timer for Anki. After the question shows, aSFM waits a delay
computed from the card's length and FSRS difficulty, then reveals the answer
automatically. **It never grades the card for you** — you still press the button.

It's a standalone reworking of the auto-reveal idea from Glutanimate's *Speed
Focus Mode*, extracted from the **AnkiBlitz** suite so you can use just this piece.

---

## What it does

- Waits `(base + per-word × words) × familiarity × difficulty`, clamped between a
  min and max, then auto-reveals.
- Counts only the words you actually **see** — hidden fields and AnKing-style tag
  chips don't inflate the timer.
- Treats new and learning/relearning cards as needing more time (tunable).
- Nudges the delay by the card's **FSRS difficulty** (harder = longer), bounded.
- Optional thin **countdown bar** and a **warning sound** before the reveal.
- **Picture-card mode:** chosen note types / decks use a set time instead of a
  word count (there's nothing to read).

## Install

- **From file:** Anki ▸ Tools ▸ Add-ons ▸ Install from file… ▸ pick
  `aSFM.ankiaddon`, then restart.
- **Manually:** drop the `asfm` folder into your Anki `addons21/` directory and
  restart.

If you also run **Glutanimate's Speed Focus Mode**, disable it so the two timers
don't double up. (If you run the full **AnkiBlitz** suite, you already have this
feature — don't install both.)

## Using it

Everything is under **Tools ▸ Adaptive Speed Focus**:

| Item | What it does |
|------|--------------|
| Settings… | The timing knobs, exclusions, picture-card mode, live preview. |
| Enabled | Master on/off. |

The live preview table in Settings always agrees with the runtime — both compute
the delay the same way.

## Credits & acknowledgements

- **Glutanimate's _Speed Focus Mode_** — the original auto-reveal-timer idea that
  aSFM reworks. aSFM deliberately differs: it **never grades**, computes the delay
  from question length **and FSRS difficulty**, and times new vs learning cards
  separately.
- **The AnKing team** — their note types and `{{tts}}` conventions drove the
  visible-word-count handling (hidden tag chips and hint/Extra chrome don't
  inflate the timer) and the set-time picture-card mode.
- **Anki** and its community — the platform this runs on.

aSFM is one of three add-ons split out of the **AnkiBlitz** suite — the full
integrated version of this feature and more:
<https://github.com/FleggaBDog69/AnkiBlitz>

## Licence

Because it reworks Glutanimate's Speed Focus Mode (GNU AGPLv3), aSFM is
distributed under the **GNU Affero General Public License v3.0 (AGPLv3)**. You may
use, study, modify and share it; if you distribute a modified version (or run it
as a network service) you must release your source under the same licence. The
full text is in [LICENSE](LICENSE).
