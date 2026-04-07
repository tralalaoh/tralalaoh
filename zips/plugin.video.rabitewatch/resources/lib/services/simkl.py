
# -*- coding: utf-8 -*-
"""
Rabite Watch - Simkl Pull Service
Pulls watch history and lists from Simkl API.
No scrobbling - read only.

Uses same CLIENT_ID as plugin.video.littlerabite.
"""

import requests
import time
import json

from resources.lib.services.base import PullService

try:
    import xbmc
    import xbmcgui
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class SimklPullService(PullService):
    service_name = 'simkl'

    # Same client ID as littlerabite
    CLIENT_ID = '63bb65010c3bcc25a9947aaebba0e7048508186c15b39bec87001d62e1739a58'
    BASE_URL  = 'https://api.simkl.com'

    def __init__(self, database):
        super().__init__(database)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _make_request(self, method, endpoint, data=None, params=None, silent_404=False):
        """
        Make API request. Returns parsed JSON dict/list or None.

        silent_404=True suppresses the error log for 404 responses.
        Used when probing endpoints (e.g. trying /shows/ vs /anime/).
        """
        url = f'{self.BASE_URL}{endpoint}'
        headers = {
            'Content-Type': 'application/json',
            'simkl-api-key': self.CLIENT_ID
        }
        token = self._get_token()
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            resp = requests.request(
                method=method, url=url, headers=headers,
                json=data, params=params, timeout=30
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get('Retry-After', 60))
                self._log(f'Rate limited, waiting {wait}s', xbmc.LOGWARNING if KODI_ENV else None)
                time.sleep(wait)
                return None
            if resp.status_code == 401:
                self._log('Unauthorized', xbmc.LOGWARNING if KODI_ENV else None)
                return None
            if resp.status_code == 404:
                # 404 is expected when probing the wrong endpoint type
                # (e.g. looking up an anime ID under /shows/ or vice versa)
                if not silent_404:
                    self._log(f'Not found: {endpoint}', xbmc.LOGDEBUG if KODI_ENV else None)
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            self._log(f'Request failed: {e}', xbmc.LOGERROR if KODI_ENV else None)
            return None

    def _get(self, endpoint, params=None, silent_404=False):
        return self._make_request('GET', endpoint, params=params, silent_404=silent_404)

    # ------------------------------------------------------------------
    # AUTH - PIN Flow (matches littlerabite SimklService.authenticate exactly)
    # ------------------------------------------------------------------

    def authenticate(self):
        """Simkl PIN-based OAuth flow."""
        if not KODI_ENV:
            return False

        dialog     = xbmcgui.Dialog()
        prog_dlg   = xbmcgui.DialogProgress()

        # Step 1: Request PIN - NOTE: params go as query string, not body
        pin_data = self._make_request('GET', '/oauth/pin', params={'client_id': self.CLIENT_ID})

        if not pin_data or 'user_code' not in pin_data:
            dialog.ok('Simkl Authentication', 'Failed to generate PIN. Please try again.')
            return False

        user_code        = pin_data['user_code']
        verification_url = pin_data.get('verification_url', 'https://simkl.com/pin')
        expires_in       = pin_data.get('expires_in', 300)
        interval         = pin_data.get('interval', 5)

        # Step 2: Show dialog
        message = (
            f'Visit: {verification_url}\n'
            f'Enter code: {user_code}\n\n'
            f'Waiting for authorization...'
        )
        prog_dlg.create('Simkl Authentication', message)

        # Step 3: Poll - /oauth/pin/{user_code} (NOT device_code)
        max_attempts = int(expires_in / interval)
        params = {'client_id': self.CLIENT_ID}

        for attempt in range(max_attempts):
            if prog_dlg.iscanceled():
                prog_dlg.close()
                dialog.ok('Authentication Cancelled', 'You cancelled the authentication.')
                return False

            progress_pct   = int((attempt / max_attempts) * 100)
            time_remaining = expires_in - (attempt * interval)
            prog_dlg.update(
                progress_pct,
                f'{message}\n\nCode expires in {time_remaining} seconds'
            )

            time.sleep(interval)

            # Poll endpoint uses user_code in path, not device_code
            poll_data = self._make_request('GET', f'/oauth/pin/{user_code}', params=params)

            if poll_data and poll_data.get('result') == 'OK':
                access_token = poll_data.get('access_token')
                if not access_token:
                    prog_dlg.close()
                    dialog.ok('Authentication Failed', 'No access token received.')
                    return False

                # Temporarily save to get user info
                self.db.store_auth(self.service_name, token=access_token)

                user_settings = self._make_request('GET', '/users/settings')
                prog_dlg.close()

                if user_settings and user_settings.get('user'):
                    u = user_settings['user']
                    username = u.get('name', 'Unknown')
                    self.db.store_auth(
                        service=self.service_name,
                        token=access_token,
                        user_data={'username': username, 'user_id': u.get('simkl_id')}
                    )
                    self._log(f'Authenticated as {username}')
                    dialog.ok('Authentication Successful', f'Logged in as: {username}')
                    return True
                else:
                    self.db.store_auth(self.service_name, token=access_token)
                    self._log('Authenticated (no user info)')
                    return True

        prog_dlg.close()
        dialog.ok('Authentication Failed', 'PIN code expired. Please try again.')
        return False

    def refresh_token(self):
        # Simkl tokens don't expire
        return True

    # ------------------------------------------------------------------
    # PULL - Main entry point
    # ------------------------------------------------------------------

    def pull_watchlist(self):
        """Pull Simkl lists needed to populate the DB for all browse views."""
        if not self.is_authenticated():
            return []

        items = []
        for status in ('watching', 'plantowatch', 'completed', 'dropped'):
            items.extend(self._pull_by_status(status))

        self._log(f'Pulled {len(items)} items from Simkl')
        return items

    def _pull_by_status(self, status):
        """Pull items by list status from /sync/all-items/{status}."""
        resp = self._get(f'/sync/all-items/{status}', params={'extended': 'full'})
        if not resp:
            return []

        list_status_map = {
            'watching':    'watching',
            'plantowatch': 'watchlist',
            'completed':   'watched',
            'dropped':     'dropped'
        }
        mapped_status = list_status_map.get(status, status)
        items = []

        for media_key in ('movies', 'shows', 'anime'):
            for entry in resp.get(media_key, []):
                try:
                    items.append(self._normalize_entry(entry, media_key, mapped_status))
                except Exception as e:
                    self._log(f'Normalize error ({media_key}): {e}', xbmc.LOGWARNING if KODI_ENV else None)

        return items

    def _pull_episode_progress(self):
        """
        Pull episode-level watched history for both shows and anime.
        Stores ONE row per show/anime (the most recently watched episode).
        """
        items = []
        for endpoint, media_key in [('/sync/watched/shows', 'shows'), ('/sync/watched/anime', 'anime')]:
            resp = self._get(endpoint, params={'extended': 'full'})
            if not resp or not isinstance(resp, list):
                continue

            for entry in resp:
                try:
                    show_obj   = entry.get('show') or entry.get('anime') or {}
                    show_ids   = show_obj.get('ids', {})
                    show_title = show_obj.get('title', 'Unknown')
                    show_year  = show_obj.get('year')
                    svc_ids    = self._build_ids(show_ids)
                    simkl_id   = show_ids.get('simkl')

                    # Fetch full details for plot + poster + fanart
                    plot, poster, fanart = self._fetch_show_details(simkl_id, show_obj, media_key=media_key)

                    # Find the most recently watched episode
                    latest_season  = None
                    latest_episode = None
                    latest_at      = None

                    for season_data in entry.get('seasons', []):
                        season_num = season_data.get('number', 1)
                        if season_num == 0:
                            continue  # skip specials
                        for ep in season_data.get('episodes', []):
                            ep_num         = ep.get('number')
                            watched_at_raw = ep.get('watched_at')
                            if not watched_at_raw:
                                continue  # episode has no timestamp — not reliably watched
                            watched_at = self._parse_time(watched_at_raw)
                            if watched_at is None:
                                continue
                            if latest_at is None or watched_at > latest_at:
                                latest_at      = watched_at
                                latest_season  = season_num
                                latest_episode = ep_num

                    if latest_season is None:
                        continue

                    items.append({
                        'service_ids':     svc_ids,
                        'media_type':      'episode',
                        'title':           f'S{latest_season:02d}E{latest_episode:02d}',
                        'show_title':      show_title,
                        'year':            show_year,
                        'season':          latest_season,
                        'episode':         latest_episode,
                        'resume_pct':      100,
                        'resume_time':     0,
                        'completed':       1,
                        'list_status':     'watched',
                        'last_watched_at': latest_at,
                        'poster':          poster,
                        'fanart':          fanart,
                        'plot':            plot,
                        'duration':        0,
                        '_service':        'simkl'
                    })
                except Exception as e:
                    self._log(f'Episode progress error ({media_key}): {e}',
                              xbmc.LOGWARNING if KODI_ENV else None)

        return items

    def _fetch_show_details(self, simkl_id, fallback_obj=None, media_key='shows'):
        """
        Fetch full details for plot, poster, fanart.

        For movies: hits /movies/{id} directly.
        For shows/anime: tries the correct endpoint first, falls back to the other.
        404 responses are suppressed — expected when probing the wrong type.

        Returns (plot, poster_url, fanart_url).
        """
        plot = poster = fanart = None

        if simkl_id:
            if media_key == 'movies':
                endpoints = ['movies']
            elif media_key == 'anime':
                endpoints = ['anime', 'shows']
            else:
                endpoints = ['shows', 'anime']

            data = None
            for ep_type in endpoints:
                data = self._get(
                    f'/{ep_type}/{simkl_id}',
                    params={'extended': 'full'},
                    silent_404=True
                )
                if data:
                    break

            if data:
                plot = data.get('overview') or data.get('en_overview') or None

                poster_path = data.get('poster')
                if poster_path:
                    poster = f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg'

                fanart_list = data.get('fanart') or []
                if isinstance(fanart_list, list) and fanart_list:
                    fp = fanart_list[0].get('full') or fanart_list[0].get('medium')
                    if fp:
                        fanart = fp if fp.startswith('http') else f'https://simkl.in/fanart/{fp}_w.jpg'
                elif isinstance(fanart_list, str) and fanart_list:
                    fanart = (fanart_list if fanart_list.startswith('http')
                              else f'https://wsrv.nl/?url=https://simkl.in/fanart/{fanart_list}_w.jpg')

        # Fallback to fields already on the list-item object
        if fallback_obj:
            if not plot:
                plot = fallback_obj.get('overview') or fallback_obj.get('en_title') or None
            if not poster:
                pp = fallback_obj.get('poster')
                if pp:
                    poster = (pp if pp.startswith('http')
                              else f'https://wsrv.nl/?url=https://simkl.in/posters/{pp}_m.jpg')
            if not fanart:
                fp = fallback_obj.get('fanart') or fallback_obj.get('cover')
                if fp and isinstance(fp, str):
                    fanart = (fp if fp.startswith('http')
                              else f'https://wsrv.nl/?url=https://simkl.in/fanart/{fp}_w.jpg')

        return plot, poster, fanart

    def _compute_season_episode(self, simkl_id, watched_eps, total_eps, media_key='shows'):
        """
        Map flat watched_episodes_count → real (season, episode).
        Uses /anime/{id}/episodes or /shows/{id}/episodes depending on media_key.
        Falls back to (1, watched_eps+1) on failure.

        404s are silent — expected when probing the wrong endpoint type.
        """
        if not simkl_id or watched_eps is None:
            return 1, (watched_eps + 1 if watched_eps is not None else 1)

        primary   = 'anime' if media_key == 'anime' else 'shows'
        secondary = 'shows' if primary == 'anime' else 'anime'

        eps_data = None
        for ep_type in (primary, secondary):
            eps_data = self._get(
                f'/{ep_type}/{simkl_id}/episodes',
                params={'extended': 'full'},
                silent_404=True
            )
            if eps_data and isinstance(eps_data, list):
                break
            eps_data = None

        if not eps_data:
            return 1, watched_eps + 1

        # Filter specials (season 0), keep normal episodes in order
        episodes = [e for e in eps_data if e.get('season', 1) != 0]

        if watched_eps > 0 and watched_eps <= len(episodes):
            last = episodes[watched_eps - 1]
            return last.get('season', 1), last.get('episode', watched_eps)
        elif watched_eps == 0 and episodes:
            return episodes[0].get('season', 1), episodes[0].get('episode', 1)

        return 1, watched_eps + 1

    def _normalize_entry(self, entry, media_key, list_status):
        is_movie = (media_key == 'movies')
        obj      = entry.get('movie') or entry.get('show') or entry.get('anime') or {}
        ids      = obj.get('ids', {})
        title    = obj.get('title', 'Unknown')
        year     = obj.get('year')
        simkl_id = ids.get('simkl')

        # Fetch full details for plot + poster + fanart
        plot, poster, fanart = self._fetch_show_details(simkl_id, obj, media_key=media_key)

        watched_eps = entry.get('watched_episodes_count', 0) or 0
        total_eps   = entry.get('total_episodes_count', 0) or obj.get('total_episodes', 0) or 0

        if total_eps > 0 and watched_eps > 0:
            resume_pct = min(int((watched_eps / total_eps) * 100), 99)
        else:
            resume_pct = 0

        completed = (list_status == 'watched')
        if completed:
            resume_pct = 100

        # Compute real season/episode via episode list API
        if not is_movie:
            use_season, use_episode = self._compute_season_episode(
                simkl_id, watched_eps, total_eps, media_key=media_key
            )
        else:
            use_season = use_episode = None

        return {
            'service_ids':     self._build_ids(ids),
            'media_type':      'movie' if is_movie else 'episode',
            'title':           title,
            'show_title':      None if is_movie else title,
            'year':            year,
            'season':          use_season,
            'episode':         use_episode,
            'resume_pct':      resume_pct,
            'resume_time':     0,
            'completed':       1 if completed else 0,
            'list_status':     list_status,
            'last_watched_at': self._parse_time(entry.get('last_watched_at')),
            'poster':          poster,
            'fanart':          fanart,
            'plot':            plot,
            'duration':        0,
            '_service':        'simkl',
            '_watched_eps':    watched_eps,
            '_total_eps':      total_eps
        }

    # ------------------------------------------------------------------
    # FAST SYNC (JIT - only watching items)
    # ------------------------------------------------------------------

    def pull_fast_watching(self):
        """
        Fast sync: only fetch actively-watching items.
        Called by pull_fast_continue_watching — no dialog, no full pull.
        """
        if not self.is_authenticated():
            return []
        try:
            return self._pull_by_status('watching')
        except Exception as e:
            self._log(f'pull_fast_watching error: {e}',
                      xbmc.LOGWARNING if KODI_ENV else None)
        return []

    def pull_fast_watchlist(self):
        """
        Fast sync: only fetch plan-to-watch items.
        Called by pull_fast_watchlist in PullManager.
        """
        if not self.is_authenticated():
            return []
        try:
            return self._pull_by_status('plantowatch')
        except Exception as e:
            self._log(f'pull_fast_watchlist error: {e}',
                      xbmc.LOGWARNING if KODI_ENV else None)
        return []

    # ------------------------------------------------------------------
    # BROWSE (live fetch for UI) - matches littlerabite SimklService
    # ------------------------------------------------------------------

    def fetch_all_items(self, content_type, status):
        """
        Fetch items of a specific content_type and status live from Simkl.
        content_type: 'shows', 'anime', or 'movies'
        status: 'watching', 'plantowatch', 'completed', 'hold', 'dropped'

        Simkl API endpoint is /sync/all-items/{status} — content_type is NOT
        part of the URL path, it is a key in the JSON response body.
        Returns raw list from data[content_type].
        Matches littlerabite SimklService.fetch_all_items.
        """
        if not self.is_authenticated():
            return []
        data = self._get(f'/sync/all-items/{status}', params={'extended': 'full'})
        if not data:
            return []
        return data.get(content_type, [])

    def fetch_list_by_status(self, status):
        """Live fetch for browse UI. Returns raw Simkl response dict."""
        status_map = {
            'watching':  'watching',
            'watchlist': 'plantowatch',
            'watched':   'completed',
            'dropped':   'dropped'
        }
        simkl_status = status_map.get(status, status)
        return self._get(f'/sync/all-items/{simkl_status}', params={'extended': 'full'}) or {}

    # ------------------------------------------------------------------
    # UTILS
    # ------------------------------------------------------------------

    def _build_ids(self, ids_dict):
        return {k: v for k, v in {
            'simkl':   ids_dict.get('simkl'),
            'mal':     ids_dict.get('mal'),
            'tmdb':    ids_dict.get('tmdb'),
            'imdb':    ids_dict.get('imdb'),
            'tvdb':    ids_dict.get('tvdb'),
            'anilist': ids_dict.get('anilist'),
        }.items() if v}

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
