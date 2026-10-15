"""Learning your pace: auto-tune and calibration.

Anki's review log can't say how long you took to REVEAL a card, only how long
until you graded it (question + answer + deciding). So aSFM measures reveals
itself, and keeps what it learns small:

* **In memory, per Anki session:** the card on screen, and a tally of this
  session's cards. Nothing per-card is ever written to disk.
* **On disk, one small JSON per profile** (``user_files/pace_<profile>.json``):
  the learned pace, a compact histogram of reveal times for calibration, and a
  one-line summary per session. Counts, not cards — it stays a few KB, and old
  data is halved away as new arrives so recent habits dominate.

One knob drives both features: ``target_timer_wins_percent``. Auto-tune steers
the pace until the timer beats you on about that share of cards; calibration
fits base / per-word to the matching percentile of your reveal times (90th for
the default 10%). The two agree by construction.

**Auto-tune** is a stochastic-approximation staircase on a single multiplier:

    timer won (it fired, or you held it with More time / the pause key):
        pace *= exp(STEP * (1 - target))
    you revealed first:
        pace *= exp(-STEP * target)

which settles where the timer wins ``target`` of the time. It is deliberately
lopsided: at the default 10% target a card you reveal first shortens the timer
by ~0.5%, a timeout lengthens it by ~4.6%, and the pace can never go below
0.85× — so it can't rush you, and a run of timeouts backs it off fast.

One guard: a timer that fires only counts as "won" if you usually reveal cards
yourself. Someone who always lets it run isn't telling us it's too short, and
without the guard their pace would climb forever. "Usually" is a slow average
(~100 cards), so a bad stretch of timeouts lengthens the timer long before it
could flip you to "lets it run". More time / pause always count.
"""

import json
import math
import os
import re
import time

from aqt import mw

from ..config import DEFAULTS

# A personal research logger can sit beside this file (engine/research.py). It
# is gitignored, so it never ships: released copies simply don't have it.
try:
    from . import research as _research
except ImportError:
    _research = None

PACE_MIN, PACE_MAX = 0.85, 2.0   # never more than 15% quicker; up to 2× slower

# Each kind of card keeps its own pace, so a slow run of new cards can't
# lengthen your review timer. "review" is the original top-level ``pace``.
# One-by-one cards are tracked cloze by cloze (the reviewer reports each one),
# and each cloze nudges their pace; when a template never runs the per-cloze
# timers, the whole card is tallied as "one_by_one_whole" instead. Learning
# and new cards are timed off the same base / per-word formula as reviews, so
# calibration rebases them (see rebase_pace).
CATEGORIES = ("review", "learning", "new", "picture", "one_by_one",
              "one_by_one_whole")
TUNED = ("review", "learning", "new", "picture", "one_by_one")
FORMULA_BASED = ("learning", "new")
D_BUCKETS = 5                # difficulty signal -1..1, in fifths
STEP = 0.05                  # won: +4.6% / revealed first: -0.5% (10% target)
MAX_REVEAL_S = 60.0          # longer = you walked away; the card is ignored
SELF_ALPHA = 0.01            # slow average of "you revealed it" (~100 cards)
ACTIVE_MIN = 20              # cards seen before that average is trusted
ACTIVE_SHARE = 0.3
SETTLE = 0.02                # per let-it-run card, the share of the way back to 1.0×
SAVE_EVERY = 25              # cards between saves, so a crash loses little
SESSIONS_KEPT = 30

# Calibration histogram. Cells are (question words, answer words) buckets;
# each holds reveal-time bins. Times are stored with the difficulty factor
# divided out, so the fit sees the length terms alone.
Q_BUCKET, Q_MAX = 5, 80
A_BUCKET, A_MAX = 5, 60
T_BIN = 0.5
HIST_CAP = 4000.0            # total weight before everything is halved
MIN_CALIBRATION = 150        # self-revealed cards before calibration uses them
MIN_CELL = 3.0

# Review-log fallback: that time includes reading the answer and grading, so
# an allowance is taken off before it is treated as a reveal time.
REVLOG_DAYS = 90
REVLOG_MAX_CARDS = 600
REVLOG_ANSWER_BASE_S = 1.5
REVLOG_ANSWER_PER_WORD_S = 0.1

_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files")

_summary = None       # the on-disk summary, loaded lazily per profile
_summary_for = None   # which profile _summary belongs to
_card = None          # the card on screen, while its timer runs
_session = None
_unsaved = 0


# ----- storage -----

def _profile() -> str:
    try:
        name = mw.pm.name or "default"
    except Exception:
        name = "default"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def _path() -> str:
    return os.path.join(_DIR, f"pace_{_profile()}.json")


