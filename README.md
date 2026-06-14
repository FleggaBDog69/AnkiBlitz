# AnkiBlitz suite

Three review-pacing add-ons for Anki. **AnkiBlitz** is the full integrated suite;
the other two are standalone spin-offs of its two reviewer features, for people
who only want that one piece.

> Don't run a standalone spin-off *and* the full AnkiBlitz at the same time — the
> timers would double up. AnkiBlitz already includes both features.

| Add-on | What it does | Install |
|--------|--------------|---------|
| **[AnkiBlitz](AnkiBlitz/)** | The whole suite: timed Blitz sessions, Pomodoro, Focus Lock, profiles, in-app music, **plus** adaptive auto-reveal and progressive word reveal. | [`dist/AnkiBlitz.ankiaddon`](dist/AnkiBlitz.ankiaddon) |
| **[Adaptive Speed Focus (aSFM)](aSFM/)** | Just the auto-**reveal** timer: waits a delay computed from the card's length and FSRS difficulty, then shows the answer. Never grades. | [`dist/aSFM.ankiaddon`](dist/aSFM.ankiaddon) |
| **[Progressive Word Reveal](progressive-reveal/)** | Just the word-by-word fade-in of the question, at a set reading pace (optionally TTS-synced). | [`dist/ProgressiveWordReveal.ankiaddon`](dist/ProgressiveWordReveal.ankiaddon) |

---

## Install

**Easiest — packaged file:** in Anki, **Tools ▸ Add-ons ▸ Install from file…** and
pick the matching `.ankiaddon` from [`dist/`](dist/), then restart Anki.

**Manual — from source:** copy the add-on's source folder into your Anki
`addons21/` directory and restart. The folder must be named so Anki can import it:

| Source folder here | Copy into `addons21/` as |
|--------------------|--------------------------|
| `AnkiBlitz/` | `focus_suite` |
| `aSFM/` | `asfm` |
| `progressive-reveal/` | `progressive_reveal` |

(The packaged `.ankiaddon` files handle this naming for you — manual copying is
only needed if you're hacking on the source.)

---

## The three, in detail

### AnkiBlitz
The integrated experience. Adaptive auto-reveal and progressive reveal run on any
review; on top of that you get timed **Blitz** sessions (by card count, time, or a
fraction of what's due) with a progress bar, **Pomodoro** work/break cycles,
**Focus Lock**, momentum nudges, an in-app **music** player, and whole-config
**profiles** (Default / Blitz / Relaxed). Controlled from **Tools ▸ AnkiBlitz**.

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

All three reimagine concepts from **Glutanimate's** add-ons — *Speed Focus Mode*,
*Progressive Word Reveal*, and *Sprint Mode* — which are licensed under the GNU
AGPLv3. Accordingly, everything here is distributed under the **GNU AGPLv3**; see
each add-on's `LICENSE`.
