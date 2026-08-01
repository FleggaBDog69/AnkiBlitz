"""Music player — keep study music inside Anki.

A small in-app player pointed at a music service (SoundCloud or YouTube Music):
you browse within the service and hit play, or use the ⏮ ⏯ ⏭ toolbar controls
to skip/pause without touching the page. No address bar, no free browsing, just
the two services. It has three homes:
  - a built-in box on the Pomodoro break screen (added by pomodoro.py),
  - a built-in box anchored below the rail on the deck list (this module), and
  - a floating window during reviews (menu / Ctrl+Shift+M).

None of these live *inside* the reviewer/deck-browser webviews — those re-render
constantly and would restart the song, and two webviews in one window glitch on
macOS. So each is its own widget/window: the break box is part of the break
dialog, the home box and review window are separate frameless windows anchored
to the main window. The audio never restarts when Anki redraws a screen.

Nothing is bundled — it's a QWebEngineView on the service's own site, using a
named, on-disk profile so logins persist across restarts. SoundCloud plays full
tracks (login optional); YouTube Music depends on the Qt build shipping the
proprietary codecs (H.264/AAC), so it may be silent on some builds.

Standalone-safe: every Qt/WebEngine touch is guarded; imports are config + aqt.
"""

import os

from aqt import gui_hooks, mw
from aqt.qt import (
    QEvent, QHBoxLayout, QLabel, QPushButton, QTimer, QUrl, QVBoxLayout,
    QWidget, Qt,
)
from aqt.utils import tooltip

from ..config import get_section, save_section, suite_enabled

# The "home" each service button jumps to.
SERVICE_HOMES = {
    "soundcloud": "https://soundcloud.com/discover",
    "youtube": "https://music.youtube.com",
}
DEFAULT_HOME = SERVICE_HOMES["soundcloud"]
HOME_STATES = ("deckBrowser", "overview")

# The player is one fixed, narrow size everywhere — no drag-resizing — so it
# sits tidily like the rail instead of sprawling across the screen.
PLAYER_W = 340
PLAYER_H = 480


def _blocked_host(host: str) -> bool:
    """Regular YouTube (the distracting kind) — kept out so the player stays on
    YouTube *Music*. music.youtube.com and the accounts.* login hosts are fine."""
    host = (host or "").lower().lstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host in ("youtube.com", "m.youtube.com", "youtu.be", "gaming.youtube.com")


_GuardedPage = None


def _guarded_page_class():
    """A QWebEnginePage that deflects regular-YouTube navigations back to YouTube
    Music. Built lazily so a WebEngine-less build doesn't break import."""
    global _GuardedPage
    if _GuardedPage is not None:
        return _GuardedPage
    try:
        from PyQt6.QtWebEngineCore import QWebEnginePage
    except Exception:
        try:
            from PyQt5.QtWebEngineWidgets import QWebEnginePage
        except Exception:
            return None

    class GuardedPage(QWebEnginePage):
        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            try:
                if is_main_frame and _blocked_host(url.host()):
                    view = getattr(self, "_guard_view", None)
                    if view is not None:
                        QTimer.singleShot(
                            0, lambda: view.setUrl(QUrl(SERVICE_HOMES["youtube"])))
                    return False
            except Exception:
                pass
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

    _GuardedPage = GuardedPage
    return _GuardedPage

_profile = None       # shared persistent web profile (keeps you logged in)
_dock = None          # floating review window (toggled)
_home_box = None      # built-in box on the deck list
_home_visible = False # user intent: show the home box (toggled from the rail)


# --------------------------------------------------------------------------- #
#  WebEngine plumbing
# --------------------------------------------------------------------------- #

def _shared_profile():
    """A named, on-disk QWebEngineProfile so cookies/logins survive restarts.
    Kept in a module global because the profile must outlive its pages. Returns
    None if WebEngine isn't available (caller falls back to the default)."""
    global _profile
    if _profile is not None:
        return _profile
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile
    except Exception:
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineProfile
        except Exception:
            return None
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_files", "music_profile")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    try:
        prof = QWebEngineProfile("ankiblitz_music")  # a name => persistent storage
        prof.setPersistentStoragePath(base)
        prof.setCachePath(os.path.join(base, "cache"))
        prof.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        try:  # let playlists/queues keep playing without re-clicking play
            from aqt.qt import QWebEngineSettings
            prof.settings().setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        except Exception:
            pass
        _profile = prof
        return prof
    except Exception:
        return None


