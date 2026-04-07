# -*- coding: utf-8 -*-
"""
Little Rabite - Scrobbler
Tracks playback progress and manages scrobbling to services.
Adapted from script.trakt's Scrobbler class.
"""

import xbmc
import time
import math
from threading import Thread, Lock

try:
    from resources.lib.database import get_database
    from resources.lib.managers.sync_manager import get_sync_manager
except ImportError:
    # For testing outside Kodi
    pass


class Scrobbler:
    """
    Scrobbler class that tracks playback and manages scrobbling.
    Calculates watch percentage and updates database/services.
    """
    
    def __init__(self, service_manager):
        """
        Initialize the scrobbler.
        
        Args:
            service_manager: ServiceManager instance with registered services
        """
        self.sync_manager = get_sync_manager()
        self.db = get_database()
        
        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.stop_scrobbler = False
        
        # Video info
        self.current_video = None
        self.current_media_info = None
        self.video_duration = 1  # Avoid division by zero
        self.watched_time = 0
        self.paused_at = 0
        
        # Multi-part episode support
        self.is_multi_part_episode = False
        self.last_mp_check = 0
        self.current_mp_episode = 0
        
        # For PVR support
        self.is_pvr = False
        
        # Thread safety
        self._lock = Lock()
        
        # Video queue for rating (not implemented yet, but keeping for compatibility)
        self.videos_to_rate = []
        
        self._log('Scrobbler initialized')
    
    # ============================================================================
    # PLAYBACK EVENT HANDLERS
    # ============================================================================
    
    def playback_started(self, data):
        """
        Called when playback starts.
        
        Args:
            data: Dict with video information from player
        """
        with self._lock:
            self._log(f'playback_started: {data.get("title", "Unknown")}')
            
            if not data:
                return
            
            self.current_video = data
            self.current_media_info = None
            self.videos_to_rate = []
            
            # Check if we have required IDs
            if not data.get('ids') or not data['ids']:
                self._log('No IDs available for scrobbling', xbmc.LOGWARNING)
                return
            
            # Get video type
            video_type = data.get('type', 'unknown')
            
            if video_type not in ['movie', 'episode']:
                self._log(f'Unsupported video type: {video_type}', xbmc.LOGWARNING)
                return
            
            self._log(f'Watching: {video_type} - {data.get("title")}')
            
            # Check if player is still playing
            if not xbmc.Player().isPlayingVideo():
                self._log('Player stopped before scrobbler could start')
                return
            
            # Wait for possible silent seek (caused by resuming)
            xbmc.sleep(1000)
            
            try:
                # Get playback info
                self.is_pvr = xbmc.getCondVisibility('Pvr.IsPlayingTv') or xbmc.Player().getPlayingFile().startswith('pvr://')
                
                if self.is_pvr:
                    # PVR playback
                    self.watched_time = self._pvr_elapsed_time()
                    self.video_duration = int(self._pvr_duration())
                else:
                    # Normal playback
                    self.watched_time = xbmc.Player().getTime()
                    self.video_duration = xbmc.Player().getTotalTime()
                
            except Exception as e:
                self._log(f'Error getting playback time: {str(e)}', xbmc.LOGERROR)
                self.current_video = None
                return
            
            # Set default duration if none available
            if self.video_duration == 0:
                if video_type == 'movie':
                    self.video_duration = 90 * 60  # 90 minutes
                elif video_type == 'episode':
                    self.video_duration = 30 * 60  # 30 minutes
                else:
                    self.video_duration = 1
            
            # Build media info for services
            self.current_media_info = self._build_media_info(data)
            
            if not self.current_media_info:
                self._log('Failed to build media info', xbmc.LOGERROR)
                return
            
            # Check for multi-part episodes
            self.is_multi_part_episode = data.get('multi_episode_count', 0) > 1
            if self.is_multi_part_episode:
                self.current_mp_episode = 0
                self._log(f'Multi-part episode detected: {data["multi_episode_count"]} parts')
            
            # Set playing state
            self.is_playing = True
            self.is_paused = False
            
            # Update local database immediately
            self._update_database_progress()
            
            # Scrobble start to services (in background thread)
            self._scrobble_threaded('start', 0)
            
    def playback_resumed(self):
        """Called when playback resumes from pause."""
        with self._lock:
            if not self.is_playing or self.is_pvr:
                return
            
            self._log('playback_resumed')
            
            if self.is_paused:
                pause_duration = time.time() - self.paused_at
                self._log(f'Resumed after {pause_duration:.1f} seconds')
                
                self.paused_at = 0
                self.is_paused = False
                
                # Scrobble resume (use start)
                current_progress = self._calculate_watched_percent()
                self._scrobble_threaded('start', current_progress)
    
    def playback_paused(self):
        """Called when playback is paused."""
        with self._lock:
            if not self.is_playing or self.is_pvr:
                return
            
            self._log(f'playback_paused at {self.watched_time:.1f}s')
            
            self.is_paused = True
            self.paused_at = time.time()
            
            # Scrobble pause to services
            current_progress = self._calculate_watched_percent()
            self._scrobble_threaded('pause', current_progress)
    
    def playback_seek(self):
        """Called when user seeks in video."""
        with self._lock:
            if not self.is_playing:
                return
            
            self._log('playback_seek')
            
            # Update watched time
            try:
                if self.is_pvr:
                    self.watched_time = self._pvr_elapsed_time()
                else:
                    self.watched_time = xbmc.Player().getTime()
            except Exception as e:
                self._log(f'Error getting time after seek: {str(e)}', xbmc.LOGWARNING)
            
            # Check for transitions (multi-part episodes, PVR channel changes)
            self._transition_check(is_seek=True)
    
    def playback_stopped(self):
        """Called when playback is stopped by user."""
        with self._lock:
            if not self.is_playing:
                return
            
            self._log('playback_stopped')
            
            # Same as playback_ended
            self._handle_playback_end()
    
    def playback_ended(self):
        """Called when playback ends naturally."""
        with self._lock:
            if not self.is_playing:
                return
            
            self._log('playback_ended')
            
            # Add to rate queue (not PVR)
            if not self.is_pvr and self.current_media_info:
                self.videos_to_rate.append(self.current_media_info)
            
            self._handle_playback_end()
    
    # ============================================================================
    # PROGRESS TRACKING
    # ============================================================================
    
    def update_progress(self):
        """
        Update current progress.
        Called periodically by the monitor.
        """
        with self._lock:
            if not self.is_playing:
                return
            
            # CRITICAL FIX: Don't update database when paused
            if self.is_paused:
                return
            
            try:
                # Update watched time
                if self.is_pvr:
                    self.watched_time = self._pvr_elapsed_time()
                    self.video_duration = int(self._pvr_duration())
                elif xbmc.Player().isPlayingVideo():
                    self.watched_time = xbmc.Player().getTime()
                else:
                    return
                
                # Update database
                self._update_database_progress()
                
                # Check for transitions (every 60 seconds)
                if time.time() > (self.last_mp_check + 60):
                    self._transition_check()
                
            except Exception as e:
                self._log(f'Error updating progress: {str(e)}', xbmc.LOGWARNING)
    
    def _transition_check(self, is_seek=False):
        """
        Check for transitions (multi-part episodes, PVR changes).
        
        Args:
            is_seek: Whether this was triggered by a seek
        """
        if not self.is_playing or not xbmc.Player().isPlayingVideo():
            return
        
        self.last_mp_check = time.time()
        watched_percent = self._calculate_watched_percent()
        
        # Multi-part episode handling
        if self.is_multi_part_episode and 'multi_episode_count' in self.current_video:
            episode_index = self._current_episode(
                watched_percent,
                self.current_video['multi_episode_count']
            )
            
            if self.current_mp_episode != episode_index:
                self._log(f'Multi-part episode transition: part {self.current_mp_episode} -> {episode_index}')
                
                # Scrobble stop for previous part
                self._scrobble_threaded('stop', watched_percent)
                
                # Update to new part
                self.current_mp_episode = episode_index
                
                # Update media info for new part
                if 'multi_episode_data' in self.current_video:
                    # This would need additional implementation for getting episode details
                    pass
                
                # Scrobble start for new part
                self._scrobble_threaded('start', 0)
        
        # PVR channel change handling
        elif self.is_pvr:
            # Check if playing item changed
            try:
                current_item = self._get_current_pvr_item()
                if current_item and current_item != self.current_video:
                    self._log('PVR item changed')
                    
                    # Stop scrobbling old item
                    self._scrobble_threaded('stop', watched_percent)
                    
                    # Start new item
                    self.current_video = current_item
                    self.current_media_info = self._build_media_info(current_item)
                    
                    if self.current_media_info:
                        self._scrobble_threaded('start', 0)
            except Exception as e:
                self._log(f'Error checking PVR transition: {str(e)}', xbmc.LOGWARNING)
        
        # Regular seek handling
        elif is_seek:
            current_progress = self._calculate_watched_percent()
            self._scrobble_threaded('start', current_progress)
    
    def _current_episode(self, watched_percent, episode_count):
        """
        Calculate current episode in multi-part file.
        
        Args:
            watched_percent: Current watch percentage
            episode_count: Number of episodes in file
            
        Returns:
            int: Current episode index (0-based)
        """
        split = 100.0 / episode_count
        
        for i in range(episode_count - 1, 0, -1):
            if watched_percent >= (i * split):
                return i
        
        return 0
    
    def _calculate_watched_percent(self):
        """
        Calculate percentage watched.
        
        Returns:
            float: Percentage (0-100)
        """
        # Floor the duration for consistency
        floored_duration = math.floor(self.video_duration)
        
        if floored_duration != 0:
            return (self.watched_time / floored_duration) * 100
        else:
            return 0
    
    # ============================================================================
    # SCROBBLING
    # ============================================================================
    
    def _scrobble_threaded(self, action, progress):
        """
        Scrobble in a background thread (non-blocking).
        
        Args:
            action: 'start', 'pause', or 'stop'
            progress: Progress percentage
        """
        def scrobble_worker():
            try:
                self._scrobble(action, progress)
            except Exception as e:
                self._log(f'Scrobble thread error: {str(e)}', xbmc.LOGERROR)
        
        thread = Thread(target=scrobble_worker, name=f'Scrobble-{action}')
        thread.daemon = True
        thread.start()
    
    def _scrobble(self, action, progress):
        """
        Send scrobble to all authenticated services.
        
        Args:
            action: 'start', 'pause', or 'stop'
            progress: Progress percentage
        """
        if not self.current_media_info:
            return
        
        self._log(f'Scrobble {action}: {progress:.1f}%')
        
        # Scrobble to all authenticated services
        try:
            results = self.sync_manager.scrobble_all(action, self.current_media_info, progress)
            
            # Log results
            for service_name, result in results.items():
                if result:
                    self._log(f'{service_name} scrobble {action} successful')
                else:
                    self._log(f'{service_name} scrobble {action} failed', xbmc.LOGWARNING)
        
        except Exception as e:
            self._log(f'Error scrobbling to services: {str(e)}', xbmc.LOGERROR)
    
    # ============================================================================
    # DATABASE MANAGEMENT
    # ============================================================================
    
    def _update_database_progress(self):
        """Update local database with current progress."""
        if not self.current_video or not self.current_media_info:
            return
        
        try:
            progress = self._calculate_watched_percent()
            
            # Build database update
            update_data = {
                'service_ids': self.current_media_info.get('ids', {}),
                'media_type': self.current_media_info.get('type'),
                'progress': int(progress),
                'resume_time': int(self.watched_time),
                'duration': int(self.video_duration),
                'title': self.current_video.get('title')
            }
            
            # Add season/episode for TV shows
            if self.current_media_info['type'] == 'episode':
                update_data['season'] = self.current_media_info.get('season')
                update_data['episode'] = self.current_media_info.get('episode')
            
            # Update database
            self.db.update_progress(**update_data)
            
            # Mark as completed if watched enough
            if progress >= 80:
                if self.current_media_info['type'] == 'episode':
                    self.db.mark_completed(
                        service_ids=self.current_media_info.get('ids', {}),
                        season=self.current_media_info.get('season'),
                        episode=self.current_media_info.get('episode')
                    )
                else:
                    self.db.mark_completed(
                        service_ids=self.current_media_info.get('ids', {})
                    )
        
        except Exception as e:
            self._log(f'Error updating database: {str(e)}', xbmc.LOGERROR)
    
    # ============================================================================
    # PLAYBACK END HANDLING
    # ============================================================================
    
    def _handle_playback_end(self):
        """Handle end of playback (stopped or ended)."""
        if self.watched_time == 0:
            self._log('Playback ended but no watch time recorded')
            self._reset_state()
            return
        
        # Calculate final progress
        final_progress = self._calculate_watched_percent()
        
        # Update database one final time
        self._update_database_progress()
        
        # Scrobble stop
        self._scrobble_threaded('stop', final_progress)
        
        self._log(f'Playback ended at {final_progress:.1f}%')
        
        # Reset state
        self._reset_state()
    
    def _reset_state(self):
        """Reset scrobbler state."""
        self.is_playing = False
        self.is_paused = False
        self.stop_scrobbler = False
        self.current_video = None
        self.current_media_info = None
        self.video_duration = 1
        self.watched_time = 0
        self.paused_at = 0
        self.is_multi_part_episode = False
        self.last_mp_check = 0
        self.current_mp_episode = 0
        self.is_pvr = False
    
    # ============================================================================
    # MEDIA INFO BUILDING
    # ============================================================================
    
    def _build_media_info(self, video_data):
        """
        Build media info dict for services.
        
        Args:
            video_data: Video data from player
            
        Returns:
            dict: Media info or None
        """
        try:
            media_type = video_data.get('type', 'unknown')
            
            if media_type not in ['movie', 'episode']:
                return None
            
            media_info = {
                'type': media_type,
                'ids': video_data.get('ids', {}),
                'title': video_data.get('title'),
                'duration': int(self.video_duration)
            }
            
            # Movie-specific fields
            if media_type == 'movie':
                media_info['year'] = video_data.get('year')
            
            # Episode-specific fields
            elif media_type == 'episode':
                media_info['season'] = video_data.get('season')
                media_info['episode'] = video_data.get('episode')
                
                # Show info
                if video_data.get('show_title'):
                    media_info['show'] = {
                        'title': video_data['show_title'],
                        'year': video_data.get('show_year'),
                        'ids': video_data.get('show_ids', {})
                    }
            
            return media_info
        
        except Exception as e:
            self._log(f'Error building media info: {str(e)}', xbmc.LOGERROR)
            return None
    
    # ============================================================================
    # PVR HELPERS
    # ============================================================================
    
    def _pvr_elapsed_time(self):
        """Get elapsed time for PVR playback."""
        try:
            time_str = xbmc.getInfoLabel('PVR.EpgEventElapsedTime(hh:mm:ss)')
            return self._time_to_seconds(time_str)
        except Exception:
            return 0
    
    def _pvr_duration(self):
        """Get duration for PVR playback."""
        try:
            time_str = xbmc.getInfoLabel('PVR.EpgEventDuration(hh:mm:ss)')
            return self._time_to_seconds(time_str)
        except Exception:
            return 1
    
    def _time_to_seconds(self, time_str):
        """
        Convert hh:mm:ss to seconds.
        
        Args:
            time_str: Time string in hh:mm:ss format
            
        Returns:
            int: Seconds
        """
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + int(s)
            return 0
        except Exception:
            return 0
    
    def _get_current_pvr_item(self):
        """
        Get current PVR item info.
        
        Returns:
            dict: Current PVR item or None
        """
        # This would need implementation to extract current PVR info
        # For now, return None
        return None
    
    # ============================================================================
    # LOGGING
    # ============================================================================
    
    def _log(self, message, level=xbmc.LOGINFO):
        """
        Log a message.
        
        Args:
            message: Message to log
            level: Log level
        """
        xbmc.log(f'[LittleRabite Scrobbler] {message}', level)
