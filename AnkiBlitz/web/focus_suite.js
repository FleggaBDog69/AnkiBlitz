/* AnkiBlitz — single reviewer JS bundle.
 *
 * Python pushes a payload per card via FocusSuite.onCard(payload); this bundle
 * owns all DOM + timing. Three jobs:
 *   1. Progressive reveal: fade the card's words in at a fixed reading rate.
 *   2. Adaptive auto-reveal: after the reveal finishes, wait delayMs (computed
 *      in Python) then ask Python to show the answer. NEVER grades. The wait can
 *      be held indefinitely by the pause key or the visible "More time" button;
 *      both call one toggleAutoPause(), so there is one hold and one state.
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
  var countdownTotalMs = 0;  // the whole wait the countdown bar stands for
  var warned = false;        // has this card passed its warning point?
  var obo = null;            // this card's per-cloze one-by-one timers (see below)

  function getRoot() {
    return document.getElementById("qa") || document.body;
  }

  // Is this node part of AnkiBlitz's own reviewer UI (progress strip, countdown,
  // paused badge, More time button)? Everything we add is id'd "fs-*".
  function isOwnUi(node) {
    for (var el = node; el; el = el.parentElement) {
      if (el.id && el.id.indexOf("fs-") === 0) return true;
    }
    return false;
  }

  function isSkippable(node) {
    if (node.nodeType !== Node.ELEMENT_NODE) return false;
    var tag = node.tagName || "";
    if (tag === "SCRIPT" || tag === "STYLE") return true;
    // Controls aren't text to read: a note type's own buttons (AnKing's
    // Reveal Next / Reveal All, hint buttons) should be usable straight away,
    // not fade in word by word.
    if (tag === "BUTTON" || tag === "INPUT" || tag === "SELECT" ||
        tag === "TEXTAREA") return true;
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
    if (!hidden.length) {
      // Already fully shown: a later click on the card (a hint button, the
      // replay button) is not a skip, so it must not cut the card's audio.
      markRevealDone();
      return;
    }
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
    if (autoFired) { autoFired = false; fireReveal(); }
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
    clickHandler = function (e) {
      // Our own on-card controls are not the card: clicking "More time" must
      // not also skip the reveal on its way past. This listener is on document
      // in the capture phase, so the button's own stopPropagation can't help.
      if (e && isOwnUi(e.target)) return;
      revealAllWords();
    };
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
    // Holding the key down auto-repeats it. On the shared default key that would
    // finish the reveal and then flicker the hold on and off; only a fresh press
    // counts.
    if (e.repeat) return;
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
    if (oboActive() && obo.left > 0 && window.revealNextCloze) {
      // Uncover the next cloze, not the answer. The template answers with an
      // anking:1b1-reveal event, which arms the next cloze's timer (or, after
      // the last one, the template flips to the answer itself).
      obo.autoNext = true;   // so the report says the timer did this one
      window.revealNextCloze();
      return;
    }
    pycmd("focus:reveal");
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
    if (autoStarted && pendingAuto) {
      armClozeTimer(Math.max(oboDelay(), (revealDurationMs || 0) + (minPostMs || 0)));
    }
  }

  // Tell Python how each cloze went: which one, whether the timer uncovered
  // it, whether it was held, and how long it was up. The template flips to
  // the answer by itself after the last cloze, so without this every
  // one-by-one card would look like you revealed it.
  function reportCloze() {
    var now = Date.now();
    var index = obo.total - obo.left;
    pycmd("focus:cloze:" + index + ":" + (obo.autoNext ? 1 : 0) + ":"
      + (obo.heldThis ? 1 : 0) + ":" + Math.max(0, now - obo.clozeT0));
    obo.clozeT0 = now;
    obo.autoNext = false;
    obo.heldThis = !!autoPaused;   // still held as the next cloze starts
  }

  function oboRevealed(left) {
    if (!oboActive() || !pendingAuto) return;
    if (!(left < obo.left)) return;   // another word of the same cloze (Shift+N)
    reportCloze();
    obo.left = left;
    if (left <= 0) {                  // the template flips to the answer now
      stopAlert();
      if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
      if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
      autoDeadline = warnDeadline = 0;
      removeCountdown();
      removeMoreTime();
      return;
    }
    // Not started yet (paused launch / held from the start): maybeStartAuto
    // picks up the right cloze when it does start.
    if (autoStarted) armClozeTimer(oboDelay());
  }

  // A fresh wait for the current cloze: new countdown, new warning point.
  function armClozeTimer(ms) {
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    warned = false;
    removeCountdown();
    countdownTotalMs = ms;
    var warnMs = warnPointMs(ms);
    if (autoPaused) {
      // Held: resuming (pause key / More time) starts this cloze's full wait.
      pauseLeftMs = ms;
      pauseWarnLeftMs = warnMs;
      return;
    }
    if (pendingAuto.showCountdown) showCountdown(ms);
    showMoreTime();
    armAutoTimers(ms, warnMs);
  }

  document.addEventListener("anking:1b1-start", function (e) {
    oboBegin(e.detail && e.detail.total);
  });
  document.addEventListener("anking:1b1-reveal", function (e) {
    oboRevealed(e.detail ? e.detail.remaining : 0);
  });

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

  // The heads-up alert. Anki routes sound FILES through mpv, and its bundled
  // mpv does not run on every macOS it ships to — on macOS 13 it aborts at
  // launch, which costs you the alert (card TTS is unaffected: that goes
  // through `say`). Playing it here keeps the alert on the reviewer's own audio
  // stack; `focus:warn` stays as the fallback when the webview won't play.
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
    var url = pendingAuto && pendingAuto.alertUrl;
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
    var url = pendingAuto && pendingAuto.alertUrl;
    if (!url) { pycmd("focus:warn"); return; }
    try {
      var el = alertElement(url);
      el.muted = false;
      el.currentTime = 0;
      var played = el.play();
      if (played && typeof played.catch === "function") {
        played.catch(function () { pycmd("focus:warn"); });
      }
    } catch (e) {
      pycmd("focus:warn");
    }
  }

  // Start (or restart, after a pause) the reveal + warning timers, remembering
  // the deadlines so a pause can work out what was left on each.
  function armAutoTimers(effectiveMs, warnMs) {
    autoTimer = setTimeout(fireReveal, effectiveMs);
    autoDeadline = Date.now() + effectiveMs;
    if (warnMs > 0 && warnMs < effectiveMs) {
      warnTimer = setTimeout(onWarn, warnMs);
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
    var delay = oboActive() ? oboDelay() : (pendingAuto.delayMs || 0);
    // The answer can't show until at least minPostMs after the reveal has
    // finished; the adaptive delay applies on top of that floor.
    var floor = (revealDurationMs || 0) + (minPostMs || 0);
    var effective = Math.max(delay, floor);
    countdownTotalMs = effective;
    if (pendingAuto.showCountdown && effective > 0) showCountdown(effective);
    if (effective <= 0) {
      fireReveal();
      return;
    }
    // Only once there is a wait to hold: on a zero-delay card the answer is
    // already up, and a button offering to pause it would do nothing.
    showMoreTime();
    armAutoTimers(effective, warnPointMs(effective));
  }

  // Heads-up (sound and/or bar colour) once warnPercent% of the wait is gone.
  function warnPointMs(ms) {
    var pct = pendingAuto.warnPercent || 0;
    var wantWarn = pendingAuto.warn
      || (pendingAuto.warnColour && pendingAuto.showCountdown);
    return (wantWarn && pct > 0 && pct < 100) ? ms * (pct / 100) : 0;
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
          showMoreTime();
        }
      } else {
        maybeStartAuto();   // the card started paused — begin its wait now
      }
      pycmd("focus:autopause:0");
      return;
    }
    autoPaused = true;
    if (oboActive()) obo.heldThis = true;
    stopAlert();
    var now = Date.now();
    pauseLeftMs = autoDeadline ? Math.max(0, autoDeadline - now) : 0;
    pauseWarnLeftMs = warnDeadline ? Math.max(0, warnDeadline - now) : 0;
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    freezeCountdown();
    removeMoreTime();     // the paused badge takes its place
    showPausedBadge();
    pycmd("focus:autopause:1");
  }

  // ----- the on-card pill -----
  //
  // Static markup only: the one variable part (the key) goes in as text.
  var ICON_PAUSE = '<svg viewBox="0 0 12 12" aria-hidden="true">'
    + '<rect x="2" y="1.5" width="3" height="9" rx="1"/>'
    + '<rect x="7" y="1.5" width="3" height="9" rx="1"/></svg>';
  var ICON_PLAY = '<svg viewBox="0 0 12 12" aria-hidden="true">'
    + '<path d="M3 1.8v8.4a.8.8 0 0 0 1.2.7l7-4.2a.8.8 0 0 0 0-1.4l-7-4.2A.8.8 0 0 0 3 1.8z"/></svg>';

  function pillText(text, cls) {
    var el = document.createElement("span");
    if (cls) el.className = cls;
    el.textContent = text;
    return el;
  }

  function keycap() {
    return pillText((FS._pauseKey || "p").toUpperCase(), "fs-kbd");
  }

  // The badge is deliberately worded, not just coloured: a paused timer that
  // only looked different would read as "Speed Focus is broken".
  function showPausedBadge() {
    // Nothing to pause on this card (Speed Focus off or excluded) — saying
    // "paused" here would be a lie; the sticky flag still applies from the next
    // card that does run a timer.
    if (!pendingAuto) return;
    removeCountdown();
    removeMoreTime();
    if (document.getElementById("fs-paused")) return;
    var b = document.createElement("div");
    b.id = "fs-paused";
    b.innerHTML = ICON_PLAY;
    b.appendChild(pillText("Speed Focus paused"));
    b.appendChild(pillText("·", "fs-sep"));
    // "click or press [P] to resume": the key as a keycap, like the button.
    var how = resumeHint();
    var cut = how.indexOf("{key}");
    if (cut < 0) {
      b.appendChild(pillText(how));
    } else {
      b.appendChild(pillText(how.slice(0, cut).replace(/\s+$/, "")));
      b.appendChild(keycap());
      b.appendChild(pillText(how.slice(cut + 5).replace(/^\s+/, "")));
    }
    b.setAttribute("aria-label", "Speed Focus paused, "
      + how.replace("{key}", (FS._pauseKey || "p").toUpperCase()));
    if (FS._moreTime) {
      // Resuming has to be possible with the same input that paused it: a mouse
      // user who pressed the button and can't press the key would otherwise be
      // stuck on the card.
      b.className = "fs-clickable";
      b.setAttribute("role", "button");
      b.addEventListener("click", onControlClick, false);
    }
    document.body.appendChild(b);
  }

  function removePausedBadge() {
    var el = document.getElementById("fs-paused");
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
    // The click must not also reach the card: while words are still fading in,
    // a bare click reveals the question.
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    toggleAutoPause();
  }

  function showMoreTime() {
    if (!FS._moreTime || !pendingAuto || autoPaused) return;
    if (document.getElementById("fs-moretime")) return;
    var b = document.createElement("div");
    b.id = "fs-moretime";
    // Announced as a button, but deliberately not focusable: a focused button
    // would take Space, which is Anki's show-answer key.
    b.setAttribute("role", "button");
    b.innerHTML = ICON_PAUSE;
    b.appendChild(pillText("More time"));
    if (FS._pauseEnabled) b.appendChild(keycap());
    b.title = FS._pauseEnabled
      ? "Hold the auto-reveal (or press "
        + (FS._pauseKey || "p").toUpperCase() + ")"
      : "Hold the auto-reveal";
    b.addEventListener("click", onControlClick, false);
    document.body.appendChild(b);
  }

  function removeMoreTime() {
    var el = document.getElementById("fs-moretime");
    if (el) el.remove();
  }

  // What the paused badge tells you to do to get going again — only ever
  // offering something that is actually switched on.
  // {key} marks where the key goes, so the badge can draw it as a keycap.
  function resumeHint() {
    if (FS._moreTime && FS._pauseEnabled) return "click or press {key} to resume";
    if (FS._moreTime) return "click to resume";
    return "press {key} to resume";
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
      var total = countdownTotalMs || ms;
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
    bar.id = "fs-countdown";
    if (pendingAuto && pendingAuto.warnColour) bar.className = "fs-shift";
    var fill = document.createElement("div");
    fill.className = "fs-countdown-fill";
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
    var bar = document.getElementById("fs-countdown");
    if (bar) bar.classList.add("fs-warned");
  }

  // The warning point: the sound, the colour shift, or both.
  function onWarn() {
    warned = true;
    if (!pendingAuto) return;
    // One-by-one: colour on every cloze, but the sound only before the last
    // one — the one that ends in the answer. A chime per cloze is just noise.
    if (pendingAuto.warn && (!oboActive() || obo.left <= 1)) playAlert();
    if (pendingAuto.warnColour) markWarned();
  }

  function removeCountdown() {
    var el = document.getElementById("fs-countdown");
    if (el) el.remove();
  }

  function cancelTimers() {
    clearRevealTimers();
    stopAlert();
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    removeListeners();
    removeCountdown();
    removePausedBadge();
    removeMoreTime();
  }

  // Public: stop the auto-reveal / warning for the current card without showing
  // the answer. Used when a Pomodoro break takes over the screen so Speed Focus
  // doesn't auto-reveal or chime on the card hidden behind the break.
  FS.pauseAuto = function () {
    stopAlert();
    if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    if (warnTimer) { clearTimeout(warnTimer); warnTimer = null; }
    autoDeadline = warnDeadline = 0;
    removeCountdown();
    // The button and badge go too: with no timer behind them, "More time"
    // would offer to hold nothing, and a paused badge would outlive its card.
    removeMoreTime();
    removePausedBadge();
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
    warned = false;
    countdownTotalMs = 0;
    pendingAuto = null;
    pausedHold = !!payload.paused;
    FS._revealKey = (payload.reveal && payload.reveal.revealKey) || "p";
    FS._stopAudioOnReveal = !!(payload.reveal && payload.reveal.stopAudio);
    FS._pauseKey = (payload.autoReveal && payload.autoReveal.pauseKey) || "p";
    FS._pauseEnabled = !!(payload.autoReveal && payload.autoReveal.pauseEnabled);
    FS._moreTime = !!(payload.autoReveal && payload.autoReveal.moreTimeButton);
    // Python owns the sticky pause, so it survives re-injection of this bundle.
    autoPaused = !!payload.autoPaused;

    if (payload.autoReveal && payload.autoReveal.enabled) {
      pendingAuto = payload.autoReveal;
    }
    // Per-cloze one-by-one timers. The template may have announced itself
    // before this onCard arrived; its state is only trusted while its element
    // is on screen (the reviewer page, and these globals, outlive the card).
    obo = null;
    var oboPlan = pendingAuto && pendingAuto.oneByOne;
    if (oboPlan && oboPlan.mode === "per_cloze" && oboPlan.delaysMs && oboPlan.delaysMs.length) {
      obo = { delaysMs: oboPlan.delaysMs, active: false, total: 0, left: 0,
              clozeT0: Date.now(), autoNext: false, heldThis: autoPaused };
      var st = window.ankingOneByOne;
      if (st && st.root && document.body.contains(st.root)) {
        oboBegin(st.total, st.remaining());
      }
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
