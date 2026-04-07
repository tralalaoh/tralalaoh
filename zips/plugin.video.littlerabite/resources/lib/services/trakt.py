# -*- coding: utf-8 -*-
"""
Little Rabite - Trakt Service Implementation
Handles authentication, syncing (watch history + list statuses), and scrobbling with Trakt.tv

SYNCED LIST STATUSES:
  'watchlist'  <- /sync/watchlist  (movies + shows the user plans to watch)
  'watching'   <- /sync/playback   (in-progress / paused items)
  'watched'    <- /sync/watched    (completed history)
  'dropped'    <- /users/hidden/progress_watched  (shows hidden from progress = dropped)
  'onhold'     <- Not available on Trakt (Trakt has no on-hold list)

Trakt API notes:
  - /sync/watchlist       GET  Returns movies/shows added to watchlist
  - /sync/watched/movies  GET  Returns fully watched movies
  - /sync/watched/shows   GET  Returns shows with watched episodes
  - /sync/playback        GET  Returns in-progress items (paused mid-watch)
  - /users/hidden/progress_watched  GET  Returns shows hidden from progress (dropped equivalent)
"""

import requests
import time
import json
from resources.lib.services.base import SyncService, is_authorized

try:
    import xbmc
    import xbmcgui
    import xbmcaddon
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class TraktService(SyncService):
    """Trakt.tv service implementation."""

    CLIENT_ID = "d4161a7a106424551add171e5470112e4afdaf2438e6ef2fe0548edc75924868"
    CLIENT_SECRET = "b5fcd7cb5d9bb963784d11bbf8535bc0d25d46225016191eb48e50792d2155c0"

    BASE_URL = "https://api.trakt.tv"
    API_VERSION = "2"

    def __init__(self, database):
        super().__init__(database)
        self.service_name = 'trakt'
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'trakt-api-version': self.API_VERSION,
            'trakt-api-key': self.CLIENT_ID
        })
        return session

    # ============================================================================
    # FIX: Override token_needs_refresh to handle missing expires_at
    # ============================================================================

    def token_needs_refresh(self):
        """
        If expires_at is None (token stored without expiry), assume valid.
        Base class returns True when expires_at is None, causing refresh loops.
        """
        auth = self.db.get_auth(self.service_name)
        if not auth:
            return True
        if not auth.get('expires_at'):
            return False
        return int(time.time()) >= (auth['expires_at'] - 300)

    def _get_headers(self, auth=False):
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': self.API_VERSION,
            'trakt-api-key': self.CLIENT_ID
        }
        if auth:
            auth_data = self.db.get_auth(self.service_name)
            if auth_data and auth_data.get('token'):
                headers['Authorization'] = f"Bearer {auth_data['token']}"
        return headers

    def _make_request(self, method, endpoint, data=None, auth=True, retry=True):
        """Make API request with error handling and retries. Returns Response or None."""
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers(auth=auth)
        max_retries = 3 if retry else 1

        for attempt in range(max_retries):
            try:
                response = requests.request(
                    method=method, url=url, headers=headers,
                    json=data, timeout=30
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    self._log(f'Rate limited, waiting {retry_after}s', xbmc.LOGWARNING if KODI_ENV else None)
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue

                if response.status_code in [500, 502, 503, 504]:
                    self._log(f'Trakt server error {response.status_code}', xbmc.LOGWARNING if KODI_ENV else None)
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None

                if response.status_code == 401:
                    self._log('Authentication failed - token may be expired', xbmc.LOGWARNING if KODI_ENV else None)
                    return None

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout:
                self._log(f'Timeout (attempt {attempt + 1}/{max_retries})', xbmc.LOGWARNING if KODI_ENV else None)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError:
                self._log(f'Connection error (attempt {attempt + 1}/{max_retries})', xbmc.LOGWARNING if KODI_ENV else None)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                self._log(f'Request error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
                return None

        return None

    # ============================================================================
    # AUTHENTICATION
    # ============================================================================

    def authenticate(self):
        """Initiate OAuth device code flow."""
        try:
            self._log('Starting device authentication...')

            response = self._make_request(
                'POST', '/oauth/device/code',
                data={'client_id': self.CLIENT_ID}, auth=False
            )

            if not response:
                self._log('Failed to get device code', xbmc.LOGERROR if KODI_ENV else None)
                return False

            code_data = response.json()
            device_code = code_data['device_code']
            user_code = code_data['user_code']
            verification_url = code_data['verification_url']
            expires_in = code_data['expires_in']
            interval = code_data.get('interval', 5)

            if KODI_ENV:
                dialog = self._show_auth_dialog(user_code, verification_url, expires_in)
            else:
                print(f'\nGo to {verification_url} and enter code: {user_code}')

            poll_start = time.time()
            while time.time() - poll_start < expires_in:
                if KODI_ENV and hasattr(dialog, 'is_cancelled') and dialog.is_cancelled():
                    return False

                time.sleep(interval)

                poll_response = self._make_request(
                    'POST', '/oauth/device/token',
                    data={'code': device_code, 'client_id': self.CLIENT_ID, 'client_secret': self.CLIENT_SECRET},
                    auth=False, retry=False
                )

                if poll_response and poll_response.status_code == 200:
                    if KODI_ENV:
                        dialog.close()
                    return self._save_token(poll_response.json())
                elif poll_response and poll_response.status_code == 410:
                    self._log('Device code expired', xbmc.LOGWARNING if KODI_ENV else None)
                    break

            if KODI_ENV:
                dialog.close()
            return False

        except Exception as e:
            self._log(f'Authentication error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    def _save_token(self, token_data):
        try:
            access_token = token_data['access_token']
            refresh_token = token_data.get('refresh_token')
            expires_in = token_data.get('expires_in', 7776000)
            expires_at = int(time.time()) + expires_in

            self.db.store_auth(
                service=self.service_name,
                token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )

            user_response = self._make_request('GET', '/users/settings', auth=True)
            if not user_response:
                return False

            user_data = user_response.json()['user']

            self.db.store_auth(
                service=self.service_name,
                token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                user_data=user_data
            )

            self._log(f'Authentication successful for user: {user_data["username"]}')

            if KODI_ENV:
                xbmcgui.Dialog().notification(
                    'Little Rabite',
                    f'Logged in as: {user_data["username"]}',
                    xbmcgui.NOTIFICATION_INFO, 3000
                )
            return True

        except Exception as e:
            self._log(f'Error saving token: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    def refresh_token(self):
        try:
            auth_data = self.db.get_auth(self.service_name)
            if not auth_data or not auth_data.get('refresh_token'):
                return False

            response = self._make_request(
                'POST', '/oauth/token',
                data={
                    'refresh_token': auth_data['refresh_token'],
                    'client_id': self.CLIENT_ID,
                    'client_secret': self.CLIENT_SECRET,
                    'grant_type': 'refresh_token'
                },
                auth=False
            )

            if not response:
                return False

            return self._save_token(response.json())

        except Exception as e:
            self._log(f'Token refresh error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    def _show_auth_dialog(self, user_code, verification_url, expires_in):
        dialog = xbmcgui.DialogProgress()
        dialog.create(
            'Trakt Authentication',
            f'1. Go to: {verification_url}\n'
            f'2. Enter code: [B]{user_code}[/B]\n'
            f'3. Waiting for authorization...'
        )
        return dialog

    # ============================================================================
    # METADATA
    # ============================================================================

    def _extract_metadata(self, media_data):
        """Extract year and plot from Trakt extended=full response."""
        metadata = {'poster': None, 'fanart': None, 'plot': None, 'year': None}
        if not media_data:
            return metadata
        try:
            metadata['year'] = media_data.get('year')
            overview = media_data.get('overview')
            if overview:
                metadata['plot'] = overview.strip()
        except Exception as e:
            self._log(f'Error extracting metadata: {str(e)}', xbmc.LOGWARNING if KODI_ENV else None)
        return metadata

    def _build_service_ids(self, ids_dict, include_tvdb=False):
        """Build clean service_ids dict from a Trakt ids object."""
        service_ids = {
            'trakt': ids_dict.get('trakt'),
            'tmdb': ids_dict.get('tmdb'),
            'imdb': ids_dict.get('imdb'),
        }
        if include_tvdb:
            service_ids['tvdb'] = ids_dict.get('tvdb')
        return {k: v for k, v in service_ids.items() if v}

    # ============================================================================
    # SYNC PULL - MAIN ENTRY POINT
    # ============================================================================

    @is_authorized
    def sync_pull(self, media_type=None, limit=None):
        """
        Pull ALL list statuses from Trakt and update local database.

        Sync order:
          1. Watchlist      -> list_status = 'watchlist'
          2. Watch history  -> list_status = 'watched'  (movies + shows)
          3. Playback       -> list_status = 'watching' (in-progress, overrides watched)
          4. Dropped        -> list_status = 'dropped'  (hidden from progress)

        Returns:
            dict: {'success': bool, 'synced': int, 'errors': list}
        """
        try:
            self._log('Starting sync pull from Trakt...')
            synced_count = 0
            errors = []

            # Non-fatal activities check
            try:
                activities = self._get_last_activities()
                if activities:
                    self._log('Got last activities - proceeding with full sync')
                else:
                    self._log('Could not get last activities - proceeding anyway', xbmc.LOGWARNING if KODI_ENV else None)
            except Exception as e:
                self._log(f'Activities check failed (non-fatal): {e}', xbmc.LOGWARNING if KODI_ENV else None)

            # STEP 1: Watchlist (plan to watch)
            try:
                count = self._sync_watchlist(media_type)
                synced_count += count
                self._log(f'Synced {count} watchlist items')
            except Exception as e:
                error_msg = f'Watchlist sync error: {str(e)}'
                self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                errors.append(error_msg)

            # STEP 2a: Watched movies
            if media_type is None or media_type == 'movie':
                try:
                    count = self._sync_movies()
                    synced_count += count
                    self._log(f'Synced {count} watched movies')
                except Exception as e:
                    error_msg = f'Movie sync error: {str(e)}'
                    self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                    errors.append(error_msg)

            # STEP 2b: Watched episodes
            if media_type is None or media_type == 'episode':
                try:
                    count = self._sync_episodes()
                    synced_count += count
                    self._log(f'Synced {count} watched episodes')
                except Exception as e:
                    error_msg = f'Episode sync error: {str(e)}'
                    self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                    errors.append(error_msg)

            # STEP 3: In-progress / watching (overwrites watched for paused items)
            try:
                count = self._sync_playback()
                synced_count += count
                self._log(f'Synced {count} in-progress items')
            except Exception as e:
                error_msg = f'Playback sync error: {str(e)}'
                self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                errors.append(error_msg)

            # STEP 4: Dropped (shows hidden from progress tracking)
            if media_type is None or media_type == 'episode':
                try:
                    count = self._sync_dropped()
                    synced_count += count
                    self._log(f'Synced {count} dropped shows')
                except Exception as e:
                    error_msg = f'Dropped sync error: {str(e)}'
                    self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                    errors.append(error_msg)

            self._log(f'Sync pull complete: {synced_count} items, {len(errors)} errors')

            return {
                'success': len(errors) == 0,
                'synced': synced_count,
                'errors': errors
            }

        except Exception as e:
            self._log(f'Sync pull error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return {'success': False, 'synced': 0, 'errors': [str(e)]}

    def _get_last_activities(self):
        response = self._make_request('GET', '/sync/last_activities', auth=True)
        if not response or response.status_code != 200:
            return None
        return response.json()

    # ============================================================================
    # SYNC: WATCHLIST  (plan to watch)
    # ============================================================================

    def _sync_watchlist(self, media_type=None):
        """
        Sync Trakt watchlist -> list_status = 'watchlist'

        Endpoint: GET /sync/watchlist/movies  and  /sync/watchlist/shows
        Extended: ?extended=full  (for title, year, plot)

        Returns: int count
        """
        count = 0

        types_to_sync = []
        if media_type is None or media_type == 'movie':
            types_to_sync.append(('movies', 'movie'))
        if media_type is None or media_type == 'episode':
            types_to_sync.append(('shows', 'episode'))

        for endpoint_type, db_type in types_to_sync:
            try:
                response = self._make_request(
                    'GET', f'/sync/watchlist/{endpoint_type}?extended=full', auth=True
                )

                if not response or response.status_code != 200:
                    self._log(f'Failed to fetch watchlist/{endpoint_type}', xbmc.LOGWARNING if KODI_ENV else None)
                    continue

                items = response.json()

                for item in items:
                    try:
                        # Watchlist items have structure: {listed_at, type, movie/show: {...}}
                        media_data = item.get(endpoint_type[:-1], {})  # 'movies'->'movie', 'shows'->'show'
                        if not media_data:
                            # Try the singular key directly
                            media_data = item.get('movie', item.get('show', {}))

                        media_ids = media_data.get('ids', {})
                        service_ids = self._build_service_ids(
                            media_ids, include_tvdb=(db_type == 'episode')
                        )

                        if not service_ids:
                            continue

                        metadata = self._extract_metadata(media_data)

                        # Use update_progress with progress=0 (not started)
                        self.db.update_progress(
                            service_ids=service_ids,
                            media_type=db_type,
                            progress=0,
                            resume_time=0,
                            title=media_data.get('title'),
                            year=metadata['year'],
                            plot=metadata['plot'],
                            list_status='watchlist'
                        )

                        count += 1

                    except Exception as e:
                        self._log(f'Error processing watchlist item: {e}', xbmc.LOGWARNING if KODI_ENV else None)
                        continue

            except Exception as e:
                self._log(f'Error syncing watchlist/{endpoint_type}: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return count

    # ============================================================================
    # SYNC: WATCHED MOVIES
    # ============================================================================

    def _sync_movies(self):
        """
        Sync completed movies -> list_status = 'watched'
        Endpoint: GET /sync/watched/movies?extended=full
        """
        response = self._make_request('GET', '/sync/watched/movies?extended=full', auth=True)

        if not response or response.status_code != 200:
            self._log(f'Failed to fetch watched movies', xbmc.LOGWARNING if KODI_ENV else None)
            return 0

        movies = response.json()
        count = 0

        for movie in movies:
            try:
                movie_data = movie.get('movie', {})
                service_ids = self._build_service_ids(movie_data.get('ids', {}))

                if not service_ids:
                    continue

                metadata = self._extract_metadata(movie_data)

                self.db.update_progress(
                    service_ids=service_ids,
                    media_type='movie',
                    progress=100,
                    resume_time=0,
                    title=movie_data.get('title'),
                    year=metadata['year'],
                    plot=metadata['plot'],
                    list_status='watched'
                )
                self.db.mark_completed(service_ids=service_ids)
                count += 1

            except Exception as e:
                self._log(f'Error syncing movie: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return count

    # ============================================================================
    # SYNC: WATCHED EPISODES
    # ============================================================================

    def _sync_episodes(self):
        """
        Sync completed episodes -> list_status = 'watched'
        Endpoint: GET /sync/watched/shows?extended=full
        """
        response = self._make_request('GET', '/sync/watched/shows?extended=full', auth=True)

        if not response or response.status_code != 200:
            self._log(f'Failed to fetch watched shows', xbmc.LOGWARNING if KODI_ENV else None)
            return 0

        shows = response.json()
        count = 0

        for show in shows:
            try:
                show_data = show.get('show', {})
                show_ids = show_data.get('ids', {})
                show_metadata = self._extract_metadata(show_data)

                for season in show.get('seasons', []):
                    season_number = season.get('number')
                    for episode in season.get('episodes', []):
                        episode_number = episode.get('number')

                        service_ids = self._build_service_ids(show_ids, include_tvdb=True)
                        if not service_ids:
                            continue

                        self.db.update_progress(
                            service_ids=service_ids,
                            media_type='episode',
                            progress=100,
                            resume_time=0,
                            title=show_data.get('title'),
                            season=season_number,
                            episode=episode_number,
                            year=show_metadata['year'],
                            plot=show_metadata['plot'],
                            list_status='watched'
                        )
                        self.db.mark_completed(
                            service_ids=service_ids,
                            season=season_number,
                            episode=episode_number
                        )
                        count += 1

            except Exception as e:
                self._log(f'Error syncing show: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return count

    # ============================================================================
    # SYNC: PLAYBACK / IN-PROGRESS (watching)
    # ============================================================================

    def _sync_playback(self):
        """
        Sync paused/in-progress items -> list_status = 'watching'
        Endpoint: GET /sync/playback?extended=full

        Must be called AFTER _sync_movies/_sync_episodes so paused items
        overwrite 'watched' status for items that are mid-rewatch.
        """
        response = self._make_request('GET', '/sync/playback?extended=full', auth=True)

        if not response or response.status_code != 200:
            self._log(f'Failed to fetch playback progress', xbmc.LOGWARNING if KODI_ENV else None)
            return 0

        playback_items = response.json()
        count = 0

        for item in playback_items:
            try:
                item_type = item.get('type')
                progress = item.get('progress', 0)

                # Skip essentially complete items
                if progress >= 95:
                    continue

                if item_type == 'movie':
                    movie_data = item.get('movie', {})
                    service_ids = self._build_service_ids(movie_data.get('ids', {}))
                    if not service_ids:
                        continue

                    metadata = self._extract_metadata(movie_data)

                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='movie',
                        progress=int(progress),
                        resume_time=0,
                        title=movie_data.get('title'),
                        year=metadata['year'],
                        plot=metadata['plot'],
                        list_status='watching'
                    )
                    count += 1

                elif item_type == 'episode':
                    episode_data = item.get('episode', {})
                    show_data = item.get('show', {})
                    service_ids = self._build_service_ids(show_data.get('ids', {}), include_tvdb=True)
                    if not service_ids:
                        continue

                    show_metadata = self._extract_metadata(show_data)

                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='episode',
                        progress=int(progress),
                        resume_time=0,
                        title=show_data.get('title'),
                        season=episode_data.get('season'),
                        episode=episode_data.get('number'),
                        year=show_metadata['year'],
                        plot=show_metadata['plot'],
                        list_status='watching'
                    )
                    count += 1

            except Exception as e:
                self._log(f'Error syncing playback item: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return count

    # ============================================================================
    # SYNC: DROPPED (shows hidden from progress)
    # ============================================================================

    def _sync_dropped(self):
        """
        Sync dropped shows -> list_status = 'dropped'

        Trakt has no dedicated "dropped" list. However, users can hide shows from
        their progress tracking via /users/hidden/progress_watched. This is the
        closest equivalent to "dropped" on Trakt.

        Endpoint: GET /users/hidden/progress_watched?type=show&extended=full

        Returns: int count
        """
        response = self._make_request(
            'GET', '/users/hidden/progress_watched?type=show&extended=full&limit=100',
            auth=True
        )

        if not response or response.status_code != 200:
            self._log(f'Failed to fetch hidden/dropped shows (status: {response.status_code if response else "no response"})',
                     xbmc.LOGWARNING if KODI_ENV else None)
            return 0

        hidden_items = response.json()
        count = 0

        for item in hidden_items:
            try:
                # Hidden items structure: {hidden_at, type, show: {...}}
                item_type = item.get('type')

                if item_type == 'show':
                    show_data = item.get('show', {})
                    service_ids = self._build_service_ids(show_data.get('ids', {}), include_tvdb=True)
                    if not service_ids:
                        continue

                    metadata = self._extract_metadata(show_data)

                    # Use update_list_status to mark as dropped without overwriting progress
                    self.db.update_list_status(
                        service_ids=service_ids,
                        list_status='dropped',
                        media_type='episode'
                    )
                    count += 1

            except Exception as e:
                self._log(f'Error processing dropped show: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return count

    # ============================================================================
    # PUBLIC METHODS: Fetch lists for catalog browsing
    # ============================================================================

    @is_authorized
    def fetch_list_by_status(self, status):
        """
        Fetch items live from Trakt API for catalog browsing.
        Returns a normalized list of dicts ready for display.

        status values:
          'watchlist' -> /sync/watchlist/movies + /sync/watchlist/shows
          'watching'  -> /sync/playback
          'watched'   -> /sync/watched/movies + /sync/watched/shows
          'dropped'   -> /users/hidden/progress_watched

        Each returned dict has:
          type, title, year, plot, poster, fanart,
          service_ids, progress (%), season, episode (for episodes)
        """
        if status == 'watchlist':
            return self._fetch_watchlist_items()
        elif status == 'watching':
            return self._fetch_playback_items()
        elif status == 'watched':
            return self._fetch_watched_items()
        elif status == 'dropped':
            return self._fetch_dropped_items()
        return []

    def _fetch_watchlist_items(self):
        """Fetch /sync/watchlist/movies and /sync/watchlist/shows live."""
        results = []
        for endpoint_type, media_type in [('movies', 'movie'), ('shows', 'show')]:
            response = self._make_request('GET', f'/sync/watchlist/{endpoint_type}?extended=full', auth=True)
            if not response or response.status_code != 200:
                continue
            for item in response.json():
                media_data = item.get('movie') or item.get('show') or {}
                entry = self._normalize_item(media_data, media_type)
                if entry:
                    results.append(entry)
        return results

    def _fetch_playback_items(self):
        """Fetch /sync/playback live (in-progress/watching items)."""
        response = self._make_request('GET', '/sync/playback?extended=full', auth=True)
        if not response or response.status_code != 200:
            return []
        results = []
        for item in response.json():
            item_type = item.get('type')
            progress_pct = item.get('progress', 0)
            if item_type == 'movie':
                media_data = item.get('movie', {})
                entry = self._normalize_item(media_data, 'movie')
            elif item_type == 'episode':
                media_data = item.get('show', {})
                episode_data = item.get('episode', {})
                entry = self._normalize_item(media_data, 'show')
                if entry:
                    entry['season'] = episode_data.get('season')
                    entry['episode'] = episode_data.get('number')
            else:
                continue
            if entry:
                entry['progress'] = int(progress_pct)
                results.append(entry)
        return results

    def _fetch_watched_items(self):
        """Fetch /sync/watched/movies and /sync/watched/shows live."""
        results = []
        # Movies
        response = self._make_request('GET', '/sync/watched/movies?extended=full', auth=True)
        if response and response.status_code == 200:
            seen_shows = set()
            for item in response.json():
                media_data = item.get('movie', {})
                entry = self._normalize_item(media_data, 'movie')
                if entry:
                    entry['plays'] = item.get('plays', 1)
                    results.append(entry)
        # Shows - deduplicate to one entry per show
        response = self._make_request('GET', '/sync/watched/shows?extended=full', auth=True)
        if response and response.status_code == 200:
            for item in response.json():
                media_data = item.get('show', {})
                entry = self._normalize_item(media_data, 'show')
                if entry:
                    # Count total watched episodes
                    total_watched = sum(
                        len(s.get('episodes', []))
                        for s in item.get('seasons', [])
                    )
                    entry['plays'] = total_watched
                    results.append(entry)
        return results

    def _fetch_dropped_items(self):
        """Fetch /users/hidden/progress_watched live (dropped shows)."""
        response = self._make_request(
            'GET', '/users/hidden/progress_watched?type=show&extended=full&limit=100', auth=True
        )
        if not response or response.status_code != 200:
            return []
        results = []
        for item in response.json():
            if item.get('type') == 'show':
                media_data = item.get('show', {})
                entry = self._normalize_item(media_data, 'show')
                if entry:
                    results.append(entry)
        return results

    def _normalize_item(self, media_data, media_type):
        """
        Normalize a Trakt API media object into a standard display dict.
        Does NOT fetch images here (would be too slow for list browsing).
        Use _fetch_tmdb_images separately when needed (e.g. Next Up).
        Returns None if no usable IDs.
        """
        if not media_data:
            return None
        ids = media_data.get('ids', {})
        service_ids = {
            'trakt': ids.get('trakt'),
            'tmdb':  ids.get('tmdb'),
            'imdb':  ids.get('imdb'),
            'tvdb':  ids.get('tvdb'),
        }
        service_ids = {k: v for k, v in service_ids.items() if v}
        if not service_ids:
            return None

        return {
            'type': media_type,
            'title': media_data.get('title', 'Unknown'),
            'year': media_data.get('year'),
            'plot': media_data.get('overview', ''),
            'poster': None,   # Not fetched here for speed — TMDbHelper handles artwork on display
            'fanart': None,
            'service_ids': service_ids,
            'progress': 0,
            'plays': 0,
            'season': None,
            'episode': None,
        }

    def _fetch_tmdb_images(self, tmdb_id, media_type):
        """
        Fetch poster and backdrop from TMDB API for a given tmdb_id.
        Uses the free TMDB API (no key required for image paths via tmdb helper).
        Falls back to graceful None if unavailable.

        Returns: (poster_url, fanart_url) or (None, None)
        """
        if not tmdb_id:
            return None, None
        try:
            tmdb_type = 'movie' if media_type == 'movie' else 'tv'
            url = f'https://api.themoviedb.org/3/{tmdb_type}/{tmdb_id}?api_key=fcb4e77ecffd5059e4d5e9c3c0b9e8f8&language=en-US'
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                base = 'https://image.tmdb.org/t/p/'
                poster_path = data.get('poster_path')
                backdrop_path = data.get('backdrop_path')
                poster  = f'{base}w342{poster_path}'  if poster_path  else None
                fanart  = f'{base}w1280{backdrop_path}' if backdrop_path else poster
                return poster, fanart
        except Exception:
            pass
        return None, None

    @is_authorized
    def fetch_next_up(self):
        """
        Fetch Next Up episodes: for every show the user is currently watching,
        return the next unwatched episode.

        Uses /sync/watched/shows to get watched seasons+episodes, then
        /shows/{id}/seasons?extended=full to find the next one.

        Returns list of dicts:
          title, year, poster, fanart, service_ids,
          next_season, next_episode, watched_count, total_count
        """
        # Get all watched shows with season/episode detail
        response = self._make_request('GET', '/sync/watched/shows', auth=True)
        if not response or response.status_code != 200:
            return []

        # Also get playback progress to know which shows are "in progress"
        # (not fully completed) — shows that appear in /sync/playback OR have
        # a last-watched episode that is not the series finale.
        playback_resp = self._make_request('GET', '/sync/playback', auth=True)
        in_progress_trakt_ids = set()
        if playback_resp and playback_resp.status_code == 200:
            for pb in playback_resp.json():
                if pb.get('type') == 'episode':
                    show_ids = pb.get('show', {}).get('ids', {})
                    tid = show_ids.get('trakt')
                    if tid:
                        in_progress_trakt_ids.add(tid)

        results = []
        watched_shows = response.json()

        for show_item in watched_shows:
            try:
                show_data = show_item.get('show', {})
                ids = show_data.get('ids', {})
                trakt_id = ids.get('trakt')
                tmdb_id  = ids.get('tmdb')
                tvdb_id  = ids.get('tvdb')
                imdb_id  = ids.get('imdb')

                if not trakt_id:
                    continue

                service_ids = {k: v for k, v in {
                    'trakt': trakt_id, 'tmdb': tmdb_id,
                    'tvdb': tvdb_id,   'imdb': imdb_id,
                }.items() if v}

                # Build a set of (season, episode) that have been watched
                watched_eps = set()
                for season_data in show_item.get('seasons', []):
                    s = season_data.get('number')
                    for ep_data in season_data.get('episodes', []):
                        e = ep_data.get('number')
                        if s is not None and e is not None:
                            watched_eps.add((s, e))

                if not watched_eps:
                    continue

                # Find highest watched episode
                max_season  = max(s for s, e in watched_eps)
                max_episode = max(e for s, e in watched_eps if s == max_season)

                # Candidate next episode
                next_season  = max_season
                next_episode = max_episode + 1

                # Fetch show seasons to validate next episode exists
                seasons_resp = self._make_request(
                    'GET', f'/shows/{trakt_id}/seasons?extended=episodes', auth=True
                )
                if not seasons_resp or seasons_resp.status_code != 200:
                    # Can't validate — still include if we know they're in progress
                    if trakt_id not in in_progress_trakt_ids:
                        continue
                    total_count = len(watched_eps)
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                    results.append({
                        'title': show_data.get('title', 'Unknown'),
                        'year': show_data.get('year'),
                        'poster': poster, 'fanart': fanart,
                        'service_ids': service_ids,
                        'next_season': next_season,
                        'next_episode': next_episode,
                        'watched_count': len(watched_eps),
                        'total_count': 0,
                    })
                    continue

                seasons_data = seasons_resp.json()
                # Build full episode map {season: max_episode}
                season_map = {}
                total_eps = 0
                for season in seasons_data:
                    snum = season.get('number', 0)
                    if snum == 0:  # skip specials
                        continue
                    eps = season.get('episodes', [])
                    ep_count = len(eps) if eps else season.get('episode_count', 0)
                    season_map[snum] = ep_count
                    total_eps += ep_count

                # Check if next episode exists in current season
                current_season_total = season_map.get(next_season, 0)
                if next_episode > current_season_total:
                    # Move to next season
                    next_season  += 1
                    next_episode  = 1

                # If next season doesn't exist → show is fully watched, skip
                if next_season not in season_map:
                    continue

                # Already watched this specific episode? skip
                if (next_season, next_episode) in watched_eps:
                    continue

                poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                results.append({
                    'title': show_data.get('title', 'Unknown'),
                    'year': show_data.get('year'),
                    'poster': poster, 'fanart': fanart,
                    'service_ids': service_ids,
                    'next_season': next_season,
                    'next_episode': next_episode,
                    'watched_count': len(watched_eps),
                    'total_count': total_eps,
                })
            except Exception as e:
                self._log(f'fetch_next_up: error on show: {e}', xbmc.LOGWARNING if KODI_ENV else None)
                continue

        return results

    # ============================================================================
    # SYNC PUSH
    # ============================================================================

    @is_authorized
    def sync_push(self):
        """Push local watch history to Trakt (process sync queue)."""
        try:
            self._log('Starting sync push to Trakt...')
            queue_items = self.db.get_sync_queue(service='trakt', limit=50)

            pushed_count = 0
            errors = []

            for item in queue_items:
                try:
                    action = item['action']
                    data = item['data']

                    if action in ('scrobble_stop', 'mark_watched'):
                        success = self._add_to_history(data)
                    else:
                        self._log(f'Unknown action: {action}', xbmc.LOGWARNING if KODI_ENV else None)
                        success = False

                    if success:
                        self.db.update_sync_item(item['id'], success=True)
                        pushed_count += 1
                    else:
                        error_msg = f'Failed to push {action}'
                        self.db.update_sync_item(item['id'], success=False, error=error_msg)
                        errors.append(error_msg)

                except Exception as e:
                    error_msg = f'Error processing queue item: {str(e)}'
                    self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                    self.db.update_sync_item(item['id'], success=False, error=error_msg)
                    errors.append(error_msg)

            return {
                'success': len(errors) == 0,
                'pushed': pushed_count,
                'errors': errors
            }

        except Exception as e:
            self._log(f'Sync push error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return {'success': False, 'pushed': 0, 'errors': [str(e)]}

    def _add_to_history(self, media_info):
        try:
            media_type = media_info.get('type')
            payload = {}

            if media_type == 'movie':
                payload['movies'] = [{'ids': media_info.get('ids', {}), 'watched_at': self._format_timestamp(media_info.get('watched_at'))}]
            elif media_type == 'episode':
                payload['episodes'] = [{'ids': media_info.get('ids', {}), 'watched_at': self._format_timestamp(media_info.get('watched_at'))}]
            else:
                return False

            response = self._make_request('POST', '/sync/history', data=payload, auth=True)
            return response is not None and response.status_code in [200, 201]

        except Exception as e:
            self._log(f'Error adding to history: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    # ============================================================================
    # SCROBBLING
    # ============================================================================

    @is_authorized
    def scrobble_start(self, media_info, progress=0):
        return self._scrobble('start', media_info, progress)

    @is_authorized
    def scrobble_pause(self, media_info, progress):
        return self._scrobble('pause', media_info, progress)

    @is_authorized
    def scrobble_stop(self, media_info, progress):
        result = self._scrobble('stop', media_info, progress)
        if result and progress >= 80:
            self._queue_for_sync('mark_watched', {
                'type': media_info.get('type'),
                'ids': media_info.get('ids'),
                'watched_at': int(time.time())
            })
        return result

    def _scrobble(self, action, media_info, progress):
        try:
            media_type = media_info.get('type')
            if media_type not in ['movie', 'episode']:
                return None

            if media_type == 'movie':
                payload = {
                    'movie': {'ids': media_info.get('ids', {})},
                    'progress': progress,
                    'app_version': '1.0.0',
                    'app_date': '2024-01-01'
                }
                if media_info.get('title'):
                    payload['movie']['title'] = media_info['title']
                if media_info.get('year'):
                    payload['movie']['year'] = media_info['year']
            else:
                show_info = media_info.get('show', {})
                show_ids = show_info.get('ids', media_info.get('ids', {}))
                payload = {
                    'show': {'ids': show_ids},
                    'episode': {
                        'season': media_info.get('season', 1),
                        'number': media_info.get('episode', 1)
                    },
                    'progress': progress,
                    'app_version': '1.0.0',
                    'app_date': '2024-01-01'
                }
                if show_info.get('title'):
                    payload['show']['title'] = show_info['title']

            response = self._make_request('POST', f'/scrobble/{action}', data=payload, auth=True)

            if response and response.status_code in [200, 201]:
                self._log(f'Scrobble {action} successful: {progress}%')
                return response.json()
            else:
                self._queue_for_sync(f'scrobble_{action}', {'media_info': media_info, 'progress': progress})
                return None

        except Exception as e:
            self._log(f'Scrobble error: {str(e)}', xbmc.LOGERROR if KODI_ENV else None)
            self._queue_for_sync(f'scrobble_{action}', {'media_info': media_info, 'progress': progress})
            return None

    # ============================================================================
    # UTILITIES
    # ============================================================================

    def _parse_timestamp(self, timestamp_str):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except Exception:
            return int(time.time())

    def _format_timestamp(self, timestamp):
        if timestamp is None:
            timestamp = int(time.time())
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        except Exception:
            return time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
