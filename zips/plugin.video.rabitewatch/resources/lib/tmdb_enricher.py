# -*- coding: utf-8 -*-
"""
Rabite Watch - TMDB Metadata Enricher
Fetches rich metadata from TMDB: poster, fanart (backdrop), landscape,
clearlogo (via /images endpoint), plot, runtime, genres.

Activated by the 'tmdb_enrichment_enabled' addon setting.
API key is read from 'tmdb_api_key' setting (required — enrichment is skipped if not set).

Service metadata preferences (trakt_use_for_metadata, anilist_use_for_metadata,
simkl_use_for_metadata) control whether each service's own images/plot are kept
or overwritten by TMDB data.
"""

import requests
import concurrent.futures

try:
    import xbmc
    import xbmcaddon
    import xbmcgui
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

_BASE         = 'https://api.themoviedb.org/3'
_IMG          = 'https://image.tmdb.org/t/p/'


def _addon():
    try:
        return xbmcaddon.Addon('plugin.video.rabitewatch')
    except Exception:
        return None


def _setting_bool(key, default=True):
    if not KODI_ENV:
        return default
    a = _addon()
    if not a:
        return default
    try:
        return a.getSettingBool(key)
    except Exception:
        return a.getSetting(key).lower() == 'true'


def _api_key():
    if KODI_ENV:
        a = _addon()
        if a:
            try:
                key = a.getSetting('tmdb_api_key').strip()
                if key:
                    return key
            except Exception:
                pass
    return None


def is_enabled():
    return _setting_bool('tmdb_enrichment_enabled', True)


def _get(url, params):
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _pick_logo(logos):
    """Pick best clearlogo: English SVG > English PNG > any."""
    if not logos:
        return None
    best, best_score = None, -1
    for logo in logos:
        lang  = logo.get('iso_639_1') or 'null'
        fmt   = logo.get('file_type', '.png').lower()
        vote  = logo.get('vote_average', 0) or 0
        lang_score = 10 if lang == 'en' else (5 if lang in ('null', '', None) else 0)
        fmt_score  = 5  if fmt == '.svg' else (3 if fmt == '.png' else 0)
        score = lang_score + fmt_score + vote
        if score > best_score:
            best_score, best = score, logo
    if best:
        path = best.get('file_path', '')
        return f'{_IMG}original{path}' if path else None
    return None


def _resolve_anizip(anilist_id):
    """
    Fetch TMDB/IMDB/TVDB IDs from api.ani.zip for an AniList item.
    Returns a dict of found IDs (may be empty on failure).
    """
    try:
        resp = requests.get(
            f'https://api.ani.zip/mappings?anilist_id={anilist_id}',
            timeout=5,
        )
        if resp.status_code == 200:
            m = resp.json().get('mappings', {})
            ids = {}
            if m.get('themoviedb_id'):
                ids['tmdb'] = str(m['themoviedb_id'])
            if m.get('imdb_id'):
                ids['imdb'] = str(m['imdb_id'])
            if m.get('thetvdb_id'):
                ids['tvdb'] = str(m['thetvdb_id'])
            return ids
    except Exception:
        pass
    return {}


def enrich(tmdb_id, media_type, fetch_logo=True):
    """
    Fetch enriched metadata for a TMDB item.
    Returns dict: poster, fanart, landscape, clearlogo, plot, runtime_s, genres.
    """
    result = {
        'poster': None, 'fanart': None, 'landscape': None,
        'clearlogo': None, 'plot': None, 'runtime_s': None, 'genres': [],
    }
    if not tmdb_id:
        return result

    tmdb_type = 'movie' if media_type == 'movie' else 'tv'
    key = _api_key()
    if not key:
        return result

    data = _get(f'{_BASE}/{tmdb_type}/{tmdb_id}', {
        'api_key':                key,
        'language':               'en-US',
        'append_to_response':     'images',
        'include_image_language': 'en,null',
    })
    if not data:
        return result

    result['plot'] = data.get('overview') or None

    if tmdb_type == 'movie':
        rt = data.get('runtime')
    else:
        rts = data.get('episode_run_time') or []
        rt  = rts[0] if rts else data.get('runtime')
    if rt:
        result['runtime_s'] = int(rt) * 60

    result['genres'] = [g['name'] for g in data.get('genres', []) if g.get('name')]

    images    = data.get('images', {})
    posters   = images.get('posters',   [])
    backdrops = images.get('backdrops', [])
    logos     = images.get('logos',     [])

    pp = (posters[0].get('file_path')   if posters   else None) or data.get('poster_path')
    bp = (backdrops[0].get('file_path') if backdrops else None) or data.get('backdrop_path')

    if pp:
        result['poster'] = f'{_IMG}w500{pp}'
    if bp:
        result['fanart']    = f'{_IMG}original{bp}'
        result['landscape'] = f'{_IMG}w1280{bp}'
    elif media_type == 'movie' and result['poster']:
        result['fanart']    = result['poster']
        result['landscape'] = result['poster']

    if fetch_logo:
        if not logos:
            img_data = _get(f'{_BASE}/{tmdb_type}/{tmdb_id}/images', {
                'api_key': key, 'include_image_language': 'en,null',
            })
            if img_data:
                logos = img_data.get('logos', [])
        result['clearlogo'] = _pick_logo(logos)

    return result


