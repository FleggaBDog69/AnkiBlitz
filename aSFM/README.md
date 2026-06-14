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

## Licence

Reworks the auto-reveal concept from Glutanimate's Speed Focus Mode (GNU AGPLv3),
so this add-on is distributed under the **GNU AGPLv3** too. See [LICENSE](LICENSE).
