"""Adaptive auto-reveal delay — computed in Python, per card.

The auto-reveal timer (our redefined "Speed Focus") never grades a card; it
only reveals the answer after a delay. That delay should feel proportionate:
longer questions and less-familiar / harder cards get more thinking time.

    delay = (base + length_term) * familiarity_mult * difficulty_mult
    delay = clamp(delay, min_delay, max_delay)

The difficulty term is driven by the card's **FSRS difficulty** (1–10) when
available, falling back to SM-2 ease only for cards without FSRS state. It is a
gentle, bounded nudge: ``difficulty_mult`` stays within ``1 ± difficulty_weight``
(set ``difficulty_weight`` to 0 to ignore difficulty entirely). Everything here
is config-tunable (see config.py → "speed_focus") and deliberately transparent.
"""

import html as _html
import re
from html.parser import HTMLParser

# Strip whole <script>/<style> blocks INCLUDING their text bodies first: a card's
# rendered question_text carries the front template's inline JS/CSS source, and
# those tokens would otherwise be counted as "words" and inflate the reveal delay
# (often pinning it at max_delay, making base/per-word inert). Comments next, so
# commented-out markup isn't counted either. Only then strip remaining tags.
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_DEFAULT_EASE = 2500  # Anki's default ease factor, in permille

# Hidden / non-question chrome must NOT count toward the reveal delay. Many note
# types (AnKing, etc.) render extra material into the FRONT HTML that the human
# never reads while answering: the full clickable tag list ({{clickable::Tags}}),
# hint/Extra fields hidden behind buttons, one-by-one source, AnKing/AnkiHub ids.
# A 15-word stem on such a note can carry ~30 extra "words" of tags + hidden
# fields, which would otherwise more than double the timer. We drop:
#   * <script>/<style>/<head>/media subtrees,
#   * anything inline-hidden (style display:none / visibility:hidden, or the
#     `hidden` attribute),
#   * elements whose id/class marks them as tag chips / hints / extras / chrome.
_HIDE_STYLE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_SKIP_TAGS = {"script", "style", "head", "title", "audio", "video", "noscript"}
_VOID_TAGS = {"br", "img", "hr", "input", "meta", "link", "area", "base",
              "col", "embed", "source", "track", "wbr"}
# Substrings matched against an element's id + class (lower-cased). Conservative:
# these name reveal-chrome on the common medical note types, not stem content.
_CHROME_TOKENS = ("tag", "hint", "extra", "ankihub", "onebyone", "one-by-one",
                  "timer", "notification", "kbd")


