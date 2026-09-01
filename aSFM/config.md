# Adaptive Speed Focus (aSFM) — settings

All options are editable from **Tools ▸ Adaptive Speed Focus ▸ Settings…**; this
file documents the raw `config.json` keys behind them. Everything is read live
per card, so a change takes effect on the next card.

The reveal delay is computed as:

```
delay = (base_seconds + seconds_per_word × words) × familiarity × difficulty
delay = clamp(delay, min_delay_seconds, max_delay_seconds)
```

| Key | Meaning |
|-----|---------|
| `enabled` | Master switch. When false, the timer never runs. |
| `base_seconds` | Fixed thinking budget added to every card. |
| `seconds_per_word` | Reading budget scaled by the question's visible word count. |
| `min_delay_seconds` / `max_delay_seconds` | Floor / ceiling for the computed delay. |
| `unfamiliar_multiplier` | Multiplier for learning / relearning cards. |
| `new_multiplier` | Multiplier for genuinely new cards. |
| `enable_on_new` | Run the timer on new cards at all. |
| `difficulty_weight` | Max ± swing applied from the card's FSRS difficulty (0 = ignore difficulty). |
| `show_countdown` | Show the thin depleting countdown bar while waiting. |
| `warning_sound` | Play an alert before the answer auto-shows. |
| `warning_at_percent` | Warn once this % of the delay has elapsed. |
| `pause_key_enabled` | A key that freezes the timer on the current card. |
| `pause_key` | Which key that is (default `p`). Give it a different key from Progressive Word Reveal's if you run both. |
| `more_time_button` | Show a small **More time** button above the countdown. Same hold as the pause key, but visible — click it and the timer stops until you click (or press the key) again. Faint until hovered. |
| `excluded_note_types` / `excluded_decks` | Skip the timer for these (a parent deck covers its subdecks). |
| `fixed_time_enabled` | Use a set time (no word count) for picture / visual cards. |
| `fixed_time_base_seconds` | The set time for a picture card (difficulty still applies). |
| `fixed_time_note_types` / `fixed_time_decks` | Which cards count as picture cards. |

### Word counting

The per-word term counts only the text a reviewer actually *sees* on the question
side: `<script>`/`<style>` blocks, inline-hidden elements, and AnKing-style tag
chips / hint / extra chrome are dropped so they don't inflate the timer.

### The warning sound

The alert is `sounds/alert.mp3`. To use your own, drop an `alert.mp3` into the
add-on's `user_files/` folder — it overrides the bundled one and survives updates.
