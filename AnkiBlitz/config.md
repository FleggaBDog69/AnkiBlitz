# AnkiBlitz

All settings are edited from **Tools ▸ AnkiBlitz ▸ Settings…** (a tabbed
window). Editing the raw JSON here is optional.

- **`enabled`** — master switch. When `false`, all three tools are off.

## `speed_focus` — adaptive auto-reveal
Reveals the answer automatically after a computed delay. **Never grades** the
card. The delay = `(base_seconds + seconds_per_word × words) × modifiers`,
clamped to `[min_delay_seconds, max_delay_seconds]`.

- `enabled` — turn adaptive auto-reveal on/off.
- `base_seconds` — fixed thinking budget added to every card.
- `seconds_per_word` — extra time per word in the question.
- `min_delay_seconds` / `max_delay_seconds` — floor / ceiling for the delay.
- `unfamiliar_multiplier` — multiply the delay for learning / relearning cards.
- `new_multiplier` — multiply the delay for genuinely new cards (used instead of
  `unfamiliar_multiplier` for them).
- `enable_on_new` — when `false`, new cards get no auto-reveal timer at all.
- `difficulty_weight` — how much the card’s **FSRS difficulty** (1–10) nudges
  the delay. It’s a bounded ± swing: `0.10` means the hardest cards get at most
  +10% and the easiest about −8%, centred on an average card. Cards with no FSRS
  state (e.g. brand-new cards) fall back to SM-2 ease. `0` = ignore difficulty.
- `min_post_seconds` — the answer can't auto-show until at least this many
  seconds after the progressive reveal has finished, so the timer never cuts the
  reading short.
- `show_countdown` — show a depleting countdown bar while waiting (off by default).
- `warning_sound` — play an alert before the answer auto-shows.
- `warning_at_percent` — the alert fires once this share of the delay has elapsed
  (e.g. `60` leaves the final 40% as a heads-up). Replace `sounds/alert.mp3`, or
  drop `alert.mp3` in `user_files/`, to change the sound.
- `pause_key_enabled` — allow a key to pause/resume the auto-reveal countdown.
- `pause_key` — that key (default `p`). Press it to freeze the countdown and its
  warning on the card you're on; press again to pick up where it stopped. The
  pause **sticks across cards** and is labelled on screen until you release it.
  It may be the *same* key as `word_reveal.reveal_key` (both default to `p`):
  while words are still fading in the key reveals them, and once the question is
  fully shown the same key pauses the timer.
- `excluded_note_types` / `excluded_decks` — skip the auto-reveal timer for these
  (a parent deck also covers its subdecks); those cards review normally.
- `fixed_time_enabled` — turn the picture-card mode on/off.
- `fixed_time_base_seconds` — the **set** reveal time for a picture/visual card.
- `fixed_time_note_types` / `fixed_time_decks` — cards matching these are treated
  as picture cards: they ignore word count **and** the new/learning multipliers,
  getting `fixed_time_base_seconds` with only the difficulty weight as a modifier
  (image cards have nothing to read). Matched like the exclusion lists. **These
  four keys live outside the profile system — the choice of which cards are
  "visual" endures across every profile.**

> Word count counts only the text a reviewer actually *sees*: hidden fields,
> `display:none` content and the tag chips (`{{clickable::Tags}}`) common on
> AnKing-style note types are excluded, so a 15-word stem is timed as 15 words,
> not inflated by its tags/extras.

## `word_reveal` — progressive reveal
- `enabled` — turn progressive reveal on/off (front side).
- `words_per_second` — reading speed; total time scales with question length.
- `reveal_mode` — `words` (one word at a time) or `chunks` (reveal several words
  together).
- `chunk_words` — how many words appear together per chunk in `chunks` mode.
- `reveal_on_answer` — also fade in the answer side.
- `reveal_key` — key (besides clicking) that reveals everything instantly.
- `stop_audio_on_reveal` — revealing everything early also stops the card's audio
  (TTS / `[sound:]` and any embedded HTML media). The audio stops rather than
  pausing; the next card plays normally.
