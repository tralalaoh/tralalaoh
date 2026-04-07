# -*- coding: utf-8 -*-
"""
Rabite Watch - AniList Pull Service (WITH WINDOWXML QR AUTH)
Pulls watch lists and progress from AniList GraphQL API.
No scrobbling - read only.

Auth flow:
  - Native Kodi WindowXMLDialog with QR code on the right and
    step-by-step instructions on the left.
  - User scans the QR with their phone, authorizes on AniList,
    then pastes the token back into Kodi using Kore's keyboard
    (or any Kodi remote with keyboard support).
  - Token is verified against the AniList Viewer GraphQL query
    and stored in the local DB on success.
"""

import re
import requests
import time
import json
import os

from resources.lib.services.base import PullService

try:
    import xbmc
    import xbmcgui
    import xbmcvfs
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

GRAPHQL_URL = 'https://graphql.anilist.co'
AUTH_URL    = 'https://anilist.co/api/v2/oauth/authorize'
CLIENT_ID   = '35064'  # Same as plugin.video.littlerabite

ADDON_ID    = 'plugin.video.rabitewatch'

# Exact regex from the AniList Scrobbler Protocol specification.
# Header: "----- ANILIST SCROBBLER DATA -----"  (5 dashes, space, text, space, 5 dashes)
# Footer: "----------------------------------"   (exactly 34 dashes)
# Capture group 1 = the single JSON line between them.
_SCROBBLER_BLOCK_RE = re.compile(
    r'-{5} ANILIST SCROBBLER DATA -{5}\n'
    r'(.*?)\n'
    r'-{34}',
    re.DOTALL,
)


