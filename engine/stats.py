"""Persistent Blitz stats, stored as JSON in the add-on's user_files/.

Only completed Blitzes count; cancelled/bailed Blitzes leave no trace.
"""

import json
import os
from datetime import date, timedelta

from aqt import mw
from aqt.qt import (
    QDialog, QVBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton, Qt,
)

from ..config import get_section


def _path() -> str:
    # engine/stats.py -> focus_suite/
    suite_dir = os.path.dirname(os.path.dirname(__file__))
    uf = os.path.join(suite_dir, "user_files")
    os.makedirs(uf, exist_ok=True)
    return os.path.join(uf, "sprint_stats.json")


def _defaults() -> dict:
    return {
        "by_day": {},
        "total_sprints": 0,
        "total_cards": 0,
        "best_cards_per_min": 0.0,
        "best_cards_per_min_size": 0,
        # Focus metrics (Stage 6).
        "best_focus_score": 0,
        "total_idle_seconds": 0.0,
        # Pomodoro day log (Stage 5): per-date list of completed work blocks,
        # each {"c": cards, "s": seconds}. Powers the break-screen timeline.
        "pomodoro_log": {},
        # Quick Start metrics (Stage 4).
        "quick_start": {
            "last_launch_date": "",       # gate "once per day" (set even if cancelled)
            "last_completed_date": "",    # drives the streak
            "streak": 0,
            "best_streak": 0,
            "last_launch_to_first_ms": 0,
            "best_launch_to_first_ms": 0,
        },
    }


