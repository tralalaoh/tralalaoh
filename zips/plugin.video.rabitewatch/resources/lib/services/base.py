# -*- coding: utf-8 -*-
"""
Rabite Watch - Base Service
Auth helpers shared by all pull-only services.
"""

import time
from abc import ABC, abstractmethod

try:
    import xbmc
    import xbmcaddon
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class PullService(ABC):
    """
    Abstract base for pull-only services (Trakt, AniList, Simkl).
    Handles auth storage. No scrobble methods.
    """

    service_name = 'base'

    def __init__(self, database):
        self.db = database
        self._user_data = None

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    def is_authenticated(self):
        auth = self.db.get_auth(self.service_name)
        return auth is not None and auth.get('token') is not None

    def token_needs_refresh(self):
        return self.db.is_token_expired(self.service_name)

    def logout(self):
        self.db.delete_auth(self.service_name)
        self._user_data = None
        self._log('Logged out')
        return True

    def get_user_data(self):
        if self._user_data is None:
            auth = self.db.get_auth(self.service_name)
            if auth:
                self._user_data = auth.get('user_data')
        return self._user_data

    # ------------------------------------------------------------------
    # ABSTRACT
    # ------------------------------------------------------------------

    @abstractmethod
    def authenticate(self):
        """Start auth flow. Returns bool."""
        pass

    @abstractmethod
    def refresh_token(self):
        """Refresh OAuth token. Returns bool."""
        pass

    @abstractmethod
    def pull_watchlist(self):
        """
        Pull all lists from service.
        Returns list of dicts with keys:
          service_ids, media_type, title, show_title, year, season, episode,
          poster, fanart, plot, duration, resume_pct, resume_time,
          completed, list_status, last_watched_at
        """
        pass

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_token(self):
        auth = self.db.get_auth(self.service_name)
        return auth.get('token') if auth else None

    def _log(self, msg, level=None):
        if KODI_ENV:
            if level is None:
                try:
                    debug = xbmcaddon.Addon(
                        'plugin.video.rabitewatch'
                    ).getSettingBool('debug_logging')
                except Exception:
                    debug = False
                level = xbmc.LOGINFO if debug else xbmc.LOGDEBUG
            xbmc.log(f'[RabiteWatch-{self.service_name}] {msg}', level)
        else:
            print(f'[{self.service_name}] {msg}')
