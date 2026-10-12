# Adaptive Speed Focus (aSFM)

**The answer shows up right when you'd have got there, and you still do the grading.**

aSFM is an auto-reveal timer for Anki. Every card gets its own wait, based on how much there is to read and how hard the card is for you. When the wait runs out, the answer appears. **It never grades the card for you.** You still press Again, Hard, Good or Easy yourself.

It keeps a review session moving without rushing you. You stop sitting on cards you already know, and the cards you're stuck on don't hold you up.

## Why it's different

- **A different wait for every card.** A two-word card and a five-line clinical vignette shouldn't get the same timer. aSFM counts the words you can actually **see**, adds time for long answers, and adjusts the wait using the card's **FSRS difficulty** (or its ease and lapses on the classic scheduler).
- **It learns your speed.** Auto-tune slowly adjusts the timer to how fast you really answer. **One-click calibration** can also set your timings from your review history, and you see the numbers before anything changes.
- **Easy to hold.** Click **More time**, or press **P**, to stop the countdown on the card you're on. Do it again and it carries on from where it stopped. The pause sticks across cards, and every card says so while it's on.
- **It never grades.** That's the main change from Glutanimate's original Speed Focus Mode: aSFM only shows the answer, and you still decide how well you knew it.

## How it looks

- A slim **countdown bar** along the bottom of the card, in Anki's own accent colour. It turns red when the answer is about to show, and an optional warning chime plays at the same point.
- A faint **More time** button with its shortcut shown as a keycap. It comes up to full strength when you hover over it.
- A clear amber **paused** badge, so a stopped timer never looks like a bug.
- Works in light and dark mode, and turns its animations off if your system asks for reduced motion.

## Built for real decks

- **AnKing-friendly.** Hidden fields, tag lists and hint buttons don't count towards the word count.
- **Picture cards** (anatomy, histology, images) can get a set time instead of a word count, since there's little text to read.
- **One-by-one cloze cards** can run a short timer for each cloze.
- **Skip lists** for any note types or decks you'd rather review untimed.
- **New cards are left alone by default**, because they need time to read, not just to recall. You can switch them on.

## New in this update

- **A fresh look on the card.** The countdown bar now has a soft glow, and the More time button and paused badge are a redesigned frosted pill that shows the pause key as a keycap.
- **Redesigned Settings.** Four tabs (**Timing**, **On screen**, **Your pace**, **Cards**) with the live preview always in view beside them.
- **A cleaner welcome window**, with calibration set apart so it's easy to find.
- **Works better with Progressive Word Reveal.** The answer now waits for the question to finish fading in, the two add-ons can share the **P** key (the first press finishes the fade, the next one pauses the timer), and clicking More time no longer skips the fade or cuts the card's audio.
- **Fixed:** pressing Esc in the pause-key box no longer sets Esc as the key.

Existing setups are untouched. An update only fills in settings you don't have yet, so nothing you've tuned is changed.

## Getting started

1. Install, restart Anki and start reviewing.
2. A welcome window explains the basics and offers to **calibrate the timer to your speed**. Reopen it any time from **Tools ▸ Adaptive Speed Focus ▸ Welcome & calibration…**.
3. Fine-tune everything under **Tools ▸ Adaptive Speed Focus ▸ Settings…**. The preview table shows the exact wait the timer will use.

**Before you start:** if you run **Glutanimate's Speed Focus Mode**, disable it so the two timers don't double up. If you run the full **AnkiBlitz** add-on, this feature is already in it, so don't install both.

## The AnkiBlitz suite

aSFM is the flagship of a small family of focus add-ons:

- [Progressive Word Reveal](https://ankiweb.net/shared/info/972193513): fades the question in word by word at your reading pace. **Pairs naturally with aSFM.**
- [AnkiBlitz Core](https://ankiweb.net/shared/info/1174429600): timed Blitz sessions, Pomodoro, Focus Lock, profiles and music.
- [AnkiBlitz](https://ankiweb.net/shared/info/178722601): all of the above in one add-on.

Core + aSFM + Progressive Word Reveal together equal the full AnkiBlitz. Don't run AnkiBlitz alongside any of the other three, because it already contains them.

## Notes

- Reworks the auto-reveal concept from **Glutanimate's Speed Focus Mode** (Copyright © 2017-2021 Aristotelis P., [glutanimate.com](https://glutanimate.com/)). The "More time" button is his idea too. Licensed under the GNU AGPLv3 **with** Glutanimate's Section 7 additional terms: preserve attribution, don't misrepresent origin, and no use of the Glutanimate name for endorsement. Full terms are in `LICENSE`.
- To change the warning sound, drop your own `alert.flac`, `.ogg`, `.opus` or `.wav` into the add-on's `user_files/` folder. An `alert.mp3` works too, but only where Anki's external media player is running, because the reviewer can't play MP3 by itself.
- Tested on Anki 2.1.50+ (Qt6). Found a problem? [Report it on GitHub](https://github.com/FleggaBDog69/AnkiBlitz/issues).