def _webengine_view(parent):
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    except Exception:
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
        except Exception:
            return None
    view = QWebEngineView(parent)
    prof = _shared_profile()
    PageCls = _guarded_page_class()
    if PageCls is not None:
        try:
            page = PageCls(prof, view) if prof is not None else PageCls(view)
            page._guard_view = view
            view.setPage(page)
        except Exception:
            pass
    try:  # zoom out so the full desktop site fits a small window without cramping
        view.setZoomFactor(0.8)
    except Exception:
        pass
    return view


def _home_for(service: str) -> str:
    return SERVICE_HOMES.get(service, DEFAULT_HOME)


# --------------------------------------------------------------------------- #
#  The reusable player widget
# --------------------------------------------------------------------------- #

class PlayerWidget(QWidget):
    """Two service quick-jumps (SoundCloud / YT Music) + reload + the webview.
    No address bar and no back/forward — you stay on the music sites. Remembers
    the last page (``music.last_url``) so it reopens where you left off."""

    _COLLAPSED_H = 46  # height of the controls-only "minimised" state (one row)

    def __init__(self, parent=None, manage_window=False):
        super().__init__(parent)
        mu = get_section("music")
        self._view = _webengine_view(self)
        self._cur_url = ""
        self._manage_window = manage_window
        self._collapsed = False
        self.setFixedWidth(PLAYER_W)  # fixed, narrow — same everywhere

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        # Two stacked rows so the toolbar stays narrow: the service quick-jumps
        # on top, the transport/window controls beneath. The services row hides
        # when minimised (just the transport controls stay).
        self._services_bar = QWidget(self)
        services = QHBoxLayout(self._services_bar)
        services.setContentsMargins(0, 0, 0, 0)
        services.setSpacing(4)
        sc = QPushButton("SoundCloud")
        sc.clicked.connect(lambda: self._go_home("soundcloud"))
        yt = QPushButton("YT Music")
        yt.clicked.connect(lambda: self._go_home("youtube"))
        services.addWidget(sc, 1)
        services.addWidget(yt, 1)
        lay.addWidget(self._services_bar)

        controls = QHBoxLayout()
        controls.setSpacing(4)
        prev_btn = QPushButton("⏮")
        prev_btn.setToolTip("Previous")
        prev_btn.clicked.connect(lambda: self._media("prev"))
        play_btn = QPushButton("⏯")
        play_btn.setToolTip("Play / Pause")
        play_btn.clicked.connect(lambda: self._media("playpause"))
        next_btn = QPushButton("⏭")
        next_btn.setToolTip("Next")
        next_btn.clicked.connect(lambda: self._media("next"))
        reload_btn = QPushButton("⟳")
        reload_btn.setToolTip("Reload")
        self._collapse_btn = QPushButton("—")
        self._collapse_btn.setToolTip("Minimise")
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        for b in (prev_btn, play_btn, next_btn, reload_btn, self._collapse_btn):
            b.setMaximumWidth(48)
        controls.addWidget(prev_btn)
        controls.addWidget(play_btn)
        controls.addWidget(next_btn)
        controls.addStretch(1)
        controls.addWidget(reload_btn)
        controls.addWidget(self._collapse_btn)
        lay.addLayout(controls)

        if self._view is None:
            note = QLabel("The web player isn't available in this Anki build.")
            note.setStyleSheet("color: gray;")
            lay.addWidget(note)
        else:
            lay.addWidget(self._view, 1)
            reload_btn.clicked.connect(self._view.reload)
            self._view.urlChanged.connect(self._on_url_changed)

        # Debounce: persist the last page 1.5s after navigation settles, rather
        # than on every urlChanged.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_last_url)

        start = (mu.get("last_url") or "").strip() or _home_for(mu.get("service", "soundcloud"))
        if self._view is not None:
            self._view.setUrl(QUrl(start))

    def _toggle_collapse(self) -> None:
        """Minimise to just the toolbar (music keeps playing — the webview is
        hidden, not destroyed) and back. Resizes the host window when the player
        owns it (review / home box); inside the break dialog it shrinks itself."""
        self._collapsed = not self._collapsed
        if self._view is not None:
            self._view.setVisible(not self._collapsed)
        self._services_bar.setVisible(not self._collapsed)
        self._collapse_btn.setText("□" if self._collapsed else "—")
        self._collapse_btn.setToolTip("Restore" if self._collapsed else "Minimise")
        win = self.window()
        if self._manage_window and win is not None:
            # Windows are fixed-size; adjust the locked height for minimise.
            if self._collapsed:
                self._prev_h = win.height()
                win.setFixedHeight(self._COLLAPSED_H)
            elif getattr(self, "_prev_h", None):
                win.setFixedHeight(self._prev_h)
            if hasattr(win, "reposition"):
                try:
                    win.reposition()
                except Exception:
                    pass
        else:
            if self._collapsed:
                self._prev_h = self.height()
                self.setFixedHeight(self._COLLAPSED_H)
            elif getattr(self, "_prev_h", None):
                self.setFixedHeight(self._prev_h)

    def _media(self, action: str) -> None:
        """Drive the embedded site's player without touching the page: click its
        prev/next/play controls (piercing shadow DOM, so YouTube Music's Polymer
        buttons are reachable), falling back to the media element for play/pause.
        Selectors cover SoundCloud + YouTube Music."""
        if self._view is None:
            return
        js = """(function(a){
  function dq(sel){function s(r){var e=r.querySelector(sel);if(e)return e;var k=r.querySelectorAll('*');for(var i=0;i<k.length;i++){var sr=k[i].shadowRoot;if(sr){var x=s(sr);if(x)return x;}}return null;}return s(document);}
  function clk(ss){for(var i=0;i<ss.length;i++){var e=dq(ss[i]);if(e){e.click();return true;}}return false;}
  if(a==='next')return clk(['.skipControl__next','.next-button','tp-yt-paper-icon-button.next-button']);
  if(a==='prev')return clk(['.skipControl__previous','.previous-button','tp-yt-paper-icon-button.previous-button']);
  if(clk(['.playControls__play','#play-pause-button','.play-pause-button']))return true;
  var m=dq('video')||dq('audio');if(m){if(m.paused){m.play();}else{m.pause();}return true;}
  return false;
})(%r);""" % action
        try:
            self._view.page().runJavaScript(js)
        except Exception:
            pass

    def _go_home(self, service: str) -> None:
        self._persist(service=service)
        if self._view is not None:
            self._view.setUrl(QUrl(_home_for(service)))

    def _on_url_changed(self, u) -> None:
        try:
            self._cur_url = u.toString()
        except Exception:
            return
        self._save_timer.start(1500)

    def _save_last_url(self) -> None:
        if self._cur_url:
            self._persist(url=self._cur_url)

    def _persist(self, service=None, url=None) -> None:
        # Additive: read the merged section, set only the touched keys, write it
        # back through Anki's own config channel (never hand-edits meta.json).
        mu = get_section("music")
        if service is not None:
            mu["service"] = service
        if url is not None:
            mu["last_url"] = url
        save_section("music", mu)


