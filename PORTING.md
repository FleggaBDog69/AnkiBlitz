# Porting notes — what the spin-offs still owe AnkiBlitz

`AnkiBlitz/` is where features get built. `ankiblitz-core/`, `aSFM/` and
`progressive-reveal/` are **independent copies**, not symlinks or imports — a fix
in AnkiBlitz does nothing to them until it's carried across by hand.

This file tracks what's outstanding. **Clear it before the next push**, or ship
AnkiBlitz alone and leave the spin-offs on their current release.

---

## Outstanding as of 2026-07-31

Five changes landed in `AnkiBlitz/` and none of them are in the spin-offs.

| # | Change | Core | aSFM | PWR |
|---|--------|:----:|:----:|:---:|
| 1 | "Finish all due" button fix | **yes** | — | — |
| 2 | Break screen: step away / floating pill | **yes** | — | — |
| 3 | Resume an unfinished run from earlier today | **yes** | — | — |
| 4 | Break journal: today's entry only | **yes** | — | — |
| 5 | Silence card audio during a break | **yes** | — | — |
| 6 | Pause key for the auto-reveal timer | — | **yes** | — |
| 7 | Key-handler guards (modifiers, typing) | — | (comes with 6) | **yes** |
| 8 | SynapsePro bridge (`engine/theme_bridge.py`) | — | — | — |
| 9 | QComboBox escape-hatch fix in `theme_bridge.py` | (with 8) | — | — |

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
3. Rebuild `dist/*.ankiaddon`.
4. Bump the version in each add-on's manifest and update its `README.md`.