- `tts_auto_match` — when on, a card with active `{{tts}}` overrides
  `words_per_second` so the reveal finishes in step with the voice. macOS `say`
  runs at `tts_base_wpm × speed` words/min, so the matching reveal rate is
  `tts_base_wpm × speed / 60` words/sec. Cards without active TTS are unaffected.
- `tts_base_wpm` — base words/min the TTS voice uses at `speed=1.0` (Anki's macOS
  default is `170`); change only if your platform/voice differs.
- `excluded_note_types` / `excluded_decks` — skip the reveal for these (a parent
  deck also covers its subdecks).

## `quick_start` — auto-launch a Blitz each day
On the **first open of the day**, AnkiBlitz can start a Blitz for you so you get
straight into reviewing. Off by default.

- `enabled` — turn the daily auto-launch on/off.
- `launch_style` — `countdown` shows a cancelable **3-2-1** screen first;
  `immediate` jumps straight into the Blitz with no prompt.
- `countdown_seconds` — how long the 3-2-1 countdown lasts (countdown style only).
- `mode` — Quick Start's own preset mode: `cards` | `time` | `fraction`.
- `target` — the preset value: card count, minutes, or the fraction denominator
  (`1/n`), depending on `mode`.
- `min_due` — don't auto-launch unless at least this many cards are due.
- `relaunch_on_new_day` — if Anki is left open across a day rollover, relaunch the
  daily Blitz the first time you bring Anki to the foreground that day. It opens
  **paused** (no auto-reveal, clock at 0:00) until your first key/click.
- `relaunch_after_hour` — the earliest local hour (0–23) that the foreground
  relaunch may fire; default `5` (5 AM).

## `momentum` — finish what you started
When you leave the reviewer **near the end** of a Blitz, AnkiBlitz asks whether
you want to keep going (with a time estimate) instead of silently cancelling.
Leaving when you're *not* near the end still cancels with no record, as before.

- `enabled` — turn the near-end intercept on/off.
- `near_end_cards` — for card / fraction Blitzes, "near the end" means within this
  many cards of the target.
- `near_end_seconds` — for time Blitzes, "near the end" means within this many
  seconds of the deadline.

## `pomodoro` — work blocks paired with breaks
A Pomodoro run chains **work blocks** (each an ordinary Blitz) with **breaks**.
Start one from **Tools ▸ AnkiBlitz ▸ Start Pomodoro…** (`Ctrl+Shift+P`) or the
on-screen widget. Each break shows a big countdown plus a preview of the next
Blitz; a longer break lands every few blocks. Leaving the reviewer during a work
block ends the whole run; *during a break* you can leave freely — **Step away**
(or `Esc`) hides the break screen with its countdown still running, so ducking
out to another app costs you nothing. A run you stop part-way through can be
**resumed** later the same day.

- `enabled` — whether Pomodoro is offered (menu + widgets).
- `work_mode` — the work-block Blitz mode: `time`, `cards`, or `fraction`.
- `work_target` — minutes / cards / denominator, per `work_mode` (default 25 min).
- `break_minutes` — short break length.
- `long_break_enabled` — take a longer break every few blocks.
- `long_break_every` — a long break after every Nth work block.
- `long_break_minutes` — long break length.
- `cycles` — stop after this many work blocks (`0` = unlimited).
- `auto_return_level` — what happens when a break's countdown ends:
  `0` notify only (the next Blitz you start resumes the run), `1` prompt to start,
  `2` auto-start the next block (only when Anki is the active window, else it
  degrades to notify), `3` raise Anki to the front then auto-start.
- `break_sound` — chime when a break starts and ends.
- `break_mute_audio` — silence card audio for the length of a break. A work block
  ends on an *answer*, so Anki carries on and renders the next card behind the
  break screen — playing its `[sound:]` / `{{tts}}` at you while you're resting.
  This stops whatever is already sounding and drops the tags of anything rendered
  during the break; *Replay Audio* (`R`) still works, and the card plays normally
  once the reviewer comes back.
