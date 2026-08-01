# AnkiBlitz Core

Session discipline for Anki, in one engine, one menu, and one settings window —
**without** the card-reveal timers. If you want focused, timed study with real
structure but don't need the answer revealing itself, this is the lean build:

- **Blitz sessions** — focused, timed review runs (by card count, time, or a
  fraction of what's due) with a progress bar and a completion screen.
- **Pomodoro** — chain work blocks with short and long breaks, a break screen
  with journaling and focus ratings, and configurable auto-return.
- **Focus Lock** — make leaving a session progressively harder (confirm →
  min-cards → finish), with an optional Focus Score.
- **Profiles** — flip the whole *feel* of a session in one click.
- **In-app music** — a SoundCloud / YouTube Music player on the break screen, as
  a floating review dock, and on the deck list.

Everything is controlled from **Tools ▸ AnkiBlitz Core**.

> **Want reveal pacing too?** Core deliberately leaves out the card-reveal
> timers so it stays light. Two companion add-ons add them and run happily
> alongside Core:
> - **Adaptive Speed Focus (aSFM)** — adaptive auto-reveal timer.
> - **Progressive Word Reveal** — fades the answer in word by word.
>
> Or install the all-in-one **AnkiBlitz** add-on, which bundles everything
> (Core + aSFM + Progressive Word Reveal) in a single package.

---

## Install

This is a folder add-on. The package folder is `ankiblitz_core`.

- **From the packaged file:** Anki ▸ Tools ▸ Add-ons ▸ Install from file… ▸ pick
  `AnkiBlitzCore.ankiaddon`, then restart Anki.
- **Manually:** drop the `ankiblitz_core` folder into your Anki `addons21/`
  directory and restart.

On first launch a short welcome wizard appears once. It asks you to **disable any
add-ons that do the same job** so timers and counters don't double up — in
particular **Sprint Mode**, and the full **AnkiBlitz** add-on (which already
includes Core). Disable those in **Tools ▸ Add-ons** and restart.

---

## Using it

Menu (**Tools ▸ AnkiBlitz Core**):

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

### During a Pomodoro break

The break screen is a full-page countdown, but it isn't a trap:

- **Step away** (or `Esc`) hides it and leaves a small floating countdown — go
  check your calendar, make a coffee, leave the app entirely. The break keeps
  running and the page comes back when you return to Anki.
- Only **End Pomodoro** ends a run.
- The break is **quiet**: the card Anki renders behind the break screen doesn't
  read itself out at you. Its audio plays when you come back to the reviewer.
- Stopped part-way through? Starting a Pomodoro later **the same day** offers to
  **resume** — same cycle, same fraction split, picking up at the block you
  stopped on. The deck-list widget's button says "Resume" when one is waiting.

---

## Profiles

A **profile** flips the *feel* of a session in one click — the Focus Lock, the
near-end momentum nudge, and the anti-pressure / progress display. Switch from
**Settings ▸ Profiles** or **Tools ▸ AnkiBlitz Core ▸ Profile**.

Three built-ins ship in code:

- **Default** — the everyday feel and the active profile out of the box: no Focus
  Lock, a gentle near-end nudge, a calm HUD.
- **Blitz** — a committed, locked-in run: a *penalty* Focus Lock so bailing costs
  Focus Score, full HUD with a completion chime.
- **Relaxed** — low friction for studying with mates or half-distracted: no Focus
  Lock, no nagging, a minimal HUD.

Profiles deliberately **do not** change how you launch a session (Blitz mode /
target / counting rule and Pomodoro work blocks are chosen in the Start dialog
every time), the music player, or your note-type / deck exclusion lists and
quick-picks.

On first run your existing settings are captured as a profile named **"My setup"**
and made active, so adopting profiles never loses your tuning. Applying a profile
is always an **explicit overwrite** of those feel settings on the other tabs.

---

## Settings reference

Every option is documented in **[config.md](config.md)**, organised by config
section:

- `sprint` — Blitz session defaults, progress display, anti-pressure, personal
  bests. *(Internal key name; the feature is "Blitz" everywhere in the UI.)*
- `quick_start` — daily auto-launch.
- `momentum` — near-end "keep going?" intercept.
- `pomodoro` — work/break cycles and the break screen.
- `music` — the in-app SoundCloud / YouTube Music player.
- `focus` — Focus Lock and Focus Score.
- `home_widget` — on-screen quick-launch panels.
- `presets` — profiles.

Edit settings from the UI; the raw JSON is optional.

---

## Files & data

- `config.json` / `config.py` — shipped defaults; live values live in Anki's
  `meta.json` (never hand-edit that).
- `user_files/sprint_stats.json` — your Blitz stats (preserved across updates).
- `user_files/music_profile/` — the music player's cookies/login.
- `web/` — the single CSS/JS reviewer bundle (the Blitz progress bar).
- `engine/` — the engine modules (one session of truth, one injection point).

---

## Standalone

AnkiBlitz Core works on its own and needs no other add-on. Any optional bridges to
other add-ons (e.g. the companion reveal tools, or Ankisstant's "Add KG" button on
the break screen) are best-effort and fail quietly if those add-ons are absent.

---

## Credits & acknowledgements

### Stands on
AnkiBlitz Core's Blitz engine builds on the idea of **Sprint Mode** by **Patrick
Lee** (<https://www.patricklee.com.au/>) — timed / counted review sessions.

### Thanks
- **Patrick Lee** — author of the original *Sprint Mode* this builds on, and for
  code / feature contributions. (<https://www.patricklee.com.au/>)
- The **AnKing** team — for the note types and conventions this is built to play
  nicely with.
- **Anki** and its community — the platform this runs on.

### Part of the AnkiBlitz suite
This is one of four downloadable tools split out of the integrated **AnkiBlitz**
add-on:

- **AnkiBlitz** — the all-in-one suite (Core + aSFM + Progressive Word Reveal).
- **AnkiBlitz Core** — this add-on.
- **Adaptive Speed Focus (aSFM)** — standalone adaptive auto-reveal timer.
- **Progressive Word Reveal** — standalone word-by-word answer fade.

---

## Licence

Distributed under the **GNU Affero General Public License v3.0** (AGPLv3). You may
use, study, modify and share it; if you distribute a modified version (or run it
as a network service) you must release your source under the same licence. See
[LICENSE](LICENSE) for the full terms.
