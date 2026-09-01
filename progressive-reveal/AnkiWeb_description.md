# Progressive Word Reveal

**Fade the question in word by word.**

Fades the card's question in one word at a time at a reading pace you set, so a longer question takes proportionally longer to appear. Click, or press the reveal key, to show everything at once.

## What it does

- Fades words — or fixed-size **chunks** of words — in at a set words-per-second.
- Counts only the text you actually **see**: scripts, styles, MathJax and CSS-hidden AnKing tag chips or hint chrome are skipped, so the pace tracks what you're really reading.
- Optional **TTS sync**: lock the reveal to the card's native Anki / AnKing `{{tts}}` voice so the words finish in step with the audio (exact on macOS).
- **Revealing early stops the card's audio** — you've read it, so the voice still reading it to you is just noise. Optional.
- Optional reveal on the answer side too.
- Per-note-type and per-deck exclusions.

## New in 1.2.0

- **Skipping the reveal now stops the card's audio** as well — TTS and `[sound:]` both. It stops rather than pauses, so the next card plays normally. On by default; turn it off in Settings.
- **Fixed:** the reveal key no longer fires while you're typing in Anki's type-in-the-answer box, or with Ctrl/Cmd/Alt held.

## Before you start

If you run **Patrick Lee's original Progressive Word Reveal**, disable it so the two don't double up. If you run the full **AnkiBlitz** suite, this feature is already in it — don't install both.

## Using it

**Tools ▸ Progressive Word Reveal ▸ Settings…** — speed, mode, chunk size, reveal key, stop-audio-on-reveal, TTS sync, exclusions, and a live preview.

## The AnkiBlitz suite

- [AnkiBlitz](https://ankiweb.net/shared/info/178722601) — all four features in one add-on.
- [AnkiBlitz Core](https://ankiweb.net/shared/info/1174429600) — sessions, Pomodoro, Focus Lock, profiles, music.
- [Adaptive Speed Focus (aSFM)](https://ankiweb.net/shared/info/1148593203) — the adaptive auto-reveal timer alone.
- [Progressive Word Reveal](https://ankiweb.net/shared/info/972193513) — this add-on: the word-by-word fade alone.

Core + aSFM + Progressive Word Reveal together equal the full AnkiBlitz. Don't run AnkiBlitz alongside any of the other three — it already contains them.

## Notes

- Reworks **Patrick Lee's Progressive Word Reveal** ([patricklee.com.au](https://www.patricklee.com.au/)); licensed under the GNU AGPLv3.
- Tested on Anki 2.1.50+ (Qt6).
