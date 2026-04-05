# -*- coding: utf-8 -*-
import xbmc, xbmcgui
import json
from threading import Thread
from urllib.parse import quote as _url_quote
from modules.MDbList import MDbListAPI
from modules.OmDb import OmDbAPI
from modules.dominant_color import update_fanart_bgcolor


VALID_MEDIA_TYPES = ["movie", "tvshow", "season", "episode"]

empty_ratings = {
    "imdbRating": "",
    "imdbImage": "",
    "tomatoMeter": "",
    "tomatoImage": "",
    "tomatoUserMeter": "",
    "tomatoUserImage": "",
    "metascore": "",
    "metascoreImage": "",
    "tmdbRating": "",
    "tmdbImage": "",
    "popularRating": "",
    "popularImage": "",
    "omdbVotes": "",
    "traktRating": "",
    "traktImage": "",
    "letterboxdRating": "",
    "letterboxdImage": "",
    "awardWins": "",
    "awardImage": "",
}

empty_watch_status = {
    "rw.resumePct": "",
    "rw.resumeTime": "",
    "rw.completed": "",
    "rw.listStatus": "",
    "rw.sources": "",
}


def logger(message, level=1):
    xbmc.log(str(message), level)


class RatingsService(xbmc.Monitor):
    last_item_label = None
    last_set_id = None

    def __init__(self):
        super(RatingsService, self).__init__()
        self.window = xbmcgui.Window
        self.get_window_id = xbmcgui.getCurrentWindowId
        # Persistent instances for main-thread cache reads (SQLite reads are thread-safe with WAL)
        self._mdblist_api = MDbListAPI()
        self._omdb_api = OmDbAPI()
        from modules.rabitewatch_bridge import RabitewatchBridge
        self._rw_bridge = RabitewatchBridge()

    def get_infolabel(self, infolabel):
        return xbmc.getInfoLabel(infolabel)

    def get_visibility(self, condition):
        return xbmc.getCondVisibility(condition)

    def _get_label_safe(self, infolabel):
        try:
            return self.get_infolabel(infolabel)
        except Exception:
            return ""

    def get_item_id(self):
        imdb_id = self._get_label_safe("ListItem.IMDBNumber")
        if imdb_id and imdb_id.startswith("tt"):
            return (imdb_id, "imdb")
        tmdb_id = self._get_label_safe("ListItem.Property(tmdb_id)")
        if tmdb_id:
            return (tmdb_id, "tmdb")
        tvdb_id = self._get_label_safe("ListItem.Property(tvdb_id)")
        if tvdb_id:
            return (tvdb_id, "tvdb")
        return (None, None)

    def listitem_monitor(self):
        while not self.abortRequested():
            # Fast poll — detects item changes within 0.3s
            if self.waitForAbort(0.3):
                break

            if xbmc.getSkinDir() != "skin.littleduck":
                self.waitForAbort(15)
                continue

            if not self.get_visibility(
                "Window.IsVisible(videos) | Window.IsVisible(programs) | Window.IsVisible(home) | Window.IsVisible(11121)"
            ):
                continue

            if self.get_visibility("Container.Scrolling"):
                continue

            if self.get_visibility("Skin.HasSetting(TrailerPlaying)"):
                self.waitForAbort(3)
                while xbmc.Player().isPlaying():
                    if self.waitForAbort(0.5):
                        break
                xbmc.executebuiltin("Skin.ToggleSetting(TrailerPlaying)")
                continue

            current_label = self._get_label_safe("ListItem.Label")

            if current_label == self.last_item_label:
                continue

            self.last_item_label = current_label

            # Dominant color — runs on every item change, no API key needed
            fanart_art = self._get_label_safe("ListItem.Art(fanart)")
            update_fanart_bgcolor(fanart_art)

            # Ratings require an API key — skip if none configured
            api_key = self.get_infolabel("Skin.String(mdblist_api_key)")
            omdb_key = self.get_infolabel("Skin.String(omdb_api_key)")
            if not api_key and not omdb_key:
                continue

            current_window_id = self.get_window_id()
            window = self.window(current_window_id)
            set_property = window.setProperty
            get_property = window.getProperty

            # Always clear immediately on item change — prevents stale ratings/status showing
            for k, v in empty_ratings.items():
                set_property("littleduck.%s" % k, v)
            for k, v in empty_watch_status.items():
                set_property("littleduck.%s" % k, v)

            item_type = self._get_label_safe("ListItem.DBTYPE")
            logger("###littleduck DEBUG svc: window=%s label=%s DBTYPE=%s Content=%s" % (
                self.get_window_id(),
                current_label,
                item_type,
                self.get_infolabel("Container.Content"),
            ))
            if not item_type:
                item_type = self._get_label_safe("ListItem.Property(MediaType)")
                logger("###littleduck DEBUG svc: MediaType fallback=%s" % item_type)
            if not item_type:
                if self.get_visibility("Container.Content(movies)"):
                    item_type = "movie"
                elif self.get_visibility("Container.Content(tvshows)"):
                    item_type = "tvshow"
                elif self.get_visibility("Container.Content(seasons)"):
                    item_type = "season"
                elif self.get_visibility("Container.Content(episodes)"):
                    item_type = "episode"
                logger("###littleduck DEBUG svc: Content fallback=%s" % item_type)
            if not item_type or item_type.lower() not in VALID_MEDIA_TYPES:
                logger("###littleduck DEBUG svc: SKIP — item_type=%s not valid" % item_type)
                continue

            item_id, id_type = self.get_item_id()
            logger("###littleduck DEBUG svc: item_id=%s id_type=%s" % (item_id, id_type))
            if not item_id or not id_type:
                self.last_set_id = None
                continue

            cache_key = "%s:%s" % (id_type, item_id)

            # Rabitewatch bridge — L1 window cache then DB (read-only, main thread safe)
            rw_cache_key = "littleduck.cachedRW.%s" % cache_key
            if not get_property(rw_cache_key):
                rw_data = self._rw_bridge.find_by_id(id_type, item_id)
                if rw_data:
                    for k, v in rw_data.items():
                        set_property("littleduck.rw.%s" % k, v)
                    set_property(rw_cache_key, "1")

            # L1: window property cache — volatile but free (survives focus changes within session)
            cached_json = get_property("littleduck.cachedRatings.%s" % cache_key)
            if cached_json:
                try:
                    ratings_dict = json.loads(cached_json)
                    for k, v in ratings_dict.items():
                        set_property("littleduck.%s" % k, v)
                    self.last_set_id = cache_key
                    continue
                except Exception as e:
                    xbmc.log(f"###littleduck: Failed to parse cached ratings JSON: {e}", 3)

            # L2: SQLite cache — persistent across restarts, fast enough for main thread
            db_cached = self._mdblist_api.get_cached_info(item_id, id_type)
            if db_cached:
                logger("###littleduck: SQLite HIT for %s" % cache_key)
                for k, v in db_cached.items():
                    set_property("littleduck.%s" % k, v)
                # Promote to L1 so future window changes are free
                set_property("littleduck.cachedRatings.%s" % cache_key, json.dumps(db_cached))
                self.last_set_id = cache_key
                continue

            # Also check OMDb SQLite cache if we have an IMDb ID (OMDb is IMDb-only)
            if omdb_key and id_type == "imdb":
                omdb_cached = self._omdb_api.get_cached_info(item_id)
                if omdb_cached:
                    logger("###littleduck: OMDb SQLite HIT for %s" % item_id)
                    for k, v in omdb_cached.items():
                        set_property("littleduck.%s" % k, v)
                    set_property("littleduck.cachedRatings.%s" % cache_key, json.dumps(omdb_cached))
                    self.last_set_id = cache_key
                    continue

            # L3: API call — background thread only for network I/O
            logger("###littleduck: Cache MISS — API fetch for %s" % cache_key)
            Thread(
                target=self._fetch_and_set,
                args=(api_key, omdb_key, item_id, id_type, cache_key, current_window_id),
                daemon=True,
            ).start()

    def keyboard_monitor(self):
        """Polls the keyboard dialog edit control (id=312) while LiveSearchActive is set,
        updating Skin.String(SearchInput) in real-time for live search results."""
        monitor = xbmc.Monitor()
        last_text = ""
        while not monitor.abortRequested():
            if monitor.waitForAbort(0.35):
                break
            if not self.get_visibility("Skin.HasSetting(LiveSearchActive)"):
                last_text = ""
                continue
            if not self.get_visibility("Window.IsVisible(10001)"):
                continue
            try:
                text = xbmcgui.Window(10001).getControl(312).getText()
            except Exception as e:
                xbmc.log(f"###littleduck keyboard_monitor: {e}", 2)
                continue
            if text == last_text:
                continue
            last_text = text
            encoded = _url_quote(text)
            xbmc.executebuiltin(f"Skin.SetString(SearchInput,{text})")
            xbmc.executebuiltin(f"Skin.SetString(SearchInputEncoded,{encoded})")
            xbmc.executebuiltin(f"Skin.SetString(SearchInputTraktEncoded,{encoded})")

    def _fetch_and_set(self, api_key, omdb_key, item_id, id_type, cache_key, window_id):
        """Background thread: API calls only. Uses own DB instances for writes."""
        # Own instances for thread-safe writes
        mdb = MDbListAPI()
        omdb = OmDbAPI() if omdb_key and id_type == "imdb" else None

        mdb_result = {}
        omdb_result = {}

        def fetch_mdb():
            if api_key:
                mdb_result.update(mdb.get_result(item_id, id_type, api_key) or {})

        def fetch_omdb():
            if omdb:
                omdb_result.update(omdb.get_result(item_id, omdb_key) or {})

        # Fetch both APIs in parallel
        t_mdb = Thread(target=fetch_mdb, daemon=True)
        t_omdb = Thread(target=fetch_omdb, daemon=True)
        t_mdb.start()
        t_omdb.start()
        t_mdb.join()
        t_omdb.join()

        # Merge: MDbList is primary, OMDb fills gaps and adds omdbVotes
        result = mdb_result
        for k, v in omdb_result.items():
            if v and not result.get(k):
                result[k] = v

        if not result:
            logger("###littleduck: No ratings returned for %s" % cache_key, 2)
            return

        logger("###littleduck: Ratings fetched for %s" % cache_key)

        # Persist to SQLite
        mdb.insert_or_update_ratings(item_id, id_type, result)

        # Set window properties
        window = self.window(window_id)
        set_property = window.setProperty
        for k, v in result.items():
            set_property("littleduck.%s" % k, v)

        # Store in L1 cache
        set_property("littleduck.cachedRatings.%s" % cache_key, json.dumps(result))


logger("###littleduck: Ratings Service Started", 1)

# Favourites monitor — runs in background, sets Window(home).Property(LittleDuck.Fav.<tmdb_id>)
from modules.favourites_monitor import favourites_monitor
Thread(target=favourites_monitor, daemon=True).start()

_svc = RatingsService()
Thread(target=_svc.keyboard_monitor, daemon=True).start()
_svc.listitem_monitor()
logger("###littleduck: Ratings Service Finished", 1)
