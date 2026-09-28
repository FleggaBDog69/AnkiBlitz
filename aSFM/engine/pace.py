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

PACE_MIN, PACE_MAX = 0.85, 2.0   # never more than 15% quicker; up to 2× slower
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
            "hist": {}, "hist_n": 0.0, "self_n": 0.0, "sessions": []}


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


# ----- the learned pace -----

def _target(cfg: dict) -> float:
    pct = cfg.get("target_timer_wins_percent", DEFAULTS["target_timer_wins_percent"])
    return min(0.5, max(0.05, float(pct) / 100.0))


def current(cfg: dict) -> float:
    """The multiplier to apply now: the learned pace, or 1.0 while auto-tune
    is off (the learned value is kept, not lost, for when it's back on)."""
    if not cfg.get("auto_tune_enabled", DEFAULTS["auto_tune_enabled"]):
        return 1.0
    try:
        return min(PACE_MAX, max(PACE_MIN, float(summary().get("pace", 1.0))))
    except Exception:
        return 1.0


def reset_pace() -> None:
    data = summary()
    data["pace"] = 1.0
    data["pace_cards"] = 0
    save()


def _nudge(won: bool, cfg: dict) -> None:
    data = summary()
    t = _target(cfg)
    step = STEP * (1.0 - t) if won else -STEP * t
    data["pace"] = min(PACE_MAX, max(PACE_MIN, float(data.get("pace", 1.0)) * math.exp(step)))
    data["pace_cards"] = int(data.get("pace_cards", 0)) + 1


def _settle(data: dict) -> None:
    """You let the timer run: no evidence either way, so drift gently back to
    1.0×. Without this, a pace learned (or pushed up by a run of timeouts)
    before you switched to letting it run would be stuck there for good."""
    p = float(data.get("pace", 1.0))
    data["pace"] = p + SETTLE * (1.0 - p)


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


# ----- per-card tracking (called from engine/injection.py) -----

def start_card(card, cfg: dict, inputs: dict, delay_s: float) -> None:
    """The timer started on this card's question."""
    global _card
    _card = {
        "cid": card.id, "t0": time.time(), "delay": delay_s,
        "words": inputs["words"], "answer_words": inputs["answer_words"],
        # Only settled review cards feed calibration: new / learning cards run
        # on their own multipliers, and picture cards have no length to fit.
        "calibrate": (not inputs["fixed_time"] and not inputs["unfamiliar"]
                      and not inputs["is_new"]),
        "mult": _mult(cfg, inputs),
        "auto": False, "held": False,
    }


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


def note_hold() -> None:
    """More time / the pause key, pressed while this card's timer ran."""
    if _card is not None:
        _card["held"] = True


def end_card(card, cfg: dict) -> None:
    """The answer is showing. Record how it got there."""
    global _card, _session, _unsaved
    c, _card = _card, None
    if c is None or card is None or c["cid"] != card.id:
        return
    elapsed = time.time() - c["t0"]
    if elapsed <= 0 or (elapsed > MAX_REVEAL_S and not c["held"]):
        return                            # walked away: tells us nothing

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

    if cfg.get("auto_tune_enabled", DEFAULTS["auto_tune_enabled"]):
        if c["held"] or (c["auto"] and active):
            _nudge(True, cfg)
        elif yourself:
            _nudge(False, cfg)
        elif c["auto"]:
            _settle(data)

    if not c["held"]:
        _note_outcome(yourself)

    # Held cards include however long you sat on them, so they can't calibrate.
    # A timeout only says "you needed longer" if you normally reveal cards
    # yourself; while you're letting the timer run, it says nothing.
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


def end_session() -> None:
    """Profile closing: file this session's one-line summary."""
    global _session
    s, _session = _session, None
    clear_card()
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


def reveal_data_ready() -> bool:
    return summary().get("self_n", 0.0) >= MIN_CALIBRATION


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