def load_stats() -> dict:
    """Load the store, back-filling any missing keys so old files gain new ones."""
    try:
        with open(_path(), "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return _defaults()
    if not isinstance(data, dict):
        return _defaults()
    # Additive default-merge: top-level keys, then the quick_start sub-keys.
    for key, default in _defaults().items():
        if key not in data:
            data[key] = default
        elif key == "quick_start" and isinstance(data[key], dict):
            for sk, sv in default.items():
                data[key].setdefault(sk, sv)
    return data


def save_stats(data: dict) -> None:
    with open(_path(), "w") as f:
        json.dump(data, f, indent=2)


def record_completed_sprint(cards: int, seconds: float,
                            focus_score: int = 0, idle_seconds: float = 0.0) -> dict:
    data = load_stats()
    today = date.today().isoformat()
    day = data["by_day"].get(today, {"sprints": 0, "cards": 0, "seconds": 0.0})
    day["sprints"] += 1
    day["cards"] += cards
    day["seconds"] += seconds
    data["by_day"][today] = day
    data["total_sprints"] += 1
    data["total_cards"] += cards

    if seconds > 0:
        cpm = cards / (seconds / 60.0)
        if cpm > data["best_cards_per_min"]:
            data["best_cards_per_min"] = cpm
            data["best_cards_per_min_size"] = cards

    if focus_score > int(data.get("best_focus_score", 0)):
        data["best_focus_score"] = int(focus_score)
    if idle_seconds > 0:
        data["total_idle_seconds"] = float(data.get("total_idle_seconds", 0.0)) + idle_seconds

    save_stats(data)
    return data


def sprints_today() -> int:
    today = date.today().isoformat()
    return load_stats()["by_day"].get(today, {}).get("sprints", 0)


# ----- Pomodoro day log (Stage 5) -----

def record_pomodoro_block(cards: int, seconds: float) -> None:
    """Append a completed Pomodoro work block to today's log."""
    data = load_stats()
    log = data.setdefault("pomodoro_log", {})
    today = date.today().isoformat()
    log.setdefault(today, []).append({"c": int(cards), "s": round(float(seconds), 1)})
    save_stats(data)


def pomodoro_blocks_today() -> list:
    return load_stats().get("pomodoro_log", {}).get(date.today().isoformat(), [])


def set_last_block_focus(rating: int) -> None:
    """Attach a 1-5 focus rating to today's most recent logged block."""
    data = load_stats()
    entries = data.get("pomodoro_log", {}).get(date.today().isoformat())
    if entries:
        entries[-1]["f"] = int(rating)
        save_stats(data)


def pomodoro_today_summary() -> dict:
    blocks = pomodoro_blocks_today()
    focus = [int(b["f"]) for b in blocks if b.get("f")]
    return {
        "blocks": len(blocks),
        "seconds": sum(float(b.get("s", 0)) for b in blocks),
        "cards": sum(int(b.get("c", 0)) for b in blocks),
        "avg_focus": (sum(focus) / len(focus)) if focus else 0.0,
    }


def pomodoro_all_time() -> dict:
    log = load_stats().get("pomodoro_log", {})
    total_blocks = total_secs = 0
    best_day = 0
    best_day_date = ""
    for d, entries in log.items():
        total_blocks += len(entries)
        total_secs += sum(float(e.get("s", 0)) for e in entries)
        if len(entries) > best_day:
            best_day, best_day_date = len(entries), d
    return {
        "blocks": total_blocks,
        "seconds": total_secs,
        "best_day": best_day,
        "best_day_date": best_day_date,
        "days": len(log),
    }


def _short_day(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%b %d").replace(" 0", " ")
    except Exception:
        return iso


# ----- Quick Start metrics (Stage 4) -----

def mark_quick_start_launched() -> None:
    """Record that Quick Start launched today (so it doesn't re-nag same-day)."""
    data = load_stats()
    data["quick_start"]["last_launch_date"] = date.today().isoformat()
    save_stats(data)


def quick_start_launched_today() -> bool:
    return load_stats()["quick_start"].get("last_launch_date", "") == date.today().isoformat()


def record_quick_start_completed() -> dict:
    """Update the consecutive-days-completed streak. Returns the saved stats."""
    data = load_stats()
    qs = data["quick_start"]
    today = date.today()
    today_iso = today.isoformat()
    last = qs.get("last_completed_date", "")
    if last == today_iso:
        return data  # already counted today
    if last == (today - timedelta(days=1)).isoformat():
        qs["streak"] = int(qs.get("streak", 0)) + 1
    else:
        qs["streak"] = 1
    qs["last_completed_date"] = today_iso
    qs["best_streak"] = max(int(qs.get("best_streak", 0)), qs["streak"])
    save_stats(data)
    return data


def current_quick_start_streak() -> int:
    """The live streak: alive only if the last completion was today or yesterday."""
    qs = load_stats()["quick_start"]
    last = qs.get("last_completed_date", "")
    today = date.today()
    if last in (today.isoformat(), (today - timedelta(days=1)).isoformat()):
        return int(qs.get("streak", 0))
    return 0


def record_launch_to_first(ms: int) -> None:
    if ms <= 0:
        return
    data = load_stats()
    qs = data["quick_start"]
    qs["last_launch_to_first_ms"] = int(ms)
    best = int(qs.get("best_launch_to_first_ms", 0))
    if best == 0 or ms < best:
        qs["best_launch_to_first_ms"] = int(ms)
    save_stats(data)


def open_stats_window() -> None:
    data = load_stats()
    cfg = get_section("sprint")
    today = date.today().isoformat()
    today_data = data["by_day"].get(today, {"sprints": 0, "cards": 0, "seconds": 0.0})

    dlg = QDialog(mw)
    dlg.setWindowTitle("Blitz stats")
    dlg.setMinimumWidth(420)
    root = QVBoxLayout(dlg)

    title = QLabel("⚡ AnkiBlitz stats")
    title.setStyleSheet("font-size: 18px; font-weight: 700; margin-bottom: 4px;")
    root.addWidget(title)

    def make_group(name):
        box = QGroupBox(name)
        grid = QGridLayout(box)
        grid.setColumnStretch(1, 1)
        grid.setVerticalSpacing(3)
        root.addWidget(box)
        state = {"row": 0}

        def add(label, value, accent=False):
            lbl = QLabel(label)
            lbl.setStyleSheet("opacity: 0.7;")
            val = QLabel(str(value))
            val.setStyleSheet("font-weight: 700;" + (" font-size: 15px;" if accent else ""))
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(lbl, state["row"], 0)
            grid.addWidget(val, state["row"], 1)
            state["row"] += 1
        return add

    # --- Today ---
    today_g = make_group("Today")
    today_g("Blitzes completed", today_data["sprints"], accent=True)
    today_g("Cards", today_data["cards"])
    today_g("Time in Blitzes", f"{(today_data['seconds'] or 0) / 60:.1f} min")

    # --- Pomodoro (shown when on or there's any history) ---
    pt, pa = pomodoro_today_summary(), pomodoro_all_time()
    if get_section("pomodoro").get("enabled", True) or pa["blocks"]:
        pg = make_group("Pomodoro")
        pg("Blocks today", pt["blocks"], accent=True)
        pg("Focus time today", f"{pt['seconds'] / 60:.0f} min")
        goal = int(get_section("pomodoro").get("daily_goal", 0))
        if goal > 0:
            done = pt["blocks"]
            pg("Daily goal", f"{done} / {goal} blocks" + ("  ✓" if done >= goal else ""))
        if pt["avg_focus"]:
            pg("Avg focus today", f"{pt['avg_focus']:.1f} / 5")
        pg("Blocks all-time", pa["blocks"])
        if pa["best_day"]:
            pg("Best day", f"{pa['best_day']} blocks ({_short_day(pa['best_day_date'])})")

    # --- All-time ---
    all_g = make_group("All-time")
    all_g("Total Blitzes", data["total_sprints"], accent=True)
    all_g("Total cards", data["total_cards"])
    if cfg.get("track_pb_speed", True) and data["best_cards_per_min"] > 0:
        all_g("Best speed", f"{data['best_cards_per_min']:.1f} cards/min")
    if int(data.get("best_focus_score", 0)) > 0:
        all_g("Best Focus Score", f"{int(data['best_focus_score'])} / 100")

    # --- Quick Start (shown when on or there's any history) ---
    qs = data["quick_start"]
    if (get_section("quick_start").get("enabled", False)
            or qs.get("last_completed_date") or qs.get("best_streak", 0)):
        qg = make_group("Quick Start")
        qg("Current streak", f"{current_quick_start_streak()} day(s)", accent=True)
        qg("Best streak", f"{int(qs.get('best_streak', 0))} day(s)")
        ltf = int(qs.get("last_launch_to_first_ms", 0))
        best_ltf = int(qs.get("best_launch_to_first_ms", 0))
        if ltf > 0:
            qg("Launch → first card", f"{ltf / 1000:.1f} s (best {best_ltf / 1000:.1f})")

    close = QPushButton("Close")
    close.clicked.connect(dlg.accept)
    root.addWidget(close)
    dlg.exec()
