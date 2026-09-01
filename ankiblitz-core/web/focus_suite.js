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
    // Live stats — each gated by its toggle (Python already applies the
    // anti-pressure hide before sending these).
    if (p.showAccuracy) {
      rowParts += '<span class="fs-acc">' + p.accuracy + "%</span>";
    }
    if (p.showAgain) {
      rowParts += '<span class="fs-again">Again ×' + p.again + "</span>";
    }
    if (p.showStreak) {
      var anim = p.streakAnim && p.streak > lastStreak ? " fs-pulse" : "";
      rowParts += '<span class="fs-streak' + anim + '">🔥 ' + p.streak + "</span>";
    }
    lastStreak = p.streak || 0;
    var barHtml = p.showBar
      ? '<div class="fs-bar-wrap"><div class="fs-bar" style="width:' + pct.toFixed(2) + '%"></div></div>'
      : "";
    bar.innerHTML = '<div class="fs-row">' + rowParts + "</div>" + barHtml;
    // Push the card below the bar's ACTUAL height (rows can wrap when live stats
    // are on), so card text is never hidden under it.
    document.body.style.paddingTop = bar.offsetHeight + "px";

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
    document.body.style.paddingTop = "";
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
