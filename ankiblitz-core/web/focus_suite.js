/* AnkiBlitz Core — reviewer JS bundle.
 *
 * Python pushes a per-card payload via FocusSuite.onCard(payload) and drives the
 * Blitz progress bar with FocusSuite.setProgress(...). This bundle owns the bar
 * and the paused-launch engagement hold.
 *
 * Core has no auto-reveal timer and no progressive reveal — those live in the
 * separate aSFM and Progressive Word Reveal add-ons.
 *
 * Injected once per webview; guarded so re-injection keeps one instance.
 */
(function () {
  var prev = window.FocusSuite;
  // A real (non-stub) instance already exists — nothing to do.
  if (prev && !prev._queue) return;

  var FS = {};

  // ----- paused-launch engagement hold -----
  //
  // Paused launch (overnight relaunch): the first card opens with the session
  // clock frozen at 0:00 until the user actually engages. The first click or key
  // tells Python (which starts the clock).
  var pausedHold = false;
  var engagementArmed = false;

  function armEngagementHold() {
    if (engagementArmed) return;
    engagementArmed = true;
    function go() {
      document.removeEventListener("click", go, true);
      document.removeEventListener("keydown", go, true);
      engagementArmed = false;
      pausedHold = false;
      pycmd("focus:engaged");
    }
    document.addEventListener("click", go, true);
    document.addEventListener("keydown", go, true);
  }

  // ----- public: per-card entry point -----

  FS.onCard = function (payload) {
    pausedHold = !!(payload && payload.paused);
    if (pausedHold) armEngagementHold();
  };

  // ----- public: Blitz progress bar -----
  //
  // Card/fraction modes fill the bar by cardsDone/target; time mode fills by
  // elapsed/deadline and, when the deadline passes, tells Python once via
  // focus:timeup. A single ticker keeps the clock and the time-mode bar live.
  //
  // The same renderer draws the ambient bar for an ordinary review session
  // (payload.ambient): it arrives as a cards-mode payload whose target is the
  // whole due pile, wears the dimmer .fs-ambient skin, and carries a label.

  var progressState = null;
  var progressTimer = null;
  var timeUpSent = false;
  var lastStartedAt = 0;
  var lastStreak = 0;   // for the streak-increase pulse animation

  function fmtClock(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var m = Math.floor(s / 60);
    var r = s % 60;
    return (m < 10 ? "0" : "") + m + ":" + (r < 10 ? "0" : "") + r;
  }

  // The estimate is rendered coarse on purpose. It is a forecast off your
  // review history (forecast.py), so "~14 min" is the whole of what it knows;
  // a seconds digit ticking down would claim a precision it doesn't have, and
  // would pull the eye off the card every second to do it.
  function fmtEta(sec) {
    if (sec < 90) return "~1 min left";
    var m = Math.round(sec / 60);
    if (m < 60) return "~" + m + " min left";
    var h = Math.floor(m / 60);
    return "~" + h + " h " + (m % 60) + " m left";
  }

  // One linear-gradient with hard stops, not one div per card: a 200-card
  // session would otherwise rebuild 200 nodes on every answer and every tick of
  // the clock, on a machine where the reviewer's memory is already the thing
  // that bites.
  //
  // The bands butt straight up against each other. A divider between them was
  // tried and cut: it only ever separates two bands of the SAME colour (a
  // colour change already separates itself), and paying for that with a gap in
  // every band on the bar is a bad trade — the run of green is the thing you're
  // meant to see, not the cards it's made of.
  function segGradient(segs) {
    var total = 0, i;
    for (i = 0; i < segs.length; i++) total += segs[i][0];
    var stops = [], at = 0;
    for (i = 0; i < segs.length; i++) {
      var w = total > 0 ? (segs[i][0] / total) * 100 : 100 / segs.length;
      // The last band lands exactly on 100% so rounding can never leave a sliver
      // of bare track inside the fill.
      var end = i === segs.length - 1 ? 100 : at + w;
      stops.push((segs[i][1] ? "var(--fs-again-c)" : "var(--fs-good-c)")
                 + " " + at.toFixed(3) + "% " + end.toFixed(3) + "%");
      at = end;
    }
    return "linear-gradient(90deg," + stops.join(",") + ")";
  }

  // Give the card its own scroll area BELOW the bar instead of letting the page
  // scroll under it. The bar keeps a fixed strip at the very top; <body> becomes
  // a scroll container pinned beneath it, so card content (even a tall histology
  // image) can never travel up behind the bar — it just scrolls inside its own
  // area. Reverted by releaseStrip() in clearProgress. (Qt WebEngine = Chromium,
  // which honours position:fixed on <body>.)
  function reserveStrip(h) {
    document.documentElement.style.overflow = "hidden";
    var s = document.body.style;
    s.position = "fixed";
    s.top = h + "px";
    s.left = "0";
    s.right = "0";
    s.bottom = "0";
    s.overflowY = "auto";
    s.overflowX = "hidden";
    s.paddingTop = "0";
  }
  function releaseStrip() {
    document.documentElement.style.overflow = "";
    var s = document.body.style;
    s.position = "";
    s.top = "";
    s.left = "";
    s.right = "";
    s.bottom = "";
    s.overflowY = "";
    s.overflowX = "";
    s.paddingTop = "";
  }

  function renderProgress() {
    var p = progressState;
    if (!p) return;
    var bar = document.getElementById("fs-progress");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "fs-progress";
      document.body.appendChild(bar);
    }
    // The ambient (no-Blitz) bar wears a dimmer skin so it reads as background
    // information rather than a session you committed to.
    bar.className = p.ambient ? "fs-ambient" : "";
    var now = Date.now();
    var isTime = p.mode === "time";
    // The countdown only runs once Python says so (first card flipped); until
    // then the bar sits full and the clock shows the whole budget.
    var timeRunning = isTime && p.running !== false && p.deadlineMs > 0;
    var unit = p.unit || "cards";

    var pct;
    if (isTime) {
      if (timeRunning) {
        var span = p.deadlineMs - p.startedAtMs;
        pct = span > 0 ? Math.min(100, ((now - p.startedAtMs) / span) * 100) : 0;
      } else {
        pct = 0;
      }
    } else {
      pct = p.target > 0 ? Math.min(100, (p.cardsDone / p.target) * 100) : 0;
    }

    var rowParts = "";
    if (p.ambient && p.label) {
      rowParts += '<span class="fs-label">' + p.label + "</span>";
    }
    if (p.showCounter) {
      var counter = isTime
        ? p.cardsDone + " " + unit
        : p.cardsDone + " / " + p.target + " " + unit;
      rowParts += '<span class="fs-counter">' + counter + "</span>";
    }
    if (p.showElapsed) {
      var clock;
      if (isTime) {
        var leftMs = timeRunning ? (p.deadlineMs - now) : (p.targetMs || 0);
        clock = fmtClock(leftMs) + " left";
      } else {
        // Paused launch: hold the clock at 0:00 until the user engages.
        clock = p.paused ? fmtClock(0) : fmtClock(now - p.startedAtMs);
      }
      rowParts += '<span class="fs-elapsed">' + clock + "</span>";
    }
    // The colours named in words. Two bands of colour alone are a state you
    // have to be told the key to; with the legend up you can read the bar
    // without one, and the standalone Again chip below would only say the same
    // number again, so it stands down while this is showing.
    if (p.splitBar && p.cardsDone > 0) {
      rowParts += '<span class="fs-split">'
        + '<span class="fs-good-txt">' + p.doneGood + " good</span>"
        + '<span class="fs-split-sep">·</span>'
        + '<span class="fs-again-txt">' + p.doneAgain + " again</span>"
        + "</span>";
    }
    // The estimate. Cards/fraction/ambient forecast the time left; time mode
    // forecasts the cards instead, because there the clock is the thing you
    // already know. Absent only when there's no estimate to give.
    if (p.showEta) {
      if (isTime && p.projCards !== null && p.projCards !== undefined) {
        rowParts += '<span class="fs-eta">~' + p.projCards + " more " + unit + "</span>";
      } else if (!isTime && p.etaSeconds) {
        rowParts += '<span class="fs-eta">' + fmtEta(p.etaSeconds) + "</span>";
      }
    }
    if (p.showPace && p.perMin) {
      rowParts += '<span class="fs-pace">' + p.perMin.toFixed(1) + " " + unit + "/min</span>";
    }
    // Live stats — each gated by its toggle (Python already applies the
    // anti-pressure hide before sending these).
    if (p.showAccuracy) {
      rowParts += '<span class="fs-acc">' + p.accuracy + "%</span>";
    }
    if (p.showAgain && !p.splitBar) {
      rowParts += '<span class="fs-again">Again ×' + p.again + "</span>";
    }
    if (p.showStreak) {
      var anim = p.streakAnim && p.streak > lastStreak ? " fs-pulse" : "";
      rowParts += '<span class="fs-streak' + anim + '">🔥 ' + p.streak + "</span>";
    }
    lastStreak = p.streak || 0;
    // The filled region carries the session's texture: one band per answer, in
    // the order you did them, green for a clean pass and red for an Again, each
    // as wide as the thinking time that card took. The fill EDGE still means
    // exactly what it did — this much of the pile is done — because the bands
    // are normalised across the fill rather than added to it.
    var fill = "";
    if (p.showBar) {
      if (p.splitBar && p.segs && p.segs.length) {
        fill = '<div class="fs-bar fs-seg fs-cap" style="width:' + pct.toFixed(2)
             + "%;background-image:" + segGradient(p.segs) + '"></div>';
      } else {
        fill = '<div class="fs-bar" style="width:' + pct.toFixed(2) + '%"></div>';
      }
    }

    // Two layouts for the same numbers.
    //
    // Overlaid (the default): one thick band IS the bar, and the counters sit on
    // top of it. The stacked layout spent most of the strip's height on empty
    // surface with a 7px bar underneath it; this spends it on the bar. The fill
    // is one even band, turned down just enough that the text stays readable
    // over it. (It used to go down twice — a faint band plus a full-strength
    // rail along the bottom — but that read as the top of the bar being greyed
    // out, not as one bar.)
    //
    // Stacked: the original. Kept because a busy row over a coloured band is a
    // fair thing to not want on every card.
    var rowHtml = '<div class="fs-row">' + rowParts + "</div>";
    if (p.overlayStats !== false && p.showBar) {
      bar.innerHTML =
        '<div class="fs-bar-wrap fs-overlay">'
        + '<div class="fs-fill">' + fill + "</div>"
        + rowHtml + "</div>";
    } else {
      bar.innerHTML = rowHtml
        + (fill ? '<div class="fs-bar-wrap">' + fill + "</div>" : "");
    }
    // Reserve a dedicated strip and scroll the card beneath it. Rows can wrap when
    // live stats are on, so measure the bar's ACTUAL height every render.
    reserveStrip(bar.offsetHeight);

    if (timeRunning && now >= p.deadlineMs && !timeUpSent) {
      timeUpSent = true;
      pycmd("focus:timeup");
    }
  }

  FS.setProgress = function (p) {
    progressState = p;
    if (p.startedAtMs !== lastStartedAt) {
      lastStartedAt = p.startedAtMs;
      timeUpSent = false;   // a fresh Blitz; allow a new time-up signal
      lastStreak = 0;
    }
    renderProgress();

    if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
    // Tick when there's a live clock to update or a time-mode bar/deadline to
    // advance between answers. Not while paused — the clock is frozen at 0:00.
    var needsTick = (p.showElapsed && !p.paused)
      || (p.mode === "time" && p.deadlineMs > 0);
    if (needsTick) {
      progressTimer = setInterval(renderProgress, 1000);
    }
  };

  FS.clearProgress = function () {
    var bar = document.getElementById("fs-progress");
    if (bar) bar.remove();
    releaseStrip();
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
    progressState = null;
  };

  window.FocusSuite = FS;

  // Flush any calls buffered by the inline shim before this bundle loaded.
  if (prev && prev._queue) {
    prev._queue.forEach(function (c) {
      try { FS[c[0]].apply(FS, c[1]); } catch (e) {}
    });
  }
})();
