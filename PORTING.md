# Porting notes — what the spin-offs still owe AnkiBlitz

`AnkiBlitz/` is where features get built. `ankiblitz-core/`, `aSFM/` and
`progressive-reveal/` are **independent copies**, not symlinks or imports — a fix
in AnkiBlitz does nothing to them until it's carried across by hand.

This file tracks what's outstanding. **Clear it before the next push**, or ship
AnkiBlitz alone and leave the spin-offs on their current release.

---

## Cleared 2026-08-01

Items 1–7 are **ported**. Items 8–9 are AnkiBlitz-only by decision (below).

| # | Change | Core | aSFM | PWR |
|---|--------|:----:|:----:|:---:|
| 1 | "Finish all due" button fix | ✅ | — | — |
| 2 | Break screen: step away / floating pill | ✅ | — | — |
| 3 | Resume an unfinished run from earlier today | ✅ | — | — |
| 4 | Break journal: today's entry only | ✅ | — | — |
| 5 | Silence card audio during a break | ✅ | — | — |
| 6 | Pause key for the auto-reveal timer | — | ✅ | — |
| 7 | Key-handler guards (modifiers, typing) | — | ✅ | ✅ |
| 8 | SynapsePro bridge (`engine/theme_bridge.py`) | n/a | n/a | n/a |
| 9 | QComboBox escape-hatch fix in `theme_bridge.py` | n/a | n/a | n/a |

**One correction to the recipe below, found doing it.** `engine/pomodoro.py` is
**no longer safe to `cp` into Core** — the SynapsePro bridge is threaded through
it (`theme_bridge.color(...)` at ~10 sites, `music_available()`, and the
two-Pomodoro-timers notice). The port stripped all of it: each `color(token,
fallback)` collapsed to its fallback literal, `music_available()` to `True`
(Core has its own player and no SynapsePro awareness), and
`_maybe_warn_synapse_pomodoro` / `_open_synapse_settings` deleted outright.
`engine/stats.py` is still a clean copy. **Re-check both before trusting either
next time** — that assumption was true when it was written and isn't now.

The cross-add-on key clash (below) was settled with **option 1**: aSFM's pause-key
hint tells you to give it a different key from Progressive Word Reveal's if you
run both.

Item 9 landed in `AnkiBlitz/` on 2026-08-01 while porting the bridge to
Ankisstant. `QComboBox` was named in the shared `QLineEdit, …` rule, which isn't
conditional, while `_combo_arrow_rules` was — so a failed arrow render would have
styled the box and silently deleted its chevron, which is the exact failure the
fallback exists to prevent. It's now one all-or-nothing `_combo_rules`. Nothing
to carry to the spin-offs (they have no bridge), but if item 8 is ever ported,
port the fixed version.

Item 8 is **deliberately AnkiBlitz-only**. The spin-offs are meant to be small,
single-purpose add-ons; knowing about a fourth one isn't their job. If that ever
changes, the module is self-contained — copy it, add the `synapse` config
section, and route the colour call sites through it. See
`AnkiBlitz/SYNAPSE_THEME_BRIDGE.md` for what shipped, and
[PORTING_TO_SYNAPSE.md](PORTING_TO_SYNAPSE.md) for the general recipe and the
traps (sidebar injection, the Qt sub-control trap, resolving the package name).

### AnkiBlitz Core — 1–5

Core carries the whole Blitz/Pomodoro stack, so every Pomodoro fix applies. Two
of its files were **byte-identical** to AnkiBlitz's pre-change versions, so they
can be copied wholesale (re-check before you trust that):

    cp AnkiBlitz/engine/pomodoro.py ankiblitz-core/engine/pomodoro.py
    cp AnkiBlitz/engine/stats.py    ankiblitz-core/engine/stats.py

`engine/widgets.py` was identical too, but **don't** blind-copy it — AnkiBlitz's
version now calls into reveal-side settings. Port the two hunks by hand:

- the `blitz-all` branch moved **above** `action.startswith("blitz-")` in
  `_on_js_message`. Core has the same bug at `engine/widgets.py:162` — "Finish
  all due" matches the `blitz-` prefix, `int("all")` raises, and the click is
  swallowed;
- the resume-aware `_pomo_label()` ("🍅 Resume · 2/3 blocks done").

Then, by hand:

- **`__init__.py`** — import `pomodoro` and call `pomodoro.register()` (new; it
  registers the `av_player_will_play_tags` hook that mutes the break).
