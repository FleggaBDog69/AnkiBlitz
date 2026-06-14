# Progressive Word Reveal

Fades the card's question in **word by word** at a reading pace you set, so longer
questions take proportionally longer to appear. Click or press the reveal key to
show everything at once.

It's a standalone reworking of Glutanimate's *Progressive Word Reveal*, extracted
from the **AnkiBlitz** suite so you can use just this piece.

---

## What it does

- Fades words (or fixed-size **chunks** of words) in at a set words-per-second.
- Counts only the text you actually **see** — `<script>`/`<style>`, MathJax, and
  CSS-hidden AnKing tag chips / hint chrome are skipped, so the pace tracks what
  you read rather than invisible markup.
- Optional **TTS sync**: lock the reveal to a card's native Anki / AnKing
  `{{tts}}` voice so the words finish in step with the audio.
- Optional reveal on the **answer** side too.
- Per-note-type / per-deck **exclusions**.

## Install

- **From file:** Anki ▸ Tools ▸ Add-ons ▸ Install from file… ▸ pick
  `ProgressiveWordReveal.ankiaddon`, then restart.
- **Manually:** drop the `progressive_reveal` folder into your Anki `addons21/`
  directory and restart.

If you also run **Glutanimate's Progressive Word Reveal**, disable it so the two
don't double up. (If you run the full **AnkiBlitz** suite, you already have this
feature — don't install both.)

## Using it

Everything is under **Tools ▸ Progressive Word Reveal**:

| Item | What it does |
|------|--------------|
| Settings… | Speed, mode, chunk size, reveal key, TTS sync, exclusions, live preview. |
| Enabled | Master on/off. |

## Licence

Reworks Glutanimate's Progressive Word Reveal (GNU AGPLv3), so this add-on is
distributed under the **GNU AGPLv3** too. See [LICENSE](LICENSE).