- `daily_goal` — a blocks-per-day target shown on the break screen (`0` = off).
- `end_summary` — show an end-of-run summary screen instead of a tooltip.
- `carry_forward` — greet the next work block with a tooltip of your last break
  note (today's note only — an older one isn't where you left off).
- `resume_same_day` — offer to resume an unfinished run from earlier **today**.
  Stopped after 2 of 3 blocks? The next start offers to pick up at block 3 with
  the same cycle and the same fraction split, and the deck-list widget's button
  reads "Resume · 2/3 blocks done". A run that used up all its blocks is done and
  is never offered.
- `break_show_timeline` / `break_show_journal` / `break_show_focus_rating` /
  `break_show_tips` / `break_show_browser` / `break_show_add_kg` /
  `break_allow_extend` — toggle each break-screen element so the screen stays as
  calm or as full-featured as you like.
- `break_allow_step_away` — the **Step away** button, and `Esc`, hide the break
  screen instead of ending the run: the countdown keeps going, the modal block
  lifts, and the screen returns by itself when Anki is next the active app. Only
  the explicit *End Pomodoro* button ends a run. With this `false`, `Esc` ends
  the Pomodoro (the old behaviour).
- `break_pill` — while you're stepped away, show a small always-on-top countdown
  you can click to go straight back to the break screen.

## `music` — keep study music inside Anki
A small **in-app player** pointed at a music service — you browse within the
service (SoundCloud / YouTube Music) and hit play, or use the **⏮ ⏯ ⏭** toolbar
buttons to skip and pause without touching the page. No address bar and no
back/forward, so you stay on the music sites; YouTube Music can't wander off into
regular YouTube. Three homes: a **built-in box** on the Pomodoro break
screen, a **built-in box** pinned below the rail on the deck list (hidden once
you start reviewing), and a **floating window** during reviews (toggle with
**Tools ▸ AnkiBlitz ▸ Music player**, `Ctrl+Shift+M`). None live inside the
reviewer/deck webviews, so they keep playing as Anki redraws. Off by default.

- `enabled` — master switch for the player (everything below is inert when off).
- `show_on_break` — show the built-in music box on the break screen.
- `show_dropdown` — allow the floating review window (menu item + `Ctrl+Shift+M`).
- `show_on_home` — show the built-in music box on the deck list (below the rail).
- `service` — which site the quick-jump opens by default: `soundcloud` |
  `youtube`.
- `last_url` — the last page you were on, remembered so the player reopens there
  (set automatically as you browse).

Each box has a **—** button to minimise it to just its toolbar (music keeps
playing). **Login persists** across restarts — cookies live in a dedicated
profile under `user_files/music_profile/`. **SoundCloud** plays full tracks
(login optional) and is the reliable choice. **YouTube Music** only plays if your
Anki build ships the proprietary codecs (H.264/AAC), and Google sometimes blocks
sign-in inside embedded browsers.

## `focus` — Focus Lock + Focus Score
Discipline and scoring for a study session. **Focus Lock** makes leaving harder;
**Focus Score** rates each finished Blitz 0–100. Focus Lock applies to a running
Blitz always, and to ordinary review sessions when `apply_to_reviews` is on; the
Focus Score is shown for finished Blitzes.

- `enabled` — master switch for the Focus features.
- `apply_to_reviews` — also lock ordinary (non-Blitz) review sessions, not just
  Blitzes. The same `lock_level` rules apply.
- `lock_level` — how hard it is to leave:
  - `0` — no lock (leaving is free).
  - `1` — a confirm prompt before you may leave.
  - `2` — trying to leave forces you to clear `lock_min_cards` **more** cards from
    that point; once you've cleared them, the next leave attempt asks you to
    confirm. (Choosing "keep going" starts a fresh lap next time.)
  - `3` — you can't leave until you're finished: the Blitz target, or — in a
    normal review — all your due cards.
  Alt-tabbing to another app still cancels a Blitz at levels 0–2 (that's the
  point); at level 3 the session is kept and Anki is pulled back to the front
  (in a normal review, level 3 likewise pulls Anki back). At the hard levels
  (2–3) the Browse, Add and Stats windows are also blocked — they'd otherwise be
  a side door out of the reviewer — and you're pulled back to the cards.
