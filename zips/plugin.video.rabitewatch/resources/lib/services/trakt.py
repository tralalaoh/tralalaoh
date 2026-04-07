
# -*- coding: utf-8 -*-
"""
Rabite Watch - Trakt Pull Service
Pulls watch history, progress and lists from Trakt API.
No scrobbling - read only.

Uses same CLIENT_ID/SECRET as plugin.video.littlerabite so users
who already authenticated there don't need to re-authenticate.
"""

import requests
import time
import json

from resources.lib.services.base import PullService

try:
    import xbmc
    import xbmcgui
    import xbmcaddon
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class TraktPullService(PullService):
    service_name = 'trakt'

    # Same credentials as plugin.video.littlerabite
    CLIENT_ID     = '227a57a92512d6f2cbb1cbd27e09a6780de39e6449f57c60d342ef4e7b6cc4ec'
    CLIENT_SECRET = 'a475a97cbc9b720bbd55c04c215d42ad124eb27292660718a171c35ea391658f'
    BASE_URL      = 'https://api.trakt.tv'
    API_VERSION   = '2'

    def __init__(self, database):
        super().__init__(database)
        self._session = requests.Session()
        self._session.headers.update({
            'Content-Type': 'application/json',
            'trakt-api-version': self.API_VERSION,
            'trakt-api-key': self.CLIENT_ID
        })

    # ------------------------------------------------------------------
    # token_needs_refresh override - handle missing expires_at gracefully
    # ------------------------------------------------------------------

    def token_needs_refresh(self):
        auth = self.db.get_auth(self.service_name)
        if not auth:
            return True
        if not auth.get('expires_at'):
            return False  # no expiry stored = assume valid (avoid refresh loops)
        return int(time.time()) >= (auth['expires_at'] - 300)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _make_request(self, method, endpoint, data=None, auth=True, retry=True):
        """Make API request. Returns requests.Response or None."""
        url = f'{self.BASE_URL}{endpoint}'
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': self.API_VERSION,
            'trakt-api-key': self.CLIENT_ID
        }
        if auth:
            token = self._get_token()
            if token:
                headers['Authorization'] = f'Bearer {token}'

        max_retries = 3 if retry else 1
        for attempt in range(max_retries):
            try:
                resp = requests.request(
                    method=method, url=url, headers=headers,
                    json=data, timeout=30
                )

                if resp.status_code == 429:
                    wait = int(resp.headers.get('Retry-After', 60))
                    self._log(f'Rate limited, waiting {wait}s', xbmc.LOGWARNING if KODI_ENV else None)
                    if attempt < max_retries - 1:
                        time.sleep(wait)
                        continue

                if resp.status_code in (500, 502, 503, 504):
                    self._log(f'Server error {resp.status_code}', xbmc.LOGWARNING if KODI_ENV else None)
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None

                if resp.status_code == 401:
                    self._log('Unauthorized - token may be expired', xbmc.LOGWARNING if KODI_ENV else None)
                    return None

                resp.raise_for_status()
                return resp

            except requests.exceptions.Timeout:
                self._log(f'Timeout attempt {attempt+1}', xbmc.LOGWARNING if KODI_ENV else None)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError:
                self._log(f'Connection error attempt {attempt+1}', xbmc.LOGWARNING if KODI_ENV else None)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                self._log(f'Request error: {e}', xbmc.LOGERROR if KODI_ENV else None)
                return None

        return None

    def _json(self, endpoint, auth=True):
        """GET and return parsed JSON or None."""
        resp = self._make_request('GET', endpoint, auth=auth)
        if resp and resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                pass
        return None

    # ------------------------------------------------------------------
    # AUTH - Device Code Flow (matches littlerabite TraktService.authenticate)
    # ------------------------------------------------------------------

    def authenticate(self):
        """OAuth device code flow - identical to littlerabite."""
        try:
            self._log('Starting device authentication...')

            resp = self._make_request(
                'POST', '/oauth/device/code',
                data={'client_id': self.CLIENT_ID},
                auth=False
            )
            if not resp:
                self._log('Failed to get device code', xbmc.LOGERROR if KODI_ENV else None)
                return False

            code_data = resp.json()
            device_code      = code_data.get('device_code')
            user_code        = code_data.get('user_code')
            verification_url = code_data.get('verification_url')
            expires_in       = code_data.get('expires_in', 600)
            interval         = code_data.get('interval', 5)

            if not device_code or not user_code or not verification_url:
                self._log('Device code response missing required fields', xbmc.LOGERROR if KODI_ENV else None)
                return False

            if KODI_ENV:
                dialog = xbmcgui.DialogProgress()
                dialog.create(
                    'Trakt Authentication',
                    f'1. Go to: {verification_url}\n'
                    f'2. Enter code: [B]{user_code}[/B]\n'
                    f'3. Waiting for authorization...'
                )

            poll_start = time.time()
            while time.time() - poll_start < expires_in:
                if KODI_ENV and dialog.iscanceled():
                    dialog.close()
                    return False

                time.sleep(interval)

                poll_resp = self._make_request(
                    'POST', '/oauth/device/token',
                    data={
                        'code': device_code,
                        'client_id': self.CLIENT_ID,
                        'client_secret': self.CLIENT_SECRET
                    },
                    auth=False, retry=False
                )

                if poll_resp and poll_resp.status_code == 200:
                    if KODI_ENV:
                        dialog.close()
                    return self._save_token(poll_resp.json())
                elif poll_resp and poll_resp.status_code == 410:
                    self._log('Device code expired', xbmc.LOGWARNING if KODI_ENV else None)
                    break

            if KODI_ENV:
                dialog.close()
            return False

        except Exception as e:
            self._log(f'Authentication error: {e}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    def _save_token(self, token_data):
        try:
            access_token   = token_data['access_token']
            refresh_token  = token_data.get('refresh_token')
            expires_in     = token_data.get('expires_in', 7776000)
            expires_at     = int(time.time()) + expires_in

            # Save token first so user request works
            self.db.store_auth(
                service=self.service_name,
                token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )

            # Get user info
            resp = self._make_request('GET', '/users/settings', auth=True)
            if not resp:
                return False

            user_data = resp.json().get('user', {})

            self.db.store_auth(
                service=self.service_name,
                token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                user_data=user_data
            )

            username = user_data.get('username', 'Unknown')
            self._log(f'Authenticated as {username}')

            if KODI_ENV:
                xbmcgui.Dialog().notification(
                    'Rabite Watch',
                    f'Trakt: Logged in as {username}',
                    xbmcgui.NOTIFICATION_INFO, 3000
                )
            return True

        except Exception as e:
            self._log(f'Error saving token: {e}', xbmc.LOGERROR if KODI_ENV else None)
            return False

    def refresh_token(self):
        try:
            auth = self.db.get_auth(self.service_name)
            if not auth or not auth.get('refresh_token'):
                return False

            resp = self._make_request(
                'POST', '/oauth/token',
                data={
                    'refresh_token': auth['refresh_token'],
                    'client_id': self.CLIENT_ID,
                    'client_secret': self.CLIENT_SECRET,
                    'grant_type': 'refresh_token'
                },
                auth=False
            )
            if resp:
                return self._save_token(resp.json())
        except Exception as e:
            self._log(f'Token refresh error: {e}', xbmc.LOGERROR if KODI_ENV else None)
        return False

    # ------------------------------------------------------------------
    # PULL - Main entry point
    # ------------------------------------------------------------------

    def pull_watchlist(self):
        """
        Pull all Trakt data and return normalized list of items.
        Pull order (mirrors littlerabite sync_pull order):
          1. Watchlist
          2. Watched movies
          3. Watched shows/episodes
          4. In-progress (playback) - overrides watched
          5. Dropped (hidden)
        """
        if not self.is_authenticated():
            return []
        if self.token_needs_refresh():
            self.refresh_token()

        items = []
        items.extend(self._pull_watchlist())
        items.extend(self._pull_watched_movies())
        items.extend(self._pull_watched_shows())
        items.extend(self._pull_playback())
        items.extend(self._pull_dropped())

        self._log(f'Pulled {len(items)} items total')
        return items

    # ------------------------------------------------------------------
    # 1. WATCHLIST
    # ------------------------------------------------------------------

    def _pull_watchlist(self):
        items = []
        for endpoint_type, db_type in [('movies', 'movie'), ('shows', 'episode')]:
            data = self._json(f'/sync/watchlist/{endpoint_type}?extended=full')
            if not data:
                continue
            for entry in data:
                try:
                    obj = entry.get('movie') or entry.get('show') or {}
                    ids = obj.get('ids', {})
                    tmdb_id = ids.get('tmdb')
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, db_type)
                    items.append({
                        'service_ids': self._build_ids(ids),
                        'media_type': db_type,
                        'title': obj.get('title'),
                        'show_title': obj.get('title') if db_type == 'episode' else None,
                        'year': obj.get('year'),
                        'season': None, 'episode': None,
                        'resume_pct': 0, 'resume_time': 0, 'completed': 0,
                        'list_status': 'watchlist',
                        'last_watched_at': self._parse_time(entry.get('listed_at')),
                        'poster': poster, 'fanart': fanart,
                        'plot': obj.get('overview'),
                        'duration': (obj.get('runtime', 0) or 0) * 60,
                        '_service': 'trakt'
                    })
                except Exception as e:
                    self._log(f'Watchlist entry error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return items

    # ------------------------------------------------------------------
    # 2. WATCHED MOVIES
    # ------------------------------------------------------------------

    def _pull_watched_movies(self):
        data = self._json('/sync/watched/movies?extended=full')
        if not data:
            return []
        items = []
        for entry in data:
            try:
                obj = entry.get('movie', {})
                ids = obj.get('ids', {})
                tmdb_id = ids.get('tmdb')
                poster, fanart = self._fetch_tmdb_images(tmdb_id, 'movie')
                items.append({
                    'service_ids': self._build_ids(ids),
                    'media_type': 'movie',
                    'title': obj.get('title'),
                    'show_title': None,
                    'year': obj.get('year'),
                    'season': None, 'episode': None,
                    'resume_pct': 100, 'resume_time': 0, 'completed': 1,
                    'list_status': 'watched',
                    'last_watched_at': self._parse_time(entry.get('last_watched_at')),
                    'poster': poster, 'fanart': fanart,
                    'plot': obj.get('overview'),
                    'duration': (obj.get('runtime', 0) or 0) * 60,
                    '_service': 'trakt'
                })
            except Exception as e:
                self._log(f'Watched movie error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return items

    # ------------------------------------------------------------------
    # 3. WATCHED SHOWS (episode level)
    # ------------------------------------------------------------------

    def _pull_watched_shows(self):
        """
        Store ONE row per show (the most recently watched episode).
        Storing per-episode creates massive duplicates in the DB/UI.
        """
        data = self._json('/sync/watched/shows?extended=full')
        if not data:
            return []
        items = []
        for show in data:
            try:
                show_obj = show.get('show', {})
                show_ids = show_obj.get('ids', {})
                service_ids = self._build_ids(show_ids, tvdb=True)

                # Find the most recently watched episode across all seasons
                latest_season  = None
                latest_episode = None
                latest_at      = None

                for season_data in show.get('seasons', []):
                    season_num = season_data.get('number')
                    if season_num == 0:
                        continue  # skip specials
                    for ep_data in season_data.get('episodes', []):
                        ep_num     = ep_data.get('number')
                        watched_at = self._parse_time(ep_data.get('last_watched_at'))
                        if watched_at is None:
                            watched_at = 0  # treat missing timestamp as oldest
                        if latest_at is None or watched_at > latest_at:
                            latest_at      = watched_at
                            latest_season  = season_num
                            latest_episode = ep_num

                if latest_season is None:
                    continue  # no valid episodes

                tmdb_id = show_ids.get('tmdb')
                poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                items.append({
                    'service_ids': service_ids,
                    'media_type': 'episode',
                    'title': f'S{latest_season:02d}E{latest_episode:02d}',
                    'show_title': show_obj.get('title'),
                    'year': show_obj.get('year'),
                    'season': latest_season,
                    'episode': latest_episode,
                    'resume_pct': 100, 'resume_time': 0, 'completed': 1,
                    'list_status': 'watched',
                    'last_watched_at': latest_at,
                    'poster': poster, 'fanart': fanart,
                    'plot': show_obj.get('overview'),
                    'duration': 0,
                    '_service': 'trakt'
                })
            except Exception as e:
                self._log(f'Watched show error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return items

    # ------------------------------------------------------------------
    # 4. PLAYBACK (in-progress / resume points)
    # ------------------------------------------------------------------

    def _pull_playback(self):
        """
        /sync/playback - the gold standard for resume points.
        Trakt stores the exact % watched when you paused.
        """
        data = self._json('/sync/playback?extended=full')
        if not data:
            return []

        # Read once before the loop — avoid an Addon() call per entry.
        threshold = 95
        if KODI_ENV:
            try:
                threshold = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingInt('resume_threshold')
            except Exception:
                pass

        items = []
        for entry in data:
            try:
                progress_pct = int(entry.get('progress', 0))
                if progress_pct >= threshold:
                    continue  # essentially complete, skip

                media_type = entry.get('type')

                if media_type == 'movie':
                    obj = entry.get('movie', {})
                    ids = obj.get('ids', {})
                    runtime_min = obj.get('runtime', 0) or 0
                    duration_s = runtime_min * 60
                    resume_time = int((progress_pct / 100.0) * duration_s)
                    poster, fanart = self._fetch_tmdb_images(ids.get('tmdb'), 'movie')
                    items.append({
                        'service_ids': self._build_ids(ids),
                        'media_type': 'movie',
                        'title': obj.get('title'),
                        'show_title': None,
                        'year': obj.get('year'),
                        'season': None, 'episode': None,
                        'resume_pct': progress_pct,
                        'resume_time': resume_time,
                        'completed': 0,
                        'list_status': 'watching',
                        'last_watched_at': self._parse_time(entry.get('paused_at')),
                        'poster': poster, 'fanart': fanart,
                        'plot': obj.get('overview'),
                        'duration': duration_s,
                        '_service': 'trakt'
                    })

                elif media_type == 'episode':
                    show   = entry.get('show', {})
                    ep_obj = entry.get('episode', {})
                    show_ids = show.get('ids', {})
                    runtime_min = ep_obj.get('runtime', 0) or 0
                    duration_s = runtime_min * 60
                    resume_time = int((progress_pct / 100.0) * duration_s)
                    poster, fanart = self._fetch_tmdb_images(show_ids.get('tmdb'), 'show')
                    items.append({
                        'service_ids': self._build_ids(show_ids),
                        'media_type': 'episode',
                        'title': ep_obj.get('title') or f'Episode {ep_obj.get("number","?")}',
                        'show_title': show.get('title'),
                        'year': show.get('year'),
                        'season': ep_obj.get('season'),
                        'episode': ep_obj.get('number'),
                        'resume_pct': progress_pct,
                        'resume_time': resume_time,
                        'completed': 0,
                        'list_status': 'watching',
                        'last_watched_at': self._parse_time(entry.get('paused_at')),
                        'poster': poster, 'fanart': fanart,
                        'plot': ep_obj.get('overview'),
                        'duration': duration_s,
                        '_service': 'trakt'
                    })
            except Exception as e:
                self._log(f'Playback entry error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return items

    # ------------------------------------------------------------------
    # 5. DROPPED (hidden from progress)
    # ------------------------------------------------------------------

    def _pull_dropped(self):
        data = self._json('/users/hidden/progress_watched?type=show&limit=100&extended=full')
        if not data:
            return []
        items = []
        for entry in data:
            try:
                obj = entry.get('show', {})
                ids = obj.get('ids', {})
                poster, fanart = self._fetch_tmdb_images(ids.get('tmdb'), 'show')
                items.append({
                    'service_ids': self._build_ids(ids),
                    'media_type': 'episode',
                    'title': obj.get('title'),
                    'show_title': obj.get('title'),
                    'year': obj.get('year'),
                    'season': None, 'episode': None,
                    'resume_pct': 0, 'resume_time': 0, 'completed': 0,
                    'list_status': 'dropped',
                    'last_watched_at': self._parse_time(entry.get('hidden_at')),
                    'poster': poster, 'fanart': fanart,
                    'plot': obj.get('overview'),
                    'duration': 0,
                    '_service': 'trakt'
                })
            except Exception as e:
                self._log(f'Dropped entry error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return items

    # ------------------------------------------------------------------
    # FAST SYNC (JIT - only in-progress items)
    # ------------------------------------------------------------------

    def pull_fast_watching(self):
        """
        Fast sync: only fetch active playback items (resume points).
        Called by pull_fast_continue_watching — no dialog, no full pull.
        """
        if not self.is_authenticated():
            return []
        if self.token_needs_refresh():
            self.refresh_token()
        return self._pull_playback()

    def pull_fast_watchlist(self):
        """
        Fast sync: only fetch watchlist items.
        Called by pull_fast_watchlist in PullManager.
        """
        if not self.is_authenticated():
            return []
        if self.token_needs_refresh():
            self.refresh_token()
        try:
            return self._pull_watchlist()
        except Exception as e:
            self._log(f'pull_fast_watchlist error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
            return []

    # ------------------------------------------------------------------
    # BROWSE (live fetch for UI) - matches littlerabite TraktService exactly
    # ------------------------------------------------------------------

    def fetch_list_by_status(self, status):
        """
        Fetch items live from Trakt API for catalog browsing.
        Returns normalized list of dicts. Matches littlerabite.
        """
        if not self.is_authenticated():
            return []
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
        results = []
        for endpoint_type, media_type in [('movies', 'movie'), ('shows', 'show')]:
            resp = self._make_request('GET', f'/sync/watchlist/{endpoint_type}?extended=full')
            if not resp or resp.status_code != 200:
                continue
            for item in resp.json():
                obj = item.get('movie') or item.get('show') or {}
                entry = self._normalize_item(obj, media_type)
                if entry:
                    tmdb_id = entry['service_ids'].get('tmdb')
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, media_type)
                    entry['poster'] = poster
                    entry['fanart'] = fanart
                    results.append(entry)
        return results

    def _fetch_playback_items(self):
        resp = self._make_request('GET', '/sync/playback?extended=full')
        if not resp or resp.status_code != 200:
            return []
        results = []
        for item in resp.json():
            item_type    = item.get('type')
            progress_pct = item.get('progress', 0)
            if item_type == 'movie':
                entry = self._normalize_item(item.get('movie', {}), 'movie')
                fetch_type = 'movie'
            elif item_type == 'episode':
                entry = self._normalize_item(item.get('show', {}), 'show')
                fetch_type = 'show'
                if entry:
                    ep = item.get('episode', {})
                    entry['season']  = ep.get('season')
                    entry['episode'] = ep.get('number')
            else:
                continue
            if entry:
                tmdb_id = entry['service_ids'].get('tmdb')
                poster, fanart = self._fetch_tmdb_images(tmdb_id, fetch_type)
                entry['poster'] = poster
                entry['fanart'] = fanart
                entry['progress'] = int(progress_pct)
                results.append(entry)
        return results

    def _fetch_watched_items(self):
        results = []
        resp = self._make_request('GET', '/sync/watched/movies?extended=full')
        if resp and resp.status_code == 200:
            for item in resp.json():
                entry = self._normalize_item(item.get('movie', {}), 'movie')
                if entry:
                    tmdb_id = entry['service_ids'].get('tmdb')
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, 'movie')
                    entry['poster'] = poster
                    entry['fanart'] = fanart
                    entry['plays'] = item.get('plays', 1)
                    results.append(entry)
        resp = self._make_request('GET', '/sync/watched/shows?extended=full')
        if resp and resp.status_code == 200:
            for item in resp.json():
                entry = self._normalize_item(item.get('show', {}), 'show')
                if entry:
                    tmdb_id = entry['service_ids'].get('tmdb')
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                    entry['poster'] = poster
                    entry['fanart'] = fanart
                    entry['plays'] = sum(
                        len(s.get('episodes', [])) for s in item.get('seasons', [])
                    )
                    results.append(entry)
        return results

    def _fetch_dropped_items(self):
        resp = self._make_request('GET', '/users/hidden/progress_watched?type=show&extended=full&limit=100')
        if not resp or resp.status_code != 200:
            return []
        results = []
        for item in resp.json():
            if item.get('type') == 'show':
                entry = self._normalize_item(item.get('show', {}), 'show')
                if entry:
                    tmdb_id = entry['service_ids'].get('tmdb')
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                    entry['poster'] = poster
                    entry['fanart'] = fanart
                    results.append(entry)
        return results

    def _normalize_item(self, media_data, media_type):
        """Normalize a Trakt API media object into a standard display dict."""
        if not media_data:
            return None
        ids = media_data.get('ids', {})
        service_ids = {k: v for k, v in {
            'trakt': ids.get('trakt'),
            'tmdb':  ids.get('tmdb'),
            'imdb':  ids.get('imdb'),
        }.items() if v}
        if not service_ids:
            return None
        return {
            'type': media_type,
            'title': media_data.get('title', 'Unknown'),
            'year': media_data.get('year'),
            'plot': media_data.get('overview', ''),
            'poster': None, 'fanart': None,
            'service_ids': service_ids,
            'progress': 0, 'plays': 0,
            'season': None, 'episode': None,
        }

    def _fetch_tmdb_images(self, tmdb_id, media_type):
        """
        Fetch poster (w500) and backdrop (original) from TMDB.
        For shows: no portrait-poster fallback for fanart.
        Returns (poster_url, fanart_url).
        """
        if not tmdb_id:
            return None, None
        try:
            key = None
            if KODI_ENV:
                try:
                    key = xbmcaddon.Addon('plugin.video.rabitewatch').getSetting('tmdb_api_key').strip() or None
                except Exception:
                    pass
            if not key:
                return None, None
            tmdb_type = 'movie' if media_type == 'movie' else 'tv'
            url = (f'https://api.themoviedb.org/3/{tmdb_type}/{tmdb_id}'
                   f'?api_key={key}&language=en-US')
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                base = 'https://image.tmdb.org/t/p/'
                pp   = data.get('poster_path')
                bp   = data.get('backdrop_path')
                poster = f'{base}w500{pp}'        if pp else None
                if bp:
                    fanart = f'{base}original{bp}'
                elif media_type == 'movie' and poster:
                    fanart = poster
                else:
                    fanart = None
                return poster, fanart
        except Exception:
            pass
        return None, None

    # ------------------------------------------------------------------
    # NEXT UP (matches littlerabite TraktService.fetch_next_up exactly)
    # ------------------------------------------------------------------

    def fetch_next_up(self):
        """
        Fetch Next Up episodes: for every show the user is watching,
        return the next unwatched episode.
        Matches littlerabite TraktService.fetch_next_up.
        """
        if not self.is_authenticated():
            return []

        resp = self._make_request('GET', '/sync/watched/shows')
        if not resp or resp.status_code != 200:
            return []

        # Get in-progress trakt IDs from /sync/playback
        pb_resp = self._make_request('GET', '/sync/playback')
        in_progress_ids = set()
        if pb_resp and pb_resp.status_code == 200:
            for pb in pb_resp.json():
                if pb.get('type') == 'episode':
                    tid = pb.get('show', {}).get('ids', {}).get('trakt')
                    if tid:
                        in_progress_ids.add(tid)

        results = []
        for show_item in resp.json():
            try:
                show_data = show_item.get('show', {})
                ids       = show_data.get('ids', {})
                trakt_id  = ids.get('trakt')
                tmdb_id   = ids.get('tmdb')
                tvdb_id   = ids.get('tvdb')
                imdb_id   = ids.get('imdb')

                if not trakt_id:
                    continue

                service_ids = {k: v for k, v in {
                    'trakt': trakt_id, 'tmdb': tmdb_id,
                    'tvdb': tvdb_id,   'imdb': imdb_id,
                }.items() if v}

                # Build watched episode set
                watched_eps = set()
                for season_data in show_item.get('seasons', []):
                    s = season_data.get('number')
                    for ep in season_data.get('episodes', []):
                        e = ep.get('number')
                        if s is not None and e is not None:
                            watched_eps.add((s, e))

                if not watched_eps:
                    continue

                max_season  = max(s for s, e in watched_eps)
                max_episode = max(e for s, e in watched_eps if s == max_season)
                next_season  = max_season
                next_episode = max_episode + 1

                # Fetch seasons to validate next episode exists
                s_resp = self._make_request(
                    'GET', f'/shows/{trakt_id}/seasons?extended=episodes'
                )
                if not s_resp or s_resp.status_code != 200:
                    if trakt_id not in in_progress_ids:
                        continue
                    poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                    results.append({
                        'title': show_data.get('title', 'Unknown'),
                        'year': show_data.get('year'),
                        'poster': poster, 'fanart': fanart,
                        'service_ids': service_ids,
                        'next_season': next_season, 'next_episode': next_episode,
                        'watched_count': len(watched_eps), 'total_count': 0,
                        'plot': show_data.get('overview', ''),
                    })
                    continue

                season_map = {}
                total_eps  = 0
                for season in s_resp.json():
                    snum = season.get('number', 0)
                    if snum == 0:
                        continue  # skip specials
                    eps      = season.get('episodes', [])
                    ep_count = len(eps) if eps else season.get('episode_count', 0)
                    season_map[snum] = ep_count
                    total_eps += ep_count

                # Roll over to next season if end of current reached
                if next_episode > season_map.get(next_season, 0):
                    next_season  += 1
                    next_episode  = 1

                # No next season means fully watched
                if next_season not in season_map:
                    continue

                # Already watched this specific episode?
                if (next_season, next_episode) in watched_eps:
                    continue

                poster, fanart = self._fetch_tmdb_images(tmdb_id, 'show')
                results.append({
                    'title': show_data.get('title', 'Unknown'),
                    'year': show_data.get('year'),
                    'poster': poster, 'fanart': fanart,
                    'service_ids': service_ids,
                    'next_season': next_season, 'next_episode': next_episode,
                    'watched_count': len(watched_eps), 'total_count': total_eps,
                    'plot': show_data.get('overview', ''),
                })

            except Exception as e:
                self._log(f'fetch_next_up show error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
                continue

        return results

    # ------------------------------------------------------------------
    # UTILS
    # ------------------------------------------------------------------

    def _build_ids(self, ids_dict, tvdb=False):
        result = {
            'trakt':   ids_dict.get('trakt'),
            'tmdb':    ids_dict.get('tmdb'),
            'imdb':    ids_dict.get('imdb'),
            'tvdb':    ids_dict.get('tvdb'),
            'slug':    ids_dict.get('slug'),
            'mal':     ids_dict.get('mal'),
            'anilist': ids_dict.get('anilist'),
            'simkl':   ids_dict.get('simkl'),
        }
        return {k: v for k, v in result.items() if v}

    def _parse_time(self, iso_str):
        """Parse an ISO-8601 string to a UNIX timestamp integer.
        Returns None when the string is absent so callers (and upsert_progress)
        can apply their own 'now' default rather than faking a timestamp."""
        if not iso_str:
            return None
        try:
            import datetime
            dt = datetime.datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            return int(dt.timestamp())
        except Exception:
            return None
