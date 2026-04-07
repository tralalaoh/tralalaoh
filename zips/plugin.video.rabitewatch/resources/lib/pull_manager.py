
# -*- coding: utf-8 -*-
"""
Rabite Watch - Pull Manager
Orchestrates data pulls from all connected services and stores
merged resume data in the local database.
"""

import time
import threading
import concurrent.futures
import xbmc

try:
    import xbmcaddon
    import xbmcgui
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

from resources.lib.database import get_database
from resources.lib.services.trakt import TraktPullService
from resources.lib.services.anilist import AniListPullService
from resources.lib.services.simkl import SimklPullService


def _service_enabled(name):
    """Check the addon setting for service enable toggle."""
    if not KODI_ENV:
        return True
    try:
        return xbmcaddon.Addon('plugin.video.rabitewatch').getSettingBool(f'{name}_enabled')
    except Exception:
        val = xbmcaddon.Addon('plugin.video.rabitewatch').getSetting(f'{name}_enabled')
        return val.lower() != 'false'


class PullManager:
    """Singleton-like manager for pull services."""

    _instance = None

    def __init__(self):
        self.db = get_database()
        self._services = {
            'trakt': TraktPullService(self.db),
            'anilist': AniListPullService(self.db),
            'simkl': SimklPullService(self.db)
        }
        self._last_pull = {}
        self._last_fast_sync = 0  # fallback for non-Kodi env

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_service(self, name):
        return self._services.get(name)

    def get_authenticated_services(self):
        return [name for name, svc in self._services.items() if svc.is_authenticated()]

    # ------------------------------------------------------------------
    # SYNC ALL
    # ------------------------------------------------------------------

    def pull_all(self, force=False, min_interval=300):
        """
        Pull from all authenticated services.
        min_interval: seconds between pulls (default 5 min)

        Returns: dict with per-service results
        """
        results = {}
        for name, svc in self._services.items():
            if not _service_enabled(name):
                self._log(f'{name}: skipped (disabled in settings)')
                continue
            if not svc.is_authenticated():
                continue
            if not force:
                last = self._last_pull.get(name, 0)
                if time.time() - last < min_interval:
                    continue

            try:
                self._log(f'Pulling from {name}...')
                raw_items = svc.pull_watchlist()
                stored = 0
                for item in raw_items:
                    try:
                        self._store_item(item, name)
                        stored += 1
                    except Exception as e:
                        self._log(f'Error storing item from {name}: {e}', xbmc.LOGWARNING)

                self._last_pull[name] = int(time.time())
                results[name] = {'success': True, 'pulled': len(raw_items), 'stored': stored}
                self._log(f'{name}: pulled {len(raw_items)}, stored {stored}')

            except Exception as e:
                self._log(f'Pull error for {name}: {e}', xbmc.LOGERROR)
                results[name] = {'success': False, 'error': str(e)}

        # Enrich any unenriched DB rows so items have TMDB art/metadata
        # before the user opens the view, not only after.
        self._spawn_enrich_pending()

        return results

    def pull_service(self, name, force=True):
        """Pull from a single service."""
        svc = self._services.get(name)
        if not svc or not svc.is_authenticated():
            return {'success': False, 'error': 'Not authenticated'}

        try:
            raw_items = svc.pull_watchlist()
            stored = 0
            for item in raw_items:
                try:
                    self._store_item(item, name)
                    stored += 1
                except Exception as e:
                    self._log(f'Store error: {e}', xbmc.LOGWARNING)

            self._last_pull[name] = int(time.time())
            self._spawn_enrich_pending()
            return {'success': True, 'pulled': len(raw_items), 'stored': stored}
        except Exception as e:
            self._log(f'Pull error: {e}', xbmc.LOGERROR)
            return {'success': False, 'error': str(e)}

    def pull_startup(self, limit=5):
        """
        Smart startup sync — called once when Kodi starts (if sync_on_startup
        is enabled).

        Two modes:
        • DB is empty (first run / cleared): runs a full pull_all() to populate
          the database completely so Continue Watching is ready immediately.
        • DB has data: fast-refreshes only the `limit` most recently watched
          items from each connected service.  Cheap on API quotas, instant from
          the user's perspective because the widget is already populated from DB.

        `limit` comes from the 'startup_pull_limit' setting so the user can
        tune it without touching code.
        """
        stats = self.db.get_stats()
        if stats['total'] == 0:
            self._log('DB is empty — running full startup sync to populate')
            return self.pull_all(force=True)

        self._log(f'DB has {stats["total"]} items — fast startup sync (top {limit} per service)')

        active = [
            (name, svc)
            for name, svc in self._services.items()
            if _service_enabled(name) and svc.is_authenticated()
        ]
        if not active:
            self._log('Startup sync: no enabled+authenticated services — skipping')
            return {}
        self._log(f'Startup sync: active services — {[n for n,_ in active]}')

        def _fetch(name, svc):
            try:
                items = svc.pull_fast_watching()
                items.sort(key=lambda x: x.get('last_watched_at') or 0, reverse=True)
                recent = items[:limit]
                self._log(f'Startup {name}: {len(recent)} item(s) fetched')
                return name, recent
            except Exception as e:
                self._log(f'Startup fetch error ({name}): {e}', xbmc.LOGWARNING)
                return name, []

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as executor:
            future_to_name = {
                executor.submit(_fetch, name, svc): name
                for name, svc in active
            }
            for future in concurrent.futures.as_completed(future_to_name):
                try:
                    results.append(future.result())
                except Exception as e:
                    name = future_to_name[future]
                    self._log(f'Startup thread error ({name}): {e}', xbmc.LOGWARNING)

        total_stored = 0
        for name, raw_items in results:
            for item in raw_items:
                try:
                    self._store_item(item, name)
                    total_stored += 1
                except Exception as e:
                    self._log(f'Startup store error ({name}): {e}', xbmc.LOGWARNING)

        if total_stored > 0 and KODI_ENV:
            self._log(f'Startup sync: firing Container.Refresh ({total_stored} item(s) stored)')
            xbmc.executebuiltin('Container.Refresh')
        else:
            self._log('Startup sync: nothing new stored — skipping Container.Refresh')

        self._spawn_enrich_pending()
        self._log(f'Fast startup sync complete — {total_stored} item(s) stored')
        return {'fast_startup': True, 'stored': total_stored}

    def pull_fast_continue_watching(self, cooldown=60):
        """
        JIT fast sync: silently refresh only actively-watching items.

        Fetches from all active services in parallel via ThreadPoolExecutor,
        then stores results sequentially to avoid SQLite write contention.

        Cooldown is enforced via a Window(10000) property so the gate
        persists across multiple plugin invocations within the same Kodi
        session (each plugin call is a separate process).

        Args:
            cooldown: minimum seconds between fast syncs (default 60)
        """
        now = int(time.time())

        # --- Cooldown gate ---
        # Claim the timestamp *before* doing any work so that a concurrent
        # call (another plugin process or thread) sees the updated value and
        # skips, rather than both passing the gate and double-fetching.
        if KODI_ENV:
            win  = xbmcgui.Window(10000)
            prop = win.getProperty('RabiteWatch.LastFastSync')
            try:
                last = int(prop) if prop else 0
            except (ValueError, TypeError):
                last = 0
        else:
            last = self._last_fast_sync

        elapsed = now - last
        if elapsed < cooldown:
            self._log(f'JIT fast sync skipped — cooldown active ({elapsed}s < {cooldown}s)')
            return  # still fresh — nothing to do

        # Claim the slot immediately so concurrent callers skip.
        if KODI_ENV:
            win.setProperty('RabiteWatch.LastFastSync', str(now))
        else:
            self._last_fast_sync = now

        # Only spawn threads for services that are enabled and authenticated.
        # Check both conditions here, before touching the executor, so we never
        # submit a thread for a service that would immediately return nothing.
        active = [
            (name, svc)
            for name, svc in self._services.items()
            if _service_enabled(name) and svc.is_authenticated()
        ]

        if not active:
            self._log('JIT fast sync: no enabled+authenticated services — skipping')
            return

        self._log(f'JIT fast sync started (parallel, {len(active)} service(s)): {[n for n,_ in active]}')

        def _fetch(name, svc):
            """Fetch watching items from one service. Returns (name, items)."""
            try:
                items = svc.pull_fast_watching()
                self._log(f'Fast sync {name}: {len(items)} items fetched')
                return name, items
            except Exception as e:
                self._log(f'Fast sync fetch error ({name}): {e}', xbmc.LOGWARNING)
                return name, []

        # --- Parallel fetch ---
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as executor:
            future_to_name = {
                executor.submit(_fetch, name, svc): name
                for name, svc in active
            }
            for future in concurrent.futures.as_completed(future_to_name):
                try:
                    results.append(future.result())
                except Exception as e:
                    name = future_to_name[future]
                    self._log(f'Fast sync thread error ({name}): {e}', xbmc.LOGWARNING)

        # --- Sequential store (avoids SQLite write contention) ---
        stored_any = False
        for name, raw_items in results:
            for item in raw_items:
                try:
                    self._store_item(item, name)
                    stored_any = True
                except Exception as e:
                    self._log(f'Fast sync store error ({name}): {e}', xbmc.LOGWARNING)

        # Refresh the widget now so progress/new items appear immediately —
        # don't wait for the enricher, which only fires if landscape is missing.
        if stored_any and KODI_ENV:
            self._log('JIT fast sync: firing Container.Refresh')
            xbmc.executebuiltin('Container.Refresh')
        else:
            self._log('JIT fast sync: no new data stored — skipping Container.Refresh')

        # Enrich any unenriched items (including those just stored above).
        # Called directly — we are already running in a background thread.
        # The enricher fires a second Container.Refresh if art was added.
        self._run_enrich_pending()

    def pull_fast_watchlist(self, cooldown=120):
        """
        JIT fast sync for the Watchlist view: silently refresh only watchlist
        items (plantowatch / PLANNING / Trakt watchlist) from all active services.

        Same pattern as pull_fast_continue_watching:
        • Cooldown gate via Window(10000) property so it persists across plugin
          processes within the same Kodi session.
        • Parallel fetch via ThreadPoolExecutor.
        • Sequential SQLite store to avoid write contention.
        • Container.Refresh if anything new was stored.
        • enrich_pending() inline afterward (already in background thread).

        Args:
            cooldown: minimum seconds between watchlist syncs (default 120)
        """
        now = int(time.time())

        if KODI_ENV:
            win  = xbmcgui.Window(10000)
            prop = win.getProperty('RabiteWatch.LastWatchlistSync')
            try:
                last = int(prop) if prop else 0
            except (ValueError, TypeError):
                last = 0
        else:
            last = getattr(self, '_last_watchlist_sync', 0)

        elapsed = now - last
        if elapsed < cooldown:
            self._log(f'JIT watchlist sync skipped — cooldown active ({elapsed}s < {cooldown}s)')
            return

        # Claim the slot immediately so concurrent callers skip.
        if KODI_ENV:
            win.setProperty('RabiteWatch.LastWatchlistSync', str(now))
        else:
            self._last_watchlist_sync = now

        active = [
            (name, svc)
            for name, svc in self._services.items()
            if _service_enabled(name) and svc.is_authenticated()
        ]

        if not active:
            self._log('JIT watchlist sync: no enabled+authenticated services — skipping')
            return

        self._log(f'JIT watchlist sync started (parallel, {len(active)} service(s)): {[n for n,_ in active]}')

        def _fetch(name, svc):
            try:
                items = svc.pull_fast_watchlist()
                self._log(f'Watchlist sync {name}: {len(items)} items fetched')
                return name, items
            except Exception as e:
                self._log(f'Watchlist sync fetch error ({name}): {e}', xbmc.LOGWARNING)
                return name, []

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as executor:
            future_to_name = {
                executor.submit(_fetch, name, svc): name
                for name, svc in active
            }
            for future in concurrent.futures.as_completed(future_to_name):
                try:
                    results.append(future.result())
                except Exception as e:
                    name = future_to_name[future]
                    self._log(f'Watchlist sync thread error ({name}): {e}', xbmc.LOGWARNING)

        stored_any = False
        for name, raw_items in results:
            for item in raw_items:
                try:
                    self._store_item(item, name)
                    stored_any = True
                except Exception as e:
                    self._log(f'Watchlist sync store error ({name}): {e}', xbmc.LOGWARNING)

        if stored_any and KODI_ENV:
            self._log('JIT watchlist sync: firing Container.Refresh')
            xbmc.executebuiltin('Container.Refresh')
        else:
            self._log('JIT watchlist sync: no new data stored — skipping Container.Refresh')

        self._run_enrich_pending()

    def pull_post_playback(self, delay_s=5):
        """
        Post-playback cloud sync — fires once after the user stops or finishes
        a video.  Fetches only the 2 most recently watched items per service so
        the round-trip is cheap and doesn't hammer rate limits.

        Why delay_s=5?  Third-party Kodi scrobblers (e.g. the official Trakt
        addon) report the session to the cloud immediately on stop.  Waiting a
        few seconds before we pull ensures we see the updated position rather
        than the pre-session value.

        No cooldown gate — the caller (service.py) guarantees this runs at most
        once per playback session.  Resets LastFastSync afterward so the next
        JIT widget render doesn't immediately double-trigger the fast sync.
        """
        active = [
            (name, svc)
            for name, svc in self._services.items()
            if _service_enabled(name) and svc.is_authenticated()
        ]
        if not active:
            self._log('Post-playback sync: no enabled+authenticated services — skipping')
            return

        self._log(f'Post-playback sync: waiting {delay_s}s for scrobblers...')
        if delay_s > 0:
            time.sleep(delay_s)

        self._log(f'Post-playback sync started ({len(active)} service(s)): {[n for n,_ in active]}')

        def _fetch(name, svc):
            try:
                items = svc.pull_fast_watching()
                # Sort by most recently watched, take the top 2 only.
                items.sort(
                    key=lambda x: x.get('last_watched_at') or 0, reverse=True
                )
                recent = items[:2]
                self._log(f'Post-playback {name}: {len(recent)} item(s)')
                return name, recent
            except Exception as e:
                self._log(f'Post-playback fetch error ({name}): {e}', xbmc.LOGWARNING)
                return name, []

        # Parallel fetch across services
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(active)) as executor:
            future_to_name = {
                executor.submit(_fetch, name, svc): name
                for name, svc in active
            }
            for future in concurrent.futures.as_completed(future_to_name):
                try:
                    results.append(future.result())
                except Exception as e:
                    name = future_to_name[future]
                    self._log(f'Post-playback thread error ({name}): {e}', xbmc.LOGWARNING)

        # Sequential store to avoid SQLite write contention
        stored_any = False
        for name, raw_items in results:
            for item in raw_items:
                try:
                    self._store_item(item, name)
                    stored_any = True
                except Exception as e:
                    self._log(f'Post-playback store error ({name}): {e}', xbmc.LOGWARNING)

        # Reset JIT cooldown so the next widget render doesn't re-trigger
        # a redundant fast sync straight away.
        if KODI_ENV:
            xbmcgui.Window(10000).setProperty(
                'RabiteWatch.LastFastSync', str(int(time.time()))
            )
        else:
            self._last_fast_sync = int(time.time())

        if stored_any:
            if KODI_ENV:
                self._log('Post-playback sync: firing Container.Refresh')
                xbmc.executebuiltin('Container.Refresh')
            self._log('Post-playback sync complete — widget refreshed')
        else:
            self._log('Post-playback sync complete — nothing new to store')

    # ------------------------------------------------------------------
    # TMDB ENRICHMENT TRIGGERS
    # ------------------------------------------------------------------

    def _run_enrich_pending(self):
        """Run enrich_pending() inline (call only from a background thread)."""
        try:
            from resources.lib import tmdb_enricher
            tmdb_enricher.enrich_pending()
        except Exception as e:
            self._log(f'enrich_pending error: {e}', xbmc.LOGWARNING)

    def _spawn_enrich_pending(self):
        """Spawn enrich_pending() in a daemon thread (safe to call from main thread)."""
        try:
            threading.Thread(target=self._run_enrich_pending, daemon=True).start()
        except Exception as e:
            self._log(f'enrich_pending spawn error: {e}', xbmc.LOGWARNING)

    # ------------------------------------------------------------------
    # STORE
    # ------------------------------------------------------------------

    def _store_item(self, item, service_name):
        """Map a pulled item dict to db.upsert_progress."""
        self.db.upsert_progress(
            service_ids=item.get('service_ids', {}),
            media_type=item.get('media_type', 'movie'),
            title=item.get('title'),
            show_title=item.get('show_title'),
            year=item.get('year'),
            season=item.get('season'),
            episode=item.get('episode'),
            poster=item.get('poster'),
            fanart=item.get('fanart'),
            landscape=item.get('landscape'),
            clearlogo=item.get('clearlogo'),
            plot=item.get('plot'),
            duration=item.get('duration', 0),
            resume_pct=item.get('resume_pct', 0),
            resume_time=item.get('resume_time', 0),
            completed=item.get('completed', 0),
            list_status=item.get('list_status'),
            service_name=service_name,
            last_watched_at=item.get('last_watched_at')
        )

    def _log(self, msg, level=None):
        if level is None:
            try:
                debug = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingBool('debug_logging')
            except Exception:
                debug = False
            level = xbmc.LOGINFO if debug else xbmc.LOGDEBUG
        xbmc.log(f'[RabiteWatch-PullManager] {msg}', level)


def get_pull_manager():
    return PullManager.get_instance()