class AniListPullService(PullService):
    service_name = 'anilist'

    def __init__(self, database):
        super().__init__(database)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _graphql(self, query, variables=None, token=None):
        """Make a GraphQL request. Returns data dict or None."""
        if token is None:
            token = self._get_token()

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            resp = requests.post(
                GRAPHQL_URL,
                json={'query': query, 'variables': variables or {}},
                headers=headers,
                timeout=30
            )
            if resp.status_code == 429:
                wait = int(resp.headers.get('Retry-After', 60))
                self._log(f'Rate limited, waiting {wait}s', xbmc.LOGWARNING if KODI_ENV else None)
                time.sleep(wait)
                return None
            resp.raise_for_status()
            result = resp.json()
            if 'errors' in result:
                err = result['errors'][0].get('message', 'Unknown GraphQL error')
                self._log(f'GraphQL error: {err}', xbmc.LOGERROR if KODI_ENV else None)
                return None
            return result.get('data')
        except requests.exceptions.RequestException as e:
            self._log(f'Request error: {e}', xbmc.LOGERROR if KODI_ENV else None)
            return None

    # ------------------------------------------------------------------
    # AUTH - WindowXML QR Dialog
    # ------------------------------------------------------------------

    def authenticate(self):
        """
        Show the native Kodi WindowXML auth dialog with QR code.

        The dialog renders entirely inside Kodi:
          - QR code on the right pointing to the AniList OAuth URL
          - Step-by-step instructions on the left
          - Edit control auto-focused so Kore's keyboard works instantly
          - Confirm button verifies the token and saves to DB

        Falls back to a plain text input dialog if the WindowXML skin
        cannot be loaded (e.g. skin file missing during development).
        """
        if not KODI_ENV:
            return False

        try:
            return self._authenticate_with_window_dialog()
        except Exception as e:
            self._log(
                f'WindowXML auth dialog failed: {e} — falling back to text input',
                xbmc.LOGWARNING
            )
            return self._authenticate_with_text_fallback()

    def _authenticate_with_window_dialog(self):
        """
        Launch the WindowXMLDialog skin.
        Generates the QR PNG before opening so the image is ready on onInit().
        """
        auth_url = f'{AUTH_URL}?client_id={CLIENT_ID}&response_type=token'

        # Generate QR code PNG into Kodi temp dir
        qr_path = self._generate_qr_code(auth_url)

        # skin_path must be the addon ROOT only.
        # Kodi appends  resources/skins/<skin>/<res>/  automatically.
        # Passing the full path causes Kodi to double it up and fail.
        addon_path = xbmcvfs.translatePath(f'special://home/addons/{ADDON_ID}')

        dialog = _AniListWindowDialog(
            'DialogAniListAuth.xml',
            addon_path,
            'default',
            '1080i',
            db=self.db,
            graphql_fn=self._graphql,
            qr_path=qr_path,
            log_fn=self._log,
            service_name=self.service_name,
        )
        dialog.doModal()

        # Clean up temp QR file regardless of outcome
        self._cleanup_qr(qr_path)

        success = dialog.success
        del dialog
        return success

    def _authenticate_with_text_fallback(self):
        """
        Plain-text fallback used only when the WindowXML skin cannot load.
        Shows the auth URL and prompts for token via Kodi's built-in input dialog.
        """
        self._log('Using text-based authentication fallback')
        dialog   = xbmcgui.Dialog()
        auth_url = f'{AUTH_URL}?client_id={CLIENT_ID}&response_type=token'

        dialog.ok(
            'AniList Authentication',
            f'Please visit:\n\n{auth_url}\n\n'
            f'Authorize Rabite Watch, then paste the access_token from the URL.\n'
            f'Click OK when you have the token ready.'
        )
        token = dialog.input('Enter AniList Token', type=xbmcgui.INPUT_ALPHANUM)
        if not token or not token.strip():
            dialog.ok('Authentication Cancelled', 'No token provided.')
            return False
        return self._verify_and_save_token(token.strip())

    def _generate_qr_code(self, url):
        """Generate QR code PNG into Kodi temp dir. Returns real filesystem path or None."""
        if not QR_AVAILABLE:
            self._log('qrcode module not available — QR will not display', xbmc.LOGWARNING)
            return None
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=12,
                border=3,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color='black', back_color='white')

            temp_path = xbmcvfs.translatePath('special://temp/rabitewatch_anilist_qr.png')
            temp_dir  = os.path.dirname(temp_path)
            if not xbmcvfs.exists(temp_dir):
                xbmcvfs.mkdirs(temp_dir)

            img.save(temp_path)
            self._log(f'QR code saved to: {temp_path}')
            return temp_path
        except Exception as e:
            self._log(f'QR generation failed: {e}', xbmc.LOGERROR)
            return None

    def _cleanup_qr(self, path):
        """Delete the temp QR PNG."""
        try:
            if path and xbmcvfs.exists(path):
                xbmcvfs.delete(path)
        except Exception:
            pass

    def _verify_and_save_token(self, token):
        """
        Verify token against AniList Viewer query and persist to DB.
        Returns True on success, False otherwise.

        NOTE: This is called by both the WindowXML dialog (via the passed
        graphql_fn callback) and the text fallback.  It is safe to call
        directly because it uses self._graphql / self.db.
        """
        query = 'query { Viewer { id name } }'

        # Temporarily store so _graphql can pick it up via _get_token()
        old_auth = self.db.get_auth(self.service_name)
        self.db.store_auth(self.service_name, token=token)

        data = self._graphql(query)

        if data and data.get('Viewer'):
            viewer   = data['Viewer']
            user_id  = viewer['id']
            username = viewer['name']

            self.db.store_auth(
                service=self.service_name,
                token=token,
                user_data={'user_id': user_id, 'username': username}
            )
            self._log(f'Authenticated as {username} (ID: {user_id})')
            return True
        else:
            # Restore previous auth state if verification fails
            if old_auth:
                self.db.store_auth(
                    service=self.service_name,
                    token=old_auth.get('token'),
                    user_data=old_auth.get('user_data')
                )
            else:
                self.db.delete_auth(self.service_name)
            return False

    def refresh_token(self):
        # AniList implicit grant tokens don't expire / no refresh flow
        return True

    # ------------------------------------------------------------------
    # PULL
    # ------------------------------------------------------------------

    @staticmethod
    def parse_resume_point(notes):
        """
        Extract the scrobbler resume block from an AniList notes field.

        Expected format (always at the very end of the notes field):
            ----- ANILIST SCROBBLER DATA -----
            {"ep": 5, "resume": 1240, "total": 1450}
            ----------------------------------

        Returns a dict  {'ep': int, 'resume': int, 'total': int}  or None.

        Caller responsibilities (per protocol):
          • Check that returned ep == the episode the user is about to play.
          • Use resume as seekTime() position in seconds.
          • total == 0 means duration unknown — still offer resume, omit "/" part.
        """
        if not notes:
            return None

        match = _SCROBBLER_BLOCK_RE.search(notes)
        if not match:
            return None

        try:
            data = json.loads(match.group(1))
        except (ValueError, Exception):
            return None  # user may have manually edited notes — never crash

        try:
            ep     = int(data['ep'])
            resume = int(data['resume'])
            total  = int(data.get('total', 0))
        except (KeyError, TypeError, ValueError):
            return None

        # Sanity-check before handing values to the player
        if ep <= 0 or resume <= 0:
            return None
        if total > 0 and resume >= total:
            # Position is at or past the end — scrobbler should have cleared
            # this, but be defensive and treat it as no resume point.
            return None

        return {'ep': ep, 'resume': resume, 'total': total}

    def pull_watchlist(self):
        """Pull all MediaList entries from AniList."""
        if not self.is_authenticated():
            return []

        user_data = self.get_user_data()
        if not user_data or not user_data.get('user_id'):
            # Try to re-fetch user data
            query = '''query { Viewer { id name } }'''
            data = self._graphql(query)
            if data and data.get('Viewer'):
                user_data = {'user_id': data['Viewer']['id'], 'username': data['Viewer']['name']}
                auth = self.db.get_auth(self.service_name)
                self.db.store_auth(self.service_name, token=auth.get('token') if auth else None, user_data=user_data)
            else:
                self._log('Cannot get user data', xbmc.LOGERROR if KODI_ENV else None)
                return []

        user_id = user_data['user_id']
        all_items = []

        for status in ('CURRENT', 'COMPLETED', 'PLANNING', 'DROPPED', 'PAUSED'):
            try:
                entries = self._pull_status(user_id, status)
                all_items.extend(entries)
            except Exception as e:
                self._log(f'Error pulling status {status}: {e}', xbmc.LOGWARNING if KODI_ENV else None)

        self._log(f'Pulled {len(all_items)} items from AniList')
        return all_items

    def _pull_status(self, user_id, status):
        query = '''
        query ($userId: Int, $status: MediaListStatus) {
            MediaListCollection(userId: $userId, status: $status, type: ANIME) {
                lists {
                    entries {
                        id
                        status
                        progress
                        score
                        notes
                        updatedAt
                        media {
                            id
                            idMal
                            format
                            episodes
                            duration
                            title { romaji english userPreferred }
                            coverImage { extraLarge large }
                            bannerImage
                            description
                            startDate { year }
                        }
                    }
                }
            }
        }
        '''
        result = self._graphql(query, variables={'userId': int(user_id), 'status': status})
        if not result:
            return []

        entries = []
        for lst in result.get('MediaListCollection', {}).get('lists', []):
            for entry in lst.get('entries', []):
                try:
                    entries.append(self._normalize_entry(entry, status))
                except Exception as e:
                    self._log(f'Entry normalize error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
        return entries

    def _normalize_entry(self, entry, status):
        media      = entry.get('media', {})
        title_obj  = media.get('title', {})
        title = (title_obj.get('userPreferred') or
                 title_obj.get('romaji') or
                 title_obj.get('english') or 'Unknown')

        anilist_id      = media.get('id')
        mal_id          = media.get('idMal')
        total_eps       = media.get('episodes') or 0
        watched_eps     = entry.get('progress', 0)
        ep_duration_min = media.get('duration') or 24  # AniList reports minutes per episode
        is_movie        = media.get('format') == 'MOVIE'
        completed       = status == 'COMPLETED'

        # AniList tracks completed episode count only, not mid-episode position.
        # resume_pct is 0 unless the AniList Scrobbler Protocol embeds an exact
        # per-episode position in the entry's notes field (handled below).
        resume_pct = 100 if completed else 0

        status_map = {
            'CURRENT': 'watching', 'COMPLETED': 'watched',
            'PLANNING': 'watchlist', 'DROPPED': 'dropped', 'PAUSED': 'watching',
            'REPEATING': 'watching'
        }
        list_status = status_map.get(status, 'watchlist')

        cover  = media.get('coverImage', {})
        poster = cover.get('extraLarge') or cover.get('large')
        fanart = media.get('bannerImage') or poster

        desc = media.get('description', '') or ''
        for tag in ('<br>', '<br/>', '<i>', '</i>', '<b>', '</b>', '<p>', '</p>'):
            desc = desc.replace(tag, ' ')

        year_data = media.get('startDate', {})
        year      = year_data.get('year') if year_data else None

        # current_ep: the episode the user is currently ON.
        # AniList progress = completed episodes, so progress=3 means watching ep 3
        # (or just finished it). We mirror what AniList shows, not the next ep.
        # Edge case: progress=0 means they haven't started → show ep 1.
        next_ep    = watched_eps + 1 if not completed and watched_eps < (total_eps or 999) else total_eps
        current_ep = total_eps if completed else max(watched_eps, 1)

        # Default: no mid-episode resume position known.
        # resume_time MUST be 0 here — setting it to watched_eps * duration
        # would produce a series-total offset (e.g. 8640 s for 6×24 min) that
        # seekTime() would try to apply to the current episode (only 1440 s),
        # causing the player to skip past the end to the wrong episode.
        resume_time    = 0
        total_duration = ep_duration_min * 60  # single episode duration

        # --- AniList Scrobbler Protocol override ---
        # The scrobbler stores resume data for the episode the user is mid-way
        # through (always next_ep: AniList only increments progress on completion).
        # If scrobbler data exists, the user is actually mid-ep next_ep, so we
        # show that episode (overrides current_ep) with the exact resume position.
        notes     = entry.get('notes', '') or ''
        scrobbler = self.parse_resume_point(notes)
        if scrobbler and scrobbler.get('ep') == next_ep:
            current_ep  = next_ep               # user is mid-way through next ep
            resume_time = scrobbler['resume']   # exact seconds into the episode
            if scrobbler['total'] > 0:
                total_duration = scrobbler['total']  # exact episode duration
            # else: keep ep_duration_min * 60 — total unknown, omit in dialog
            # Compute per-episode resume % from scrobbler data
            if total_duration > 0:
                resume_pct = min(int((resume_time / total_duration) * 100), 99)
            self._log(
                f'Scrobbler override for {title} ep{current_ep}: '
                f'resume={resume_time}s / total={total_duration}s'
            )

        return {
            'service_ids': {
                'anilist': anilist_id,
                'mal': mal_id
            },
            'media_type': 'movie' if is_movie else 'episode',
            'title': title,
            'show_title': None if is_movie else title,
            'year': year,
            'season': None if is_movie else 1,
            'episode': None if is_movie else current_ep,
            'resume_pct': resume_pct,
            'resume_time': resume_time,
            'completed': 1 if completed else 0,
            'list_status': list_status,
            'last_watched_at': entry.get('updatedAt', int(time.time())),
            'poster': poster,
            'fanart': fanart,
            'plot': desc[:500] if desc else None,
            'duration': total_duration,
            '_service': 'anilist',
            '_watched_eps': watched_eps,
            '_total_eps': total_eps,
            '_score': entry.get('score', 0)
        }

    # ------------------------------------------------------------------
    # FAST SYNC (JIT - only CURRENT list)
    # ------------------------------------------------------------------

    def pull_fast_watching(self):
        """
        Fast sync: only fetch CURRENT (actively watching) anime.
        Called by pull_fast_continue_watching — no dialog, no full pull.
        """
        if not self.is_authenticated():
            return []

        user_data = self.get_user_data()
        if not user_data or not user_data.get('user_id'):
            return []

        try:
            return self._pull_status(user_data['user_id'], 'CURRENT')
        except Exception as e:
            self._log(f'pull_fast_watching error: {e}', xbmc.LOGERROR if KODI_ENV else None)
            return []

    def pull_fast_watchlist(self):
        """
        Fast sync: only fetch PLANNING (watchlisted) anime.
        Called by pull_fast_watchlist in PullManager.
        """
        if not self.is_authenticated():
            return []

        user_data = self.get_user_data()
        if not user_data or not user_data.get('user_id'):
            return []

        try:
            return self._pull_status(user_data['user_id'], 'PLANNING')
        except Exception as e:
            self._log(f'pull_fast_watchlist error: {e}', xbmc.LOGWARNING if KODI_ENV else None)
            return []

    # ------------------------------------------------------------------
    # BROWSE (live fetch for UI)
    # ------------------------------------------------------------------

    def fetch_list_by_status(self, user_id, status):
        """Live fetch for browse UI. Returns raw AniList entries."""
        query = '''
        query ($userId: Int, $status: MediaListStatus) {
            MediaListCollection(userId: $userId, status: $status, type: ANIME) {
                lists {
                    entries {
                        id
                        status
                        progress
                        score
                        notes
                        updatedAt
                        media {
                            id
                            idMal
                            episodes
                            duration
                            title { romaji english userPreferred }
                            coverImage { extraLarge large }
                            bannerImage
                            description
                            startDate { year }
                        }
                    }
                }
            }
        }
        '''
        result = self._graphql(query, variables={'userId': int(user_id), 'status': status})
        if not result:
            return []
        entries = []
        for lst in result.get('MediaListCollection', {}).get('lists', []):
            entries.extend(lst.get('entries', []))
        return entries


# ══════════════════════════════════════════════════════════════════════════════
# WindowXML Dialog — lives in this file to avoid any import path issues
# Skin XML: resources/skins/Default/1080i/DialogAniListAuth.xml
# ══════════════════════════════════════════════════════════════════════════════

# Control IDs — must match DialogAniListAuth.xml exactly
#   100  <control type="image">   QR code image
#   200  <control type="label">   status / feedback text
#   300  <control type="button">  "Enter Token"
#   301  <control type="button">  "Cancel"
_ID_QR_IMAGE     = 100
_ID_STATUS_LABEL = 200
_ID_ENTER_BTN    = 300
_ID_CANCEL_BTN   = 301


class _AniListWindowDialog(xbmcgui.WindowXMLDialog if KODI_ENV else object):
    """
    Internal WindowXMLDialog subclass.
    Only instantiated when KODI_ENV is True (Kodi is running).

    Constructor params (passed as kwargs to avoid colliding with the
    positional xml/path args that Kodi's WindowXMLDialog.__new__ requires):
        db          — WatchDatabase instance
        graphql_fn  — bound method AniListPullService._graphql
        qr_path     — real filesystem path to the generated QR PNG (or None)
        log_fn      — bound method AniListPullService._log
        service_name — 'anilist'
    """

    def __init__(self, xml_file, xml_path,
                 default_skin='default', default_res='1080i',
                 db=None, graphql_fn=None, qr_path=None,
                 log_fn=None, service_name='anilist'):
        if KODI_ENV:
            super().__init__(xml_file, xml_path, default_skin, default_res)
        self.db           = db
        self._graphql     = graphql_fn
        self.qr_path      = qr_path
        self._log_fn      = log_fn
        self.service_name = service_name
        self.success      = False  # caller reads this after doModal() returns

    # ── Kodi lifecycle ────────────────────────────────────────────────────

    def onInit(self):
        """Called by Kodi once the XML is fully rendered."""
        # Load QR image into control 100
        try:
            qr_ctrl = self.getControl(_ID_QR_IMAGE)
            if self.qr_path and xbmcvfs.exists(self.qr_path):
                qr_ctrl.setImage(self.qr_path)
            else:
                # Fallback: show the AniList logo so the dialog isn't broken
                fallback = (
                    f'special://home/addons/{ADDON_ID}/media/anilist.png'
                )
                qr_ctrl.setImage(fallback)
                self._set_status(
                    'QR unavailable — use the URL below',
                    color='FFFFFF4A'
                )
        except Exception as e:
            self._log(f'onInit QR image error: {e}', xbmc.LOGWARNING)

        # Small delay so all textures finish loading before we attempt to focus.
        # Without this, Kodi can raise "Control X has been asked to focus, but
        # it can't" because the control tree isn't fully rendered yet.
        xbmc.sleep(100)

        # Focus the Enter Token button so the remote's select key opens the
        # keyboard immediately. Buttons are focusable; labels are not.
        try:
            self.setFocus(self.getControl(_ID_ENTER_BTN))
        except Exception as e:
            self._log(f'onInit setFocus error: {e}', xbmc.LOGWARNING)

    def onClick(self, control_id):
        if control_id == _ID_ENTER_BTN:
            self._handle_enter_token()
        elif control_id == _ID_CANCEL_BTN:
            self.close()

    def onAction(self, action):
        # Back button / Escape closes without authenticating
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU,
                               xbmcgui.ACTION_NAV_BACK):
            self.close()

    # ── Token handling ────────────────────────────────────────────────────

    def _handle_enter_token(self):
        """Open the system keyboard dialog so the user can paste their token."""
        token = xbmcgui.Dialog().input(
            'Paste your AniList token',
            type=xbmcgui.INPUT_ALPHANUM,
        )

        if not token or not token.strip():
            return  # user pressed Cancel in the keyboard dialog — do nothing

        token = token.strip()
        self._set_status('Verifying token…', color='FF02A9FF')

        if self._verify_and_save(token):
            self._set_status('[COLOR FF3EE8A0]✓  Authenticated![/COLOR]')
            self.success = True
            xbmc.sleep(1000)
            self.close()
        else:
            self._set_status('Invalid token — please try again.', color='FFFF6B9D')
            xbmcgui.Dialog().notification(
                'Rabite Watch', 'Token verification failed.',
                xbmcgui.NOTIFICATION_ERROR, 3000
            )

    def _verify_and_save(self, token):
        """
        Call the AniList Viewer query via the service's _graphql method
        (passed in at construction), then save to DB on success.
        Returns True on success.
        """
        query = 'query { Viewer { id name } }'

        # Temporarily store the token so _graphql's _get_token() picks it up
        old_auth = self.db.get_auth(self.service_name)
        self.db.store_auth(self.service_name, token=token)

        try:
            data = self._graphql(query)
        except Exception as e:
            self._log(f'GraphQL call error during verification: {e}', xbmc.LOGERROR)
            data = None

        if data and data.get('Viewer'):
            viewer   = data['Viewer']
            user_id  = viewer['id']
            username = viewer['name']
            self.db.store_auth(
                service=self.service_name,
                token=token,
                user_data={'user_id': user_id, 'username': username}
            )
            self._log(f'Authenticated as {username} (ID: {user_id})')
            return True
        else:
            # Roll back: restore previous auth state
            if old_auth:
                self.db.store_auth(
                    service=self.service_name,
                    token=old_auth.get('token'),
                    user_data=old_auth.get('user_data')
                )
            else:
                self.db.delete_auth(self.service_name)
            return False

    # ── Helpers ───────────────────────────────────────────────────────────

    def _set_status(self, text, color='FF02A9FF'):
        """Update the status label (control 200)."""
        try:
            label = f'[COLOR {color}]{text}[/COLOR]' if not text.startswith('[COLOR') else text
            self.getControl(_ID_STATUS_LABEL).setLabel(label)
        except Exception:
            pass

    def _log(self, msg, level=None):
        if self._log_fn:
            self._log_fn(msg, level)
        elif KODI_ENV:
            xbmc.log(f'[RabiteWatch-AniListDialog] {msg}', level or xbmc.LOGINFO)