class _VisibleText(HTMLParser):
    """Collects only the text a reviewer actually sees on the question side.

    Skips the subtree of any element that is hidden (inline) or is reveal-chrome
    (tags / hints / extras), using a tag stack so nested markup is handled even
    when the card HTML is imperfectly closed.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack = []   # (tag, started_a_skip)
        self._skip = 0
        self.parts = []

    @staticmethod
    def _hides(tag, attrs) -> bool:
        if tag in _SKIP_TAGS:
            return True
        d = {k: (v or "") for k, v in attrs}
        if "hidden" in d:
            return True
        if _HIDE_STYLE_RE.search(d.get("style", "")):
            return True
        idcls = (d.get("id", "") + " " + d.get("class", "")).lower()
        return any(tok in idcls for tok in _CHROME_TOKENS)

    def handle_starttag(self, tag, attrs):
        if tag in _VOID_TAGS:
            return
        hide = self._hides(tag, attrs)
        if hide:
            self._skip += 1
        self._stack.append((tag, hide))

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                for _, hide in self._stack[i:]:
                    if hide:
                        self._skip -= 1
                del self._stack[i:]
                return

    def handle_data(self, data):
        if self._skip == 0:
            self.parts.append(data)


def _count_words(text: str) -> int:
    return len([w for w in text.split() if any(ch.isalnum() for ch in w)])


def _question_word_count(card) -> int:
    """Word count of the rendered question as a human SEES it: scripts/styles and
    hidden / tag-chip / hint chrome dropped, remaining tags stripped, entities
    unescaped. Falls back to a plain tag-strip if HTML parsing ever fails."""
    raw = ""
    try:
        raw = card.render_output(reload=False).question_text
    except Exception:
        try:
            raw = card.question()
        except Exception:
            raw = ""
    raw = raw or ""
    try:
        parser = _VisibleText()
        parser.feed(raw)
        parser.close()
        return _count_words("".join(parser.parts))
    except Exception:
        # Defensive fallback: old behaviour (over-counts hidden chrome, but never
        # crashes the timer). Drop script/style/comment bodies, then tags.
        text = _SCRIPT_STYLE_RE.sub(" ", raw)
        text = _COMMENT_RE.sub(" ", text)
        text = _html.unescape(_TAG_RE.sub(" ", text))
        return _count_words(text)


def _is_unfamiliar(card) -> bool:
    """New, learning, or relearning cards are treated as less familiar."""
    try:
        return card.type in (0, 1, 3)
    except Exception:
        return False


def is_new_card(card) -> bool:
    """True for a genuinely new (never-studied) card."""
    try:
        return card.type == 0
    except Exception:
        return False


_FSRS_MID = 5.0  # FSRS difficulty runs 1 (easiest) .. 10 (hardest); ~5 is average


def fsrs_difficulty(card):
    """The card's FSRS difficulty (1–10) if it has memory state, else None.

    Returns None for cards with no FSRS state (e.g. brand-new cards, or a
    collection not using FSRS) so the caller can fall back to the ease heuristic.
    """
    try:
        ms = card.memory_state
    except Exception:
        return None
    if ms is None:
        return None
    try:
        d = float(ms.difficulty)
    except Exception:
        return None
    if d <= 0:
        return None
    # Defend against a 0–1 normalised representation by rescaling to 1–10.
    if d <= 1.0:
        d = 1.0 + d * 9.0
    return d


def _difficulty_signal(difficulty, ease: int, lapses: int, reps: int) -> float:
    """A centered hardness signal in [-1, 1]; 0 = an average card.

    Prefers FSRS difficulty (1–10, average ~5). For cards without FSRS state it
    falls back to SM-2 ease (lower = harder) with a small lapse nudge. The signal
    is bounded so the delay adjustment can only swing by ±weight.
    """
    if difficulty is not None:
        return max(-1.0, min(1.0, (difficulty - _FSRS_MID) / 5.0))
    ease = ease or _DEFAULT_EASE
    sig = (_DEFAULT_EASE - ease) / 1200.0          # 1300 ease -> +1.0, 3500 -> ~-0.83
    if reps > 0:
        sig += 0.5 * min(1.0, max(0, lapses) / reps)
    return max(-1.0, min(1.0, sig))


def _difficulty_multiplier(difficulty, ease: int, lapses: int, reps: int,
                           weight: float) -> float:
    """1.0 for an average card; >1 harder, <1 easier, bounded to 1 ± weight."""
    if weight <= 0:
        return 1.0
    return 1.0 + _difficulty_signal(difficulty, ease, lapses, reps) * weight


def delay_for(cfg: dict, words: int, ease: int, lapses: int, reps: int,
              unfamiliar: bool, is_new: bool = False, difficulty=None,
              fixed_time: bool = False) -> float:
    """Pure core: the reveal delay from explicit card primitives.

    Shared by the live runtime (reveal_delay_seconds) and the settings preview,
    so both always agree on the math. New cards use ``new_multiplier``;
    learning / relearning cards use ``unfamiliar_multiplier``. ``difficulty`` is
    the FSRS difficulty (1–10) when available; otherwise the ease/lapse fallback
    is used. The difficulty term only shifts the delay by ±``difficulty_weight``.

    ``fixed_time`` cards (picture / visual note types or decks — see
    ``is_fixed_time_card``) ignore word count and familiarity entirely: they get
    a SET base time (``fixed_time_base_seconds``) with only the difficulty term
    as a modifier, since there is no text to read.
    """
    lo = float(cfg.get("min_delay_seconds", 2.0))
    hi = float(cfg.get("max_delay_seconds", 30.0))
    weight = float(cfg.get("difficulty_weight", 1.0))

    if fixed_time:
        delay = float(cfg.get("fixed_time_base_seconds", 6.0))
        delay *= _difficulty_multiplier(difficulty, ease, lapses, reps, weight)
    else:
        base = float(cfg.get("base_seconds", 4.0))
        per_word = float(cfg.get("seconds_per_word", 0.35))
        unfamiliar_mult = float(cfg.get("unfamiliar_multiplier", 1.3))
        new_mult = float(cfg.get("new_multiplier", 2.0))
        delay = base + per_word * words
        if is_new:
            delay *= new_mult
        elif unfamiliar:
            delay *= unfamiliar_mult
        delay *= _difficulty_multiplier(difficulty, ease, lapses, reps, weight)

    if hi < lo:
        hi = lo
    return max(lo, min(delay, hi))


def is_fixed_time_card(card, cfg: dict) -> bool:
    """True when this card is a 'picture / visual' card that should use a set
    reveal time (no per-word term). Matched by note-type name or deck, exactly
    like the exclusion lists. These two lists live outside the profile system so
    the choice endures across every profile."""
    if not cfg.get("fixed_time_enabled", True):
        return False
    note_types = cfg.get("fixed_time_note_types", [])
    decks = cfg.get("fixed_time_decks", [])
    if not note_types and not decks:
        return False
    try:
        nt = card.note_type()
        if nt and nt.get("name") in note_types:
            return True
    except Exception:
        pass
    try:
        from aqt import mw
        deck_name = mw.col.decks.name(card.current_deck_id())
        for entry in decks:
            if entry and (deck_name == entry or deck_name.startswith(entry + "::")):
                return True
    except Exception:
        pass
    return False


def reveal_delay_seconds(card, cfg: dict) -> float:
    """Seconds to wait (after the reveal finishes) before showing the answer."""
    try:
        ease = card.factor or _DEFAULT_EASE
    except Exception:
        ease = _DEFAULT_EASE
    try:
        lapses, reps = card.lapses, card.reps
    except Exception:
        lapses, reps = 0, 1
    fixed = is_fixed_time_card(card, cfg)
    return delay_for(
        cfg,
        words=0 if fixed else _question_word_count(card),
        ease=ease,
        lapses=lapses,
        reps=reps,
        unfamiliar=_is_unfamiliar(card),
        is_new=is_new_card(card),
        difficulty=fsrs_difficulty(card),
        fixed_time=fixed,
    )
