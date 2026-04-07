# -*- coding: utf-8 -*-
"""
Little Rabite - Simkl Service Implementation
Handles authentication (PIN flow), syncing, and scrobbling with Simkl.com

ARCHITECTURE:
- Inherits from SyncService (resources/lib/services/base.py)
- Uses PIN-based OAuth flow
- REST API at https://api.simkl.com
- Episode-based progress tracking
- CRITICAL: Requests multiple IDs (simkl, mal, tvdb, imdb) for database bridging
"""

import requests
import time
import json
from resources.lib.services.base import SyncService, is_authorized

try:
    import xbmc
    import xbmcgui
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class SimklService(SyncService):
    """
    Simkl.com service implementation.
    
    Authentication: PIN-based OAuth flow
    Sync: Episode-based progress (not time-based)
    Bridge: Uses MAL, TVDB, IMDB IDs to link with Trakt/AniList items
    """
    
    BASE_URL = "https://api.simkl.com"
    # Little Rabite Client ID
    CLIENT_ID = "63bb65010c3bcc25a9947aaebba0e7048508186c15b39bec87001d62e1739a58"
    
    def __init__(self, database):
        """
        Initialize Simkl service.
        
        Args:
            database: Database instance
        """
        super().__init__(database)
        self.service_name = 'simkl'
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'simkl-api-key': self.CLIENT_ID
        })
    
    def _get_headers(self):
        """
        Get request headers with authorization.
        
        Returns:
            dict: Request headers
        """
        headers = {
            'Content-Type': 'application/json',
            'simkl-api-key': self.CLIENT_ID
        }
        
        auth_data = self.db.get_auth(self.service_name)
        if auth_data and auth_data.get('token'):
            headers['Authorization'] = f"Bearer {auth_data['token']}"
        
        return headers
    
    def _make_request(self, method, endpoint, data=None, params=None):
        """
        Make API request with error handling.
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint
            data: Optional JSON data
            params: Optional query parameters
            
        Returns:
            dict: Response data or None on failure
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params,
                timeout=30
            )
            
            # Rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self._log(f'Rate limited, waiting {retry_after} seconds', 
                         xbmc.LOGWARNING if KODI_ENV else None)
                time.sleep(retry_after)
                return None
            
            # Authentication errors
            if response.status_code == 401:
                self._log('Authentication failed - token may be invalid', 
                         xbmc.LOGWARNING if KODI_ENV else None)
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self._log(f'Request failed: {str(e)}', 
                     xbmc.LOGERROR if KODI_ENV else None)
            return None
    
    # ============================================================================
    # AUTHENTICATION (PIN FLOW)
    # ============================================================================
    
    def authenticate(self):
        """
        Initiate PIN-based OAuth authentication flow.
        
        Flow:
        1. GET /oauth/pin -> get user_code and verification_url
        2. Show dialog to user with code and URL
        3. Poll /oauth/pin/{user_code} until authorized
        4. Store access_token
        
        Returns:
            bool: True if authentication successful
        """
        if not KODI_ENV:
            self._log('Authentication requires Kodi environment', None)
            return False
        
        dialog = xbmcgui.Dialog()
        progress_dialog = xbmcgui.DialogProgress()
        
        # Step 1: Request PIN
        params = {'client_id': self.CLIENT_ID}
        
        pin_data = self._make_request('GET', '/oauth/pin', params=params)
        
        if not pin_data or 'user_code' not in pin_data:
            dialog.ok('Simkl Authentication', 'Failed to generate PIN. Please try again.')
            return False
        
        user_code = pin_data['user_code']
        verification_url = pin_data.get('verification_url', 'https://simkl.com/pin')
        expires_in = pin_data.get('expires_in', 300)  # Default 5 minutes
        interval = pin_data.get('interval', 5)  # Poll every 5 seconds
        
        # Step 2: Show dialog to user
        message = (
            f'Visit: {verification_url}\n'
            f'Enter code: {user_code}\n\n'
            f'Waiting for authorization...'
        )
        
        progress_dialog.create('Simkl Authentication', message)
        
        # Step 3: Poll for authorization
        max_attempts = int(expires_in / interval)
        
        for attempt in range(max_attempts):
            if progress_dialog.iscanceled():
                progress_dialog.close()
                dialog.ok('Authentication Cancelled', 'You cancelled the authentication.')
                return False
            
            # Update progress
            progress_percent = int((attempt / max_attempts) * 100)
            time_remaining = expires_in - (attempt * interval)
            progress_dialog.update(
                progress_percent,
                f'{message}\n\nCode expires in {time_remaining} seconds'
            )
            
            # Wait before polling
            time.sleep(interval)
            
            # Poll for result
            poll_data = self._make_request('GET', f'/oauth/pin/{user_code}', params=params)
            
            if poll_data and poll_data.get('result') == 'OK':
                # Success! Got access token
                access_token = poll_data.get('access_token')
                
                if not access_token:
                    progress_dialog.close()
                    dialog.ok('Authentication Failed', 'No access token received.')
                    return False
                
                # Get user settings to verify and get username
                old_auth = self.db.get_auth(self.service_name)
                self.db.store_auth(self.service_name, token=access_token)
                
                user_settings = self._make_request('GET', '/users/settings')
                
                if user_settings and user_settings.get('user'):
                    user_data = user_settings['user']
                    username = user_data.get('name', 'Unknown')
                    
                    # Store complete auth data with user info
                    user_info = {
                        'username': username,
                        'user_id': user_data.get('id')
                    }
                    self.db.store_auth(
                        self.service_name,
                        token=access_token,
                        user_data=user_info
                    )
                    
                    progress_dialog.close()
                    dialog.ok(
                        'Authentication Successful',
                        f'Logged in as: {username}'
                    )
                    
                    self._log(f'Successfully authenticated as {username}')
                    return True
                else:
                    # Failed to get user settings - restore old auth
                    if old_auth:
                        self.db.store_auth(
                            self.service_name,
                            token=old_auth.get('token'),
                            refresh_token=old_auth.get('refresh_token'),
                            expires_at=old_auth.get('expires_at'),
                            user_data=old_auth.get('user_data')
                        )
                    else:
                        self.db.delete_auth(self.service_name)
                    
                    progress_dialog.close()
                    dialog.ok('Authentication Failed', 'Could not verify user.')
                    return False
        
        # Timeout - code expired
        progress_dialog.close()
        dialog.ok(
            'Authentication Timeout',
            'The code expired. Please try again.'
        )
        return False
    
    def refresh_token(self):
        """
        Simkl tokens don't expire - no refresh needed.
        
        Returns:
            bool: Always True (no refresh required)
        """
        return True
    
    # ============================================================================
    # SYNC METHODS
    # ============================================================================
    
    @is_authorized
    def sync_pull(self, media_type=None, limit=None):
        """
        Pull watch history from Simkl and update local database.
        
        CRITICAL: Requests multiple IDs (simkl, mal, tvdb, imdb) for bridging.
        
        Fetches:
        - /sync/all-items/shows/watching (TV Shows)
        - /sync/all-items/shows/completed
        - /sync/all-items/anime/watching (Anime)
        - /sync/all-items/anime/completed
        
        Args:
            media_type: Ignored (Simkl supports both)
            limit: Optional limit on items to sync
            
        Returns:
            dict: {'success': bool, 'synced': int, 'errors': list}
        """
        self._log('Starting Simkl sync pull...')
        
        # Fetch both shows and anime
        content_types = ['shows', 'anime']
        statuses_to_sync = ['watching', 'completed']
        synced_count = 0
        errors = []
        
        for content_type in content_types:
            for status in statuses_to_sync:
                try:
                    items = self.fetch_all_items(content_type, status)
                    
                    if not items:
                        self._log(f'No items found for {content_type}/{status}')
                        continue
                    
                    for item in items:
                        try:
                            self._process_sync_item(item, status)
                            synced_count += 1
                        except Exception as e:
                            error_msg = f'Failed to process item: {str(e)}'
                            self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                            errors.append(error_msg)
                    
                    self._log(f'Synced {len(items)} items from {content_type}/{status} list')
                    
                except Exception as e:
                    error_msg = f'Failed to fetch {content_type}/{status} list: {str(e)}'
                    self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                    errors.append(error_msg)
        
        self._log(f'Simkl sync complete: {synced_count} items synced, {len(errors)} errors')
        
        return {
            'success': len(errors) == 0,
            'synced': synced_count,
            'errors': errors
        }
    
    def fetch_all_items(self, content_type, status):
        """
        Fetch all items for a specific content type and status.
        
        Public method for catalog browsing.
        
        Args:
            content_type: Content type ('shows', 'anime', or 'movies')
            status: Status (watching, completed, plantowatch, hold, dropped)
            
        Returns:
            list: List of items
        """
        params = {'extended': 'full'}
        
        data = self._make_request('GET', f'/sync/all-items/{content_type}/{status}', params=params)
        
        if not data:
            return []
        
        # The response key matches the content type
        # For 'shows' -> data['shows']
        # For 'anime' -> data['anime']
        # For 'movies' -> data['movies']
        return data.get(content_type, [])
    
    def _process_sync_item(self, item, status):
        """
        Process a single show/anime item and update database.
        
        Args:
            item: Simkl item data
            status: List status
        """
        show = item.get('show', {})
        
        # Extract IDs - CRITICAL for bridging
        ids = show.get('ids', {})
        simkl_id = ids.get('simkl')
        mal_id = ids.get('mal')
        tvdb_id = ids.get('tvdb')
        imdb_id = ids.get('imdb')
        anilist_id = ids.get('anilist')
        kitsu_id = ids.get('kitsu')
        
        if not simkl_id:
            self._log('Item missing Simkl ID, skipping', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return
        
        # Build service IDs dict (multiple IDs for bridging)
        service_ids = {'simkl': simkl_id}
        if mal_id:
            service_ids['mal'] = mal_id
        if tvdb_id:
            service_ids['tvdb'] = tvdb_id
        if imdb_id:
            service_ids['imdb'] = imdb_id
        if anilist_id:
            service_ids['anilist'] = anilist_id
        if kitsu_id:
            service_ids['kitsu'] = kitsu_id
        
        # Extract metadata
        title = show.get('title', 'Unknown Title')
        year = show.get('year')
        
        # Poster (Simkl uses a CDN)
        poster_path = show.get('poster')
        poster = f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg' if poster_path else None
        
        # Simkl doesn't provide fanart or plot in sync responses
        fanart = poster  # Use poster as fallback
        plot = None
        
        # Progress tracking
        watched_episodes = item.get('watched_episodes_count', 0)
        total_episodes = item.get('total_episodes_count', 0)
        
        # Debug logging
        self._log(f'Processing: {title} - Watched: {watched_episodes}/{total_episodes}, Status: {status}', 
                 xbmc.LOGINFO if KODI_ENV else None)
        
        # Calculate progress percentage
        if total_episodes > 0:
            progress_percent = int((watched_episodes / total_episodes) * 100)
        else:
            progress_percent = 50 if watched_episodes > 0 else 0
        
        # Resume time (Simkl doesn't store timestamps)
        resume_time = 0
        
        # Check if it's a movie (1 episode)
        is_movie = total_episodes == 1
        
        if is_movie:
            # Handle as movie
            media_type = 'movie'
            
            self.db.update_progress(
                service_ids=service_ids,
                media_type=media_type,
                progress=progress_percent,
                resume_time=resume_time,
                duration=None,  # Simkl doesn't provide duration
                title=title,
                year=year,
                poster=poster,
                fanart=fanart,
                plot=plot
            )
        else:
            # Handle as TV show episodes
            if status == 'completed' or (total_episodes > 0 and watched_episodes >= total_episodes):
                # Show is completed - store last episode as watched
                if total_episodes > 0:
                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='episode',
                        progress=100,
                        resume_time=0,
                        duration=None,
                        title=title,
                        year=year,
                        season=1,  # Simkl doesn't use seasons by default
                        episode=total_episodes,
                        poster=poster,
                        fanart=fanart,
                        plot=plot
                    )
            else:
                # In progress OR not started yet - store next episode to watch
                # If watched_episodes = 0, next episode is 1 (first episode)
                # If watched_episodes = 5, next episode is 6
                next_episode = watched_episodes + 1
                
                # Only store if next episode exists or total is unknown
                if total_episodes == 0 or next_episode <= total_episodes:
                    # For Continue Watching, we need progress > 0
                    # If they haven't started (watched = 0), set progress to 1% so it shows up
                    display_progress = 1 if watched_episodes == 0 else 0
                    
                    self._log(f'Storing episode S01E{next_episode:02d} with {display_progress}% progress', 
                             xbmc.LOGINFO if KODI_ENV else None)
                    
                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='episode',
                        progress=display_progress,  # 1% for unwatched, 0% for in-progress
                        resume_time=0,
                        duration=None,
                        title=title,
                        year=year,
                        season=1,
                        episode=next_episode,
                        poster=poster,
                        fanart=fanart,
                        plot=plot
                    )
    
    @is_authorized
    def sync_push(self):
        """
        Push local watch history to Simkl (process sync queue).
        
        Returns:
            dict: {'success': bool, 'pushed': int, 'errors': list}
        """
        self._log('Starting Simkl sync push...')
        
        # Get queued items for Simkl
        queue = self.db.get_sync_queue(self.service_name)
        
        if not queue:
            self._log('No items in sync queue')
            return {'success': True, 'pushed': 0, 'errors': []}
        
        pushed_count = 0
        errors = []
        
        for item in queue:
            try:
                action = item.get('action')
                data = json.loads(item.get('data', '{}'))
                
                if action == 'scrobble_stop':
                    # Mark episode as watched on Simkl
                    success = self._mark_episode_watched(data)
                    
                    if success:
                        self.db.remove_from_sync_queue(item['id'])
                        pushed_count += 1
                    else:
                        errors.append(f'Failed to push item {item["id"]}')
                else:
                    # Unknown action - remove from queue
                    self.db.remove_from_sync_queue(item['id'])
                    
            except Exception as e:
                error_msg = f'Error processing queue item {item["id"]}: {str(e)}'
                self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                errors.append(error_msg)
        
        self._log(f'Simkl sync push complete: {pushed_count} items pushed, {len(errors)} errors')
        
        return {
            'success': len(errors) == 0,
            'pushed': pushed_count,
            'errors': errors
        }
    
    def _mark_episode_watched(self, data):
        """
        Mark episode as watched on Simkl using /sync/history.
        
        Args:
            data: Dict with media_info and progress
            
        Returns:
            bool: True if successful
        """
        media_info = data.get('media_info', {})
        progress = data.get('progress', 0)
        
        # Only mark as watched if progress > 80%
        if progress < 80:
            self._log(f'Progress {progress}% < 80%, not marking as watched', 
                     xbmc.LOGINFO if KODI_ENV else None)
            return True  # Not an error, just skip
        
        # Get IDs
        ids = media_info.get('ids', {})
        
        # Simkl prefers MAL ID
        mal_id = ids.get('mal')
        simkl_id = ids.get('simkl')
        
        if not mal_id and not simkl_id:
            self._log('No MAL or Simkl ID found, cannot mark as watched', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return False
        
        # Get episode/season info
        season = media_info.get('season', 1)
        episode = media_info.get('episode')
        
        if episode is None:
            self._log('No episode number found, cannot mark as watched', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return False
        
        # Build sync/history payload
        watched_at = time.strftime('%Y-%m-%d %H:%M:%S')
        
        payload = {
            "shows": [{
                "ids": {},
                "seasons": [{
                    "number": season,
                    "episodes": [{
                        "number": episode
                    }]
                }]
            }]
        }
        
        # Add ID (prefer MAL, fallback to Simkl)
        if mal_id:
            payload["shows"][0]["ids"]["mal"] = mal_id
        elif simkl_id:
            payload["shows"][0]["ids"]["simkl"] = simkl_id
        
        # Add title if available (helps with matching)
        title = media_info.get('title')
        if title:
            payload["shows"][0]["title"] = title
        
        result = self._make_request('POST', '/sync/history', data=payload)
        
        if result:
            # Check for errors in response
            not_found = result.get('not_found', {})
            if not_found.get('shows') or not_found.get('movies'):
                self._log('Simkl could not find the show', 
                         xbmc.LOGWARNING if KODI_ENV else None)
                return False
            
            self._log(f'Marked as watched: S{season}E{episode}')
            return True
        else:
            return False
    
    # ============================================================================
    # SCROBBLING METHODS
    # ============================================================================
    
    @is_authorized
    def scrobble_start(self, media_info, progress=0):
        """
        Send 'start watching' scrobble (NO-OP for Simkl).
        
        Simkl is episode-based, not time-based.
        We log the event but don't make API calls.
        
        Args:
            media_info: Media information dict
            progress: Playback progress (0-100)
            
        Returns:
            dict: Status response
        """
        title = media_info.get('title', 'Unknown')
        episode = media_info.get('episode')
        
        if episode:
            self._log(f'Scrobble start: {title} S{media_info.get("season", 1)}E{episode} ({progress}%)')
        else:
            self._log(f'Scrobble start: {title} ({progress}%)')
        
        return {'status': 'logged', 'message': 'Simkl does not support real-time scrobbling'}
    
    @is_authorized
    def scrobble_pause(self, media_info, progress):
        """
        Send 'pause' scrobble (NO-OP for Simkl).
        
        Args:
            media_info: Media information dict
            progress: Playback progress (0-100)
            
        Returns:
            dict: Status response
        """
        title = media_info.get('title', 'Unknown')
        self._log(f'Scrobble pause: {title} ({progress}%)')
        
        return {'status': 'logged', 'message': 'Simkl does not support real-time scrobbling'}
    
    @is_authorized
    def scrobble_stop(self, media_info, progress):
        """
        Send 'stop watching' scrobble.
        
        If progress > 80%, mark episode as watched on Simkl.
        
        Args:
            media_info: Media information dict
            progress: Final playback progress (0-100)
            
        Returns:
            dict: Response from service or None
        """
        title = media_info.get('title', 'Unknown')
        episode = media_info.get('episode')
        
        if episode:
            self._log(f'Scrobble stop: {title} S{media_info.get("season", 1)}E{episode} ({progress}%)')
        else:
            self._log(f'Scrobble stop: {title} ({progress}%)')
        
        # Only update if progress > 80%
        if progress < 80:
            self._log(f'Progress {progress}% < 80%, not updating Simkl')
            return {'status': 'skipped', 'message': 'Progress below 80%'}
        
        # Queue for sync push (will be processed in background)
        self._queue_for_sync('scrobble_stop', {
            'media_info': media_info,
            'progress': progress
        })
        
        return {'status': 'queued', 'message': 'Queued for sync'}