def build_player_widget(parent=None, manage_window=False) -> "PlayerWidget":
    return PlayerWidget(parent, manage_window=manage_window)


# --------------------------------------------------------------------------- #
#  Floating review window (toggled with the menu / Ctrl+Shift+M)
# --------------------------------------------------------------------------- #

class _MusicDock(QWidget):
    def __init__(self):
        super().__init__(mw)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("AnkiBlitz — Music")
        self.setFixedSize(PLAYER_W, PLAYER_H)  # no drag-resizing
        # Park off-screen until positioned, so the webview realizing its native
        # surface can't flash at the default (0,0) before reposition() runs.
        self.move(-10000, -10000)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(PlayerWidget(self, manage_window=True))
        self.reposition()

    def reposition(self) -> None:
        try:
            g = mw.frameGeometry()
            x = g.right() - self.width() - 8
            y = g.bottom() - self.height() - 40
            self.move(x, max(g.top() + 70, y))
        except Exception:
            pass


def _deferred_to_synapse() -> bool:
    """SynapsePro installed and handling the music? Then don't open ours.

    Checked at every entry point, not just where the UI is drawn — the menu item
    hides itself but Ctrl+Shift+M would still fire, and a box left open from
    before SynapsePro appeared would linger.
    """
    try:
        from . import theme_bridge
        return theme_bridge.music_deferred()
    except Exception:
        return False


