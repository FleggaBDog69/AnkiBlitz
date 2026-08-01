/* Adaptive Speed Focus (aSFM) — the auto-reveal timer.
 *
 * Python pushes a per-card payload via ASFM.onCard(payload); this bundle owns the
 * delay timer, the depleting countdown bar, and the pre-reveal warning. When the
 * delay elapses it asks Python to show the answer. It NEVER grades the card.
 *
 * Standalone: it does not depend on any word-reveal add-on. The delay is whatever
 * Python computed; the answer shows when it elapses.
 *
 * Injected once per webview; guarded so re-injection keeps one instance.
 */
(function () {
  var prev = window.ASFM;
  // A real (non-stub) instance already exists — nothing to do.
  if (prev && !prev._queue) return;

  var A = {};
  var autoTimer = null;   // the auto-reveal delay timer
  var warnTimer = null;   // the pre-reveal warning-sound timer
  var started = false;    // has the timer been started for this card?
  var pending = null;     // this card's auto-reveal config
  // Pause key state. autoPaused is sticky across cards (Python mirrors it, so it
  // also survives the bundle being re-injected) — a held timer stays held until
  // you press the key again, and every card says so on screen while it is.
  var autoPaused = false;
  var autoDeadline = 0;   // when the pending auto-reveal would fire
  var warnDeadline = 0;   // when the warning sound would play
  var pauseLeftMs = 0;    // what was left on each when the timer was paused
  var pauseWarnLeftMs = 0;

  function fire() {
    pycmd("asfm:reveal");
  }

  // ----- the pause key -----

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  function onKeyDown(e) {
    if (!A._pauseEnabled) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTypingTarget(e.target)) return;   // e.g. Anki's type-in-the-answer box
    if ((e.key || "").toLowerCase() !== A._pauseKey) return;
    e.preventDefault();
    toggleAutoPause();
  }

  function toggleAutoPause() {
    if (autoPaused) {
      autoPaused = false;
      removePausedBadge();
      if (started) {
        // Mid-card: pick the timer up where it was frozen.
        var left = Math.max(0, pauseLeftMs);
        if (left <= 0) {
          fire();
        } else {
          if (pending && pending.showCountdown) resumeCountdown(left);
          armAutoTimers(left, pauseWarnLeftMs);
        }
      } else {
        start();          // the card started paused — begin its wait now
      }
      pycmd("asfm:autopause:0");
      return;
    }
    autoPaused = true;
    var now = Date.now();
    pauseLeftMs = autoDeadline ? Math.max(0, autoDeadline - now) : 0;
    pauseWarnLeftMs = warnDeadline ? Math.max(0, warnDeadline - now) : 0;
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    freezeCountdown();
    showPausedBadge();
    pycmd("asfm:autopause:1");
  }

  // The badge is deliberately worded, not just coloured: a paused timer that
  // only looked different would read as "aSFM is broken".
  function showPausedBadge() {
    // Nothing to pause on this card (aSFM off or excluded) — saying "paused"
    // here would be a lie; the sticky flag still applies from the next card
    // that does run a timer.
    if (!pending) return;
    removeCountdown();
    if (document.getElementById("asfm-paused")) return;
    var b = document.createElement("div");
    b.id = "asfm-paused";
    b.textContent = "⏸ Auto-reveal paused · press "
      + (A._pauseKey || "p").toUpperCase() + " to resume";
    document.body.appendChild(b);
  }

  function removePausedBadge() {
    var el = document.getElementById("asfm-paused");
    if (el) el.remove();
  }

  function countdownFill() {
    var bar = document.getElementById("asfm-countdown");
    return bar ? bar.querySelector(".asfm-countdown-fill") : null;
  }

  // Stop the depleting bar where it stands by pinning its current transform.
  function freezeCountdown() {
    var fill = countdownFill();
    if (!fill) return;
    var current = "scaleX(1)";
    try {
      var t = window.getComputedStyle(fill).transform;
      if (t && t !== "none") current = t;
    } catch (e) {}
    fill.style.transition = "none";
    fill.style.transform = current;
  }

  function resumeCountdown(ms) {
    var fill = countdownFill();
    if (!fill) {
      showCountdown(ms);
      return;
    }
    requestAnimationFrame(function () {
      fill.style.transition = "transform " + ms + "ms linear";
      requestAnimationFrame(function () { fill.style.transform = "scaleX(0)"; });
    });
  }

  function showCountdown(ms) {
    removeCountdown();
    var bar = document.createElement("div");
    bar.id = "asfm-countdown";
    var fill = document.createElement("div");
    fill.className = "asfm-countdown-fill";
    bar.appendChild(fill);
    document.body.appendChild(bar);
    // Deplete left-to-right over ms.
    requestAnimationFrame(function () {
      fill.style.transition = "transform " + ms + "ms linear";
      requestAnimationFrame(function () {
        fill.style.transform = "scaleX(0)";
      });
    });
  }

  function removeCountdown() {
    var el = document.getElementById("asfm-countdown");
    if (el) el.remove();
  }

  function cancel() {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    removeCountdown();
    removePausedBadge();
  }

  // Start (or restart, after a pause) the reveal + warning timers, remembering
  // the deadlines so a pause can work out what was left on each.
  function armAutoTimers(delay, warnMs) {
    autoTimer = setTimeout(fire, delay);
    autoDeadline = Date.now() + delay;
    if (warnMs > 0 && warnMs < delay) {
      warnTimer = setTimeout(function () { pycmd("asfm:warn"); }, warnMs);
      warnDeadline = Date.now() + warnMs;
    } else {
      warnDeadline = 0;
    }
  }

  function start() {
    if (!pending || started) return;
    if (autoPaused) {       // held by you, until you press the pause key
      showPausedBadge();
      return;
    }
    started = true;
    var delay = pending.delayMs || 0;
    if (pending.showCountdown && delay > 0) showCountdown(delay);
    if (delay <= 0) {
      fire();
      return;
    }
    // Heads-up alert once warnPercent% of the wait has elapsed.
    var pct = pending.warnPercent || 0;
    var warnMs = (pending.warn && pct > 0 && pct < 100) ? delay * (pct / 100) : 0;
    armAutoTimers(delay, warnMs);
  }

  // Public: stop the timer/countdown for the current card without showing the
  // answer (e.g. if another add-on takes over the screen). Safe to call anytime.
  A.pauseAuto = function () {
    cancel();
    pending = null;
  };

  // Public: per-card entry point.
  A.onCard = function (payload) {
    cancel();
    started = false;
    pending = null;
    payload = payload || {};
    A._pauseKey = (payload.pauseKey || "p").toLowerCase();
    A._pauseEnabled = !!payload.pauseEnabled;
    // Python owns the sticky pause, so it survives re-injection of this bundle.
    autoPaused = !!payload.autoPaused;
    if (payload.enabled) {
      pending = payload;
      start();
    }
  };

  // One listener for the life of the webview. The bundle is guarded against
  // re-injection above, so this can't stack duplicates.
  document.addEventListener("keydown", onKeyDown, true);

  window.ASFM = A;

  // Flush any calls buffered by the inline shim before this bundle loaded.
  if (prev && prev._queue) {
    prev._queue.forEach(function (c) {
      try { A[c[0]].apply(A, c[1]); } catch (e) {}
    });
  }
})();
