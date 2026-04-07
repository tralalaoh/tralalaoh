# -*- coding: utf-8 -*-
"""
Little Rabite Service Monitor
Monitors Kodi player events and manages scrobbling.
Based on TMDbHelper's ServiceMonitor pattern.
"""

import xbmc
import xbmcgui
import time
from threading import Thread, Lock

from resources.lib.scrobbler import Scrobbler
from resources.lib.managers.sync_manager import get_sync_manager
from resources.lib.services.trakt import TraktService


class PlayerMonitor(xbmc.Player):
    """
    Custom player class that monitors playback events.
    Inherits from xbmc.Player to receive callbacks.
    """

    def __init__(self, scrobbler):
        """
        Initialize player monitor.

        Args:
            scrobbler: Scrobbler instance
        """
        super(PlayerMonitor, self).__init__()
        self.scrobbler = scrobbler
        self._log('PlayerMonitor initialized')

    def onAVStarted(self):
        """Called when audio/video playback starts."""
        # Wait a moment for player to stabilize
        xbmc.sleep(1000)

        if self.isPlayingVideo():
            self._log('Video playback started, extracting info...')

            try:
                video_data = self._extract_video_info()

                if video_data:
                    self.scrobbler.playback_started(video_data)
                else:
                    self._log('Could not extract video info', xbmc.LOGWARNING)

            except Exception as e:
                self._log(f'Error in onAVStarted: {str(e)}', xbmc.LOGERROR)
                import traceback
                self._log(traceback.format_exc(), xbmc.LOGERROR)

    def onPlayBackPaused(self):
        """Called when playback is paused."""
        try:
            self.scrobbler.playback_paused()
        except Exception as e:
            self._log(f'Error in onPlayBackPaused: {str(e)}', xbmc.LOGERROR)

    def onPlayBackResumed(self):
        """Called when playback resumes."""
        try:
            self.scrobbler.playback_resumed()
        except Exception as e:
            self._log(f'Error in onPlayBackResumed: {str(e)}', xbmc.LOGERROR)

    def onPlayBackSeek(self, time, seekOffset):
        """Called when user seeks."""
        try:
            self.scrobbler.playback_seek()
        except Exception as e:
            self._log(f'Error in onPlayBackSeek: {str(e)}', xbmc.LOGERROR)

    def onPlayBackStopped(self):
        """Called when playback is stopped."""
        try:
            self.scrobbler.playback_stopped()
        except Exception as e:
            self._log(f'Error in onPlayBackStopped: {str(e)}', xbmc.LOGERROR)

    def onPlayBackEnded(self):
        """Called when playback ends naturally."""
        try:
            self.scrobbler.playback_ended()
        except Exception as e:
            self._log(f'Error in onPlayBackEnded: {str(e)}', xbmc.LOGERROR)

    def _extract_video_info(self):
        """
        Extract video information from Kodi player.
        Uses InfoLabels and InfoTag to get IDs and metadata.

        Returns:
            dict: Video information or None
        """
        try:
            info_tag = self.getVideoInfoTag()

            # Determine media type
            media_type = self._determine_media_type(info_tag)

            if media_type not in ['movie', 'episode']:
                self._log(f'Unsupported media type: {media_type}', xbmc.LOGWARNING)
                return None

            # Extract IDs from BOTH InfoTag and InfoLabels
            ids = self._extract_ids(info_tag, media_type)

            if not ids:
                self._log('No IDs found for video', xbmc.LOGWARNING)
                return None

            # Build video data
            video_data = {
                'type': media_type,
                'ids': ids,
                'title': info_tag.getTitle() or xbmc.getInfoLabel('VideoPlayer.Title')
            }

            # Movie-specific info
            if media_type == 'movie':
                video_data['year'] = info_tag.getYear() or self._extract_year_from_label()

            # Episode-specific info
            elif media_type == 'episode':
                video_data['season'] = info_tag.getSeason()
                video_data['episode'] = info_tag.getEpisode()
                video_data['show_title'] = info_tag.getTVShowTitle() or xbmc.getInfoLabel('VideoPlayer.TVShowTitle')

                # Try to get show year
                show_year = self._extract_show_year()
                if show_year:
                    video_data['show_year'] = show_year

                # Try to get show IDs
                show_ids = self._extract_show_ids()
                if show_ids:
                    video_data['show_ids'] = show_ids

            self._log(f'Extracted info: {media_type} - {video_data.get("title")}')

            return video_data

        except Exception as e:
            self._log(f'Error extracting video info: {str(e)}', xbmc.LOGERROR)
            import traceback
            self._log(traceback.format_exc(), xbmc.LOGERROR)
            return None

    def _determine_media_type(self, info_tag):
        """
        Determine if playing content is a movie or episode.

        Args:
            info_tag: Video info tag

        Returns:
            str: 'movie', 'episode', or 'unknown'
        """
        # Check for TV show title
        if info_tag.getTVShowTitle() or xbmc.getInfoLabel('VideoPlayer.TVShowTitle'):
            return 'episode'

        # Check for season/episode numbers
        if info_tag.getSeason() >= 0 and info_tag.getEpisode() >= 0:
            return 'episode'

        # Check media type from info label
        media_type = xbmc.getInfoLabel('VideoPlayer.MediaType')
        if media_type:
            if media_type in ['episode', 'tvshow']:
                return 'episode'
            elif media_type == 'movie':
                return 'movie'

        # Default to movie if we have a year
        if info_tag.getYear() > 0:
            return 'movie'

        # Check DBTYPE
        dbtype = xbmc.getInfoLabel('VideoPlayer.DBTYPE')
        if dbtype:
            if dbtype in ['episode', 'tvshow']:
                return 'episode'
            elif dbtype == 'movie':
                return 'movie'

        return 'unknown'

    def _extract_ids(self, info_tag, media_type):
        """
        Extract all available IDs for the video from InfoTag AND InfoLabels.

        Args:
            info_tag: Video info tag
            media_type: 'movie' or 'episode'

        Returns:
            dict: IDs or None
        """
        ids = {}

        # PRIORITY 1: Try InfoTag.getUniqueIDs() (modern addons like TMDb Helper)
        if hasattr(info_tag, 'getUniqueIDs'):
            try:
                unique_ids = info_tag.getUniqueIDs()
                if unique_ids:
                    for key, value in unique_ids.items():
                        if value:
                            # Normalize key names
                            key_lower = key.lower()
                            if key_lower in ['tmdb', 'tvdb', 'imdb', 'trakt', 'tvmaze', 'mal', 'anilist', 'anidb']:
                                if key_lower == 'tmdb' or key_lower == 'tvdb' or key_lower == 'trakt':
                                    ids[key_lower] = int(value) if str(value).isdigit() else value
                                elif key_lower == 'imdb' and str(value).startswith('tt'):
                                    ids['imdb'] = str(value)
                                else:
                                    ids[key_lower] = value
            except Exception as e:
                self._log(f"getUniqueIDs failed: {e}", xbmc.LOGDEBUG)

        # PRIORITY 2: IMDB ID from InfoTag
        imdb = info_tag.getIMDBNumber() or xbmc.getInfoLabel('VideoPlayer.IMDBNumber')
        if imdb and imdb.startswith('tt') and 'imdb' not in ids:
            ids['imdb'] = imdb

        # PRIORITY 3: Try InfoLabels for IDs as fallback
        if not ids.get('tmdb'):
            tmdb_label = xbmc.getInfoLabel('VideoPlayer.TMDBNumber')
            if tmdb_label and tmdb_label.isdigit():
                ids['tmdb'] = int(tmdb_label)

        # For episodes, try to get TVDB from different sources
        if media_type == 'episode' and not ids.get('tvdb'):
            tvdb_label = xbmc.getInfoLabel('VideoPlayer.TVDBNumber')
            if tvdb_label and tvdb_label.isdigit():
                ids['tvdb'] = int(tvdb_label)

        # PRIORITY 4: Try ListItem properties (set by some addons)
        try:
            listitem = xbmc.Player().getPlayingItem()
            if listitem:
                # Check properties for IDs
                for id_key in ['tmdb_id', 'tvdb_id', 'imdb_id', 'trakt_id', 'mal_id', 'anilist_id']:
                    prop_value = listitem.getProperty(id_key)
                    if prop_value:
                        # Clean up key name (remove _id suffix)
                        clean_key = id_key.replace('_id', '')
                        if clean_key not in ids:
                            if clean_key in ['tmdb', 'tvdb', 'trakt'] and prop_value.isdigit():
                                ids[clean_key] = int(prop_value)
                            else:
                                ids[clean_key] = prop_value
        except Exception as e:
            self._log(f"ListItem property extraction failed: {e}", xbmc.LOGDEBUG)

        return ids if ids else None

    def _extract_show_ids(self):
        """
        Extract show IDs for TV episodes.

        Returns:
            dict: Show IDs or None
        """
        ids = {}

        # Try various InfoLabels
        tvdb = xbmc.getInfoLabel('VideoPlayer.TvShowDBID')
        if tvdb and tvdb.isdigit():
            ids['tvdb'] = int(tvdb)

        imdb = xbmc.getInfoLabel('VideoPlayer.TvShowIMDBNumber')
        if imdb and imdb.startswith('tt'):
            ids['imdb'] = imdb

        tmdb = xbmc.getInfoLabel('VideoPlayer.TvShowTMDBNumber')
        if tmdb and tmdb.isdigit():
            ids['tmdb'] = int(tmdb)

        return ids if ids else None

    def _extract_year_from_label(self):
        """
        Extract year from InfoLabel.

        Returns:
            int: Year or None
        """
        try:
            year_str = xbmc.getInfoLabel('VideoPlayer.Year')
            if year_str and year_str.isdigit():
                year = int(year_str)
                if 1900 < year < 2100:
                    return year
        except Exception:
            pass

        return None

    def _extract_show_year(self):
        """
        Extract show year for TV episodes.

        Returns:
            int: Year or None
        """
        try:
            year_str = xbmc.getInfoLabel('VideoPlayer.Year')
            if year_str and year_str.isdigit():
                return int(year_str)
        except Exception:
            pass

        return None

    def _log(self, message, level=xbmc.LOGINFO):
        """Log a message."""
        xbmc.log(f'[LittleRabite Player] {message}', level)


