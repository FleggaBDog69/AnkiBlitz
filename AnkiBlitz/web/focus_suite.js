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
  // Pause key state. autoPaused is sticky across cards (Python mirrors it, so it
  // also survives the bundle being re-injected) — a held timer stays held until
  // you press the key again, and every card says so on screen while it is.
  var autoPaused = false;
  var autoDeadline = 0;      // when the pending auto-reveal would fire
  var warnDeadline = 0;      // when the warning sound would play
  var pauseLeftMs = 0;       // what was left on each when the timer was paused
  var pauseWarnLeftMs = 0;

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
    stopCardAudio();
    markRevealDone();
  }

  // Skipping the reveal means you've read it — the voice reading it to you is
  // now just noise. Anki's own audio ([sound:] / {{tts}}) lives in mpv, so
  // Python has to cut it; media embedded in the card is paused here.
  function stopCardAudio() {
    if (!FS._stopAudioOnReveal) return;
    var media = document.querySelectorAll("audio, video");
    Array.prototype.forEach.call(media, function (el) {
      try { el.pause(); } catch (e) {}
    });
    pycmd("focus:stopaudio");
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

    // Escape hatch: a click shows everything at once. (The reveal KEY is handled
    // by the shared key listener, which shares it with the pause key.)
    clickHandler = function () { revealAllWords(); };
    document.addEventListener("click", clickHandler, true);
  }

  // ----- keys -----
  //
  // One listener owns both shortcuts, so the reveal key and the pause key are
  // allowed to be the same key (they are, by default: "p"). Order of precedence
  // on a shared key is what you'd do by hand anyway — first press finishes the
  // word reveal, and once there's nothing left to reveal the key pauses (then
  // resumes) the auto-reveal timer.
  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  function onKeyDown(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (isTypingTarget(e.target)) return;   // e.g. Anki's type-in-the-answer box
    var k = (e.key || "").toLowerCase();
    if (!revealDone && k === FS._revealKey) {
      revealAllWords();
      return;
    }
    if (FS._pauseEnabled && k === FS._pauseKey) {
      e.preventDefault();
      toggleAutoPause();
    }
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

  // Start (or restart, after a pause) the reveal + warning timers, remembering
  // the deadlines so a pause can work out what was left on each.
  function armAutoTimers(effectiveMs, warnMs) {
    autoTimer = setTimeout(fireReveal, effectiveMs);
    autoDeadline = Date.now() + effectiveMs;
    if (warnMs > 0 && warnMs < effectiveMs) {
      warnTimer = setTimeout(function () { pycmd("focus:warn"); }, warnMs);
      warnDeadline = Date.now() + warnMs;
    } else {
      warnDeadline = 0;
    }
  }

  function maybeStartAuto() {
    if (!pendingAuto || autoStarted) return;
    if (pausedHold) return;   // held until the user engages
    if (autoPaused) {         // held by you, until you press the pause key
      showPausedBadge();
      return;
    }
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
    // Heads-up alert once warnPercent% of the wait has elapsed.
    var pct = pendingAuto.warnPercent || 0;
    var warnMs = (pendingAuto.warn && pct > 0 && pct < 100) ? effective * (pct / 100) : 0;
    armAutoTimers(effective, warnMs);
  }

  // ----- pause / resume the auto-reveal timer -----

  function toggleAutoPause() {
    if (autoPaused) {
      autoPaused = false;
      removePausedBadge();
      if (autoStarted) {
        // Mid-card: pick the timer up where it was frozen.
        var left = Math.max(0, pauseLeftMs);
        if (left <= 0) {
          fireReveal();
        } else {
          if (pendingAuto && pendingAuto.showCountdown) resumeCountdown(left);
          armAutoTimers(left, pauseWarnLeftMs);
        }
      } else {
        maybeStartAuto();   // the card started paused — begin its wait now
      }
      pycmd("focus:autopause:0");
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
    pycmd("focus:autopause:1");
  }

  // The badge is deliberately worded, not just coloured: a paused timer that
  // only looked different would read as "Speed Focus is broken".
  function showPausedBadge() {
    // Nothing to pause on this card (Speed Focus off or excluded) — saying
    // "paused" here would be a lie; the sticky flag still applies from the next
    // card that does run a timer.
    if (!pendingAuto) return;
    removeCountdown();
    if (document.getElementById("fs-paused")) return;
    var b = document.createElement("div");
    b.id = "fs-paused";
    b.textContent = "⏸ Speed Focus paused · press "
      + (FS._pauseKey || "p").toUpperCase() + " to resume";
    document.body.appendChild(b);
  }

  function removePausedBadge() {
    var el = document.getElementById("fs-paused");
    if (el) el.remove();
  }

  function countdownFill() {
    var bar = document.getElementById("fs-countdown");
    return bar ? bar.querySelector(".fs-countdown-fill") : null;
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
    autoDeadline = warnDeadline = 0;
    removeListeners();
    removeCountdown();
    removePausedBadge();
  }

  // Public: stop the auto-reveal / warning for the current card without showing
  // the answer. Used when a Pomodoro break takes over the screen so Speed Focus
  // doesn't auto-reveal or chime on the card hidden behind the break.
  FS.pauseAuto = function () {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
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
    FS._stopAudioOnReveal = !!(payload.reveal && payload.reveal.stopAudio);
    FS._pauseKey = (payload.autoReveal && payload.autoReveal.pauseKey) || "p";
    FS._pauseEnabled = !!(payload.autoReveal && payload.autoReveal.pauseEnabled);
    // Python owns the sticky pause, so it survives re-injection of this bundle.
    autoPaused = !!payload.autoPaused;

    if (payload.autoReveal && payload.autoReveal.enabled) {
      pendingAuto = payload.autoReveal;
    }

    if (payload.reveal && payload.reveal.enabled) {
      startReveal(payload.reveal);
    } else {
      // Nothing to fade in — the question is "fully revealed" at once.
      revealDone = true;
    }
    // One listener for both shortcuts, on every card (the pause key has to work
    // even when there's no progressive reveal running to hang it off).
    keyHandler = onKeyDown;
    document.addEventListener("keydown", keyHandler, true);
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