def toggle_dock(respect_dropdown: bool = True) -> None:
    """Show/hide the floating review player (menu + Ctrl+Shift+M)."""
    mu = get_section("music")
    if not mu.get("enabled", False):
        tooltip("Turn on the music player in Settings ▸ Music first.")
        return
    if _deferred_to_synapse():
        tooltip("SynapsePro is handling the music — its player is the one to use. "
                "Settings ▸ AnkiBlitz ▸ SynapsePro to change that.")
        return
    if respect_dropdown and not mu.get("show_dropdown", True):
        tooltip("The review music window is off in Settings ▸ Music.")
        return
    global _dock
    if _dock is None:
        _dock = _MusicDock()
    if _dock.isVisible():
        _dock.hide()
    else:
        _dock.reposition()
        _dock.show()
        _dock.raise_()


# --------------------------------------------------------------------------- #
#  Built-in box on the deck list (auto-shown, anchored below the rail)
# --------------------------------------------------------------------------- #

class _HomeMusicBox(QWidget):
    """A small frameless window pinned to the right of the deck list, under the
    AnkiBlitz rail. A separate window (not a child painted over the deck-browser
    webview) to avoid macOS native-webview z-order glitches; repositions with the
    main window."""

    def __init__(self):
        super().__init__(mw)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(PLAYER_W, PLAYER_H)  # no drag-resizing
        # Park off-screen until positioned, so the webview realizing its native
        # surface can't flash at the default (0,0) before reposition() runs.
        self.move(-10000, -10000)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(PlayerWidget(self, manage_window=True))
        mw.installEventFilter(self)
        self.reposition()

    def reposition(self) -> None:
        try:
            g = mw.frameGeometry()
            # Flush to the right edge, anchored to the bottom so it never covers
            # the rail's buttons at the top.
            x = g.right() - self.width() - 8
            y = g.bottom() - self.height() - 40
            self.move(x, max(g.top() + 70, y))
        except Exception:
            pass

    def eventFilter(self, obj, ev):
        try:
            if obj is mw and self.isVisible() and ev.type() in (
                    QEvent.Type.Resize, QEvent.Type.Move):
                self.reposition()
        except Exception:
            pass
        return False


def _update_home_box() -> None:
    """Show the built-in box on the deck list / overview when the user has it
    toggled on; hide it on other screens (and when toggled off)."""
    global _home_box
    try:
        mu = get_section("music")
        want = (
            _home_visible
            and suite_enabled() and mu.get("enabled", False)
            and mu.get("show_on_home", True)
            and not _deferred_to_synapse()
            and getattr(mw, "state", None) in HOME_STATES
        )
    except Exception:
        want = False
    if want:
        if _home_box is None:
            _home_box = _HomeMusicBox()
        _home_box.reposition()
        _home_box.show()
        _home_box.raise_()
    elif _home_box is not None:
        _home_box.hide()


def toggle_home_box() -> None:
    """Rail button: show/hide the built-in music box on the deck list. The box no
    longer auto-appears — it's off until you ask for it here."""
    global _home_visible
    mu = get_section("music")
    if not mu.get("enabled", False):
        tooltip("Turn on the music player in Settings ▸ Music first.")
        return
    if _deferred_to_synapse():
        tooltip("SynapsePro is handling the music — use its player.")
        return
    _home_visible = not _home_visible
    _update_home_box()


def _on_state_change(new_state, old_state) -> None:
    _update_home_box()


def register() -> None:
    gui_hooks.state_did_change.append(_on_state_change)
    # The first deckBrowser render can land before this hook is wired at profile
    # open, so nudge once so the box appears on initial load.
    mw.progress.single_shot(200, _update_home_box, False)
