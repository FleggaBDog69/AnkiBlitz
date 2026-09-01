# AnkiBlitz

A review-pacing toolkit for Anki that rolls three ideas into one engine, one
menu, and one settings window:

- **Adaptive auto-reveal** (Speed Focus) — shows the answer automatically after a
  delay computed from the card's length and difficulty. **It never grades for
  you** — you still press the button.
- **Progressive word reveal** — fades the question in word-by-word at a set
  reading pace, optionally synced to `{{tts}}` playback.
- **Blitz sessions** — focused, timed review runs (by card count, time, or a
  fraction of what's due) with a progress bar, plus Pomodoro work/break cycles,
  Focus Lock, momentum nudges, an in-app music player, and whole-config
  **profiles**.

Everything is controlled from **Tools ▸ AnkiBlitz**.

---

## Install

This is a folder add-on. The package folder is `focus_suite` (the historical
internal name — kept so existing settings and stats are preserved; the add-on
presents itself everywhere as **AnkiBlitz**).

- **From AnkiWeb (recommended — you get updates):** Anki ▸ Tools ▸ Add-ons ▸
  Get Add-ons… ▸ paste the code **`178722601`**, then restart.
  <https://ankiweb.net/shared/info/178722601>
- **From the packaged file:** Anki ▸ Tools ▸ Add-ons ▸ Install from file… ▸ pick
  `AnkiBlitz.ankiaddon`, then restart Anki.
- **Manually:** drop the `focus_suite` folder into your Anki
  `addons21/` directory and restart.

On first launch a short welcome wizard appears once. It asks you to **disable any
add-ons that do the same job** so timers don't double up — in particular:

- Speed Focus Mode (SFM)
- Progressive Word Reveal
- Sprint Mode

Disable those in **Tools ▸ Add-ons** and restart.

---

## Using it

Menu (**Tools ▸ AnkiBlitz**):

| Item | Shortcut | What it does |
|------|----------|--------------|
| Start Blitz… | `Ctrl+Shift+S` | Launch a focused session (cards / time / fraction). |
| Blitz all due cards | — | Blitz the whole due queue. |
| Start Pomodoro… | `Ctrl+Shift+P` | Chain work blocks with breaks. |
| Blitz stats | — | Daily and all-time totals, personal bests. |
| Break journal… | — | Review notes written during Pomodoro breaks. |
| Music player | `Ctrl+Shift+M` | Floating in-app player during reviews. |
| Profile ▸ | — | Switch the whole-config profile (see below). |
| Settings… | — | The tabbed settings window. |
| Enabled | — | Master on/off for everything. |

Adaptive auto-reveal and progressive reveal also work **outside** a Blitz, on any
normal review — the Blitz session just adds the target and the completion screen
on top.

The **progress bar** stays up outside a Blitz too, dimmed and labelled *All due*,
filling against everything you have due rather than a session target. Its target
is live rather than fixed at the start — a card that comes back in learning
pushes it out by one — so it reaches the end exactly when your queue empties,
never before. It shows nothing but the count and the clock: no accuracy, no
Again count, no streak. Turn it off under **Settings ▸ Blitz ▸ Show during
Blitz**.

Starting a Blitz from **Start Blitz…** also lets you pick a **Focus lock** level
for that one session — commit hard to a session you need to finish, or let
yourself off for a tired one, without changing your saved default.

### In the reviewer

| Key | What it does |
|-----|--------------|
| reveal key (default `p`) | Show the rest of the question at once, while it's still fading in. Also stops the card's audio (you've read it — the voice is just noise); turn that off in settings. |
| pause key (default `p`) | Pause / resume the auto-reveal countdown on the card you're on. |
| **More time** button | The same hold, as a control you can see: it sits above the countdown, faint until hovered. Click it and the timer stops; click it (or the *paused* badge) again to carry on. Turn it off in settings. |

The two keys may be **the same key** — that's the default. While words are still
fading in the key reveals them; once the question is fully shown, the same key
pauses the timer (and the next press starts it again where it stopped). A paused
timer is labelled on screen and stays paused across cards until you release it.

### During a Pomodoro break

The break screen is a full-page countdown, but it isn't a trap:

- **Step away** (or `Esc`) hides it and leaves a small floating countdown — go
  check your calendar, make a coffee, leave the app entirely. The break keeps
  running and the page comes back when you return to Anki.
- Only **End Pomodoro** ends a run.
- **🫁 Breathe** opens a guided breathing pacer: a circle that expands and
  contracts with the phase named and counted underneath, so there's something to
  follow rather than just being told to relax. It sits collapsed as a button
  until you press it, and you can switch rhythm on the spot — Box 4-4-4-4,
  Simple 4-4, Coherent 5-5, or Calming 4-7-8 (that last one will make you
  drowsy, so keep it for long breaks).
- The break is **quiet**: the card Anki renders behind the break screen doesn't
  read itself out at you. Its audio plays when you come back to the reviewer.
- Stopped part-way through? Starting a Pomodoro later **the same day** offers to
  **resume** — same cycle, same fraction split, picking up at the block you
  stopped on. The deck-list widget's button says "Resume" when one is waiting.

---

## Profiles

A **profile** flips the *feel* of reviewing in one click — the adaptive
auto-reveal pace, Focus Lock, the near-end momentum nudge, and the
anti-pressure / progress display. Switch from **Settings ▸ Profiles** or
**Tools ▸ AnkiBlitz ▸ Profile**.

Three built-ins ship in code:

- **Default** — the everyday review feel and the active profile out of the box:
  relaxed ~7s auto-reveal on a typical card, a quiet countdown, no Focus Lock, a
  gentle near-end nudge.
- **Blitz** — what you switch to for a committed run: brisk auto-reveal,
  countdown + pre-reveal warning, a *penalty* Focus Lock so bailing costs Focus
  Score, full HUD with a completion chime.
- **Relaxed** — low friction for studying with mates or half-distracted: generous
  auto-reveal, no countdown/warning pressure, no lock, no nagging.

Profiles deliberately **do not** change:

- **how you launch a session** — Blitz mode / target / counting rule and Pomodoro
  work blocks are chosen in the Start dialog *every time*, the same regardless of
  profile;
- your **word-reveal speed** (one reading pace across every profile);
- the **music** player, or your note-type / deck exclusion lists and quick-picks.

On first run your existing settings are captured as a profile named **"My setup"**
and made active, so adopting profiles never loses your tuning. Applying a profile
is always an **explicit overwrite** of those feel settings on the other tabs.

---

## Settings reference

Every option is documented in **[config.md](config.md)**, organised by config
section:

- `speed_focus` — adaptive auto-reveal timing and exclusions.
- `word_reveal` — progressive reveal speed, mode, TTS matching.
- `sprint` — Blitz session defaults, progress display, anti-pressure, personal
  bests. *(Internal key name; the feature is "Blitz" everywhere in the UI.)*
- `quick_start` — daily auto-launch.
- `momentum` — near-end "keep going?" intercept.
- `pomodoro` — work/break cycles and the break screen.
- `music` — the in-app SoundCloud / YouTube Music player.
- `focus` — Focus Lock and Focus Score.
- `home_widget` — on-screen quick-launch panels.
- `presets` — profiles.
- `synapse` — sharing a screen with the SynapsePro add-on (see below).

Edit settings from the UI; the raw JSON is optional.

---

## Files & data

- `config.json` / `config.py` — shipped defaults; live values live in Anki's
  `meta.json` (never hand-edit that).
- `user_files/sprint_stats.json` — your Blitz stats (preserved across updates).
- `user_files/music_profile/` — the music player's cookies/login.
- `sounds/` — the auto-reveal warning sound (`alert.mp3`; override by dropping
  your own `alert.mp3` in `user_files/`).
- `web/` — the single CSS/JS reviewer bundle.
- `engine/` — the engine modules (one session of truth, one injection point).

---

## Alongside SynapsePro

If you also run the **SynapsePro** add-on, AnkiBlitz moves in with it rather than
sitting alongside — controlled from **Settings ▸ SynapsePro**:

- **It lives in SynapsePro's sidebar.** Two icons are added to the strip:
  🍅 start or resume a Pomodoro (in SynapsePro's accent colour), and ⚡ the
  AnkiBlitz panel (in plain text colour, so only one of the two asks for your
  attention). The panel holds everything else — Blitz quick-launches,
  finish-all-due, today's totals, stats, the break journal, the Quick Start
  toggle and Settings — as an HTML page built to SynapsePro's own settings-page
  design.
- **The deck-list rail goes away**, since the sidebar is now the way in. It
  returns if you switch the integration off or remove SynapsePro.
- **It borrows SynapsePro's colours.** The panel, the reveal overlay, the break
  screen and the Settings window use its palette, and follow along when you
  switch its colour theme. Only colours change; nothing moves.
- **It stands its music player down.** SynapsePro has one, so AnkiBlitz's rail
  button, break-screen box and `Ctrl+Shift+M` step aside. Nothing is deleted —
  they come back if you turn the setting off or remove SynapsePro.
- **Its Pomodoro doesn't.** AnkiBlitz's Pomodoro stays in charge. Both add-ons
  have one, so if SynapsePro's is also switched on you'll be told once and
  offered its settings — AnkiBlitz won't change another add-on's config for you.

Without SynapsePro installed, none of this does anything.

## Standalone

AnkiBlitz works on its own. It bundles its own copies of the concepts from the
add-ons it replaces, so you don't need them installed (and shouldn't keep them
enabled). Any optional bridges to other add-ons are best-effort and fail quietly
if those add-ons are absent.

---

## Credits, references & thanks

### Stands on
AnkiBlitz reimplements and merges three add-ons into one engine:

- **Speed Focus Mode (SFM)** by **Glutanimate** — the auto-reveal-timer idea
  (here: never grades, separate new vs learning timing, a pre-reveal warning).
- **Progressive Word Reveal** by **Patrick Lee**
  (<https://www.patricklee.com.au/>) — fading the question in word by word.
- **Sprint Mode** by **Patrick Lee** (<https://www.patricklee.com.au/>) —
  timed / counted review sessions (here: the Blitz engine).

Glutanimate's Speed Focus Mode is licensed under the GNU AGPLv3, so AnkiBlitz is
distributed under the AGPLv3 too.

### TTS sync
The progressive reveal can lock to a card's spoken pace by reading the card's
native **Anki** `{{tts}}` tags (Anki's `MacTTSPlayer` runs `say -r base×speed`)
and the **AnKing** note-type TTS conventions. No speech engine is bundled —
AnkiBlitz only *syncs to* the TTS that Anki / AnKing already produce.

### Thanks
- **Patrick Lee** — author of the original *Progressive Word Reveal* and *Sprint
  Mode* this builds on, and for code / feature contributions to AnkiBlitz.
  (<https://www.patricklee.com.au/>)
- The **AnKing** team — for the note types and TTS conventions AnkiBlitz is built
  to play nicely with (these drove the visible-word-count fix and the picture-card
  timing mode).
- **Anki** and its community — the platform this runs on.

### References
- **[LICENSE](LICENSE)** — the full GNU AGPLv3 text.
- **[config.md](config.md)** — every setting, per config section.
- **[AnkiWeb_description.md](AnkiWeb_description.md)** — paste-ready listing copy;
  the AnkiWeb description box renders Markdown.

## Licence

Distributed under the **GNU Affero General Public License v3.0 (AGPLv3)**. You may
use, study, modify and share it; if you distribute a modified version (or run it
as a network service) you must release your source under the same licence.

Because AnkiBlitz incorporates and reworks **Glutanimate's Speed Focus Mode**
(Copyright (C) 2017-2021 Aristotelis P., <https://glutanimate.com/>), it is also
subject to **Glutanimate's additional terms under AGPL Section 7**: you must
**preserve all copyright and author attributions**, **not misrepresent the
origin** of the work, and you are **not granted any right to use the
"Glutanimate" name or logo** for endorsement. Those additional terms are
reproduced in full in [LICENSE](LICENSE) (per term 6, the complete licence text is
included).