- **`config.py` / `config.json`** — add the four new `pomodoro` keys:
  `resume_same_day`, `break_allow_step_away`, `break_pill`, `break_mute_audio`.
  Core's config files differ from AnkiBlitz's (no `speed_focus` / `word_reveal`
  sections), so **merge the keys, don't copy the file**.
- **`settings.py`** — Pomodoro tab: the `resume_same_day` checkbox, the
  `break_mute_audio` checkbox, the two `_break_toggles` entries (`br_away`,
  `br_pill`), their hints, and the matching lines in the save dict. Core's
  `settings.py` is heavily trimmed — hand-merge only.
- **`README.md` / `config.md`** — the "During a Pomodoro break" section and the
  four key descriptions.

Core's `injection.pause_auto_reveal()` is a no-op there (its JS bundle has no
`pauseAuto`) — harmless, leave it.

### aSFM — 6

aSFM has **no key handling at all** right now. The pause key is a whole feature
port:

- **`web/asfm.js`** — `isTypingTarget()`, `onKeyDown()`, `toggleAutoPause()`,
  `showPausedBadge()` / `removePausedBadge()`, `freezeCountdown()` /
  `resumeCountdown(ms)`, and `armAutoTimers()` recording `autoDeadline` /
  `warnDeadline`. Drop the reveal-key branch from `onKeyDown` — aSFM has no
  progressive reveal, so it's the pause key alone.
- **`engine/injection.py`** — the sticky `_auto_paused` flag, the
  `autopause:1|0` bridge branch, and `payload["autoPaused"]` on both the question
  and answer payloads. Note the bridge prefix here is **`asfm:`**, not `focus:`.
