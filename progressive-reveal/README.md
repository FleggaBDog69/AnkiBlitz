# Progressive Word Reveal

Fades the card's question in **word by word** at a reading pace you set, so longer
questions take proportionally longer to appear. Click or press the reveal key to
show everything at once.

It's a standalone reworking of **Patrick Lee's** *Progressive Word Reveal*,
extracted from the **AnkiBlitz** suite so you can use just this piece.

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

If you also run **Patrick Lee's original Progressive Word Reveal**, disable it so
the two don't double up. (If you run the full **AnkiBlitz** suite, you already
have this feature — don't install both.)

## Using it

Everything is under **Tools ▸ Progressive Word Reveal**:

| Item | What it does |
|------|--------------|
| Settings… | Speed, mode, chunk size, reveal key, stop-audio-on-reveal, TTS sync, exclusions, live preview. |
| Enabled | Master on/off. |

## Credits & acknowledgements

- **Patrick Lee's _Progressive Word Reveal_** — the original word-by-word fade-in
  idea that this add-on reworks. (<https://www.patricklee.com.au/>)
- **TTS sync** reads the card's native **Anki** `{{tts}}` tags (Anki's
  `MacTTSPlayer` runs `say -r base×speed`) and the **AnKing** note-type TTS
  conventions, so the reveal can lock to the spoken pace. No speech engine is
  bundled — this only *syncs to* the TTS that Anki / AnKing already produce.
- **The AnKing team** — their note types drove the visible-word handling
  (CSS-hidden tag chips / hint chrome are skipped, so the pace tracks what you
  actually read).
- **Anki** and its community — the platform this runs on.

This is one of four add-ons split out of the **AnkiBlitz** suite — the full
integrated version of this feature and more:
<https://github.com/FleggaBDog69/AnkiBlitz>

## Licence

Distributed under the **GNU Affero General Public License v3.0 (AGPLv3)**, in
keeping with the rest of the AnkiBlitz suite. You may use, study, modify and share
it; if you distribute a modified version (or run it as a network service) you must
release your source under the same licence. The full text is in [LICENSE](LICENSE).
