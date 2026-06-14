# AnkiBlitz suite

Four study add-ons for Anki. **AnkiBlitz** is the full integrated suite; the
other three are standalone spin-offs — **AnkiBlitz Core** (everything *except* the
two reviewer-reveal features) plus the two reveal features on their own — for
people who only want one piece.

> Don't run a standalone spin-off *and* the full AnkiBlitz at the same time — the
> timers/counters would double up. AnkiBlitz already includes all of them, and
> AnkiBlitz Core already includes the Blitz/Pomodoro/Focus/profiles/music stack.

| Add-on | What it does | Install |
|--------|--------------|---------|
| **[AnkiBlitz](AnkiBlitz/)** | The whole suite: timed Blitz sessions, Pomodoro, Focus Lock, profiles, in-app music, **plus** adaptive auto-reveal and progressive word reveal. | [`dist/AnkiBlitz.ankiaddon`](dist/AnkiBlitz.ankiaddon) |
| **[AnkiBlitz Core](ankiblitz-core/)** | The session-discipline stack **without** the reveal timers: timed Blitz sessions, Pomodoro, Focus Lock, profiles, in-app music. | [`dist/AnkiBlitzCore.ankiaddon`](dist/AnkiBlitzCore.ankiaddon) |
| **[Adaptive Speed Focus (aSFM)](aSFM/)** | Just the auto-**reveal** timer: waits a delay computed from the card's length and FSRS difficulty, then shows the answer. Never grades. | [`dist/aSFM.ankiaddon`](dist/aSFM.ankiaddon) |
| **[Progressive Word Reveal](progressive-reveal/)** | Just the word-by-word fade-in of the question, at a set reading pace (optionally TTS-synced). | [`dist/ProgressiveWordReveal.ankiaddon`](dist/ProgressiveWordReveal.ankiaddon) |

Mix and match: **AnkiBlitz Core + aSFM + Progressive Word Reveal** together equal
the full **AnkiBlitz** — install Core plus whichever reveal feature(s) you want,
or just grab the all-in-one AnkiBlitz.

---

## Install

**Easiest — packaged file:** in Anki, **Tools ▸ Add-ons ▸ Install from file…** and
pick the matching `.ankiaddon` from [`dist/`](dist/), then restart Anki.

**Manual — from source:** copy the add-on's source folder into your Anki
`addons21/` directory and restart. The folder must be named so Anki can import it:

| Source folder here | Copy into `addons21/` as |
|--------------------|--------------------------|
| `AnkiBlitz/` | `focus_suite` |
| `ankiblitz-core/` | `ankiblitz_core` |
| `aSFM/` | `asfm` |
| `progressive-reveal/` | `progressive_reveal` |

(The packaged `.ankiaddon` files handle this naming for you — manual copying is
only needed if you're hacking on the source.)

---

## The four, in detail

### AnkiBlitz
The integrated experience. Adaptive auto-reveal and progressive reveal run on any
review; on top of that you get timed **Blitz** sessions (by card count, time, or a
fraction of what's due) with a progress bar, **Pomodoro** work/break cycles,
**Focus Lock**, momentum nudges, an in-app **music** player, and whole-config
**profiles** (Default / Blitz / Relaxed). Controlled from **Tools ▸ AnkiBlitz**.

### AnkiBlitz Core
The same Blitz/Pomodoro/Focus/profiles/music stack as the full suite, but **with
the two reviewer-reveal features removed** — for people who want the session
discipline without the answer ever revealing itself. Pair it with aSFM and/or
Progressive Word Reveal to add reveal pacing back piece by piece. Controlled from
**Tools ▸ AnkiBlitz Core**.

### Adaptive Speed Focus (aSFM)
The auto-reveal timer on its own. `delay = (base + per-word × words) × familiarity
× difficulty`, clamped to a min/max, with an optional countdown bar and pre-reveal
warning. Counts only the words you actually see (hidden fields and AnKing tag
chips don't inflate it), and supports a set-time "picture card" mode. Controlled
from **Tools ▸ Adaptive Speed Focus**.

### Progressive Word Reveal
The word fade on its own. Fades the question in word-by-word (or in chunks) at a
reading pace you set, optionally locked to the card's native `{{tts}}` voice.
Click or the reveal key shows everything at once. Controlled from **Tools ▸
Progressive Word Reveal**.

---

## Credits & licence

These reimagine concepts from three Anki add-ons:

- **Speed Focus Mode** by **Glutanimate** (GNU AGPLv3) — the auto-reveal idea
  behind aSFM.
- **Progressive Word Reveal** by **Patrick Lee** (<https://www.patricklee.com.au/>)
  — the word-by-word fade.
- **Sprint Mode** by **Patrick Lee** (<https://www.patricklee.com.au/>) — the
  timed/counted-session idea behind Blitz.

Everything here is distributed under the **GNU AGPLv3**. Glutanimate's Speed Focus
Mode is AGPLv3 **with additional terms under Section 7** (preserve all copyright /
author attributions, don't misrepresent the work's origin, and no right to use the
"Glutanimate" name or logo for endorsement). Those additional terms apply to the
add-ons that incorporate or rework Speed Focus Mode — **AnkiBlitz** and **aSFM** —
and are reproduced in full in their `LICENSE` files. (AnkiBlitz Core and
Progressive Word Reveal contain no Speed Focus Mode code.) See each add-on's
`LICENSE`.