- `lock_min_cards` — the number of extra cards a level-2 leave attempt forces.
- `score_enabled` — compute and show the Focus Score (completion screen + stats).
- `score_include_accuracy` — count accuracy as one of the score components.
  (Suppressed anyway when `sprint.hide_all_accuracy_stats` is on.)
- `idle_threshold_seconds` — a pause between answers longer than this counts the
  extra time as idle (feeds the engagement component and the idle stat).
- `target_seconds_per_card` — your reference pace; hitting it (or faster) scores
  full marks on the speed component.

## `home_widget` — on-screen launch panels
Compact AnkiBlitz panels injected into Anki's own screens.

- `enabled` — show the rail on the deck list (home): per-mode quick-launch Blitz
  buttons + a Start Pomodoro button + a ⚙ settings button.
- `show_on_overview` — show the rail on a deck's overview screen (acts on that deck).
- `presets` — the rail's quick-launch buttons, each `{"mode": "time"|"cards"|
  "fraction", "value": N}` (minutes / cards / denominator). Each starts that Blitz
  immediately. Empty `[]` falls back to the three Blitz defaults. Mix freely —
  e.g. all card counts, or all timers. Edit them in Settings ▸ Pomodoro ▸ On-screen
  widgets.

`pomodoro.auto_return_level` default is **2 (auto-start)** — when a break ends or
you skip it, you go straight back to the cards with no prompt.

## `sprint` — Blitz sessions
A Blitz is a focused review session run from **Tools ▸ AnkiBlitz ▸ Start Blitz…**
(`Ctrl+Shift+S`) in one of three modes. It ends when the target/clock is met, or
when the due queue empties; leaving the reviewer or losing focus cancels it with
no record.

- `enabled` — turn Blitz mode on/off.
- `default_mode` — `cards` | `time` | `fraction` (which mode the start dialog opens on).
- `count_mode` — what the progress bar counts, so it can't mislead:
  - `unique` — distinct cards (an Again-requeued card counts once).
  - `answers` — every grade press (re-reviews included).
- `default_target` / `quick_picks` — card-count default and quick buttons.
- `default_time_minutes` / `time_quick_picks` — time-mode default and quick buttons.
- `fraction_quick_picks` — denominators for fraction-of-due (e.g. `[2, 3]` → ½, ⅓);
  the card target = `ceil(due ÷ n)` computed when the Blitz starts.
- `card_source` — `current_queue` | `pick_deck`.
- `show_*` — what to display during a Blitz and on the completion screen.
- `track_pb_*` — which personal bests to record.
- `hide_all_accuracy_stats` — master anti-pressure switch; hides every
  accuracy/streak/again figure (including on the end-of-Blitz summary) regardless
  of the individual toggles.

## `presets` — profiles (feel snapshots)

A **profile** flips the *feel* of reviewing in one click — the adaptive
auto-reveal pace, Focus Lock, the near-end momentum nudge, and the
anti-pressure / progress display. Switch from **Settings ▸ Profiles** or
**Tools ▸ AnkiBlitz ▸ Profile**.

- Three **built-ins** ship in code (not stored here): **Default** (the everyday
  review feel and the active profile out of the box — relaxed ~7s auto-reveal, a
  quiet countdown, no lock, a gentle near-end nudge), **Blitz** (a committed run —
  brisk auto-reveal, countdown + warning, a *penalty* Focus Lock, full HUD with a
  completion chime), and **Relaxed** (low friction for studying with mates or
  half-distracted — generous auto-reveal, no countdown/warning pressure, no lock,
  no nagging). A saved profile of the same name *shadows* a built-in; delete the
  copy to restore the original.
- A profile governs **feel only**. It deliberately **does not** touch the
  **session shape** (Blitz `default_mode` / `default_target` / `count_mode` /
  time, Quick Start, Pomodoro work blocks — you pick those in the Start dialog
  each launch), the **word-reveal speed** (one reading pace across all profiles),
  the **music** player, your note-type / deck exclusion lists, the fixed-time
  picture lists, all `*_quick_picks`, or the top-level `enabled` master switch.
  The exact whitelist of keys a profile writes is `engine/presets.py` →
  `PROFILE_SPEC` (only `speed_focus`, `focus`, `momentum`, and `sprint`'s display
  toggles).
- The profile picker (Settings ▸ Profiles, and the Tools ▸ AnkiBlitz ▸ Profile
  submenu) shows each profile's **key settings** — auto-reveal range, Focus Lock
  level, momentum nudge, anti-pressure — so you can see what it does before
  applying.
- On first run your existing settings are captured as a profile named
  **“My setup”** and made active, so adopting profiles never loses your tuning.
- Applying a profile is always an **explicit overwrite** of those feel settings —
  it is never auto-applied.

Keys:
- `active` — name of the profile last applied (informational).
- `saved` — `name → snapshot`; holds your saved profiles and the captured
  “My setup”. Built-ins are not stored here. Edit via the UI, not by hand.

---

## `synapse` — living alongside the SynapsePro add-on

If the **SynapsePro** add-on is installed, AnkiBlitz can borrow its colours so
the two read as one product, and stand down the parts it duplicates. Every key
here is inert without it: no SynapsePro, no change — AnkiBlitz renders exactly
as it does standalone.

All of it is a **soft bridge** (`engine/theme_bridge.py`, the only module that
knows SynapsePro exists). SynapsePro is never a dependency, nothing is imported
by name (its package is `SynapsePro1`, a checkout is often symlinked as
`SynapsePro`, and an AnkiWeb install is a numeric folder — it's resolved at
runtime by manifest name), and AnkiBlitz **never writes into SynapsePro's
config**.

Keys:
- `sidebar_buttons` *(default on)* — add AnkiBlitz's three icons to SynapsePro's
  launcher strip: 🍅 Pomodoro (start, or resume an unfinished run from earlier
  today), ⚡ the AnkiBlitz panel, ⚙ settings. **SynapsePro is not modified** —
  the buttons are injected into the live sidebar at runtime, carrying the
  property its own stylesheet keys off so they pick up its hover and accent
  colours. It rebuilds that strip whenever its settings are applied, so they're
  put back automatically on the next screen change.
- `hide_rail` *(default on)* — drop AnkiBlitz's floating deck-list rail once the
  sidebar buttons are there. One AnkiBlitz, one place. Off = both.
- `theme_bridge` *(default on)* — take colours from SynapsePro's palette: the
  panel, the reveal overlay and the Pomodoro break screen. Follows along live
  when you change SynapsePro's colour theme (ocean / orchid / forest …) and when
  Anki flips light↔dark. **Only colours change** — no layout, sizing or
  behaviour. Off = AnkiBlitz's own colours.
- `theme_settings` *(default on)* — also recolour AnkiBlitz's Settings window
  (tabs, inputs, buttons) from that palette, the way SynapsePro styles its own
  native dialogs. **Checkbox and radio indicators are deliberately left native**:
  a mis-specified indicator reads as permanently unchecked, and a settings window
  whose state you can't read is worse than one that doesn't match. Applies next
  time you open Settings.
- `match_font` *(default off)* — also adopt SynapsePro's `FONT_FAMILY`. Off by
  default: the colours usually carry the resemblance on their own.
- `defer_music` *(default on)* — SynapsePro ships a background music player, so
  AnkiBlitz hides its own: the rail button, the break-screen box and
  `Ctrl+Shift+M` all step aside. Nothing is removed — turn this off (or uninstall
  SynapsePro) and AnkiBlitz's player is back, settings intact.
- `pomodoro_notice` *(default on)* — SynapsePro has a Pomodoro of its own. If
  both are switched on, AnkiBlitz says so **once** (on the next Pomodoro you
  start) and offers to open SynapsePro's settings. It won't flip the switch for
  you.
- `_pomodoro_warned` — internal; set once that notice has been shown. Reset it to
  `false` to see the notice again.
