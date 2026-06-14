# Progressive Word Reveal — settings

All options are editable from **Tools ▸ Progressive Word Reveal ▸ Settings…**;
this file documents the raw `config.json` keys. Read live per card.

| Key | Meaning |
|-----|---------|
| `enabled` | Master switch. |
| `words_per_second` | Reading speed; total reveal time scales with the question's visible length. |
| `reveal_mode` | `"words"` (one at a time) or `"chunks"` (groups of N). |
| `chunk_words` | Words revealed together per step in chunk mode. |
| `reveal_on_answer` | Also fade the answer side in (otherwise it shows at once). |
| `reveal_key` | A key (besides clicking) that reveals everything instantly. |
| `tts_auto_match` | Per card, drive the reveal speed from the card's active `{{tts}}` tag. |
| `tts_base_wpm` | The `say` base words-per-minute (macOS = 170 × speed). |
| `excluded_note_types` / `excluded_decks` | Skip the reveal for these (a parent deck covers its subdecks). |

### What counts as a word

Only the text a reviewer actually **sees** on the question side is faded in:
`<script>`/`<style>` blocks, MathJax, and anything hidden by CSS (including
AnKing-style tag chips and hint/extra chrome hidden by the note's stylesheet) are
skipped, so the reveal tracks what you read — not invisible markup.

### TTS sync

On macOS, Anki's `say` voice runs at `tts_base_wpm × speed` words/min, so the
reveal rate that matches a card's `{{tts}} speed=` is exact. With `tts_auto_match`
on, each card with an active TTS tag overrides your reading speed so the words
finish in step with the voice; cards without active TTS use your set speed.
