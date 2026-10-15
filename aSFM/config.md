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
| `difficulty_weight` | Max ± swing applied from the card's FSRS difficulty, or its ease and lapses on SM-2 (0 = ignore difficulty). |
| `show_countdown` | Show the thin depleting countdown bar while waiting. |
| `countdown_warning_colour` | Run the bar in Anki's blue, then turn it red at the warning point. Off = the original amber-to-red gradient. |
| `warning_sound` | Play an alert before the answer auto-shows. |
| `warning_at_percent` | Warn (sound and/or colour) once this % of the delay has elapsed. |
| `pause_key_enabled` | A key that freezes the timer on the current card. |
| `pause_key` | Which key that is (default `p`). It can be the same key as Progressive Word Reveal's reveal key: while the question is still fading in, the press finishes the fade; after that it pauses. |
| `learn_my_pace` | **Off by default.** The consent switch: while it's off aSFM records nothing about your reviews, writes no pace file, and auto-tune doesn't run. Ticked on the welcome screen or in Settings ▸ Your pace. |
| `auto_tune_enabled` | Apply a personal pace multiplier (0.85–2×) from how you actually reveal cards. See *Learn my pace* below. |
| `target_timer_wins_percent` | How often the answer should appear before you've revealed it yourself (default 10%). Drives both auto-tune and calibration. |
| `more_time_button` | Show a small **More time** button above the countdown (with the pause key shown on it as a keycap). Same hold as the pause key, but visible — click it and the timer stops until you click (or press the key) again. Faint until hovered. |
| `excluded_note_types` / `excluded_decks` | Skip the timer for these (a parent deck covers its subdecks). |
| `fixed_time_enabled` | Use a set time (no word count) for picture / visual cards. |
| `fixed_time_base_seconds` | The set time for a picture card (difficulty still applies). |
| `fixed_time_note_types` / `fixed_time_decks` | Which cards count as picture cards. |
| `one_by_one_mode` | Cloze one-by-one cards (AnKing "One by one" field): `"per_cloze"` = a short timer per cloze, each uncovering the next; `"multiplier"` = the normal whole-card delay × `one_by_one_multiplier`; `"off"` = time them like any other card. Per-cloze needs the AnKing template to do its one-by-one on the front; with the stock auto-flip template it falls back to one whole-card timer. |
| `one_by_one_seconds_per_cloze` / `one_by_one_seconds_per_word` | Per cloze: this many seconds, plus this many per word of that cloze's answer, then the card's familiarity / difficulty modifiers. The first cloze also gets the normal question-reading time. |
| `one_by_one_max_cloze_seconds` | The longest any single cloze waits. |
| `one_by_one_multiplier` | Multiplier mode: the whole-card delay × this. |
| `picture_types_autodetected` | Set once aSFM has looked for picture note types (image occlusion, "Image Q/A", "IO…", or a `Question Mask` / `OccludedImage` field) and filled them into `fixed_time_note_types`. It only fills an empty list; a list you've set is never touched. The picker also has a **Tick picture types** button. |
| `show_welcome` | Show the welcome / calibration window on the next start. Set back to `true` to see it again (or use the Tools menu). |

### Learn my pace

Nothing below happens until you turn on `learn_my_pace`. Without it, aSFM
times cards from your settings alone, and **Calibrate** can still work from
Anki's own review history: read on request, nothing saved.

Auto-tune scales every delay by a learned pace until the timer beats you on
about `target_timer_wins_percent` of cards. It is deliberately gentle: each
card you reveal first shortens the timer ~0.5%, each timeout or More time
lengthens it ~5%, and it never goes below 0.85×. If you normally let the
timer run, timeouts aren't counted as "too short" and the pace drifts back to
1.0×.

Review, learning, new and picture cards each keep **their own pace**, so a
slow run of new cards can't lengthen your review timer (a kind with nothing
learned yet follows the review pace). One-by-one cards aren't auto-tuned.
Calibrating resets the review pace to 1.0× and rescales the learning and new
paces so their real timings don't jump.

**Calibrate from my reviews…** (in Settings) fits `base_seconds`,
`seconds_per_word` and, if it's on, `seconds_per_answer_word` to your reveal
times, and shows the suggestion before anything changes. Pick where from:

- **What aSFM has seen** — your measured reveals, once there are 150 you
  revealed yourself (needs `learn_my_pace`).
- **Anki's review history** — works from day one. It reads graded reviews from
  the last 180 days (up to 1,200 cards, skipping excluded note types and
  decks) and sorts them into review / learning / new / picture / one-by-one by
  the same rules as the timer. Anki times a review until you grade it, so the
  answer-side time comes off each: your own median reveal-to-grade gap once
  `learn_my_pace` has measured 30, else 1.5 s + 0.1 s per answer word. Because
  the slow tail of the review log is mostly answer-side time, it fits the
  median and scales it to the target percentile by the usual spread of reveal
  times (yours once measured). The one-by-one per-cloze settings can't come
  from history, which only times the whole card.

Once each kind has enough cards (from either source), Calibrate also suggests, each as its own
tickable row: `unfamiliar_multiplier` and `new_multiplier` (40 cards of that
kind), `difficulty_weight` (150 review cards spread over difficulties; it fits
whether harder cards really take you longer, and never goes below 0),
`fixed_time_base_seconds` (30 picture cards), and the one-by-one per-cloze /
per-word or multiplier settings (30 one-by-one cards). Each is fitted from that
kind's own times against the base / per-word formula being applied, so
applying one resets that kind's pace to 1.0×.

What's learned is kept per profile in `user_files/pace_<profile>.json`:
the paces, a compact histogram of reveal times, a per-kind tally (by length
and difficulty, for fitting the learning / new / difficulty / picture settings
later), how long the answer is up before you grade (for calibrating from
Anki's review history), and a one-line summary per session. Counts only, never card content or which cards, a few KB at most,
and never sent anywhere. Turning learning off stops recording at once; the
file is left in place so turning it back on picks up where you were.

### Word counting

The per-word term counts only the text a reviewer actually *sees* on the question
side: `<script>`/`<style>` blocks, inline-hidden elements, and AnKing-style tag
chips / hint / extra chrome are dropped so they don't inflate the timer.

### The warning sound

The bundled alert is `sounds/alert.flac`. To use your own, drop an `alert.flac`,
`.ogg`, `.opus` or `.wav` into the add-on's `user_files/` folder — it overrides
the bundled one and survives updates. An `alert.mp3` works too, but only where
Anki's external media player (mpv) runs: the reviewer can't decode MP3 itself.

### Running alongside Progressive Word Reveal

aSFM and Progressive Word Reveal don't depend on each other, but when both are
installed they cooperate the way the full AnkiBlitz does:

- **The answer waits for the question.** If the timer runs out while words are
  still fading in, the answer shows as soon as the fade finishes, never over a
  half-shown question.
- **One key can do both.** With the default `p` for both, the first press
  finishes the fade and the next one pauses the timer.
- **Clicking More time is not a click on the card.** It holds the timer without
  also skipping the fade or cutting the card's audio.
