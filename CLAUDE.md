# AnkiBlitz suite

This is a monorepo for four Anki add-ons, all shipped and live on AnkiWeb:
AnkiBlitz (the full suite), AnkiBlitz Core (session discipline, no reveal
timers), Adaptive Speed Focus (aSFM), and Progressive Word Reveal. Fletcher is
the sole author and publisher, and AnkiBlitz is his daily driver in his real
Anki profile — this is not a toy repo, changes reach a live add-on he studies
medicine with.

## Directory map

| Folder | Add-on | Package name | AnkiWeb code |
|---|---|---|---|
| `AnkiBlitz/` | AnkiBlitz (full suite) | `focus_suite` | `178722601` |
| `ankiblitz-core/` | AnkiBlitz Core | `ankiblitz_core` | `1174429600` |
| `aSFM/` | Adaptive Speed Focus | `asfm` | `1148593203` |
| `progressive-reveal/` | Progressive Word Reveal | `progressive_reveal` | `972193513` |

**The source folder is `AnkiBlitz/` but the package/folder name is still
`focus_suite`** — this is deliberate, not stale naming. It was never renamed
because config keys and the AnkiWeb-export path are derived from the package
name; renaming would silently reset users' config on update. Confirmed live:
`~/Library/Application Support/Anki2/addons21/focus_suite` is a symlink to
`AnkiBlitz/` in this repo — edits here are live in Anki immediately, no copy
step.

**Since 2026-10-15 his daily driver is aSFM + Progressive Word Reveal, not
AnkiBlitz** (`focus_suite` is disabled, not removed). `addons21/asfm` and
`addons21/progressive_reveal` are installed COPIES (from the .ankiaddon), not
symlinks: after editing `aSFM/`, sync with
`rsync -a --exclude meta.json --exclude user_files --exclude __pycache__ aSFM/ ~/Library/Application\ Support/Anki2/addons21/asfm/`.
`aSFM/engine/research.py` is his personal research logger (per-card JSONL in
`user_files/research_<profile>.jsonl`), **gitignored on purpose so it never
ships**; pace.py imports it softly. An AnkiWeb update of aSFM would delete it
from the live folder (the data in user_files survives) — re-sync after.

Otherwise, the spin-off folders (`ankiblitz-core/`, `aSFM/`, `progressive-reveal/`)
were historically **not** installed in his live `addons21/` — running a standalone spin-off
alongside the full AnkiBlitz would double up timers/counters. They're built
and tested from this repo only.

Each add-on's internals mirror the others (`engine/`, `web/`, `settings.py`,
`config.py`/`config.json`, `manifest.json`). `focus.py`, `session.py`, and
`sprint.py` are byte-identical across AnkiBlitz and Core apart from the ported
features, so changes to those three copy wholesale between folders.
`pomodoro.py` and `breathing.py` need hand-merging (theme bridge differs) —
re-diff before trusting this, these files drift.

`tools/` exists but is **not tracked by git** (see `.gitignore` — only stray
`__pycache__` shows up). Don't assume anything under it is part of the build.

## Gotchas

**Never reset or overwrite Fletcher's live settings.** Anki reads add-on
config from each folder's `meta.json` at runtime, not from `config.json`
(defaults only). His real, hand-tuned values live in `meta.json` and are
NOT under version control (gitignored, and correctly so). Every config change
must be **additive only**:
- add new keys/sections to `config.json` + the `DEFAULTS` in `config.py`
- never rename or remove an existing key — a rename is a silent reset for
  that field
- never edit or rewrite `meta.json` directly; rely on `config.ensure_defaults()`
  / `config.migrate()` to back-fill new keys onto the existing saved config
- in settings panels, keep the `cfg = get_section(); cfg.update({...});
  save_section(cfg)` pattern so unknown keys are never dropped on save
- verify by diffing `meta.json` before/after a restart: old values intact,
  new keys appended at their defaults

**"Speed Focus" / aSFM is an adaptive auto-*reveal* timer. It never grades
cards.** Progressive reveal finishes, an adaptive delay elapses (computed in
`engine/adaptive.py` from card state, question length, ease/lapses), then the
answer is shown. That's it — no auto-answering, ever. Don't reintroduce
auto-grading; that was Glutanimate's original design and was deliberately
scrapped.

**AnkiWeb manifest facts that have cost real time:**
- Anki displays `human_version` in Tools ▸ Add-ons, **not** `version` (and
  not `description`). Keep both in sync but know only `human_version` shows.
- `conflicts` matches installed **folder names**, and an AnkiWeb install
  lands in a folder named by the numeric code while a manual/git install
  keeps the source name — so every conflict entry needs **both** the source
  folder name (e.g. `focus_suite`) and the numeric AnkiWeb code (e.g.
  `178722601`), or the guard misses half of all installs.

**The `focus_suite` folder is symlinked into `addons21/` — edits are live,
but restart Anki for `.py` changes.** Anki loads Python modules once at
startup; only web assets (`.js`/`.css`) and things read fresh from disk take
effect without a restart. Don't report a Python change as "done" until
Fletcher has restarted Anki.

**Stage-3 TTS was built, then deliberately reverted — it's stashed, not
lost.** It read out AnKing markup/CSS and felt janky, so it was pulled from
the live add-on but the full implementation is saved at
`~/.claude/projects/-Users-fletcherbucat/stash/ankiblitz-stage3-tts/`
(`tts.py` + `INTEGRATION.md` with exact re-wiring steps). Don't rebuild TTS
from scratch — check that stash first. Stale `tts`/`sync_reveal_to_tts` keys
remain in his live `meta.json`; nothing reads them, and per the additive-only
rule above they are left in place, not removed.

**Add-on independence.** These four don't import each other, and don't
assume any other of Fletcher's add-ons (Ankisstant, SynapsePro, etc.) is
installed. Any cross-add-on integration is a soft bridge: deferred import
inside `try/except`, no-ops silently if the other add-on is absent. Never add
a top-level `import` of another add-on's package.

**Long background jobs need `uses_collection=False`.** If a job doesn't
touch `mw.col`, pass `uses_collection=False` to
`mw.taskman.run_in_background(...)` — the default routes onto Anki's single
worker thread that periodic backups and syncs also use, and a long job there
produces the "stuck backing up" hang.

**Programmatic grading:** if a feature needs to actually answer a card
(Again/Hard/Good/Easy), delegate to AJT Card Management's `grade_cards(col,
cards, ease)` (`addons21/1021636467/grade_now.py`, imported via
`importlib.import_module("1021636467.grade_now")`, soft/optional). Don't
manipulate `card.queue`/`card.type`/`card.due` directly — that bypasses the
scheduler and FSRS won't log it as a real review.

## Commands

There is no test suite in this repo — treat any change as needing a manual
restart-and-check in Anki, not a test run.

Build the four `.ankiaddon` packages into `dist/`:

```
python3 build.py                 # all four
python3 build.py AnkiBlitz       # one add-on by source folder name
```

`build.py` sources its file list from `git ls-files`, which is what keeps
`meta.json` (personal config) and `user_files/` (break journal, Blitz stats,
music profile — both gitignored) out of the shipped package. **Never build a
release by zipping a folder by hand** — that risks shipping someone's live
config to every installer. A file that isn't committed can't ship, so commit
first, then build.

There is no separate lint/format command recorded for this repo — don't
invent one.
