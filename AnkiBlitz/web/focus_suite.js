/* AnkiBlitz — single reviewer JS bundle.
 *
 * Python pushes a payload per card via FocusSuite.onCard(payload); this bundle
 * owns all DOM + timing. Three jobs:
 *   1. Progressive reveal: fade the card's words in at a fixed reading rate.
 *   2. Adaptive auto-reveal: after the reveal finishes, wait delayMs (computed
 *      in Python) then ask Python to show the answer. NEVER grades.
 *   3. Blitz progress bar bound to the session counter.
 *
 * Injected once per webview; guarded so re-injection keeps one instance.
 */
(function () {
  var prev = window.FocusSuite;
  // A real (non-stub) instance already exists — nothing to do.
  if (prev && !prev._queue) return;

  var FS = {};

  // ----- shared state -----
  var wordTimeouts = [];     // pending word-reveal timeouts
  var doneTimeout = null;    // fires when the whole reveal has finished
  var autoTimer = null;      // the auto-reveal delay timer
  var warnTimer = null;      // pre-reveal warning-sound timer
  var revealDone = false;    // has the reveal finished for this card?
  var revealDurationMs = 0;  // how long the progressive reveal takes
  var minPostMs = 0;         // hold the answer >= this long after the reveal finishes
  var autoStarted = false;   // has the auto-reveal timer been started?
  var autoFired = false;     // delay elapsed but waiting on the reveal to finish
  var pendingAuto = null;    // autoReveal config for this card
  var clickHandler = null;
  var keyHandler = null;

  function getRoot() {
    return document.getElementById("qa") || document.body;
  }

  function isSkippable(node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return false;
    var tag = node.tagName || "";
    if (tag === "SCRIPT" || tag === "STYLE") return true;
    if (tag.indexOf("MJX") === 0) return true; // MathJax v3
    var id = node.id || "";
    if (id.indexOf("fs-") === 0) return true;   // our own UI
    if (node.classList && (node.classList.contains("MathJax") ||
        node.classList.contains("MathJax_Display") ||
        node.classList.contains("mjx-chtml"))) return true;
    // Skip anything the reviewer can't actually see. AnKing-style note types
    // render extra material into the question DOM that is hidden by the note's
    // CSS stylesheet (not inline) — the full {{clickable::Tags}} list in a
    // display:none #tags-container, hint/Extra buttons, the legacy .timer, etc.
    // Those nodes stay in the DOM, so without this check wrapAndHide would wrap
    // their words and count them toward the reveal duration — stretching an
    // 11-word card's reveal from ~2s to ~9s (and, via the max() with the
    // auto-reveal delay, pinning the whole wait far longer than intended).
    // We walk top-down, so skipping a hidden container also skips its subtree.
    if (isComputedHidden(node)) return true;
    return false;
  }

  // True when the element is hidden by *any* CSS (stylesheet or inline): the
  // word-count side of this lives in Python (adaptive._VisibleText), but only
  // the browser can resolve the note type's stylesheet, so the reveal-duration
  // side has to be decided here at render time.
  function isComputedHidden(node) {
    try {
      var cs = window.getComputedStyle(node);
      if (!cs) return false;
      return cs.display === "none" || cs.visibility === "hidden" ||
             cs.visibility === "collapse";
    } catch (e) {
      return false;
    }
  }

  // Wrap each word AND each whitespace run in a hidden span. Whitespace is
  // wrapped too so that an underlined/decorated space doesn't show its
  // decoration before the surrounding text is revealed. Spaces don't count
  // toward reveal timing; each one is shown together with the word before it.
  // Returns { words: [...], spaces: [{el, after}] } where `after` is the number
  // of words emitted before that space.
  function wrapAndHide(root) {
    var words = [];
    var spaces = [];
    function process(node) {
      if (node.nodeType === Node.TEXT_NODE) {
        var parts = node.textContent.split(/(\s+)/);
        var frag = document.createDocumentFragment();
        parts.forEach(function (part) {
          if (!part) return;
          var span = document.createElement("span");
          span.textContent = part;
          if (/^\s+$/.test(part)) {
            span.className = "fs-word fs-space fs-hidden";
            frag.appendChild(span);
            spaces.push({ el: span, after: words.length });
          } else {
            span.className = "fs-word fs-hidden";
            frag.appendChild(span);
            words.push(span);
          }
        });
        if (node.parentNode) node.parentNode.replaceChild(frag, node);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        if (isSkippable(node)) return;
        Array.prototype.slice.call(node.childNodes).forEach(process);
      }
    }
    Array.prototype.slice.call(root.childNodes).forEach(process);
    return { words: words, spaces: spaces };
  }

  function clearRevealTimers() {
    wordTimeouts.forEach(function (id) { clearTimeout(id); });
    wordTimeouts = [];
    if (doneTimeout) { clearTimeout(doneTimeout); doneTimeout = null; }
  }

  function removeListeners() {
    if (clickHandler) document.removeEventListener("click", clickHandler, true);
    if (keyHandler) document.removeEventListener("keydown", keyHandler, true);
    clickHandler = keyHandler = null;
  }

  function revealAllWords() {
    clearRevealTimers();
    var hidden = document.querySelectorAll(".fs-word.fs-hidden");
    Array.prototype.forEach.call(hidden, function (el) {
      el.classList.remove("fs-hidden");
    });
    markRevealDone();
  }

  function markRevealDone() {
    if (revealDone) return;
    revealDone = true;
    // If the delay already elapsed while words were still fading, the answer was
    // held back until now — show it the moment the question is fully visible.
    if (autoFired) pycmd("focus:reveal");
  }

  // `reveal` is the per-card reveal config: { wordsPerSecond, mode, chunkWords }.
  function startReveal(reveal) {
    var root = getRoot();
    var res = wrapAndHide(root);
    var words = res.words;
    if (!words.length) {
      // No words to time, but reveal any wrapped whitespace so nothing lingers.
      res.spaces.forEach(function (s) { s.el.classList.remove("fs-hidden"); });
      revealDurationMs = 0;
      markRevealDone();
      return;
    }
    var total = words.length;
    var wps = (reveal.wordsPerSecond > 0) ? reveal.wordsPerSecond : 6;
    var durationMs = (total / wps) * 1000;
    revealDurationMs = durationMs;

    // The reveal index a word belongs to: every word in word mode; the chunk it
    // falls in (groups of chunkWords) in chunk mode. Spans sharing an index fade
    // in together.
    var chunkWords = (reveal.mode === "chunks") ? Math.max(1, reveal.chunkWords || 3) : 1;
    var steps = Math.ceil(total / chunkWords);
    var stepMs = steps > 0 ? durationMs / steps : durationMs;

    words.forEach(function (span, i) {
      var t = Math.floor(i / chunkWords) * stepMs;
      wordTimeouts.push(setTimeout(function () {
        span.classList.remove("fs-hidden");
      }, t));
    });
    // Reveal each space together with the word/chunk in front of it (the gap
    // fills as you read); leading whitespace shows immediately.
    res.spaces.forEach(function (s) {
      var t = s.after > 0 ? Math.floor((s.after - 1) / chunkWords) * stepMs : 0;
      wordTimeouts.push(setTimeout(function () {
        s.el.classList.remove("fs-hidden");
      }, t));
    });
    doneTimeout = setTimeout(markRevealDone, durationMs);

    // Escape hatch: click or the reveal key shows everything at once.
    clickHandler = function () { revealAllWords(); };
    keyHandler = function (e) {
      if ((e.key || "").toLowerCase() === FS._revealKey) revealAllWords();
    };
    document.addEventListener("click", clickHandler, true);
    document.addEventListener("keydown", keyHandler, true);
  }

  // ----- auto-reveal -----

  // The answer never shows before the question is fully revealed.
  function fireReveal() {
    if (!revealDone) { autoFired = true; return; }
    pycmd("focus:reveal");
  }

  // Started the instant the card shows, in parallel with the word reveal. The
  // wait is stretched to cover the reveal (max of the two) so the bar runs for
  // the time shown in settings AND the answer is never sprung early.
  // Paused launch (overnight relaunch): hold the auto-reveal / countdown / warn
  // for the first card until the user actually engages. The first click or key
  // tells Python (which starts the session clock) and then lets the timer run.
  // Works even when Speed Focus is off for this card (no pendingAuto): the clock
  // still starts on first interaction.
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
      maybeStartAuto();
    }
    document.addEventListener("click", go, true);
    document.addEventListener("keydown", go, true);
  }

  function maybeStartAuto() {
    if (!pendingAuto || autoStarted) return;
    if (pausedHold) return;   // held until the user engages
    autoStarted = true;
    var delay = pendingAuto.delayMs || 0;
    // The answer can't show until at least minPostMs after the reveal has
    // finished; the adaptive delay applies on top of that floor.
    var floor = (revealDurationMs || 0) + (minPostMs || 0);
    var effective = Math.max(delay, floor);
    if (pendingAuto.showCountdown && effective > 0) showCountdown(effective);
    if (effective <= 0) {
      fireReveal();
      return;
    }
    autoTimer = setTimeout(fireReveal, effective);
    // Heads-up alert once warnPercent% of the wait has elapsed.
    var pct = pendingAuto.warnPercent || 0;
    if (pendingAuto.warn && pct > 0 && pct < 100) {
      var wt = effective * (pct / 100);
      if (wt > 0 && wt < effective) {
        warnTimer = setTimeout(function () { pycmd("focus:warn"); }, wt);
      }
    }
  }

  function showCountdown(ms) {
    removeCountdown();
    var bar = document.createElement("div");
    bar.id = "fs-countdown";
    var fill = document.createElement("div");
    fill.className = "fs-countdown-fill";
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
    var el = document.getElementById("fs-countdown");
    if (el) el.remove();
  }

  function cancelTimers() {
    clearRevealTimers();
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    removeListeners();
    removeCountdown();
  }

  // Public: stop the auto-reveal / warning for the current card without showing
  // the answer. Used when a Pomodoro break takes over the screen so Speed Focus
  // doesn't auto-reveal or chime on the card hidden behind the break.
  FS.pauseAuto = function () {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    removeCountdown();
    pendingAuto = null;
    autoFired = false;
  };

  // ----- public: per-card entry point -----

  FS.onCard = function (payload) {
    cancelTimers();
    revealDone = false;
    revealDurationMs = 0;
    minPostMs = (payload.autoReveal && payload.autoReveal.minPostMs) || 0;
    autoStarted = false;
    autoFired = false;
    pendingAuto = null;
    pausedHold = !!payload.paused;
    FS._revealKey = (payload.reveal && payload.reveal.revealKey) || "p";

    if (payload.autoReveal && payload.autoReveal.enabled) {
      pendingAuto = payload.autoReveal;
    }

    if (payload.reveal && payload.reveal.enabled) {
      startReveal(payload.reveal);
    } else {
      // Nothing to fade in — the question is "fully revealed" at once.
      revealDone = true;
    }
    // Start the auto-reveal countdown now, alongside the reveal, so the bar
    // appears immediately and the wait matches the time shown in settings.
    maybeStartAuto();
    // Paused launch: arm the engagement listener even if Speed Focus is off for
    // this card, so the first interaction still starts the session clock.
    if (pausedHold) armEngagementHold();
  };

  // ----- public: Blitz progress bar -----
  //
  // Card/fraction modes fill the bar by cardsDone/target; time mode fills by
  // elapsed/deadline and, when the deadline passes, tells Python once via
  // focus:timeup. A single ticker keeps the clock and the time-mode bar live.

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
