# -*- coding: utf-8 -*-
"""
Little Rabite - Sync Manager
Manages synchronization across multiple services (Trakt, AniList, Simkl).
Implements singleton pattern and provides unified sync/scrobble operations.
"""

import time
import xbmc
import xbmcaddon
from threading import Thread, Lock, Event
from typing import Dict, List, Optional, Any
import logging

try:
    from resources.lib.database import get_database
except ImportError:
    # For development
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from database import get_database

from resources.lib.services import TraktService, AniListService, SimklService

class SyncManager:
    """
    Singleton manager for coordinating sync operations across multiple services.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Singleton pattern - ensure only one instance exists."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SyncManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Initialize the sync manager (only once due to singleton)."""
        # Skip if already initialized
        if self._initialized:
            return

        self._initialized = True

        # Service registry
        self._services = {}  # Dict[str, SyncService]
        self._service_classes = {}  # Dict[str, type]

        # Threading
        self._sync_thread = None
        self._sync_lock = Lock()
        self._stop_event = Event()

        # Database
        self.db = get_database()

        # Addon for settings
        self.addon = xbmcaddon.Addon()

        # Sync state
        self._last_sync = {}  # Dict[str, int] - service_name -> timestamp
        self._is_syncing = False

        self.logger = logging.getLogger("LittleRabite SyncManager")
        self._log('SyncManager initialized (singleton)')

        # Register services
        self.register_service(TraktService)
        self.register_service(AniListService)
        self.register_service(SimklService)

    # ============================================================================
    # SERVICE REGISTRY
    # ============================================================================

    def register_service(self, service_class):
        """Register a service class."""
        service_name = service_class.__name__.replace('Service', '').lower()
        self._service_classes[service_name] = service_class
        self._log(f'Registered service class: {service_name}')

    def get_service(self, service_name: str):
        """Get or create a service instance."""
        service_name = service_name.lower()

        if service_name in self._services:
            return self._services[service_name]

        if service_name in self._service_classes:
            try:
                service_class = self._service_classes[service_name]
                service_instance = service_class(self.db)
                self._services[service_name] = service_instance
                self._log(f'Created service instance: {service_name}')
                return service_instance
            except Exception as e:
                self._log(f'Error creating service {service_name}: {str(e)}', xbmc.LOGERROR)
                return None

        self._log(f'Service not registered: {service_name}', xbmc.LOGWARNING)
        return None

    def get_enabled_services(self):
        """Get list of enabled services from settings."""
        enabled = []

        try:
            if self.addon.getSettingBool('trakt_enabled'):
                enabled.append('trakt')
        except Exception:
            pass

        try:
            if self.addon.getSettingBool('anilist_enabled'):
                enabled.append('anilist')
        except Exception:
            pass

        try:
            if self.addon.getSettingBool('simkl_enabled'):
                enabled.append('simkl')
        except Exception:
            pass

        return enabled

    def get_authenticated_services(self) -> List[str]:
        """Get list of authenticated services."""
        authenticated = []
        for service_name in self.get_enabled_services():
            service = self.get_service(service_name)
            if service and service.is_authenticated():
                authenticated.append(service_name)
        return authenticated

    # ============================================================================
    # UNIFIED SYNC OPERATIONS
    # ============================================================================

    def sync_all(self, force: bool = False, threaded: bool = True) -> Dict[str, Any]:
        """Sync all enabled and authenticated services."""
        if threaded:
            self._start_sync_thread(force)
            return {'status': 'started', 'threaded': True}
        else:
            return self._sync_all_internal(force)

    def sync_all_pull(self, silent=True):
        """Pull updates from all authorized services"""
        for name in self.get_authenticated_services():
            service = self.get_service(name)
            if service:
                try:
                    self._log(f"Starting sync PULL for {name}...")
                    service.sync_pull()
                except Exception as e:
                    self._log(f"Error pulling from {name}: {e}", xbmc.LOGERROR)

    def sync_all_push(self, silent=True):
        """Push local changes to all authorized services"""
        for name in self.get_authenticated_services():
            service = self.get_service(name)
            if service:
                try:
                    self._log(f"Starting sync PUSH for {name}...")
                    service.sync_push()
                except Exception as e:
                    self._log(f"Error pushing to {name}: {e}", xbmc.LOGERROR)

    def _start_sync_thread(self, force: bool = False):
        if self._is_syncing:
            self._log('Sync already in progress', xbmc.LOGWARNING)
            return

        def sync_worker():
            try:
                self._is_syncing = True
                self._sync_all_internal(force)
            except Exception as e:
                self._log(f'Sync thread error: {str(e)}', xbmc.LOGERROR)
            finally:
                self._is_syncing = False

        self._sync_thread = Thread(target=sync_worker, name='LittleRabite-SyncAll')
        self._sync_thread.daemon = True
        self._sync_thread.start()
        self._log('Started background sync thread')

    def _sync_all_internal(self, force: bool = False) -> Dict[str, Any]:
        with self._sync_lock:
            self._log('Starting sync_all...')
            results = {'pull': {}, 'push': {}, 'total_synced': 0, 'total_pushed': 0, 'errors': []}
            services = self.get_authenticated_services()

            if not services:
                self._log('No authenticated services to sync', xbmc.LOGWARNING)
                return results

            for service_name in services:
                try:
                    if not force and not self._should_sync(service_name):
                        continue

                    service = self.get_service(service_name)
                    if not service: continue

                    # Pull
                    pull_result = service.sync_pull()
                    results['pull'][service_name] = pull_result
                    if pull_result and pull_result.get('success'):
                        results['total_synced'] += pull_result.get('synced', 0)

                    # Push
                    push_result = service.sync_push()
                    results['push'][service_name] = push_result
                    if push_result and push_result.get('success'):
                        results['total_pushed'] += push_result.get('pushed', 0)

                    self._update_last_sync(service_name)
                except Exception as e:
                    results['errors'].append(f'{service_name}: {str(e)}')

            return results

    def _should_sync(self, service_name: str, min_interval: int = 300) -> bool:
        last_sync = self._last_sync.get(service_name, 0)
        return (int(time.time()) - last_sync) >= min_interval

    def _update_last_sync(self, service_name: str):
        self._last_sync[service_name] = int(time.time())

    # ============================================================================
    # SCROBBLE ROUTING (ADDED)
    # ============================================================================

    def scrobble_all(self, action, media_info, progress):
        """Route scrobble to all services."""
        results = {}
        for service_name in self.get_authenticated_services():
            try:
                service = self.get_service(service_name)
                if service:
                    if action == 'start':
                        results[service_name] = service.scrobble_start(media_info, progress)
                    elif action == 'pause':
                        results[service_name] = service.scrobble_pause(media_info, progress)
                    elif action == 'stop':
                        results[service_name] = service.scrobble_stop(media_info, progress)
            except Exception as e:
                self._log(f'Error scrobbling to {service_name}: {str(e)}', xbmc.LOGERROR)
        return results

    def _log(self, message: str, level: int = xbmc.LOGINFO):
        xbmc.log(f'[LittleRabite SyncManager] {message}', level)


# Singleton getter
def get_sync_manager() -> SyncManager:
    return SyncManager()
