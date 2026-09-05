"""The blank band Anki leaves above the reviewer.

Anki's *Hide top bar during review* doesn't remove the toolbar: ``TopWebView``
only adds ``body.hidden`` to its page, which is an ``opacity: 0`` rule (a
translate on the fancy skin). The widget keeps the fixed height Anki measured
for it, so the reviewer webview starts a toolbar's height down the window — and
the Blitz strip, which is fixed to the top of the *reviewer*, sits in mid-air
with an empty band above it instead of at the top of the screen.

So while the strip is up and Anki has the toolbar hidden, this module collapses
the toolbar widget to zero height and the strip rises to the top of the window.
The height goes straight back the moment Anki shows the toolbar again (hovering
the top of the window still reveals it), and whenever we leave the reviewer —
the deck list must never be left without its links.

Two rules keep it honest:

  * it only ever takes a band Anki has *already* blanked. A toolbar you can see
    is a toolbar you're using, and no progress bar is worth eating it;
  * it hands back the exact height it took, so nothing here has to guess at a
    number Anki owns.
"""

from aqt import gui_hooks, mw

from ..config import get_section

# The toolbar webview we've wrapped, so a profile switch (which builds a new
# one) is re-wrapped rather than silently left alone.
_hooked_web = None

# The strip is up and wants the band.
_wanted = False

# The height we collapsed away, or 0 when we're holding nothing. This is the
# whole of our state: if it's 0 there is nothing to give back.
_taken = 0


def _enabled() -> bool:
    return bool(get_section("sprint").get("bar_flush_with_top", True))


def _web():
    tb = getattr(mw, "toolbar", None)
    return getattr(tb, "web", None) if tb is not None else None


def _anki_hid_it(web) -> bool:
    """Anki's own flag for "the toolbar is faded out during review".

    Absent on an Anki that predates it, and a missing flag has to read as
    *visible* — collapsing a toolbar the user can see is the one outcome worth
    ruling out.
    """
    return bool(getattr(web, "hidden", False))


def _take(web) -> None:
    global _taken
    if _taken:
        return
    h = web.height()
    if h <= 0:
        return
    _taken = h
    web.setFixedHeight(0)


def _give_back(web) -> None:
    global _taken
    if not _taken:
        return
    h, _taken = _taken, 0
    web.setFixedHeight(h)


def _install(web) -> None:
    """Follow Anki's hide/show decisions rather than guessing at them.

    Per-instance wrappers, not a class patch: Anki calls ``self.hide()`` /
    ``self.show()`` on this one widget, the instance attribute shadows the class
    method, and no other webview in the app is touched.
    """
    global _hooked_web
    if _hooked_web is web:
        return
    try:
        orig_hide, orig_show = web.hide, web.show

        def hide(*args, **kwargs):
            orig_hide(*args, **kwargs)
            if _wanted and _enabled():
                _take(web)

        def show(*args, **kwargs):
            # About to be seen: give the height back first, or the hover reveals
            # a toolbar with nowhere to draw itself.
            _give_back(web)
            orig_show(*args, **kwargs)

        web.hide, web.show = hide, show
    except Exception:
        return
    _hooked_web = web


def claim() -> None:
    """The strip is up: take the band if Anki isn't using it.

    Called on every progress push, so it doubles as the repair: anything that
    re-measures the toolbar behind our back (Anki adjusts its height on theme
    and state changes) is undone on the next card rather than leaving the gap
    back for the rest of the session.
    """
    global _wanted
    if not _enabled():
        release()
        return
    _wanted = True
    web = _web()
    if web is None:
        return
    _install(web)
    if mw.state == "review" and _anki_hid_it(web):
        _take(web)


def release() -> None:
    """The strip is gone (or we're leaving the reviewer): give the band back."""
    global _wanted
    _wanted = False
    web = _web()
    if web is not None:
        _give_back(web)


def _on_state_change(new_state: str, old_state: str) -> None:
    if new_state != "review":
        release()


def register() -> None:
    gui_hooks.state_did_change.append(_on_state_change)