def _service_wants_metadata(service_name):
    """
    Return True if the service is enabled AND its 'use for metadata' toggle is on.
    """
    if not service_name:
        return True
    enabled_key  = f'{service_name}_enabled'
    metadata_key = f'{service_name}_use_for_metadata'
    return _setting_bool(enabled_key, True) and _setting_bool(metadata_key, True)


def enrich_item(item):
    """
    Enrich a progress dict in-place with TMDB data.

    Fast-path: if `landscape` is already set the row was previously enriched
    and the result was persisted back to the DB — skip all API calls.

    After a live fetch the enriched fields are written back to the DB via
    update_enriched_metadata() so every subsequent widget render is instant.

    Logic per field:
    - If the item already has a value AND the originating service has
      'use_for_metadata' ON → keep the service value (don't overwrite).
    - If the service has 'use_for_metadata' OFF, or the field is empty
      → fill from TMDB (if tmdb_enrichment_enabled).

    Granular TMDB toggles (tmdb_fetch_clearlogo etc.) still apply.
    """
    if not is_enabled():
        return item

    service_ids = dict(item.get('service_ids') or {})
    tmdb_id     = service_ids.get('tmdb')
    media_type  = item.get('media_type', 'episode')

    # AniList items arrive without a TMDB ID. Try AniZip to resolve one so
    # TMDB enrichment (poster, fanart, landscape, clearlogo) can proceed.
    if not tmdb_id:
        anilist_id = service_ids.get('anilist')
        if anilist_id:
            found = _resolve_anizip(anilist_id)
            if found:
                service_ids.update(found)
                item['service_ids'] = service_ids
                tmdb_id = service_ids.get('tmdb')
                row_id = item.get('id')
                if row_id:
                    try:
                        from resources.lib.database import get_database
                        get_database().update_service_ids(row_id, service_ids)
                    except Exception:
                        pass

    if not tmdb_id:
        return item

    # Fast-path: landscape is only ever written by this enricher (services
    # never set it).  If it is present the DB row was already enriched on a
    # previous render — return immediately without any network I/O.
    if item.get('landscape'):
        return item

    # Which services contributed this item?
    sources = item.get('sources') or []
    # If ANY contributing service wants its own metadata kept, respect that
    # for fields that service actually provides.
    keep_service_meta = any(_service_wants_metadata(s) for s in sources)

    want_logo    = _setting_bool('tmdb_fetch_clearlogo', True)
    want_plot    = _setting_bool('tmdb_fetch_plot',      True)
    want_runtime = _setting_bool('tmdb_fetch_runtime',   True)

    enriched = enrich(tmdb_id, media_type, fetch_logo=want_logo)

    # Poster / fanart / landscape: fill if missing, or if service says don't use its own
    if enriched['poster']:
        if not item.get('poster') or not keep_service_meta:
            item['poster'] = enriched['poster']

    if enriched['fanart']:
        if not item.get('fanart') or not keep_service_meta:
            item['fanart'] = enriched['fanart']

    if enriched['landscape']:
        if not item.get('landscape') or not keep_service_meta:
            item['landscape'] = enriched['landscape']

    # Clearlogo — always from TMDB if toggle on (services don't provide real logos)
    if want_logo and enriched['clearlogo'] and not item.get('clearlogo'):
        item['clearlogo'] = enriched['clearlogo']

    # Plot — only fill missing, or if service meta disabled
    if want_plot and enriched['plot']:
        if not item.get('plot') or not keep_service_meta:
            item['plot'] = enriched['plot']

    # Runtime
    if want_runtime and enriched['runtime_s']:
        if not item.get('duration') or not keep_service_meta:
            item['duration'] = enriched['runtime_s']

    # Genres — always fill if missing
    if enriched['genres'] and not item.get('genres'):
        item['genres'] = enriched['genres']

    # Persist enriched fields back to the DB so the next widget render hits
    # the fast-path above and skips all TMDB network calls.
    row_id = item.get('id')
    if row_id:
        try:
            from resources.lib.database import get_database
            get_database().update_enriched_metadata(
                row_id,
                poster    = item.get('poster'),
                fanart    = item.get('fanart'),
                landscape = item.get('landscape'),
                clearlogo = item.get('clearlogo'),
                plot      = item.get('plot'),
                duration  = item.get('duration') or 0,
            )
        except Exception:
            pass

    return item


