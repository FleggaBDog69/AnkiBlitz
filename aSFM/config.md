# Adaptive Speed Focus (aSFM) — settings

All options are editable from **Tools ▸ Adaptive Speed Focus ▸ Settings…**; this
file documents the raw `config.json` keys behind them. Everything is read live
per card, so a change takes effect on the next card.

The reveal delay is computed as:

```
delay = (base_seconds + seconds_per_word × words + answer_term) × familiarity × difficulty
answer_term = min(seconds_per_answer_word × answer_words, max_answer_seconds)
delay = clamp(delay, min_delay_seconds, max_delay_seconds)
```

| Key | Meaning |
|-----|---------|
| `enabled` | Master switch. When false, the timer never runs. |
| `base_seconds` | Fixed thinking budget added to every card. |
| `seconds_per_word` | Reading budget scaled by the question's visible word count. |
| `seconds_per_answer_word` | Extra time per word the answer side adds (cloze: the hidden text; front/back: the answer field). `0` = off. |
| `max_answer_seconds` | The most the answer term can ever add. |
| `min_delay_seconds` / `max_delay_seconds` | Floor / ceiling for the computed delay. |
| `unfamiliar_multiplier` | Multiplier for learning / relearning cards. |
| `new_multiplier` | Multiplier for genuinely new cards. |
| `enable_on_new` | Run the timer on new cards at all. |
| `difficulty_weight` | Max ± swing applied from the card's FSRS difficulty (0 = ignore difficulty). |
| `show_countdown` | Show the thin depleting countdown bar while waiting. |
| `countdown_warning_colour` | Run the bar in Anki's blue, then turn it red at the warning point. Off = the original amber-to-red gradient. |
| `warning_sound` | Play an alert before the answer auto-shows. |
| `warning_at_percent` | Warn (sound and/or colour) once this % of the delay has elapsed. |
| `pause_key_enabled` | A key that freezes the timer on the current card. |
| `pause_key` | Which key that is (default `p`). Give it a different key from Progressive Word Reveal's if you run both. |
| `auto_tune_enabled` | Learn a personal pace multiplier (0.85–2×) from how you actually reveal cards. See *Learn my pace* below. |
| `target_timer_wins_percent` | How often the answer should appear before you've revealed it yourself (default 10%). Drives both auto-tune and calibration. |
| `more_time_button` | Show a small **More time** button above the countdown. Same hold as the pause key, but visible — click it and the timer stops until you click (or press the key) again. Faint until hovered. |
| `excluded_note_types` / `excluded_decks` | Skip the timer for these (a parent deck covers its subdecks). |
| `fixed_time_enabled` | Use a set time (no word count) for picture / visual cards. |
| `fixed_time_base_seconds` | The set time for a picture card (difficulty still applies). |
| `fixed_time_note_types` / `fixed_time_decks` | Which cards count as picture cards. |

### Learn my pace

Auto-tune scales every delay by a learned pace until the timer beats you on
about `target_timer_wins_percent` of cards. It is deliberately gentle: each
card you reveal first shortens the timer ~0.5%, each timeout or More time
lengthens it ~5%, and it never goes below 0.85×. If you normally let the
timer run, timeouts aren't counted as "too short" and the pace drifts back to
1.0×.

**Calibrate from my reviews…** (in Settings) fits `base_seconds`,
`seconds_per_word` and, if it's on, `seconds_per_answer_word` to your reveal
times, and shows the suggestion before anything changes. It uses what aSFM
has measured once it has seen 150 cards you revealed yourself; before that it
makes a rough estimate from Anki's review history.

What's learned is kept per profile in `user_files/pace_<profile>.json`:
the pace, a compact histogram of reveal times, and a one-line summary per
session. Counts only, never card content, and a few KB at most.

### Word counting

The per-word term counts only the text a reviewer actually *sees* on the question
side: `<script>`/`<style>` blocks, inline-hidden elements, and AnKing-style tag
chips / hint / extra chrome are dropped so they don't inflate the timer.

### The warning sound

The bundled alert is `sounds/alert.flac`. To use your own, drop an `alert.flac`,
`.ogg`, `.opus` or `.wav` into the add-on's `user_files/` folder — it overrides
the bundled one and survives updates. An `alert.mp3` works too, but only where
Anki's external media player (mpv) runs: the reviewer can't decode MP3 itself.
