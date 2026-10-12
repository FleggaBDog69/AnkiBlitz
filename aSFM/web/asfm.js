/* Adaptive Speed Focus (aSFM) — the auto-reveal timer.
 *
 * Python pushes a per-card payload via ASFM.onCard(payload); this bundle owns the
 * delay timer, the depleting countdown bar, and the pre-reveal warning. When the
 * delay elapses it asks Python to show the answer. It NEVER grades the card.
 *
 * Standalone: it does not depend on any word-reveal add-on. The delay is whatever
 * Python computed; the answer shows when it elapses.
 *
 * The wait can be held indefinitely — by the pause key, or by the "More time"
 * button that sits above the countdown while it runs. Both call the same
 * toggleAutoPause(), so there is one hold and one state, not two.
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
  var warned = false;     // has this card passed its warning point?
  var obo = null;         // this card's per-cloze one-by-one timers (see below)

  function fire() {
    if (oboActive() && obo.left > 0 && window.revealNextCloze) {
      // Uncover the next cloze, not the answer. The template answers with an
      // anking:1b1-reveal event, which arms the next cloze's timer (or, after
      // the last one, the template flips to the answer itself).
      window.revealNextCloze();
      return;
    }
    pycmd("asfm:reveal");
  }

  // ----- cloze one-by-one: a timer per cloze -----
  //
  // The AnKing template (patched to do one-by-one on the FRONT) keeps the
  // question up while you uncover its clozes, and announces itself with
  // document events. In per_cloze mode Python sends one delay per cloze; each
  // firing uncovers the next cloze, and uncovering one yourself starts the next
  // cloze's timer. With a template that never announces itself nothing here
  // starts, and the ordinary whole-card timer runs.
  function oboActive() { return !!(obo && obo.active); }

  function oboDelay() {
    var d = obo.delaysMs;
    return d[Math.min(Math.max(0, obo.total - obo.left), d.length - 1)] || 0;
  }

  function oboBegin(total, left) {
    if (!obo || obo.active || !obo.delaysMs.length) return;
    obo.active = true;
    obo.total = total || obo.delaysMs.length;
    obo.left = (left === undefined) ? obo.total : left;
    // The whole-card timer may already be running (the template announced
    // itself after this card's onCard): swap it for the first cloze's.
    if (started && pending) armClozeTimer(oboDelay());
  }

  function oboRevealed(left) {
    if (!oboActive() || !pending) return;
    if (!(left < obo.left)) return;   // another word of the same cloze (Shift+N)
    obo.left = left;
    if (left <= 0) {                  // the template flips to the answer now
      cancel();
      return;
    }
    // Not started yet (held from the start): start() picks up the right cloze.
    if (started) armClozeTimer(oboDelay());
  }

  // A fresh wait for the current cloze: new countdown, new warning point.
  function armClozeTimer(ms) {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    warned = false;
    removeCountdown();
    obo.waitMs = ms;       // the whole wait this cloze's bar stands for
    var warnMs = warnPointMs(ms);
    if (autoPaused) {
      // Held: resuming (pause key / More time) starts this cloze's full wait.
      pauseLeftMs = ms;
      pauseWarnLeftMs = warnMs;
      return;
    }
    if (pending.showCountdown) showCountdown(ms);
    showMoreTime();
    armAutoTimers(ms, warnMs);
  }

  document.addEventListener("anking:1b1-start", function (e) {
    oboBegin(e.detail && e.detail.total);
  });
  document.addEventListener("anking:1b1-reveal", function (e) {
    oboRevealed(e.detail ? e.detail.remaining : 0);
  });

  // ----- the pause key -----

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  function onKeyDown(e) {
    if (!A._pauseEnabled) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // Holding the key down auto-repeats it, which would flicker the hold on and
    // off; only a fresh press toggles.
    if (e.repeat) return;
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
          showMoreTime();
        }
      } else {
        start();          // the card started paused — begin its wait now
      }
      pycmd("asfm:autopause:0");
      return;
    }
    autoPaused = true;
    stopAlert();
    var now = Date.now();
    pauseLeftMs = autoDeadline ? Math.max(0, autoDeadline - now) : 0;
    pauseWarnLeftMs = warnDeadline ? Math.max(0, warnDeadline - now) : 0;
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    freezeCountdown();
    removeMoreTime();     // the paused badge takes its place
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
    removeMoreTime();
    if (document.getElementById("asfm-paused")) return;
    var b = document.createElement("div");
    b.id = "asfm-paused";
    b.textContent = "⏸ Auto-reveal paused · " + resumeHint();
    if (A._moreTime) {
      // Resuming has to be possible with the same input that paused it: a
      // mouse user who pressed the button and can't press the key would
      // otherwise be stuck on the card.
      b.className = "asfm-clickable";
      b.setAttribute("role", "button");
      b.addEventListener("click", onControlClick, false);
    }
    document.body.appendChild(b);
  }

  function removePausedBadge() {
    var el = document.getElementById("asfm-paused");
    if (el) el.remove();
  }

  // ----- the "More time" button -----
  //
  // The pause key is invisible: you only find it if you read the settings. This
  // is the same hold with a control you can see, which is what Glutanimate's
  // Speed Focus Mode offered. It holds indefinitely rather than adding a fixed
  // number of seconds — "give me a moment" almost never means "give me exactly
  // five more seconds", and an indefinite hold has one obvious way out.

  function onControlClick(e) {
    // The click must not also reach the card: with Progressive Word Reveal
    // installed, a bare click reveals the question.
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    toggleAutoPause();
  }

  function showMoreTime() {
    if (!A._moreTime || !pending || autoPaused) return;
    if (document.getElementById("asfm-moretime")) return;
    var b = document.createElement("div");
    b.id = "asfm-moretime";
    // Announced as a button, but deliberately not focusable: a focused button
    // would take Space, which is Anki's show-answer key.
    b.setAttribute("role", "button");
    b.textContent = "⏸ More time";
    b.title = A._pauseEnabled
      ? "Hold the auto-reveal (or press "
        + (A._pauseKey || "p").toUpperCase() + ")"
      : "Hold the auto-reveal";
    b.addEventListener("click", onControlClick, false);
    document.body.appendChild(b);
  }

  function removeMoreTime() {
    var el = document.getElementById("asfm-moretime");
    if (el) el.remove();
  }

  // What the paused badge tells you to do to get going again — only ever
  // offering something that is actually switched on.
  function resumeHint() {
    var key = (A._pauseKey || "p").toUpperCase();
    if (A._moreTime && A._pauseEnabled) return "click or press " + key + " to resume";
    if (A._moreTime) return "click to resume";
    return "press " + key + " to resume";
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

  // The inline transition replaces the stylesheet's, so it has to carry the
  // colour fade for the warning point as well as the depletion.
  function depletion(ms) {
    return "transform " + ms + "ms linear, background-color 0.4s ease";
  }

  function resumeCountdown(ms) {
    var fill = countdownFill();
    if (!fill) {
      // The paused badge took the bar down; rebuild it at the length that was
      // actually left, not at full, so it doesn't overstate the wait.
      var total = (oboActive() && obo.waitMs) || (pending && pending.delayMs) || ms;
      showCountdown(ms, Math.min(1, ms / total));
      return;
    }
    requestAnimationFrame(function () {
      fill.style.transition = depletion(ms);
      requestAnimationFrame(function () { fill.style.transform = "scaleX(0)"; });
    });
  }

  // Deplete left-to-right over ms, starting from `from` (1 = full).
  function showCountdown(ms, from) {
    removeCountdown();
    var bar = document.createElement("div");
    bar.id = "asfm-countdown";
    if (pending && pending.warnColour) bar.className = "asfm-shift";
    var fill = document.createElement("div");
    fill.className = "asfm-countdown-fill";
    if (from !== undefined && from < 1) {
      fill.style.transform = "scaleX(" + Math.max(0, from) + ")";
    }
    bar.appendChild(fill);
    document.body.appendChild(bar);
    if (warned) markWarned();
    requestAnimationFrame(function () {
      fill.style.transition = depletion(ms);
      requestAnimationFrame(function () {
        fill.style.transform = "scaleX(0)";
      });
    });
  }

  function markWarned() {
    var bar = document.getElementById("asfm-countdown");
    if (bar) bar.classList.add("asfm-warned");
  }

  // The warning point: the sound, the colour shift, or both.
  function onWarn() {
    warned = true;
    if (!pending) return;
    // One-by-one: colour on every cloze, but the sound only before the last
    // one — the one that ends in the answer. A chime per cloze is just noise.
    if (pending.warn && (!oboActive() || obo.left <= 1)) playAlert();
    if (pending.warnColour) markWarned();
  }

  function removeCountdown() {
    var el = document.getElementById("asfm-countdown");
    if (el) el.remove();
  }

  function cancel() {
    stopAlert();
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    removeCountdown();
    removePausedBadge();
    removeMoreTime();
  }

  // The heads-up alert. Anki routes sound FILES through mpv, and its bundled
  // mpv does not run on every macOS it ships to — on macOS 13 it aborts at
  // launch, which costs you the alert (card TTS is unaffected: that goes
  // through `say`). Playing it here keeps the alert on the reviewer's own audio
  // stack; `asfm:warn` stays as the fallback when the webview won't play.
  var alertAudio = null;
  var alertPrimed = false;

  function alertElement(url) {
    if (!alertAudio || alertAudio.getAttribute("data-src") !== url) {
      alertAudio = new Audio(url);
      alertAudio.setAttribute("data-src", url);
      alertAudio.preload = "auto";
    }
    return alertAudio;
  }

  // Chromium refuses to play audio until the DOCUMENT has seen a user gesture,
  // and Anki rebuilds the reviewer document every time you enter the reviewer —
  // so on the first card the alert fires before the page has been touched and
  // is refused. A muted play/pause on the first gesture is enough to mark the
  // element allowed, so the alert is ready by the time the timer reaches it.
  // Left registered rather than {once:true}: the first gesture can land before
  // any card payload has arrived, and there is nothing to prime yet.
  function primeAlert() {
    if (alertPrimed) return;
    var url = pending && pending.alertUrl;
    if (!url) return;
    alertPrimed = true;
    try {
      var el = alertElement(url);
      el.muted = true;
      var settle = function () {
        try { el.pause(); el.currentTime = 0; } catch (e) {}
        el.muted = false;
      };
      var p = el.play();
      if (p && typeof p.then === "function") { p.then(settle, settle); }
      else { settle(); }
    } catch (e) {}
  }
  document.addEventListener("pointerdown", primeAlert, true);
  document.addEventListener("keydown", primeAlert, true);

  // The chime belongs to the reviewer page, not the card, so on its own it
  // plays on after you flip. Cut it whenever the wait it was warning about
  // ends: you showed the answer (space mid-chime), the timer did, the card
  // changed, or you held the timer.
  function stopAlert() {
    if (!alertAudio) return;
    try { alertAudio.pause(); alertAudio.currentTime = 0; } catch (e) {}
  }

  function playAlert() {
    var url = pending && pending.alertUrl;
    if (!url) { pycmd("asfm:warn"); return; }
    try {
      var el = alertElement(url);
      el.muted = false;
      el.currentTime = 0;
      var played = el.play();
      if (played && typeof played.catch === "function") {
        played.catch(function () { pycmd("asfm:warn"); });
      }
    } catch (e) {
      pycmd("asfm:warn");
    }
  }

  // Start (or restart, after a pause) the reveal + warning timers, remembering
  // the deadlines so a pause can work out what was left on each.
  function armAutoTimers(delay, warnMs) {
    autoTimer = setTimeout(fire, delay);
    autoDeadline = Date.now() + delay;
    if (warnMs > 0 && warnMs < delay) {
      warnTimer = setTimeout(onWarn, warnMs);
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
    var delay = oboActive() ? oboDelay() : (pending.delayMs || 0);
    if (oboActive()) obo.waitMs = delay;
    if (pending.showCountdown && delay > 0) showCountdown(delay);
    if (delay <= 0) {
      fire();
      return;
    }
    // Only once there is a wait to hold: on a zero-delay card the answer is
    // already up, and a button offering to pause it would do nothing.
    showMoreTime();
    armAutoTimers(delay, warnPointMs(delay));
  }

  // Heads-up (sound and/or bar colour) once warnPercent% of the wait is gone.
  function warnPointMs(ms) {
    var pct = pending.warnPercent || 0;
    var wantWarn = pending.warn || (pending.warnColour && pending.showCountdown);
    return (wantWarn && pct > 0 && pct < 100) ? ms * (pct / 100) : 0;
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
    warned = false;
    pending = null;
    payload = payload || {};
    A._pauseKey = (payload.pauseKey || "p").toLowerCase();
    A._pauseEnabled = !!payload.pauseEnabled;
    A._moreTime = !!payload.moreTimeButton;
    // Python owns the sticky pause, so it survives re-injection of this bundle.
    autoPaused = !!payload.autoPaused;
    // Per-cloze one-by-one timers. The template may have announced itself
    // before this onCard arrived; its state is only trusted while its element
    // is on screen (the reviewer page, and these globals, outlive the card).
    obo = null;
    var plan = payload.enabled && payload.oneByOne;
    if (plan && plan.mode === "per_cloze" && plan.delaysMs && plan.delaysMs.length) {
      obo = { delaysMs: plan.delaysMs, active: false, total: 0, left: 0, waitMs: 0 };
      var st = window.ankingOneByOne;
      if (st && st.root && document.body.contains(st.root)) {
        obo.active = true;
        obo.total = st.total;
        obo.left = st.remaining();
      }
    }
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
