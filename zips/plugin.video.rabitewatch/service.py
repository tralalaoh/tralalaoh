# -*- coding: utf-8 -*-
"""
Rabite Watch - Background Service
Periodically pulls data from all connected services.
Sync interval is read live from addon settings so changes take effect
without restarting Kodi.
"""

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import sys
import time
import os
import threading

addon = xbmcaddon.Addon()
addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
sys.path.insert(0, addon_path)

from resources.lib.pull_manager import get_pull_manager
from resources.lib.database import get_database



# ---------------------------------------------------------------------------
# Player listener — local progress tracking
# ---------------------------------------------------------------------------

class RabiteWatchPlayer(xbmc.Player):
    """
    Persistent player listener that runs inside the background service process.

    Tracks local playback progress: when the plugin stores the active DB row ID
    in 'RabiteWatch.ActiveDbId', this listener polls the playback position
    every 30 s and writes it to the local DB on stop/end.  The widget then
    refreshes instantly without waiting for the next cloud sync.

    Uses onAVStarted (NOT onPlayBackStarted): the latter fires when Kodi
    creates the demuxer, which is far too early — A/V streams are not open yet.
    onAVStarted fires once all codecs are initialised and the first frame has
    been rendered.
    """

    _POLL_INTERVAL     = 30    # seconds between position polls while playing
    _MIN_TRACK_S       = 60    # minimum seconds watched before saving progress
    _MIN_TRACK_PCT     = 5     # minimum % watched before saving progress

    def __init__(self):
        # Kodi's C++ Player bindings don't always accept super().__init__() —
        # use the explicit form and swallow any error so a C-level quirk never
        # prevents the player object (and therefore the whole service) from
        # being created.
        _init_ok = True
        try:
            xbmc.Player.__init__(self)
        except Exception as _e:
            _init_ok = False
            xbmc.log(f'[RabiteWatch-Player] C++ Player.__init__ failed (non-fatal): {_e}', xbmc.LOGWARNING)
        self._active_db_id      = None   # DB row id of the currently playing item
        self._last_pos          = 0.0    # last polled position (seconds)
        self._active_total_time = 0.0    # total duration of the current item
        self._poll_stop         = None   # threading.Event that stops the poll thread
        if _init_ok:
            self._log('Player listener ready')

    def onAVStarted(self):
        win = xbmcgui.Window(10000)

        # Read the active DB row id advertised by resolve_item() in default.py.
        db_id_raw = win.getProperty('RabiteWatch.ActiveDbId')
        dur_raw   = win.getProperty('RabiteWatch.ActiveDuration')
        if db_id_raw:
            win.clearProperty('RabiteWatch.ActiveDbId')
            win.clearProperty('RabiteWatch.ActiveDuration')
            self._active_db_id = db_id_raw
            self._last_pos     = 0.0
            try:
                total = self.getTotalTime()
                self._active_total_time = total if total > 0 else float(dur_raw or 0)
            except Exception:
                self._active_total_time = float(dur_raw or 0)
            self._start_poll()
            self._log(
                f'Tracking playback: db_id={db_id_raw} '
                f'duration={self._active_total_time:.0f}s'
            )

        # Smooth seek: wait until the stream is truly running then seek once.
        raw = win.getProperty('RabiteWatch.PendingSeek')
        if raw:
            win.clearProperty('RabiteWatch.PendingSeek')
            try:
                seek_to = float(raw)
            except (ValueError, TypeError):
                seek_to = 0.0
            if seek_to > 0:
                threading.Thread(
                    target=self._seek_when_ready,
                    args=(seek_to,),
                    daemon=True,
                ).start()

    def _seek_when_ready(self, seek_to):
        """
        Poll until the player is truly running and has a valid position,
        then perform a single seekTime() call.  No retries — if the stream
        is playing and seekable we seek once and trust Kodi/the provider.
        """
        for _ in range(25):          # up to ~5 s in 200 ms steps
            xbmc.sleep(200)
            if not self.isPlaying():
                return
            try:
                if self.getTime() >= 0:
                    break
            except Exception:
                pass
        else:
            self._log(f'Seek timed out waiting for stream (target={seek_to:.1f}s)', xbmc.LOGWARNING)
            return

        if not self.isPlaying():
            return
        try:
            self.seekTime(seek_to)
            self._log(f'Seeked to {seek_to:.1f}s')
        except Exception as e:
            self._log(f'Seek error: {e}', xbmc.LOGWARNING)

    def onPlayBackStopped(self):
        """User manually stopped — save position as a resume point."""
        self._log('onPlayBackStopped fired')
        self._stop_poll()
        self._save_local_progress(ended=False)

    def onPlayBackEnded(self):
        """Video played to the end — mark as completed."""
        self._log('onPlayBackEnded fired')
        self._stop_poll()
        self._save_local_progress(ended=True)

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log(self, msg, level=None):
        if level is None:
            try:
                debug = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingBool('debug_logging')
            except Exception:
                debug = False
            level = xbmc.LOGINFO if debug else xbmc.LOGDEBUG
        xbmc.log(f'[RabiteWatch-Player] {msg}', level)

    # ------------------------------------------------------------------
    # Progress poll helpers
    # ------------------------------------------------------------------

    def _start_poll(self):
        """Start a daemon thread that updates _last_pos every POLL_INTERVAL s."""
        if self._poll_stop:
            self._poll_stop.set()   # stop any stale poll from a previous item
        self._poll_stop = threading.Event()
        threading.Thread(
            target=self._poll_progress, args=(self._poll_stop,), daemon=True
        ).start()

    def _stop_poll(self):
        if self._poll_stop:
            self._poll_stop.set()
            self._poll_stop = None

    def _poll_progress(self, stop_event):
        """Runs in a background thread; updates _last_pos every POLL_INTERVAL s."""
        while not stop_event.wait(self._POLL_INTERVAL):
            try:
                if self.isPlaying():
                    pos   = self.getTime()
                    total = self.getTotalTime()
                    if pos > 0:
                        self._last_pos = pos
                    if total > 0:
                        self._active_total_time = total
            except Exception:
                pass

    def _save_local_progress(self, ended):
        """
        Write the playback position to the local DB and refresh the widget.

        ended=True  — video finished naturally; mark the row as completed.
        ended=False — user stopped; save the actual resume position.

        Silently skips items not launched via our plugin (no ActiveDbId) and
        trivially short plays (< 60 s AND < 5 %) to avoid polluting the DB.
        """
        db_id = self._active_db_id
        self._active_db_id = None   # clear before any early return so re-fires are safe

        if not db_id:
            return

        total_time = self._active_total_time

        if ended:
            resume_time = 0.0
            resume_pct  = 100
            completed   = True
        else:
            # getTime() may or may not be reliable after stop; fall back to
            # the last polled position if it returns 0.
            try:
                pos = float(self.getTime())
                resume_time = pos if pos > 0 else self._last_pos
            except Exception:
                resume_time = self._last_pos

            if total_time > 0:
                resume_pct = min(int((resume_time / total_time) * 100), 99)
            else:
                resume_pct = 0

            # Skip if the user just previewed for a few seconds
            if resume_time < self._MIN_TRACK_S and resume_pct < self._MIN_TRACK_PCT:
                self._log(
                    f'Local save skipped — too short '
                    f'({resume_time:.0f}s / {resume_pct}%)'
                )
                return

            completed = False

        try:
            db = get_database()
            db.update_local_progress(int(db_id), resume_time, resume_pct, completed)
            self._log(
                f'Local progress saved — id={db_id} '
                f't={resume_time:.0f}s pct={resume_pct}% completed={completed}'
            )
            # Instant widget refresh from the local write above.
            xbmc.executebuiltin('Container.Refresh')
            self._log('Container.Refresh fired after local progress save')

            # Background cloud sync: fetch the 2 most recently watched items
            # from each service so the widget gets the authoritative position
            # once any third-party scrobbler has had time to report (5 s delay
            # built into pull_post_playback).
            self._log('Spawning post-playback cloud sync thread')
            threading.Thread(
                target=get_pull_manager().pull_post_playback,
                daemon=True
            ).start()

        except Exception as e:
            self._log(f'Local progress save failed: {e}', xbmc.LOGWARNING)