def _blank() -> dict:
    return {"version": 1, "pace": 1.0, "pace_cards": 0,
            "hist": {}, "hist_n": 0.0, "self_n": 0.0, "sessions": [],
            "paces": {}, "pace_counts": {}, "tally": {}, "tally_n": 0.0}


def _new_session() -> dict:
    return {"start": time.time(), "cards": 0, "self": 0, "auto": 0,
            "held": 0, "reveal_s": []}


def summary() -> dict:
    global _summary, _summary_for
    prof = _profile()
    if _summary is None or _summary_for != prof:
        data = _blank()
        try:
            with open(_path(), encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                data.update(saved)
        except Exception:
            pass
        _summary, _summary_for = data, prof
    return _summary


def save() -> None:
    global _unsaved
    data = summary()
    try:
        os.makedirs(_DIR, exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp, _path())
        _unsaved = 0
    except Exception:
        pass


# ----- consent -----

def learning(cfg: dict) -> bool:
    """Has the user opted in to aSFM recording their reveals? Until they do,
    nothing here touches the disk and the pace stays at 1.0."""
    return bool(cfg.get("learn_my_pace", DEFAULTS["learn_my_pace"]))


# ----- the learned pace -----

def _target(cfg: dict) -> float:
    pct = cfg.get("target_timer_wins_percent", DEFAULTS["target_timer_wins_percent"])
    return min(0.5, max(0.05, float(pct) / 100.0))


def category(inputs: dict, one_by_one: bool = False) -> str:
    if inputs.get("fixed_time"):
        return "picture"
    if one_by_one:
        return "one_by_one"
    if inputs.get("is_new"):
        return "new"
    if inputs.get("unfamiliar"):
        return "learning"
    return "review"


def _clamp(p) -> float:
    return min(PACE_MAX, max(PACE_MIN, float(p)))


def pace_of(cat: str = "review") -> float:
    """The learned pace for a kind of card, ignoring the switches. A kind that
    hasn't learned anything of its own yet follows your review pace: that is
    what it ran on before the kinds were split."""
    data = summary()
    review = float(data.get("pace", 1.0))
    if cat == "review" or cat not in TUNED:
        return _clamp(review)
    return _clamp(data.get("paces", {}).get(cat, review))


def _set_pace(data: dict, cat: str, value: float) -> None:
    if cat == "review":
        data["pace"] = _clamp(value)
    else:
        data.setdefault("paces", {})[cat] = _clamp(value)


def count_of(cat: str = "review") -> int:
    data = summary()
    if cat == "review":
        return int(data.get("pace_cards", 0))
    return int(data.get("pace_counts", {}).get(cat, 0))


def current(cfg: dict, cat: str = "review") -> float:
    """The multiplier to apply now: the learned pace for this kind of card,
    or 1.0 while auto-tune is off (the learned value is kept, not lost, for
    when it's back on)."""
    if not learning(cfg) or not cfg.get("auto_tune_enabled",
                                        DEFAULTS["auto_tune_enabled"]):
        return 1.0
    try:
        return pace_of(cat)
    except Exception:
        return 1.0


def _save_if_recorded() -> None:
    # With learning off there may be no file on disk; writing one would
    # record you anyway.
    if os.path.exists(_path()):
        save()


def reset_pace() -> None:
    """The Reset button: every kind back to 1.0×."""
    data = summary()
    data["pace"] = 1.0
    data["pace_cards"] = 0
    data["paces"] = {cat: 1.0 for cat in TUNED if cat != "review"}
    data["pace_counts"] = {}
    _save_if_recorded()


# Which kind's pace a calibrated setting already carries.
SETTING_KIND = {"unfamiliar_multiplier": "learning", "new_multiplier": "new",
                "fixed_time_base_seconds": "picture",
                "one_by_one_seconds_per_cloze": "one_by_one",
                "one_by_one_seconds_per_word": "one_by_one",
                "one_by_one_multiplier": "one_by_one"}


def rebase_pace(refitted=()) -> None:
    """After calibrating. The new base / per-word already carry your review
    pace, so that goes back to 1.0×. A kind whose own setting was refitted
    (``refitted``: kinds, see SETTING_KIND) goes to 1.0× too, since the fit
    was made from its real times. Otherwise learning and new cards, which run
    off the same formula, have their pace divided by the old review pace to
    keep their real timings where they were; picture cards have their own set
    time and keep theirs."""
    data = summary()
    old = pace_of("review")
    for cat in FORMULA_BASED:
        _set_pace(data, cat, 1.0 if cat in refitted else pace_of(cat) / old)
    if "picture" in refitted:
        _set_pace(data, "picture", 1.0)
    data["pace"] = 1.0
    data["pace_cards"] = 0
    _save_if_recorded()


def _nudge(won: bool, cfg: dict, cat: str) -> None:
    data = summary()
    t = _target(cfg)
    step = STEP * (1.0 - t) if won else -STEP * t
    _set_pace(data, cat, pace_of(cat) * math.exp(step))
    if cat == "review":
        data["pace_cards"] = int(data.get("pace_cards", 0)) + 1
    else:
        counts = data.setdefault("pace_counts", {})
        counts[cat] = int(counts.get(cat, 0)) + 1


def _settle(data: dict, cat: str) -> None:
    """You let the timer run: no evidence either way, so drift gently back to
    1.0×. Without this, a pace learned (or pushed up by a run of timeouts)
    before you switched to letting it run would be stuck there for good."""
    p = pace_of(cat)
    _set_pace(data, cat, p + SETTLE * (1.0 - p))


def _reveals_yourself() -> bool:
    data = summary()
    if data.get("self_seen", 0) < ACTIVE_MIN:
        return False
    return data.get("self_share", 0.0) >= ACTIVE_SHARE


def _note_outcome(yourself: bool) -> None:
    """Fold one card into the slow 'do you reveal it yourself?' average. Kept
    in the summary, so it carries across sessions instead of restarting."""
    data = summary()
    share = float(data.get("self_share", 0.0))
    seen = int(data.get("self_seen", 0))
    # Plain mean for the first cards, then the slow exponential average.
    alpha = max(SELF_ALPHA, 1.0 / (seen + 1))
    data["self_share"] = share + alpha * ((1.0 if yourself else 0.0) - share)
    data["self_seen"] = seen + 1


# ----- the calibration histogram -----

def _cell_key(words: float, answer_words: float) -> str:
    qb = int(min(words, Q_MAX) // Q_BUCKET)
    ab = int(min(answer_words, A_MAX) // A_BUCKET)
    return f"{qb}:{ab}"


def _hist_add(hist: dict, words, answer_words, seconds, censored, weight=1.0):
    cell = hist.setdefault(_cell_key(words, answer_words),
                           {"n": 0.0, "sq": 0.0, "sa": 0.0, "t": {}, "c": {}})
    cell["n"] += weight
    cell["sq"] += weight * words
    cell["sa"] += weight * answer_words
    b = str(int(min(seconds, MAX_REVEAL_S) // T_BIN))
    side = cell["c" if censored else "t"]
    side[b] = side.get(b, 0.0) + weight


def _hist_decay(data: dict) -> None:
    """Halve everything once the histogram is 'full', so it tracks you now."""
    if data.get("hist_n", 0.0) <= HIST_CAP:
        return
    for key in list(data["hist"]):
        cell = data["hist"][key]
        for f in ("n", "sq", "sa"):
            cell[f] *= 0.5
        for side in ("t", "c"):
            cell[side] = {b: w * 0.5 for b, w in cell[side].items() if w * 0.5 >= 0.05}
        if cell["n"] < 0.05:
            del data["hist"][key]
    data["hist_n"] *= 0.5
    data["self_n"] = data.get("self_n", 0.0) * 0.5


# ----- the per-kind tally -----
#
# Every kind of card, by (question words, answer words or cloze count,
# difficulty). Times are raw seconds, nothing divided out, so a later fit can
# work out the learning / new multipliers, the difficulty weight, the picture
# time and the one-by-one timings from what you actually did. Counts only, and
# halved like the histogram once it's full.

def _d_bucket(signal: float) -> int:
    return min(D_BUCKETS - 1, max(0, int((signal + 1.0) / 2.0 * D_BUCKETS)))


def _tally_add(data: dict, c: dict, seconds: float, censored: bool) -> None:
    # key = question words : answer words (one-by-one: clozes) : difficulty,
    # and one-by-one also splits by answer words, which its timer uses too.
    one_by_one = c["cat"] == "one_by_one_whole"
    second = c["clozes"] if one_by_one else c["answer_words"]
    key = (f"{int(min(c['words'], Q_MAX) // Q_BUCKET)}:"
           f"{int(min(second, A_MAX)) if one_by_one else int(min(second, A_MAX) // A_BUCKET)}:"
           f"{_d_bucket(c['dsig'])}")
    if one_by_one:
        key += f":{int(min(c['answer_words'], A_MAX) // A_BUCKET)}"
    _tally_cell_add(data, c["cat"], key, c["words"], second, c["dsig"],
                    c["answer_words"], seconds, censored)


def _tally_cloze(data: dict, c: dict, index: int, seconds: float,
                 censored: bool) -> None:
    """One cloze of a one-by-one card. Key = first cloze? : question words
    (first cloze only, it also carries the reading) : difficulty : this
    cloze's answer words. ``sw`` holds the first-cloze flag."""
    words = c["cloze_words"]
    cw = words[min(index, len(words) - 1)] if words else 0
    first = 1 if index == 0 else 0
    qw = c["words"] if first else 0
    key = (f"{first}:{int(min(qw, Q_MAX) // Q_BUCKET)}:{_d_bucket(c['dsig'])}:"
           f"{int(min(cw, A_MAX) // A_BUCKET)}")
    _tally_cell_add(data, "one_by_one", key, qw, cw, c["dsig"], first,
                    seconds, censored)


def _tally_cell_add(data, cat, key, words, second, dsig, sw, seconds, censored):
    cell = data.setdefault("tally", {}).setdefault(cat, {}).setdefault(
        key, {"n": 0.0, "sq": 0.0, "sa": 0.0, "sd": 0.0, "sw": 0.0, "t": {}, "c": {}})
    cell["n"] += 1.0
    cell["sq"] += words
    cell["sa"] += second
    cell["sd"] += dsig
    cell["sw"] = cell.get("sw", 0.0) + sw
    b = str(int(min(seconds, MAX_REVEAL_S) // T_BIN))
    side = cell["c" if censored else "t"]
    side[b] = side.get(b, 0.0) + 1.0
    data["tally_n"] = data.get("tally_n", 0.0) + 1.0
    if data["tally_n"] > HIST_CAP:
        for cat in list(data["tally"]):
            cells = data["tally"][cat]
            for k in list(cells):
                cl = cells[k]
                for f in ("n", "sq", "sa", "sd", "sw"):
                    cl[f] *= 0.5
                for sd in ("t", "c"):
                    cl[sd] = {b: w * 0.5 for b, w in cl[sd].items() if w * 0.5 >= 0.05}
                if cl["n"] < 0.05:
                    del cells[k]
        data["tally_n"] *= 0.5


def tally_counts() -> dict:
    """Cards tallied so far, per kind (for the Your pace tab)."""
    return {cat: sum(cl.get("n", 0.0) for cl in cells.values())
            for cat, cells in summary().get("tally", {}).items()}


# ----- per-card tracking (called from engine/injection.py) -----

def start_card(card, cfg: dict, inputs: dict, delay_s: float,
               cloze_words=None) -> None:
    """The timer started on this card's question. ``cloze_words`` (answer
    words per cloze, in reveal order) marks a one-by-one card."""
    global _card
    if not learning(cfg):
        _card = None
        return
    clozes = len(cloze_words) if cloze_words else 0
    cat = category(inputs, one_by_one=clozes > 0)
    _card = {
        "cid": card.id, "t0": time.time(), "delay": delay_s, "cat": cat,
        "words": inputs["words"], "answer_words": inputs["answer_words"],
        "clozes": clozes, "cloze_words": list(cloze_words or []),
        "cloze_events": [], "dsig": _dsig(inputs),
        # Only settled review cards feed calibration: new / learning cards run
        # on their own multipliers, and picture cards have no length to fit.
        "calibrate": cat == "review",
        "mult": _mult(cfg, inputs),
        "pace": current(cfg, cat),
        "auto": False, "held": False,
    }
    if _research is not None:
        try:
            _research.capture(card, cfg, inputs, _card, _session)
        except Exception:
            pass


def _dsig(inputs) -> float:
    from . import adaptive
    try:
        return adaptive._difficulty_signal(inputs["difficulty"], inputs["ease"],
                                           inputs["lapses"], inputs["reps"])
    except Exception:
        return 0.0


def _mult(cfg, inputs) -> float:
    from . import adaptive
    try:
        return max(0.1, adaptive.difficulty_multiplier(cfg, inputs))
    except Exception:
        return 1.0


def clear_card() -> None:
    """No timer on this card (off, excluded, new, or held from the start)."""
    global _card
    _card = None


def note_auto_fire() -> None:
    if _card is not None:
        _card["auto"] = True


def note_cloze(index: int, auto: bool, held: bool, seconds: float) -> None:
    """A one-by-one cloze was uncovered (reported by the reviewer)."""
    if _card is not None and _card["cat"] == "one_by_one":
        _card["cloze_events"].append(
            {"i": index, "auto": auto, "held": held, "s": round(seconds, 3)})


def note_hold() -> None:
    """More time / the pause key, pressed while this card's timer ran."""
    if _card is not None:
        _card["held"] = True


def end_card(card, cfg: dict) -> None:
    """The answer is showing. Record how it got there."""
    global _card, _session, _unsaved
    c, _card = _card, None
    if c is None or card is None or c["cid"] != card.id or not learning(cfg):
        return
    elapsed = time.time() - c["t0"]
    if elapsed <= 0 or (elapsed > MAX_REVEAL_S and not c["held"]):
        return                            # walked away: tells us nothing

    if c["cloze_events"]:
        # The template shows a one-by-one card's answer itself, so whether
        # the timer "got there first" is down to who uncovered the last cloze.
        last = c["cloze_events"][-1]
        c["auto"] = last["auto"]
        c["held"] = c["held"] or last["held"]

    if _session is None:
        _session = _new_session()
    s = _session
    s["cards"] += 1
    data = summary()
    yourself = not c["auto"] and not c["held"]
    # Judged once, before this card moves the average.
    active = _reveals_yourself()

    if c["held"]:
        s["held"] += 1
    elif c["auto"]:
        s["auto"] += 1
    else:
        s["self"] += 1
        s["reveal_s"].append(round(elapsed, 2))

    if _research is not None:
        try:
            _research.record(c, elapsed, active)
        except Exception:
            pass

    if c["cat"] == "one_by_one":
        _end_one_by_one(c, cfg, data, active)
        _unsaved += 1
        if _unsaved >= SAVE_EVERY:
            save()
        return

    if cfg.get("auto_tune_enabled", DEFAULTS["auto_tune_enabled"]) and c["cat"] in TUNED:
        if c["held"] or (c["auto"] and active):
            _nudge(True, cfg, c["cat"])
        elif yourself:
            _nudge(False, cfg, c["cat"])
        elif c["auto"]:
            _settle(data, c["cat"])

    if not c["held"]:
        _note_outcome(yourself)

    # Held cards include however long you sat on them, so they can't calibrate.
    # A timeout only says "you needed longer" if you normally reveal cards
    # yourself; while you're letting the timer run, it says nothing.
    if yourself or (c["auto"] and active):
        _tally_add(data, c, elapsed, censored=c["auto"])
    if c["calibrate"] and (yourself or (c["auto"] and active)):
        _hist_add(data["hist"], c["words"], c["answer_words"],
                  elapsed / c["mult"], censored=c["auto"])
        data["hist_n"] = data.get("hist_n", 0.0) + 1.0
        if yourself:
            data["self_n"] = data.get("self_n", 0.0) + 1.0
        _hist_decay(data)

    _unsaved += 1
    if _unsaved >= SAVE_EVERY:
        save()


def _end_one_by_one(c: dict, cfg: dict, data: dict, active: bool) -> None:
    """Score a one-by-one card cloze by cloze, as if each were its own card:
    the same nudges, the same 'counts only if you usually reveal' guard.
    Without per-cloze reports (a template that never ran the per-cloze
    timers) the whole card is tallied as one_by_one_whole."""
    tune = cfg.get("auto_tune_enabled", DEFAULTS["auto_tune_enabled"])
    events = c["cloze_events"]
    if not events:
        c = dict(c, cat="one_by_one_whole")
        yourself = not c["auto"] and not c["held"]
        if tune:
            if c["held"] or (c["auto"] and active):
                _nudge(True, cfg, "one_by_one")
            elif yourself:
                _nudge(False, cfg, "one_by_one")
        if not c["held"]:
            _note_outcome(yourself)
        if yourself or (c["auto"] and active):
            _tally_add(data, c, time.time() - c["t0"], censored=c["auto"])
        return
    for ev in events:
        if ev["s"] > MAX_REVEAL_S and not ev["held"]:
            continue
        yourself = not ev["auto"] and not ev["held"]
        if tune:
            if ev["held"] or (ev["auto"] and active):
                _nudge(True, cfg, "one_by_one")
            elif yourself:
                _nudge(False, cfg, "one_by_one")
        if not ev["held"]:
            _note_outcome(yourself)
        if yourself or (ev["auto"] and active):
            _tally_cloze(data, c, ev["i"], ev["s"], censored=ev["auto"])


def end_session() -> None:
    """Profile closing: file this session's one-line summary."""
    global _session
    s, _session = _session, None
    clear_card()
    if not s and not _unsaved:
        return                            # nothing recorded: don't write a file
    data = summary()
    if s and s["cards"]:
        times = sorted(s["reveal_s"])
        data["sessions"].append({
            "date": time.strftime("%Y-%m-%d", time.localtime(s["start"])),
            "cards": s["cards"],
            "self": s["self"], "auto": s["auto"], "held": s["held"],
            "median_s": times[len(times) // 2] if times else None,
            "pace": round(float(data.get("pace", 1.0)), 3),
        })
        del data["sessions"][:-SESSIONS_KEPT]
    save()


def session_so_far():
    return _session


# ----- calibration -----

def _percentile(cell: dict, q: float) -> float:
    """The q-quantile of a cell's reveal times. A timer that fired only says
    'at least this long', so those sit at their value as a lower bound."""
    pts = [((int(b) + 0.5) * T_BIN, w) for b, w in cell["t"].items()]
    pts += [((int(b) + 0.5) * T_BIN, w) for b, w in cell["c"].items()]
    pts.sort()
    total = sum(w for _, w in pts)
    acc = 0.0
    for v, w in pts:
        acc += w
        if acc >= q * total:
            return v
    return pts[-1][0] if pts else 0.0


def _solve(rows, cols: int):
    """Weighted least squares via the normal equations. rows = (w, xs, y)."""
    a = [[0.0] * cols for _ in range(cols)]
    b = [0.0] * cols
    for w, xs, y in rows:
        for i in range(cols):
            b[i] += w * xs[i] * y
            for j in range(cols):
                a[i][j] += w * xs[i] * xs[j]
    for i in range(cols):                 # Gaussian elimination, pivoting
        p = max(range(i, cols), key=lambda r: abs(a[r][i]))
        if abs(a[p][i]) < 1e-9:
            return None
        a[i], a[p] = a[p], a[i]
        b[i], b[p] = b[p], b[i]
        for r in range(i + 1, cols):
            f = a[r][i] / a[i][i]
            for c in range(i, cols):
                a[r][c] -= f * a[i][c]
            b[r] -= f * b[i]
    x = [0.0] * cols
    for i in range(cols - 1, -1, -1):
        x[i] = (b[i] - sum(a[i][j] * x[j] for j in range(i + 1, cols))) / a[i][i]
    return x


def fit(hist: dict, cfg: dict):
    """Suggested base / per-word / per-answer-word from a histogram, or None.

    Fits the target percentile of each cell against its mean word counts. The
    answer term is only fitted while it's switched on (a 0 there is your
    choice, not something to overrule). A term that comes out negative is
    dropped and the rest refitted, rather than suggesting a nonsense value.
    """
    q = 1.0 - _target(cfg)
    pts = []
    for cell in hist.values():
        n = cell.get("n", 0.0)
        if n < MIN_CELL:
            continue
        pts.append((n, cell["sq"] / n, cell["sa"] / n, _percentile(cell, q)))
    if len(pts) < 3 or len({round(p[1]) for p in pts}) < 2:
        return None

    use_answer = float(cfg.get("seconds_per_answer_word",
                               DEFAULTS["seconds_per_answer_word"])) > 0
    terms = ["words", "answer"] if use_answer else ["words"]
    while True:
        rows = [(w, [1.0] + [qw if t == "words" else aw for t in terms], y)
                for w, qw, aw, y in pts]
        x = _solve(rows, 1 + len(terms))
        if x is None:
            return None
        neg = [t for t, v in zip(terms, x[1:]) if v < 0]
        if not neg:
            break
        terms.remove(neg[0])
    coef = dict(zip(terms, x[1:]))
    return {
        "base_seconds": round(min(30.0, max(0.5, x[0])), 1),
        "seconds_per_word": round(min(2.0, coef.get("words", 0.0)), 2),
        "seconds_per_answer_word": (round(min(2.0, coef.get("answer", 0.0)), 2)
                                    if use_answer else 0.0),
        "cards": int(sum(p[0] for p in pts)),
    }


def length_rows(cfg: dict, n_rows: int = 4, min_n: float = 10.0) -> list:
    """Your most common question lengths, each with its typical answer length
    and the time you'd revealed the target share of those cards by (the same
    percentile calibration fits, difficulty evened out). For the preview.
    Empty while learning is off or there isn't enough to say anything."""
    if not learning(cfg):
        return []
    q = 1.0 - _target(cfg)
    merged = {}
    for key, cell in summary().get("hist", {}).items():
        m = merged.setdefault(key.split(":")[0],
                              {"n": 0.0, "sq": 0.0, "sa": 0.0, "t": {}, "c": {}})
        for f in ("n", "sq", "sa"):
            m[f] += cell.get(f, 0.0)
        for side in ("t", "c"):
            for b, w in cell.get(side, {}).items():
                m[side][b] = m[side].get(b, 0.0) + w
    cells = sorted((m for m in merged.values() if m["n"] >= min_n),
                   key=lambda m: m["n"], reverse=True)[:n_rows]
    rows = [{"words": int(round(m["sq"] / m["n"])),
             "answer_words": int(round(m["sa"] / m["n"])),
             "n": m["n"], "reveal_s": _percentile(m, q)} for m in cells]
    return sorted(rows, key=lambda r: r["words"]) if len(rows) >= 2 else []


# ----- calibrating the other settings, from the per-kind tally -----
#
# Each kind's times are compared with the plain base / per-word formula (the
# one Calibrate is about to apply, else the current one) at the same lengths,
# using the same percentile as everything else. Raw seconds in, so a fitted
# setting already carries that kind's pace: applying it resets that pace to 1.

MIN_KIND = {"learning": 40, "new": 40, "picture": 30, "one_by_one": 60,
            "one_by_one_whole": 30, "difficulty": 150}
UNIT = {"one_by_one": "clozes"}


def _formula(cfg: dict, words: float, answer_words: float) -> float:
    k = lambda key: float(cfg.get(key, DEFAULTS[key]))
    answer = min(k("seconds_per_answer_word") * max(0.0, answer_words),
                 max(0.0, k("max_answer_seconds")))
    return k("base_seconds") + k("seconds_per_word") * words + answer


def _kind_points(cat: str, q: float, dm=None) -> list:
    """(weight, mean q words, mean second slot, mean answer words, mean
    difficulty signal, percentile seconds) per usable cell.

    With ``dm`` (difficulty signal -> multiplier) the difficulty buckets are
    pooled, so a kind with few cards still has cells big enough to read a
    percentile from. Each bucket's times are divided by its own multiplier
    first — pooling raw times would let the hard cards set the percentile —
    so pooled points come back difficulty-neutral (signal 0)."""
    cells = summary().get("tally", {}).get(cat, {})
    if dm is not None:
        pooled = {}
        for key, cell in cells.items():
            n = cell.get("n", 0.0)
            if n <= 0:
                continue
            parts = key.split(":")
            m = pooled.setdefault(":".join(parts[:2] + parts[3:]), {
                "n": 0.0, "sq": 0.0, "sa": 0.0, "sd": 0.0, "sw": 0.0, "t": {}, "c": {}})
            for f in ("n", "sq", "sa", "sw"):
                m[f] += cell.get(f, 0.0)
            factor = dm(cell.get("sd", 0.0) / n)
            for side in ("t", "c"):
                for b, w in cell.get(side, {}).items():
                    secs = (int(b) + 0.5) * T_BIN / factor
                    nb = str(int(min(secs, MAX_REVEAL_S) // T_BIN))
                    m[side][nb] = m[side].get(nb, 0.0) + w
        cells = pooled
    out = []
    for cell in cells.values():
        n = cell.get("n", 0.0)
        if n < MIN_CELL:
            continue
        out.append((n, cell["sq"] / n, cell["sa"] / n, cell.get("sw", 0.0) / n,
                    cell["sd"] / n, _percentile(cell, q)))
    return out


def _cards(cat: str) -> int:
    return int(sum(cl.get("n", 0.0)
                   for cl in summary().get("tally", {}).get(cat, {}).values()))


def _ratio(points, ref) -> float:
    """Weighted ratio of measured to reference seconds."""
    num = sum(w * y for w, *_, y in points)
    den = sum(w * ref(p) for p in points for w in [p[0]])
    return num / den if den > 0 else 0.0


def fit_kinds(cfg: dict, main=None) -> dict:
    """Suggestions for the settings beyond base / per word. ``main`` is the
    base / per-word fit that Calibrate will apply alongside (or None).

    Returns {key: {"label", "value", "cards", "need"}}: ``value`` is None while
    there isn't enough data (``need`` = how many cards it wants), and a
    ``reason`` replaces both when it can't be measured at all.
    """
    if not learning(cfg):
        return {}
    ref_cfg = dict(cfg)
    if main:
        for key in ("base_seconds", "seconds_per_word", "seconds_per_answer_word"):
            if key in main and (key != "seconds_per_answer_word" or
                                float(cfg.get(key, 0)) > 0):
                ref_cfg[key] = main[key]
    q = 1.0 - _target(cfg)
    k = lambda key: float(cfg.get(key, DEFAULTS[key]))
    out = {}

    def entry(key, label, cat, value=None, reason=None, need=None):
        n = _cards(cat)
        need = need or MIN_KIND[cat]
        out[key] = {"label": label, "cards": n, "need": need,
                    "unit": UNIT.get(cat, "cards"),
                    "value": value if n >= need and not reason else None,
                    "reason": reason}

    # Difficulty weight: on review cards, does the measured / formula ratio
    # climb with difficulty? ratio ~ a + b * signal, weight = b / a.
    pts = _kind_points("review", q)
    fitted, reason = None, None
    if len({round(p[4] * 2) for p in pts}) >= 3:
        rows = [(w, [1.0, d], y / max(0.1, _formula(ref_cfg, qw, aw)))
                for w, qw, _, aw, d, y in pts]
        x = _solve(rows, 2)
        if x and x[0] > 0:
            fitted = round(min(1.0, max(0.0, x[1] / x[0])), 2)
    elif _cards("review") >= MIN_KIND["difficulty"]:
        reason = "cards too alike in difficulty to tell"
    entry("difficulty_weight", "Difficulty weight", "review", fitted, reason,
          need=MIN_KIND["difficulty"])
    weight = out["difficulty_weight"]["value"]
    if weight is None:
        weight = k("difficulty_weight")

    dm = lambda d: max(0.1, 1.0 + d * weight)

    for key, label, cat, lo in (("unfamiliar_multiplier", "Learning cards", "learning", 1.0),
                                ("new_multiplier", "New cards", "new", 1.0)):
        pts = _kind_points(cat, q, dm)
        value = None
        if pts:
            r = _ratio(pts, lambda p: _formula(ref_cfg, p[1], p[3]) * dm(p[4]))
            value = round(min(5.0, max(lo, r)), 2) if r else None
        entry(key, label, cat, value)
    if not cfg.get("enable_on_new", DEFAULTS["enable_on_new"]) and _cards("new") == 0:
        out["new_multiplier"]["reason"] = "timer is off on new cards"

    if cfg.get("fixed_time_enabled", DEFAULTS["fixed_time_enabled"]):
        pts = _kind_points("picture", q, dm)
        value = None
        if pts:
            r = sum(w * y / dm(d) for w, _, _, _, d, y in pts) / sum(p[0] for p in pts)
            value = round(min(60.0, max(0.5, r)), 1)
        entry("fixed_time_base_seconds", "Picture cards", "picture", value)

    mode = cfg.get("one_by_one_mode", DEFAULTS["one_by_one_mode"])
    if mode == "multiplier":
        pts = _kind_points("one_by_one_whole", q, dm)
        value = None
        if pts:
            r = _ratio(pts, lambda p: _formula(ref_cfg, p[1], p[3]) * dm(p[4]))
            value = round(min(5.0, max(0.5, r)), 2) if r else None
        entry("one_by_one_multiplier", "One-by-one multiplier", "one_by_one_whole", value)
    elif mode == "per_cloze":
        # Each cloze's time = per cloze + per word x its answer words; the
        # first cloze also carries the question's reading time, which comes
        # off first. A part that fits negative is held at 0 and the other
        # refitted on its own.
        rows = []
        for w, qw, cw, first, _d, y in _kind_points("one_by_one", q, dm):
            reading = _formula(ref_cfg, qw, 0) if first >= 0.5 else 0.0
            rows.append((w, cw, y - reading))
        pc = pw = None
        if len(rows) >= 2:
            x = _solve([(w, [1.0, cw], r) for w, cw, r in rows], 2)
            if x and x[0] >= 0 and x[1] >= 0:
                pc, pw = x
            elif x and x[1] < 0:
                pc = max(0.0, sum(w * r for w, _, r in rows) / sum(w for w, _, _ in rows))
                pw = 0.0
            else:
                den = sum(w * cw * cw for w, cw, _ in rows)
                pc, pw = 0.0, max(0.0, sum(w * cw * r for w, cw, r in rows) / den) if den else 0.0
        entry("one_by_one_seconds_per_cloze", "One-by-one, per cloze", "one_by_one",
              round(min(30.0, pc), 1) if pc is not None else None)
        entry("one_by_one_seconds_per_word", "One-by-one, per answer word", "one_by_one",
              round(min(5.0, pw), 2) if pw is not None else None)
    return out


def reveal_data_ready(cfg: dict) -> bool:
    return learning(cfg) and summary().get("self_n", 0.0) >= MIN_CALIBRATION


def fit_from_reveals(cfg: dict):
    return fit(summary().get("hist", {}), cfg)


def fit_from_revlog(col, cfg: dict):
    """Rough fallback for when aSFM hasn't watched enough reveals yet.

    Runs on the collection thread (it renders cards to count their words).
    Uses passed reviews under Anki's 60 s cap, takes an answer-reading
    allowance off each, and fits the same way as the reveal data.
    """
    from . import adaptive
    cutoff = int((time.time() - REVLOG_DAYS * 86400) * 1000)
    rows = col.db.all(
        "select cid, time from revlog where type = 1 and ease > 1 "
        "and time > 0 and time < 59000 and id > ? order by id desc limit 5000",
        cutoff)
    hist, cache = {}, {}
    for cid, ms in rows:
        if cid not in cache:
            if len(cache) >= REVLOG_MAX_CARDS:
                continue
            try:
                card = col.get_card(cid)
                inputs = adaptive.card_inputs(card, cfg)
                if inputs["fixed_time"]:
                    cache[cid] = None
                    continue
                cache[cid] = (inputs, _mult(cfg, inputs))
            except Exception:
                cache[cid] = None
                continue
        entry = cache.get(cid)
        if not entry:
            continue
        inputs, mult = entry
        allowance = REVLOG_ANSWER_BASE_S + REVLOG_ANSWER_PER_WORD_S * inputs["answer_words"]
        seconds = max(0.5, ms / 1000.0 - allowance)
        _hist_add(hist, inputs["words"], inputs["answer_words"], seconds / mult, False)
    result = fit(hist, cfg)
    if result is not None:
        result["cards_seen"] = len([v for v in cache.values() if v])
    return result