- **`web/asfm.css`** — the `#fs-paused` badge (rename to the `asfm-` prefix to
  match the file's conventions).
- **`config.py` / `config.json`** — `speed_focus.pause_key_enabled`,
  `speed_focus.pause_key`.
- **`settings.py`** — the checkbox and the `_KeyCaptureEdit` for the key.

### Progressive Word Reveal — 7

Its key handler at `web/reveal.js:150` fires on the bare key with no guards:

```js
keyHandler = function (e) {
  if ((e.key || "").toLowerCase() === revealKey) revealAllWords();
};
```

That's the pre-fix version — `p` typed into Anki's type-in-the-answer box
reveals the question. Port the two guards from `AnkiBlitz/web/focus_suite.js:208`:
bail on `ctrl/meta/alt`, and bail when `e.target` is an `INPUT` / `TEXTAREA` /
`contentEditable`.

---

## Cleared 2026-08-04 — 10: stop card audio on an early reveal

| # | Change | Core | aSFM | PWR |
|---|--------|:----:|:----:|:---:|
| 10 | Reveal-all also stops the card's audio | n/a | n/a | ✅ |

Ported to PWR **the same day it was built**, so nothing is outstanding.

Skipping the reveal (key or click) now calls `stopCardAudio()`, which pauses any
`<audio>`/`<video>` in the card and pycmds Python to
`av_player.stop_and_clear_queue()`. Anki's own `[sound:]` / `{{tts}}` playback
lives in **mpv**, so JS can't touch it — it has to be a bridge call. New config
key `word_reveal.stop_audio_on_reveal` (PWR: top-level `stop_audio_on_reveal`),
default on, with a checkbox under the reveal-speed row.

Two decisions worth keeping:

- It **stops**, it doesn't pause. `av_player.toggle_pause()` exists, but mpv's
  pause is a persistent property — pause it and every later file loads paused
  too, so a missed un-pause leaves cards silently mute. Stopping has no state to
  get stuck in, and there's nothing to resume to anyway (you skipped ahead
  because you'd already read it).
- `stop_and_clear_queue()`, not just stop: a card with several audio tags would
  otherwise start the next one the moment the current one is cut.

PWR had **no JS→Python bridge at all** before this (its header said so). It now
registers `webview_did_receive_js_message` with the **`pwr:`** prefix — note the
prefix differs per add-on (`focus:` / `asfm:` / `pwr:`).

---

## Cleared 2026-09-01 — 11–13

| #  | Change | Core | aSFM | PWR |
|----|--------|:----:|:----:|:---:|
| 11 | Ambient progress bar outside a Blitz | ✅ | n/a | n/a |
| 12 | Focus-lock picker in the Start Blitz dialog | ✅ | n/a | n/a |
| 13 | Guided breathing pacer on the break screen | ✅ | n/a | n/a |

**Correction to the recipe, found doing the port.** `engine/focus.py`,
`engine/session.py` and — contrary to what you'd expect — `engine/sprint.py`
were all **byte-identical to AnkiBlitz apart from items 11–12**, so all three
were copied wholesale. sprint.py in particular carries nothing reveal-specific;
the assumption that it needed hand-merging was wrong. `engine/pomodoro.py` still
does need hand-porting (the theme bridge is threaded through it), and so does
`engine/breathing.py` — its one `theme_bridge.color("blue", "#3b82f6")` call
collapses to the literal. **Re-check all of this before trusting it next time:
it was true on 2026-09-01 and these files drift.**

Hand-merged, not copied: `engine/injection.py` (the `push_progress` ambient
fallback + `"ambient": False` — Core already imports `get_section` at module
level, so AnkiBlitz's local re-import isn't needed), `web/focus_suite.css` and
`web/focus_suite.js` (Core's are trimmed and use literal colours, not the
`var(--ab-*)` bridge vars — the ambient `.fs-bar` becomes a plain
`rgba(255,255,255,0.45)`), `config.py` / `config.json`, `settings.py`,
`config.md`, `README.md` and the `engine/__init__.py` module map.

Core's `focus.keeps_session_on_focus_loss` picked up the optional `s` argument
with the file copy, so the two call sites in its `sprint.py` are now correct too.

All three were Core-relevant only — aSFM and PWR have no session, no Focus Lock
and no Pomodoro. What each one touches, and why:

**11 — ambient bar.** With no Blitz running, an ordinary review session now gets
the same top strip, dimmed (`.fs-ambient`), labelled *All due*, filling against
the whole due pile. Touches: `session.py` (new `AmbientSession` + `_ambient` and
its three module functions), `sprint.py` (`_maybe_arm_ambient` /
`_ambient_wanted` / `ambient_payload`, plus the arm-on-enter, count-on-answer and
clear-on-leave hooks), `injection.py` (`push_progress` falls through to it),
`focus_suite.js` (the `p.ambient` class + `fs-label` span), `focus_suite.css`,
and the config key `sprint.show_bar_outside_blitz`.

The one decision worth keeping: the target is **live, not snapshotted** —
`cards_done + still_due`, recomputed on every push. A snapshot looks right until
a learning card requeues, at which point the bar is claiming ground it hasn't
taken; the live target instead pushes out by one and reaches 100% exactly when
the queue empties. That's the same "the bar must not lie" rule `count_mode`
already follows. It also deliberately shows **no** accuracy / Again / streak
regardless of the `sprint` toggles: a bar you never opted into is the worst place
to put grading pressure.

**12 — per-Blitz focus lock.** The Start dialog has a *Focus lock* combo
pre-filled from `focus.lock_level`. The choice rides on the session
(`BlitzSession.lock_level_override`) and is **never written back to config** —
`focus.effective_level(s, cfg)` is the new single resolver, and
`leave_decision` / `keeps_session_on_focus_loss` / `sprint._hard_locked` all go
through it. `keeps_session_on_focus_loss(cfg, s=None)` gained an optional second
arg and stays back-compatible with a cfg-only call. The override still bows to
`focus.enabled`. Blitzes started without the dialog (Quick Start, *Finish all
due*, widget buttons, Pomodoro blocks) pass `lock_level=None` and behave exactly
as before.

**13 — breathing pacer.** New self-contained `engine/breathing.py`:
`BreathingPacer` (a `QWidget` with a `paintEvent` and a ~30fps timer — no QML, no
web view, no assets) and `BreathingPanel` (the collapsed *🫁 Breathe* button that
expands into it). `pomodoro.py` embeds the panel under the micro-break tip and
stops it on `finished`. Config: `pomodoro.break_show_breathing` (in the existing
`_break_toggles` list, so settings load/save came free) and
`break_breathing_pattern`.

Notes for the port: the module imports `theme_bridge` for its accent colour, so
Core needs that one call collapsed to its fallback literal (`#3b82f6`) the same
way `pomodoro.py` was. `_tick` uses `while`, not `if`, to drain a stalled event
loop that hands it a jump longer than a whole phase; holds are drawn at the size
the preceding phase ended on, which is what makes box breathing read as a square
instead of a circle twitching at the corners.

---

## Cleared 2026-09-01 — 14: the "More time" button

| #  | Change | Core | aSFM | PWR |
|----|--------|:----:|:----:|:---:|
| 14 | Visible "More time" button for the auto-reveal hold | n/a | ✅ | n/a |

Built in AnkiBlitz and aSFM together, so nothing is outstanding. Core has no
auto-reveal timer and PWR has no hold, so neither has anywhere to put it.

Asked for on aSFM's AnkiWeb listing, against Glutanimate's Speed Focus Mode,
which has one. Reading his source (`1046608507/reviewer.py`) settles what it
should do: SFM's "More Time!" **stops the automated events for that card** and
its default hotkey is `p` — which is exactly the pause key we already had. The
feature that was missing was never the behaviour, only the **affordance**: a
keypress nobody can discover without reading the settings.

So this adds no second mechanism. `#fs-moretime` / `#asfm-moretime` is a quiet
pill above the countdown whose click calls the same `toggleAutoPause()`; the
paused badge becomes clickable in turn, and its wording is now built by
`resumeHint()` from whichever inputs are actually on.

Three decisions worth keeping:

- **It holds indefinitely; it does not add N seconds.** "Give me a moment" almost
  never means "give me exactly five more seconds", and an indefinite hold has one
  obvious way out. It also keeps one hold and one state rather than two.
- **The key and the button are gated separately** (`speed_focus.more_time_button`;
  top-level in aSFM) — the button is for people who don't know a key exists, and
  the key is for people who don't want a control over their cards.
- **A hold has to keep an input that can release it.** Turning both off while
  paused would strand the card behind a badge naming a key that no longer works,
  so the sticky flag is now dropped (permanently, not hidden) when neither is on.
  aSFM does this in `_pause_block`; AnkiBlitz in `injection._sticky_pause`,
  because that's where `_auto_paused` lives.

**The AnkiBlitz-only half of the port**: its reveal click handler sits on
`document` in the **capture** phase, so the button's own `stopPropagation` can't
stop it — clicking "More time" would have skipped the word reveal on the way
past. `clickHandler` now bails via a new `isOwnUi(target)`, which walks up
looking for an `fs-`-prefixed id. aSFM needs none of this: it has no click
handler of its own.

---

## The cross-add-on trap (decide before shipping 6)

In the full AnkiBlitz the reveal key and the pause key can be **the same key**
(both default `p`) because *one* listener handles them in sequence: while words
are still fading in the key reveals, once the question is fully shown the same
key pauses.

Split across add-ons that sequencing is gone. Someone running **aSFM + PWR**
with both keys on `p` gets two independent listeners on the same event, so one
press reveals the question **and** pauses the timer. Options:

1. **Document it** — different keys when running the two separately (cheapest).
2. Default aSFM's pause key to something else, e.g. `k`.
3. A soft bridge: aSFM checks for PWR's "still revealing" state and skips that
   press. Per the house rule this must be `try/except`-wrapped and degrade to
   plain behaviour when the other add-on is absent.

Option 1 unless you want to spend time on it.

---

## Before the push

1. Port the above.
2. `python3 -m py_compile` every changed `.py`; `node --check` every changed
   `.js`; `json.load` every `config.json`.
3. Check the four `config.json` files still match their `config.py` DEFAULTS,
   key for key — a key in one and not the other is a setting that silently
   can't be saved.
4. Rebuild with **`python3 build.py`**. Don't zip the folders by hand: it takes
   its file list from `git ls-files`, which is what keeps `meta.json` (the
   builder's own live config) and `user_files/` (real user data — break journal,
   stats, music profile) out of the package. A file that isn't committed doesn't
   ship.
5. Bump `version` **and `human_version`** in each add-on's manifest, and update
   its `README.md` and `AnkiWeb_description.txt`. Anki displays
   `human_version`; it never reads `version`, so bumping only that one changes
   nothing anybody can see.
6. Upload each `dist/*.ankiaddon` to its AnkiWeb listing and paste the matching
   `AnkiWeb_description.txt`:

   | Add-on | Code |
   |--------|------|
   | AnkiBlitz | `178722601` |
   | AnkiBlitz Core | `1174429600` |
   | Adaptive Speed Focus (aSFM) | `1148593203` |
   | Progressive Word Reveal | `972193513` |