class RabiteWatchService(xbmc.Monitor):

    def __init__(self):
        super().__init__()
        self.addon      = xbmcaddon.Addon()
        self.pm         = get_pull_manager()
        self._last_pull = 0
        # Hold a strong reference — xbmc.Player subclasses are GC'd if not kept
        self._player    = RabiteWatchPlayer()
        self._log('Service started')

        xbmcgui.Window(10000).setProperty('RabiteWatch.ServiceStarted', 'true')

        if self._setting_bool('sync_on_startup'):
            self._do_startup_pull()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def _reload_addon(self):
        """Re-instantiate Addon() to pick up changed settings."""
        self.addon = xbmcaddon.Addon()

    def _setting_bool(self, key):
        try:
            return self.addon.getSettingBool(key)
        except Exception:
            return self.addon.getSetting(key) == 'true'

    def _sync_interval_s(self):
        """Return sync interval in seconds, or None if disabled (0 minutes)."""
        try:
            minutes = int(self.addon.getSettingInt('sync_interval'))
        except Exception:
            minutes = 15  # default
        if minutes == 0:
            return None  # never auto-sync
        return minutes * 60

    # ------------------------------------------------------------------
    # xbmc.Monitor callbacks
    # ------------------------------------------------------------------

    def onSettingsChanged(self):
        """Called by Kodi when any addon setting is changed."""
        self._reload_addon()
        self._log('Settings changed — triggering background sync')
        threading.Thread(target=self._do_pull, daemon=True).start()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        """Check every 60 s; pull when interval has elapsed."""
        while not self.waitForAbort(60):
            interval = self._sync_interval_s()
            if interval is None:
                continue  # 'Never' — skip automatic sync
            if time.time() - self._last_pull >= interval:
                self._do_pull()

        self._cleanup()

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def _do_pull(self):
        self._log('Starting background pull...')
        try:
            results      = self.pm.pull_all()
            self._last_pull = time.time()
            for svc, res in results.items():
                if res.get('success'):
                    self._log(f'{svc}: pulled {res.get("pulled", 0)} items')
                else:
                    self._log(f'{svc}: pull failed — {res.get("error")}', xbmc.LOGWARNING)
        except Exception as e:
            self._log(f'Pull error: {e}', xbmc.LOGERROR)

    def _do_startup_pull(self):
        """
        Startup sync — smart: full pull when DB is empty, fast top-N otherwise.
        Reads 'startup_pull_limit' from settings so the user controls the limit.
        Runs on the calling thread (already a non-blocking context at startup).
        """
        limit = self._startup_pull_limit()
        self._log(f'Startup sync — limit={limit}')
        try:
            self.pm.pull_startup(limit=limit)
            self._last_pull = time.time()
        except Exception as e:
            self._log(f'Startup pull error: {e}', xbmc.LOGERROR)

    def _startup_pull_limit(self):
        try:
            return max(1, int(self.addon.getSettingInt('startup_pull_limit')))
        except Exception:
            return 5

    def _cleanup(self):
        xbmcgui.Window(10000).clearProperty('RabiteWatch.ServiceStarted')
        self._log('Service stopped')

    def _log(self, msg, level=None):
        if level is None:
            try:
                debug = self.addon.getSettingBool('debug_logging')
            except Exception:
                debug = False
            level = xbmc.LOGINFO if debug else xbmc.LOGDEBUG
        xbmc.log(f'[RabiteWatch] {msg}', level)


def main():
    service = RabiteWatchService()
    service.run()


if __name__ == '__main__':
    main()
