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

  function fire() {
    pycmd("asfm:reveal");
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
    removeCountdown();
  }

  function start() {
    if (!pending || started) return;
    started = true;
    var delay = pending.delayMs || 0;
    if (pending.showCountdown && delay > 0) showCountdown(delay);
    if (delay <= 0) {
      fire();
      return;
    }
    autoTimer = setTimeout(fire, delay);
    // Heads-up alert once warnPercent% of the wait has elapsed.
    var pct = pending.warnPercent || 0;
    if (pending.warn && pct > 0 && pct < 100) {
      var wt = delay * (pct / 100);
      if (wt > 0 && wt < delay) {
        warnTimer = setTimeout(function () { pycmd("asfm:warn"); }, wt);
      }
    }
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
    if (payload && payload.enabled) {
      pending = payload;
      start();
    }
  };

  window.ASFM = A;

  // Flush any calls buffered by the inline shim before this bundle loaded.
  if (prev && prev._queue) {
    prev._queue.forEach(function (c) {
      try { A[c[0]].apply(A, c[1]); } catch (e) {}
    });
  }
})();
