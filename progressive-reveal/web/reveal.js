/* Progressive Word Reveal — fade the card's words in at a set reading rate.
 *
 * Python pushes a per-card payload via PWReveal.onCard(payload); this bundle owns
 * all DOM + timing. Purely visual — no callback into Python. Click or the reveal
 * key shows everything at once.
 *
 * Running beside Adaptive Speed Focus, the two share a key by default ("p") and
 * a timer that mustn't show the answer mid-fade. Neither imports the other: this
 * bundle publishes PWReveal.isRevealing() / claimsKey(e) and fires a
 * "pwr:revealed" document event when the fade is done, and aSFM looks for them
 * if they're there.
 *
 * Injected once per webview; guarded so re-injection keeps one instance.
 */
(function () {
  var prev = window.PWReveal;
  // A real (non-stub) instance already exists — nothing to do.
  if (prev && !prev._queue) return;

  var R = {};
  var wordTimeouts = [];      // pending word-reveal timeouts
  var clickHandler = null;
  var keyHandler = null;
  var revealKey = "p";
  var stopAudioOnReveal = true;
  var revealing = false;      // words still fading in on this card

  function getRoot() {
    return document.getElementById("qa") || document.body;
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
    if (id.indexOf("pwr-") === 0) return true; // our own UI
    if (node.classList && (node.classList.contains("MathJax") ||
        node.classList.contains("MathJax_Display") ||
        node.classList.contains("mjx-chtml"))) return true;
    // Skip anything the reviewer can't actually see. AnKing-style note types
    // render extra material (the full {{clickable::Tags}} list in a display:none
    // #tags-container, hint/Extra buttons, the legacy .timer, etc.) that is hidden
    // by the note's CSS stylesheet — not inline. Those nodes stay in the DOM, so
    // without this check wrapAndHide would wrap their words and stretch the reveal
    // far past what the reader actually sees. We walk top-down, so skipping a
    // hidden container also skips its subtree.
    if (isComputedHidden(node)) return true;
    return false;
  }

  // True when the element is hidden by *any* CSS (stylesheet or inline). Only the
  // browser can resolve the note type's stylesheet, so this has to be decided here
  // at render time.
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

  // Wrap each word AND each whitespace run in a hidden span. Whitespace is wrapped
  // too so a decorated space doesn't show before the surrounding text. Spaces
  // don't count toward timing; each shows together with the word before it.
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
            span.className = "pwr-word pwr-space pwr-hidden";
            frag.appendChild(span);
            spaces.push({ el: span, after: words.length });
          } else {
            span.className = "pwr-word pwr-hidden";
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

  function clearTimers() {
    wordTimeouts.forEach(function (id) { clearTimeout(id); });
    wordTimeouts = [];
  }

  function removeListeners() {
    if (clickHandler) document.removeEventListener("click", clickHandler, true);
    if (keyHandler) document.removeEventListener("keydown", keyHandler, true);
    clickHandler = keyHandler = null;
  }

  // The fade is over (it ran out, or you skipped it). Announced so a timer
  // add-on waiting on the question can carry on.
  function markRevealed() {
    if (!revealing) return;
    revealing = false;
    try {
      document.dispatchEvent(new CustomEvent("pwr:revealed"));
    } catch (e) {}
  }

  function revealAllWords() {
    clearTimers();
    var hidden = document.querySelectorAll(".pwr-word.pwr-hidden");
    // Already fully shown: a later click or key press is not a skip, so it must
    // not cut the card's audio (the listeners stay up until the next card).
    if (!hidden.length) { markRevealed(); return; }
    Array.prototype.forEach.call(hidden, function (el) {
      el.classList.remove("pwr-hidden");
    });
    stopCardAudio();
    markRevealed();
  }

  // Skipping the reveal means you've read it — the voice reading it to you is
  // now just noise. Anki's own audio ([sound:] / {{tts}}) lives in mpv, so
  // Python has to cut it; media embedded in the card is paused here.
  function stopCardAudio() {
    if (!stopAudioOnReveal) return;
    var media = document.querySelectorAll("audio, video");
    Array.prototype.forEach.call(media, function (el) {
      try { el.pause(); } catch (e) {}
    });
    pycmd("pwr:stopaudio");
  }

  function isTypingTarget(el) {
    if (!el) return false;
    var tag = (el.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || el.isContentEditable;
  }

  // An on-screen control (another add-on's "More time" button, say) is not
  // the card: clicking it mustn't also skip the reveal and cut the audio. The
  // click listener is on document in the capture phase, so the control's own
  // stopPropagation can't keep the click from reaching it.
  function isControl(node) {
    for (var el = node; el && el !== document.body; el = el.parentElement) {
      if (el.getAttribute && el.getAttribute("role") === "button") return true;
    }
    return false;
  }

  // Would this key press skip the fade? Marked on the event once handled, so
  // the answer is the same whichever listener runs first.
  function isRevealKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return false;
    if (e.repeat) return false;
    if (isTypingTarget(e.target)) return false;
    return (e.key || "").toLowerCase() === revealKey;
  }

  // `reveal` is the per-card config: { wordsPerSecond, mode, chunkWords }.
  function startReveal(reveal) {
    var root = getRoot();
    var res = wrapAndHide(root);
    var words = res.words;
    if (!words.length) {
      // No words to time — reveal any wrapped whitespace so nothing lingers.
      res.spaces.forEach(function (s) { s.el.classList.remove("pwr-hidden"); });
      return;
    }
    var total = words.length;
    var wps = (reveal.wordsPerSecond > 0) ? reveal.wordsPerSecond : 6;
    var durationMs = (total / wps) * 1000;
    revealing = true;

    // The reveal index a word belongs to: every word in word mode; its chunk in
    // chunk mode. Spans sharing an index fade in together.
    var chunkWords = (reveal.mode === "chunks") ? Math.max(1, reveal.chunkWords || 3) : 1;
    var steps = Math.ceil(total / chunkWords);
    var stepMs = steps > 0 ? durationMs / steps : durationMs;

    words.forEach(function (span, i) {
      var t = Math.floor(i / chunkWords) * stepMs;
      wordTimeouts.push(setTimeout(function () {
        span.classList.remove("pwr-hidden");
      }, t));
    });
    // Reveal each space together with the word/chunk in front of it; leading
    // whitespace shows immediately.
    res.spaces.forEach(function (s) {
      var t = s.after > 0 ? Math.floor((s.after - 1) / chunkWords) * stepMs : 0;
      wordTimeouts.push(setTimeout(function () {
        s.el.classList.remove("pwr-hidden");
      }, t));
    });

    wordTimeouts.push(setTimeout(markRevealed, durationMs));

    // Escape hatch: click or the reveal key shows everything at once.
    clickHandler = function (e) {
      if (e && isControl(e.target)) return;
      revealAllWords();
    };
    keyHandler = function (e) {
      // A bare key match isn't enough: without these guards, "p" typed into
      // Anki's type-in-the-answer box reveals the question, and any shortcut
      // using the key as a modifier combination triggers it too.
      if (!isRevealKey(e)) return;
      // Once the fade is done the key belongs to whoever else wants it (aSFM's
      // pause key shares it by default).
      if (!revealing) return;
      e._pwrRevealed = true;
      revealAllWords();
    };
    document.addEventListener("click", clickHandler, true);
    document.addEventListener("keydown", keyHandler, true);
  }

  // Public: per-card entry point.
  R.onCard = function (payload) {
    clearTimers();
    removeListeners();
    revealing = false;
    var reveal = payload && payload.reveal;
    revealKey = (reveal && reveal.revealKey) || "p";
    stopAudioOnReveal = !!(reveal && reveal.stopAudio);
    if (reveal && reveal.enabled) {
      startReveal(reveal);
    }
  };

  // Public, for a timer add-on running alongside (see the header).
  R.isRevealing = function () { return revealing; };
  R.claimsKey = function (e) {
    return !!(e && (e._pwrRevealed || (revealing && isRevealKey(e))));
  };

  window.PWReveal = R;

  // Flush any calls buffered by the inline shim before this bundle loaded.
  if (prev && prev._queue) {
    prev._queue.forEach(function (c) {
      try { R[c[0]].apply(R, c[1]); } catch (e) {}
    });
  }
})();