class ServiceMonitor:
    """
    Service monitor that manages scrobbling and syncing.
    """

    # Polling intervals (in seconds)
    POLL_FAST = 1.0      # Fast polling when player is active
    POLL_NORMAL = 5.0    # Normal polling for general monitoring
    POLL_SLOW = 30.0     # Slow polling when idle

    # Progress update interval (seconds)
    PROGRESS_UPDATE_INTERVAL = 10

    def __init__(self, database):
        """
        Initialize the service monitor.

        Args:
            database: Database instance
        """
        self.db = database
        self.monitor = xbmc.Monitor()

        self.exit = False

        self._mutex = Lock()

        # Initialize service manager
        self.sync_manager = get_sync_manager()

        # Register services
        self.sync_manager.register_service(TraktService)

        # Initialize scrobbler
        self.scrobbler = Scrobbler(self.sync_manager)

        # Initialize player monitor
        self.player_monitor = PlayerMonitor(self.scrobbler)

        # Sync thread
        self.sync_thread = None
        self.last_sync = 0
        self.sync_interval = 3600  # Sync every hour

        # Progress update tracking
        self.last_progress_update = 0

        xbmc.log('[LittleRabite] ServiceMonitor initialized', xbmc.LOGINFO)

    def run(self):
        """
        Main monitoring loop.
        """
        xbmc.log('[LittleRabite] Service monitor starting...', xbmc.LOGINFO)

        # Run initial sync if authenticated
        self._initial_sync()

        # Start background sync thread
        self._start_sync_thread()

        # Main loop
        while not self.monitor.abortRequested() and not self.exit:
            try:
                # Check if we should stop
                if xbmcgui.Window(10000).getProperty('LittleRabite.ServiceStop') == 'true':
                    xbmc.log('[LittleRabite] Stop signal received', xbmc.LOGINFO)
                    break

                # Determine polling interval
                if self.scrobbler.is_playing:
                    poll_interval = self.POLL_FAST

                    # Update progress periodically
                    if time.time() - self.last_progress_update >= self.PROGRESS_UPDATE_INTERVAL:
                        self.scrobbler.update_progress()
                        self.last_progress_update = time.time()
                else:
                    poll_interval = self.POLL_NORMAL

                # Wait for abort or interval
                if self.monitor.waitForAbort(poll_interval):
                    break

            except Exception as e:
                xbmc.log(f'[LittleRabite] Error in monitor loop: {str(e)}', xbmc.LOGERROR)
                import traceback
                xbmc.log(traceback.format_exc(), xbmc.LOGERROR)

                # Wait a bit before continuing to avoid tight error loop
                if self.monitor.waitForAbort(5):
                    break

        xbmc.log('[LittleRabite] Service monitor stopped', xbmc.LOGINFO)

    def _initial_sync(self):
        """Run initial sync on startup."""
        try:
            authenticated_services = self.sync_manager.get_authenticated_services()

            if authenticated_services:
                xbmc.log(f'[LittleRabite] Running initial sync for: {", ".join(authenticated_services)}', xbmc.LOGINFO)

                # Run sync in background thread
                def sync_worker():
                    results = self.sync_manager.sync_all(threaded=False)
                    # Process pull results
                    if 'pull' in results:
                        for service, result in results['pull'].items():
                            if result and result.get('success'):
                                xbmc.log(f'[LittleRabite] {service}: Synced {result.get("synced", 0)} items', xbmc.LOGINFO)
                            else:
                                error = result.get('error', 'Unknown error') if result else 'No result'
                                xbmc.log(f'[LittleRabite] {service}: Sync failed - {error}', xbmc.LOGWARNING)

                thread = Thread(target=sync_worker, name='InitialSync')
                thread.daemon = True
                thread.start()
            else:
                xbmc.log('[LittleRabite] No authenticated services, skipping initial sync', xbmc.LOGINFO)

        except Exception as e:
            xbmc.log(f'[LittleRabite] Error in initial sync: {str(e)}', xbmc.LOGERROR)

    def _start_sync_thread(self):
        """Start background thread for periodic syncing."""
        def sync_worker():
            """Background worker that syncs periodically."""
            xbmc.log('[LittleRabite] Sync worker started', xbmc.LOGINFO)

            while not self.exit and not self.monitor.abortRequested():
                try:
                    current_time = time.time()

                    # Check if it's time to sync
                    if current_time - self.last_sync >= self.sync_interval:
                        xbmc.log('[LittleRabite] Running periodic sync...', xbmc.LOGINFO)

                        # Run sync (non-threaded since we are already in a thread)
                        results = self.sync_manager.sync_all(threaded=False)

                        # Process pull results
                        if 'pull' in results:
                            for service, result in results['pull'].items():
                                if result and result.get('success'):
                                    xbmc.log(f'[LittleRabite] {service}: Synced {result.get("synced", 0)} items', xbmc.LOGINFO)

                        # Process push results
                        if 'push' in results:
                            for service, result in results['push'].items():
                                if result and result.get('success'):
                                    xbmc.log(f'[LittleRabite] {service}: Pushed {result.get("pushed", 0)} items', xbmc.LOGINFO)

                        self.last_sync = current_time

                except Exception as e:
                    xbmc.log(f'[LittleRabite] Sync worker error: {str(e)}', xbmc.LOGERROR)

                # Wait before next check
                if self.monitor.waitForAbort(60):  # Check every minute
                    break

            xbmc.log('[LittleRabite] Sync worker stopped', xbmc.LOGINFO)

        self.sync_thread = Thread(target=sync_worker, name='LittleRabite-Sync')
        self.sync_thread.daemon = True
        self.sync_thread.start()

    def cleanup(self):
        """Cleanup resources before shutdown."""
        xbmc.log('[LittleRabite] ServiceMonitor cleanup started', xbmc.LOGINFO)

        self.exit = True

        # Wait for sync thread to finish
        if self.sync_thread and self.sync_thread.is_alive():
            xbmc.log('[LittleRabite] Waiting for sync thread to finish...', xbmc.LOGINFO)
            self.sync_thread.join(timeout=5)

        xbmc.log('[LittleRabite] ServiceMonitor cleanup complete', xbmc.LOGINFO)


def restart_service_monitor():
    """
    Restart the service monitor.
    Useful for testing or when settings change.
    """
    window = xbmcgui.Window(10000)

    # Check if service is running
    if window.getProperty('LittleRabite.ServiceStarted') == 'true':
        xbmc.log('[LittleRabite] Requesting service restart...', xbmc.LOGINFO)

        # Signal service to stop
        window.setProperty('LittleRabite.ServiceStop', 'true')

        # Wait for service to stop
        max_wait = 10
        for _ in range(max_wait):
            if window.getProperty('LittleRabite.ServiceStarted') != 'true':
                break
            xbmc.sleep(1000)

        # Clear stop signal
        window.clearProperty('LittleRabite.ServiceStop')

        # Start service again
        Thread(target=lambda: xbmc.executebuiltin('RunScript(service.littlerabite)')).start()
    else:
        xbmc.log('[LittleRabite] Service not running, starting...', xbmc.LOGINFO)
        xbmc.executebuiltin('RunScript(service.littlerabite)')
