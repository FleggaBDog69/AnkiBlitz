"""The progress bar's time estimate: what's in the pile, priced off your history.

    time left = (presses the pile will still cost) x (seconds per press)

**Presses the pile will still cost.** Not one per card. A review you get right
is one press; one you miss comes back as a relearn step; a new card goes round
its learning steps. So each kind of card is charged the number of presses that
kind of card has actually cost YOU on the day it was due, read off the last
HISTORY_DAYS of the review log:

* ``new``    — presses a brand-new card took on the day you first saw it
* ``review`` — presses a due review took that day (1.0 if you never missed)
* ``learn``  — presses still to come for a card that's mid-step (it was pressed
  and is coming back today)

On top of what Anki's counts show, it also charges the learning cards that are
waiting on a step timer and aren't in the counts yet. Those are the cards that
used to make the pile look like it "wasn't shrinking": they were never left out
of the work, only out of the count.

**Seconds per press.** Your historical gap between presses, blended toward
today's as the session goes (PRIOR_PRESSES of history against everything
today). It has a number from the first card, and no single card can swing it
much: one slow card is one press out of all of today's plus the prior's.

All of it is read-only and cheap: the history is a single revlog scan, cached
for the day; the live part is Anki's counts plus one indexed count query.
Everything is defensive — any failure just means no estimate.
"""

import time
from typing import Optional

from aqt import mw

HISTORY_DAYS = 90
# Below this many presses of history, the defaults stand in.
MIN_HISTORY_PRESSES = 200
# How many presses' worth of weight the history carries against today's pace.
PRIOR_PRESSES = 50
# Same clamp the rolling pace uses: a hard card counts as slow, a walk-away
# doesn't count as a 20-minute card.
GAP_CAP = 120.0
# Gaps longer than this are a break between sittings, not a slow card.
SITTING_GAP = 300.0

# Typical values, used until there's enough history to measure them.
DEFAULTS = {"spp": 12.0, "new": 1.5, "learn": 1.3, "review": 1.15}

_cache: dict = {"key": None, "stats": None}


def _day_of(ms: int, rollover_h: int) -> tuple:
    """The Anki day a press falls on: local date, with the day starting at the
    rollover hour. Via localtime rather than a fixed offset so daylight saving
    doesn't shift the boundary by an hour for half the year."""
    lt = time.localtime(ms / 1000 - rollover_h * 3600)
    return (lt.tm_year, lt.tm_yday)


def _measure(col) -> Optional[dict]:
    since_ms = int((time.time() - HISTORY_DAYS * 86400) * 1000)
    rows = col.db.all(
        "select id, cid, type from revlog where id > ? and ease > 0 "
        "and type in (0, 1, 2, 3) order by id", since_ms)
    if len(rows) < MIN_HISTORY_PRESSES:
        return None
    try:
        rollover = int(col.get_config("rollover", 4))
    except Exception:
        rollover = 4
    # Cards whose very first press falls in the window are the genuinely new
    # ones; a type-0 press on an older card is just a learning step.
    first_seen = dict(col.db.all(
        "select cid, min(id) from revlog where ease > 0 and type in (0, 1, 2, 3) "
        "and cid in (select distinct cid from revlog where id > ?) group by cid",
        since_ms))

    gap_sum = gap_n = 0.0
    prev = None
    groups: dict = {}          # (cid, day) -> [first press id, first type, presses]
    for rid, cid, rtype in rows:
        if prev is not None:
            gap = (rid - prev) / 1000.0
            if gap < SITTING_GAP:
                gap_sum += min(gap, GAP_CAP)
                gap_n += 1
        prev = rid
        key = (cid, _day_of(rid, rollover))
        g = groups.get(key)
        if g is None:
            groups[key] = [rid, rtype, 1]
        else:
            g[2] += 1

    tot = {"new": [0, 0], "review": [0, 0]}
    learn_after = learn_n = 0
    for (cid, _day), (fid, ftype, n) in groups.items():
        if ftype == 0 and first_seen.get(cid) == fid:
            kind = "new"
        elif ftype in (1, 3):
            kind = "review"
        else:
            kind = None
        if kind:
            tot[kind][0] += n
            tot[kind][1] += 1
        # Every press but the day's last left the card coming back today; what
        # followed it is what a mid-step card still costs.
        learn_after += n * (n - 1) / 2
        learn_n += n - 1

    out = dict(DEFAULTS)
    if gap_n >= MIN_HISTORY_PRESSES:
        out["spp"] = gap_sum / gap_n
    for kind, (presses, cards) in tot.items():
        if cards >= 30:
            out[kind] = presses / cards
    if learn_n >= 30:
        out["learn"] = learn_after / learn_n
    return out


def history(col=None) -> dict:
    """Your per-kind press costs and seconds per press, cached for the day."""
    col = col or mw.col
    key = (id(col), time.strftime("%Y-%m-%d"))
    if _cache["key"] != key:
        stats = None
        try:
            stats = _measure(col)
        except Exception:
            stats = None
        _cache["key"] = key
        _cache["stats"] = stats or dict(DEFAULTS)
    return _cache["stats"]


def _pending_learning(col) -> int:
    """Intraday learning cards in this deck that are coming back today but
    aren't in Anki's counts yet (their step timer is still running)."""
    try:
        did = col.decks.current()["id"]
        dids = list(col.decks.deck_and_child_ids(did))
        ahead = int(col.get_config("collapseTime", 1200))
        now = int(time.time())
        cutoff = int(col.sched.day_cutoff)
        return int(col.db.scalar(
            "select count() from cards where queue = 1 and due > ? and due < ? "
            "and did in (%s)" % ",".join(str(int(d)) for d in dids),
            now + ahead, cutoff) or 0)
    except Exception:
        return 0


def pile(col=None) -> Optional[dict]:
    """What's left today: the counts, the hidden learning cards, and what the
    lot will cost in presses."""
    col = col or mw.col
    try:
        new, learn, review = (int(x) for x in col.sched.counts())
    except Exception:
        return None
    h = history(col)
    pending = _pending_learning(col)
    presses = (new * h["new"] + (learn + pending) * h["learn"]
               + review * h["review"])
    cards = new + learn + review
    return {
        "cards": cards,
        "pending": pending,
        "presses": presses,
        # Presses per card for this particular pile — what a card the counter
        # counts once is going to cost, given the mix you've got.
        "per_card": (presses / (cards + pending)) if (cards + pending) else 1.0,
    }


def seconds_per_press(sess) -> float:
    """History's pace, pulled toward today's as today's presses pile up."""
    h = history()
    k = PRIOR_PRESSES
    s_sum = float(getattr(sess, "gap_sum", 0.0))
    s_n = int(getattr(sess, "gap_n", 0))
    return (h["spp"] * k + s_sum) / (k + s_n)