def enrich_items_background(items):
    """
    Background-enrich a list of progress dicts.

    Called from list_continue_watching after endOfDirectory so the UI never
    waits for network I/O.  Items already enriched (landscape present) are
    skipped instantly via the fast-path in enrich_item().  After all pending
    items are processed, Container.Refresh is triggered so the widget picks
    up the new art, plot, runtime, and clearlogo on its next cycle.

    Respects all settings:
      tmdb_enrichment_enabled, tmdb_api_key,
      tmdb_fetch_clearlogo, tmdb_fetch_plot, tmdb_fetch_runtime,
      {name}_enabled, {name}_use_for_metadata
    (all read live inside enrich_item() per item, so changes between items
    are picked up without restarting).
    """
    if not is_enabled():
        return

    # Only process items that have a tmdb_id and haven't been enriched yet.
    # enrich_item() has its own fast-path, but filtering here avoids
    # spawning thread slots for items that would return immediately anyway.
    to_enrich = [
        item for item in items
        if not item.get('landscape') and (
            (item.get('service_ids') or {}).get('tmdb') or
            (item.get('service_ids') or {}).get('anilist')
        )
    ]

    if not to_enrich:
        return

    def _one(item):
        try:
            enrich_item(item)
        except Exception as e:
            if KODI_ENV:
                xbmc.log(f'[RabiteWatch-TMDB] Background enrich error: {e}', xbmc.LOGWARNING)
        # landscape is written by enrich_item() only when TMDB returned useful
        # data and update_enriched_metadata() persisted it to the DB.
        # to_enrich already excluded items that had landscape, so if it is now
        # set the row genuinely changed and the widget needs a refresh.
        return bool(item.get('landscape'))

    max_workers = min(4, len(to_enrich))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        changed = list(executor.map(_one, to_enrich))

    # Only refresh the widget when at least one row was actually updated.
    # Avoids a redundant reload when TMDB returns nothing (unknown titles,
    # network down) or when a second enrichment pass races the first.
    if KODI_ENV and any(changed):
        xbmc.executebuiltin('Container.Refresh')


def enrich_pending():
    """
    Enrich every DB row that hasn't been TMDB-enriched yet.

    Called automatically after every sync (pull_all, pull_service,
    pull_fast_continue_watching) so that newly-added items already have
    their poster/fanart/plot/clearlogo/runtime by the time the user
    opens Continue Watching — no waiting for the view to open first.

    Delegates to enrich_items_background() which:
      • respects tmdb_enrichment_enabled, tmdb_api_key,
        tmdb_fetch_clearlogo/plot/runtime, {name}_use_for_metadata
      • skips items already enriched (landscape present) via fast-path
      • persists results to DB
      • triggers Container.Refresh when done
    """
    if not is_enabled():
        return

    if not _api_key():
        if KODI_ENV:
            xbmc.log(
                '[RabiteWatch-TMDB] Enrichment enabled but no API key configured — '
                'set tmdb_api_key in addon settings.',
                xbmc.LOGWARNING
            )
            # Show a notification once per Kodi session so the user knows why
            # metadata/artwork is missing on a fresh install.
            win = xbmcgui.Window(10000)
            if not win.getProperty('RabiteWatch.TmdbKeyWarned'):
                win.setProperty('RabiteWatch.TmdbKeyWarned', '1')
                xbmcgui.Dialog().notification(
                    'Rabite Watch',
                    'TMDB metadata disabled — add your API key in addon settings.',
                    xbmcgui.NOTIFICATION_WARNING,
                    6000,
                )
        return
    try:
        from resources.lib.database import get_database
        items = get_database().get_unenriched()
    except Exception as e:
        if KODI_ENV:
            xbmc.log(f'[RabiteWatch-TMDB] enrich_pending: DB error: {e}', xbmc.LOGWARNING)
        return
    enrich_items_background(items)
