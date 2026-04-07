
# -*- coding: utf-8 -*-
"""
Rabite Watch - UI Entry Point
Pull-only watch tracker: Continue Watching + Next Up + Browse Lists.
No scrobbling.
"""

import sys
import os
import threading
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs
from urllib.parse import parse_qsl, urlencode, quote_plus

addon      = xbmcaddon.Addon()
addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
sys.path.insert(0, addon_path)

from resources.lib.database import get_database
from resources.lib.pull_manager import get_pull_manager
from resources.lib import tmdb_enricher

# ---------------------------------------------------------------------------
# Service icons — trakt.png / anilist.png / simkl.png in media/ folder
# ---------------------------------------------------------------------------

SERVICE_ICONS = {
    'trakt':   'special://home/addons/plugin.video.rabitewatch/media/trakt.png',
    'anilist': 'special://home/addons/plugin.video.rabitewatch/media/anilist.png',
    'simkl':   'special://home/addons/plugin.video.rabitewatch/media/simkl.png',
}

SERVICE_COLORS = {
    'trakt':   'FFED1C24',  # Trakt red
    'anilist': 'FF02A9FF',  # AniList blue
    'simkl':   'FF1CE1C1',  # Simkl teal
}

# Maps service name to the unique ID namespace used by setUniqueIDs / other addons
# 'tmdb' and 'imdb' are Kodi-standard; the rest are custom namespaces
SERVICE_ID_NAMESPACES = {
    'tmdb':    'tmdb',
    'imdb':    'imdb',
    'tvdb':    'tvdb',
    'trakt':   'trakt',
    'anilist': 'anilist',
    'simkl':   'simkl',
    'mal':     'mal',
}


def _set_art_with_service_icon(li, poster, fanart, sources,
                               landscape=None, clearlogo=None, media_type='movie'):
    """
    Set artwork on a ListItem.

    thumb behaviour:
      movie   → landscape > fanart > poster  (wide tile, Netflix-style)
      episode → fanart > poster              (show backdrop; no landscape as thumb
                                              since episodes don't have episode-specific
                                              wide art — landscape stays in its own slot)

    poster   → portrait poster (always the show/movie cover)
    fanart   → full-resolution backdrop
    landscape → w1280 backdrop (wide slot; wide images only, never portrait)
    clearlogo → TMDB logo if available, else service icon badge
    """
    art = {}
    if poster:
        art['poster'] = poster

    if fanart:
        art['fanart'] = fanart

    # landscape slot: wide (16:9) images only — never fall back to portrait poster.
    if landscape:
        art['landscape'] = landscape
    elif fanart:
        art['landscape'] = fanart

    # thumb: movies get landscape/wide; episodes get show fanart or poster.
    if media_type == 'movie':
        if landscape:
            art['thumb'] = landscape
        elif fanart:
            art['thumb'] = fanart
        elif poster:
            art['thumb'] = poster
    else:
        # episode / tvshow — use show backdrop or poster, not landscape
        if fanart:
            art['thumb'] = fanart
        elif poster:
            art['thumb'] = poster

    # Prefer a real TMDB clearlogo; fall back to service icon badge
    if clearlogo:
        art['clearlogo'] = clearlogo
    else:
        primary = sources[0] if sources else None
        if primary and primary in SERVICE_ICONS:
            art['clearlogo'] = SERVICE_ICONS[primary]

    if art:
        li.setArt(art)


def _set_unique_ids(vi, service_ids, media_type='movie'):
    """
    Register all known IDs with the Kodi VideoInfoTag using setUniqueIDs().
    This is the standard way for other addons (e.g. TMDbHelper, Trakt addon)
    to discover our IDs without scraping labels or properties.

    setUniqueIDs(ids_dict, default_id_type)
      - ids_dict: {'tmdb': '12345', 'imdb': 'tt1234567', ...}
      - default_id_type: the key to treat as the canonical ID for this item

    For episodes, addons monitoring playback (TMDbHelper, scrobblers) read
    UniqueId(tvshow.tmdb) / UniqueId(tvshow.imdb) to look up the parent show,
    not just UniqueId(tmdb). We register both so all addons find what they need.
    """
    uid = {}
    default_type = None

    for key, val in service_ids.items():
        if val:
            namespace = SERVICE_ID_NAMESPACES.get(key, key)
            uid[namespace] = str(val)
            # Prefer tmdb > imdb > trakt > simkl > anilist as canonical
            if default_type is None or (
                namespace == 'tmdb' or
                (namespace == 'imdb' and default_type not in ('tmdb',)) or
                (namespace == 'trakt' and default_type not in ('tmdb', 'imdb'))
            ):
                default_type = namespace

    # Episodes and tvshow items: alias show IDs under tvshow.* namespace so
    # monitoring addons (TMDbHelper player, Trakt scrobblers) can resolve
    # the parent show regardless of which Kodi mediatype is used.
    if media_type in ('episode', 'tvshow'):
        for key in ('tmdb', 'imdb', 'tvdb', 'trakt'):
            if uid.get(key):
                uid[f'tvshow.{key}'] = uid[key]

    if uid:
        vi.setUniqueIDs(uid, default_type or '')

    # setIMDBNumber for backward-compat (older skins/addons read IMDBNumber
    # infolabel directly instead of UniqueId).
    imdb = service_ids.get('imdb')
    if imdb and str(imdb).startswith('tt'):
        vi.setIMDBNumber(str(imdb))

    return uid


# ---------------------------------------------------------------------------
# Service helper
# ---------------------------------------------------------------------------

def _get_service(name):
    pm = get_pull_manager()
    return pm.get_service(name)


def _get_user_data(service):
    """Return user_data dict from DB auth."""
    db   = get_database()
    auth = db.get_auth(service.service_name)
    if not auth:
        return None
    ud = auth.get('user_data')
    if isinstance(ud, str):
        import json
        try:
            ud = json.loads(ud)
        except Exception:
            ud = {}
    return ud or {}


# ===========================================================================
# MAIN MENU
# ===========================================================================

def show_main_menu(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Rabite Watch')

    items = [
        ('[B]Continue Watching[/B]',            'DefaultVideoPlaylists.png',           'continue_watching',  True),
        ('[B]Watchlist[/B]',                    'DefaultVideoPlaylists.png',           'watchlist_menu',     True),
        ('[COLOR lightblue]Sync All Services[/COLOR]', 'DefaultAddonService.png',      'sync_all',           False),
        ('Trakt',   SERVICE_ICONS.get('trakt',   'DefaultAddonService.png'), 'trakt_menu',   True),
        ('AniList', SERVICE_ICONS.get('anilist', 'DefaultAddonService.png'), 'anilist_menu', True),
        ('Simkl',   SERVICE_ICONS.get('simkl',   'DefaultAddonService.png'), 'simkl_menu',   True),
        ('Database Stats',                       'DefaultAddonService.png',             'db_stats',          True),
    ]
    for label, icon, action, is_folder in items:
        li = xbmcgui.ListItem(label=label)
        li.setArt({'icon': icon})
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action": action})}', li, isFolder=is_folder)

    xbmcplugin.endOfDirectory(handle)


def show_watchlist_menu(handle, url):
    """
    Watchlist hub — shows all 'watchlist' items from every connected service.

    Top level splits by media category so the user can browse their planned
    content without needing to open each service separately.
    Each category delegates to list_watchlist with the appropriate filter.

    Per-service watchlists are still accessible under each service's own menu
    (Trakt → Watchlist, AniList → Planning, Simkl → Plan to Watch).
    """
    xbmcplugin.setPluginCategory(handle, 'Watchlist')

    cats = [
        ('Movies',  'movie',  'DefaultMovies.png'),
        ('Anime',   'anime',  SERVICE_ICONS.get('anilist', 'DefaultAddonService.png')),
        ('Series',  'series', 'DefaultTVShows.png'),
        ('All',     '',       'DefaultVideoPlaylists.png'),
    ]
    for label, cat, icon in cats:
        li = xbmcgui.ListItem(label=label)
        li.setArt({'icon': icon})
        params = {'action': 'watchlist', 'status': 'watchlist'}
        if cat:
            params['category'] = cat
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode(params)}', li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


# Source filter index → service name (matches settings.xml values= order)
_SOURCE_FILTER_MAP = {
    0: None,       # All Services
    1: 'trakt',
    2: 'anilist',
    3: 'simkl',
}


def _get_continue_watching_source_filter():
    """Return service name to filter by, or None for all."""
    try:
        idx = int(addon.getSettingInt('continue_watching_source'))
    except Exception:
        idx = 0
    return _SOURCE_FILTER_MAP.get(idx)


def list_continue_watching(handle, url, params):
    # widget=1 is set by the skin widget source URL.
    # In widget mode: no sync button, auto-resume on click (no dialog).
    is_widget = params.get('widget') == '1'

    xbmcplugin.setPluginCategory(handle, 'Continue Watching')
    xbmcplugin.setPluginFanart(handle, '')   # per-item fanart, not addon bg

    # Always 'movies' — prevents skins from forcing episode/tvshow view types.
    xbmcplugin.setContent(handle, 'movies')

    # ----------------------------------------------------------------
    # Sync button — shown in the full plugin view only, not in widgets.

    # JIT fast sync: fire in a background thread so it never blocks the render.
    # The widget shows cached DB data immediately; updated data appears on the
    # next refresh (Kodi auto-refreshes widgets periodically).
    try:
        import threading
        threading.Thread(
            target=get_pull_manager().pull_fast_continue_watching,
            daemon=True
        ).start()
    except Exception as _e:
        xbmc.log(f'[RabiteWatch] fast sync error: {_e}', xbmc.LOGWARNING)

    db    = get_database()
    try:
        limit = int(addon.getSettingInt('continue_watching_limit'))
    except Exception:
        limit = 25
    items = db.get_continue_watching(limit=limit)

    # ---- Background TMDB enrichment ----
    # Spawn before filters so all DB items get enriched (even those currently
    # filtered out may become visible after a settings change).
    # enrich_items_background() skips already-enriched items (landscape set)
    # and items with no tmdb_id, then persists results to DB and triggers
    # Container.Refresh so the widget re-renders with full art/metadata.
    try:
        threading.Thread(
            target=tmdb_enricher.enrich_items_background,
            args=(items,),
            daemon=True
        ).start()
    except Exception as _e:
        xbmc.log(f'[RabiteWatch] background enrichment error: {_e}', xbmc.LOGWARNING)

    # ---- Source filter (from settings) ----
    source_filter = _get_continue_watching_source_filter()
    if source_filter:
        items = [i for i in items if source_filter in (i.get('sources') or [])]

    # ---- Simkl-only filter ----
    # Simkl provides no resume points or durations, so items that come
    # *exclusively* from Simkl are hidden by default. Items shared with
    # Trakt or AniList are kept — the other service supplies the resume data.
    # Users can opt in via Settings → General → Continue Watching.
    try:
        simkl_in_cw = addon.getSettingBool('simkl_include_in_cw')
    except Exception:
        simkl_in_cw = False
    if not simkl_in_cw:
        items = [i for i in items if set(i.get('sources') or []) != {'simkl'}]

    if not items:
        li = xbmcgui.ListItem(label='[COLOR gray]Nothing in Continue Watching yet[/COLOR]')
        if is_widget:
            li.getVideoInfoTag().setPlot(
                'No items in Continue Watching.\n'
                'Open Rabite Watch and sync your services to get started.'
            )
        else:
            li.getVideoInfoTag().setPlot(
                'Use the Sync button above to pull your watch lists,\n'
                'or configure auto-sync interval in Settings.'
            )
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
    else:
        for item in items:
            media_type  = item.get('media_type', 'video')
            show_title  = item.get('show_title') or item.get('title', 'Unknown')
            year        = item.get('year')
            resume_pct  = item.get('resume_pct', 0)
            resume_data = item.get('resume_data', {})
            sources     = item.get('sources', [])
            kodi_type   = _kodi_media_type(media_type, item.get('season'), item.get('episode'))

            # ---- Label ----
            if kodi_type == 'episode':
                s      = item.get('season') or 0
                e      = item.get('episode') or 0
                ep_str = f'S{s:02d}E{e:02d}' if (s and e) else ''
                label  = show_title
                if ep_str:
                    label += f' — [B]{ep_str}[/B]'
            else:
                label = show_title
                if year:
                    label += f' ({year})'

            if resume_pct > 0:
                label += f' [COLOR gray]{resume_pct}%[/COLOR]'

            li = xbmcgui.ListItem(label=label)

            # ---- Artwork: poster, fanart, landscape, clearlogo ----
            _set_art_with_service_icon(
                li,
                poster     = item.get('poster'),
                fanart     = item.get('fanart'),
                landscape  = item.get('landscape'),
                clearlogo  = item.get('clearlogo'),
                sources    = sources,
                media_type = media_type,
            )

            # ---- VideoInfoTag ----
            vi = li.getVideoInfoTag()
            vi.setTitle(item.get('title') or show_title)
            vi.setMediaType(kodi_type)
            vi.setPlaycount(0)

            if year:
                try:
                    vi.setYear(int(year))
                except Exception:
                    pass

            # Genres from TMDB enrichment
            genres = item.get('genres') or []
            if genres:
                vi.setGenres(genres)

            # Plot: progress bar + overview + per-service breakdown
            plot = item.get('plot') or ''
            if resume_pct > 0:
                bar  = _progress_bar(resume_pct)
                plot = bar + ('\n\n' + plot.strip() if plot.strip() else '')
            svc_lines = []
            for svc, info in sorted(resume_data.items()):
                pct = info.get('pct', 0)
                if pct > 0:
                    color = SERVICE_COLORS.get(svc, 'FFFFFFFF')
                    svc_lines.append(f'[COLOR {color}]{svc.capitalize()}:[/COLOR] {pct}%')
            if svc_lines:
                plot = (plot.strip() + '\n\n' if plot.strip() else '') + '  '.join(svc_lines)
            vi.setPlot(plot)

            if kodi_type == 'episode':
                vi.setSeason(item.get('season') or 0)
                vi.setEpisode(item.get('episode') or 0)
                vi.setTvShowTitle(show_title)
                ep_title = item.get('title')
                if ep_title and ep_title != show_title:
                    vi.setTitle(f'{show_title} — {ep_title}')
            elif kodi_type == 'tvshow':
                vi.setTvShowTitle(show_title)

            # Duration
            duration = item.get('duration', 0)
            if duration:
                vi.setDuration(duration)

            if resume_pct > 0:
                li.setProperty('percentplayed', str(resume_pct))

            # ---- IDs ----
            service_ids = item.get('service_ids', {})
            _set_unique_ids(vi, service_ids, kodi_type)
            for k, v in service_ids.items():
                if v:
                    li.setProperty(f'{k}_id', str(v))
                    if kodi_type in ('episode', 'tvshow'):
                        li.setProperty(f'tvshow.{k}_id', str(v))

            db_id       = item.get('id', '')
            resume_time = item.get('resume_time', 0) or 0
            duration_f  = float(item.get('duration') or 0)

            # ---- Skin-readable properties ----
            # Skins read these via ListItem.Property(RabiteWatch.*)
            # RabiteWatch.Category: 'movie' | 'anime' | 'series'
            if media_type == 'movie':
                item_cat = 'movie'
            elif 'anilist' in sources:
                item_cat = 'anime'
            else:
                item_cat = 'series'

            li.setProperty('RabiteWatch.DbId',          str(db_id))
            li.setProperty('RabiteWatch.MediaType',     media_type)
            li.setProperty('RabiteWatch.Category',      item_cat)
            li.setProperty('RabiteWatch.Sources',       ','.join(sources))
            li.setProperty('RabiteWatch.ListStatus',    item.get('list_status', ''))
            li.setProperty('RabiteWatch.HasResume',     '1' if resume_time > 0 else '0')
            li.setProperty('RabiteWatch.ResumeTime',    str(int(resume_time)))
            li.setProperty('RabiteWatch.Duration',      str(int(duration_f)))
            if resume_time > 0:
                li.setProperty('RabiteWatch.ResumeTimeFmt', _fmt_seconds(int(resume_time)))

            # CW items always have a resume position — play directly.
            # Kodi shows its native "Resume / Play from beginning" dialog
            # when a resume point is set via setResumePoint.
            li.setProperty('IsPlayable', 'true')
            if resume_time > 0:
                vi.setResumePoint(float(resume_time), duration_f)
            play_url = f'{url}?{urlencode({"action": "resolve_item", "db_id": db_id})}'
            xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def list_watchlist(handle, url, params):
    """
    Unified DB-backed watchlist — fast, no API calls, ideal for skin widgets.

    Returns all local DB rows matching `status` (default: 'watching').
    Each item exposes RabiteWatch.* properties so the skin can render
    play/resume controls without needing to parse URLs.

    Skin source URL examples:
      plugin://plugin.video.rabitewatch/?action=watchlist&status=watchlist
      plugin://plugin.video.rabitewatch/?action=watchlist&status=watchlist&category=anime&widget=1
    """
    status    = params.get('status', 'watchlist')
    is_widget = params.get('widget') == '1'
    category  = params.get('category', '')   # 'movie' | 'anime' | 'series' | ''

    # JIT fast sync: fetch only watchlist items in the background so the DB
    # render is instant and updated data appears on the next Container.Refresh.
    # Cooldown (2 min default) is enforced inside pull_fast_watchlist() via a
    # Window(10000) property so it survives across plugin processes.
    try:
        threading.Thread(
            target=get_pull_manager().pull_fast_watchlist,
            daemon=True
        ).start()
    except Exception as _e:
        xbmc.log(f'[RabiteWatch] watchlist sync error: {_e}', xbmc.LOGWARNING)

    status_labels = {
        'watching':    'Watching',
        'watchlist':   'Watchlist',
        'watched':     'Watched',
        'plantowatch': 'Plan to Watch',
        'completed':   'Completed',
        'hold':        'On Hold',
        'dropped':     'Dropped',
        'repeating':   'Repeating',
    }
    cat_labels = {'movie': 'Movies', 'anime': 'Anime', 'series': 'Series'}
    base_label = status_labels.get(status, status.title())
    cat_label  = cat_labels.get(category, '')
    heading    = f'{base_label} — {cat_label}' if cat_label else base_label
    xbmcplugin.setPluginCategory(handle, heading)
    xbmcplugin.setContent(handle, 'movies')

    db    = get_database()
    try:
        limit = int(addon.getSettingInt('continue_watching_limit'))
    except Exception:
        limit = 200
    items = db.get_by_list_status(status, limit=limit)

    # ---- Background TMDB enrichment ----
    try:
        threading.Thread(
            target=tmdb_enricher.enrich_items_background,
            args=(items,),
            daemon=True
        ).start()
    except Exception as _e:
        xbmc.log(f'[RabiteWatch] watchlist enrichment error: {_e}', xbmc.LOGWARNING)

    # ---- Category filter ----
    # anime  : AniList-sourced episodes ('anilist' in sources)
    # series : non-anime episodes
    # movie  : media_type == 'movie'
    if category == 'movie':
        items = [i for i in items if i.get('media_type') == 'movie']
    elif category == 'anime':
        items = [i for i in items if i.get('media_type') != 'movie'
                 and 'anilist' in (i.get('sources') or [])]
    elif category == 'series':
        items = [i for i in items if i.get('media_type') != 'movie'
                 and 'anilist' not in (i.get('sources') or [])]

    if not items:
        li = xbmcgui.ListItem(label=f'[COLOR gray]Nothing in {status_labels.get(status, status)} list yet[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
    else:
        for item in items:
            media_type  = item.get('media_type', 'video')
            show_title  = item.get('show_title') or item.get('title', 'Unknown')
            year        = item.get('year')
            resume_pct  = item.get('resume_pct', 0)
            resume_data = item.get('resume_data', {})
            sources     = item.get('sources', [])
            resume_time = item.get('resume_time', 0) or 0
            duration_f  = float(item.get('duration') or 0)
            db_id       = item.get('id', '')
            service_ids = item.get('service_ids', {})
            kodi_type   = _kodi_media_type(media_type, item.get('season'), item.get('episode'))

            if kodi_type == 'episode':
                s      = item.get('season') or 0
                e      = item.get('episode') or 0
                ep_str = f'S{s:02d}E{e:02d}' if (s and e) else ''
                label  = show_title
                if ep_str:
                    label += f' — [B]{ep_str}[/B]'
            else:
                label = show_title
                if year:
                    label += f' ({year})'
            if resume_pct > 0:
                label += f' [COLOR gray]{resume_pct}%[/COLOR]'

            li = xbmcgui.ListItem(label=label)
            _set_art_with_service_icon(
                li,
                poster     = item.get('poster'),
                fanart     = item.get('fanart'),
                landscape  = item.get('landscape'),
                clearlogo  = item.get('clearlogo'),
                sources    = sources,
                media_type = media_type,
            )

            vi = li.getVideoInfoTag()
            vi.setTitle(item.get('title') or show_title)
            vi.setMediaType(kodi_type)
            vi.setPlaycount(0)
            if year:
                try:
                    vi.setYear(int(year))
                except Exception:
                    pass
            if item.get('plot'):
                vi.setPlot(item['plot'])
            if duration_f:
                vi.setDuration(int(duration_f))
            if kodi_type == 'episode':
                vi.setSeason(item.get('season') or 0)
                vi.setEpisode(item.get('episode') or 0)
                vi.setTvShowTitle(show_title)
            elif kodi_type == 'tvshow':
                vi.setTvShowTitle(show_title)

            _set_unique_ids(vi, service_ids, kodi_type)
            for k, v in service_ids.items():
                if v:
                    li.setProperty(f'{k}_id', str(v))
                    if kodi_type in ('episode', 'tvshow'):
                        li.setProperty(f'tvshow.{k}_id', str(v))

            if resume_pct > 0:
                li.setProperty('percentplayed', str(resume_pct))

            # ---- Skin-readable properties ----
            # RabiteWatch.Category: 'movie' | 'anime' | 'series'
            if media_type == 'movie':
                item_cat = 'movie'
            elif 'anilist' in sources:
                item_cat = 'anime'
            else:
                item_cat = 'series'

            li.setProperty('RabiteWatch.DbId',          str(db_id))
            li.setProperty('RabiteWatch.MediaType',     media_type)
            li.setProperty('RabiteWatch.Category',      item_cat)
            li.setProperty('RabiteWatch.ListStatus',    item.get('list_status', ''))
            li.setProperty('RabiteWatch.Sources',       ','.join(sources))
            li.setProperty('RabiteWatch.HasResume',     '1' if resume_time > 0 else '0')
            li.setProperty('RabiteWatch.ResumeTime',    str(int(resume_time)))
            li.setProperty('RabiteWatch.Duration',      str(int(duration_f)))
            if resume_time > 0:
                li.setProperty('RabiteWatch.ResumeTimeFmt', _fmt_seconds(int(resume_time)))

            if media_type != 'movie':
                # TV shows / anime in the watchlist: open the show's season
                # listing in TMDbHelper so the user can pick which episode
                # to watch.  Never trigger the player selector here.
                item_url = _tmdbhelper_show_url(service_ids, item)
                xbmcplugin.addDirectoryItem(handle, item_url, li, isFolder=True)
            else:
                li.setProperty('IsPlayable', 'true')
                if resume_time > 0:
                    vi.setResumePoint(float(resume_time), duration_f)
                play_url = f'{url}?{urlencode({"action": "resolve_item", "db_id": db_id})}'
                xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def _get_play_url(service_ids, media_type, item):
    tmdb_id = service_ids.get('tmdb')
    if tmdb_id:
        if media_type == 'movie':
            return f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
        else:
            s = item.get('season', 1)
            e = item.get('episode', 1)
            return f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=episode&season={s}&episode={e}'
    title      = item.get('title', '')
    search_type = 'movie' if media_type == 'movie' else 'tv'
    return f'plugin://plugin.video.themoviedb.helper/?{urlencode({"info":"search","query":title,"type":search_type})}'


def _tmdbhelper_show_url(service_ids, item):
    """
    Return a TMDbHelper URL that opens a TV show's season listing.

    If the TMDB ID is already known, build the direct seasons URL so Kodi
    navigates straight to TMDbHelper without an extra plugin hop.
    If the TMDB ID is missing (unenriched AniList item), route through our
    own open_in_tmdbhelper handler which resolves IDs first.
    """
    tmdb_id = (service_ids or {}).get('tmdb')
    if tmdb_id:
        return (
            f'plugin://plugin.video.themoviedb.helper/'
            f'?info=seasons&tmdb_type=tv&tmdb_id={tmdb_id}'
        )
    # TMDB ID not yet resolved — fall back to our resolver handler.
    db_id = item.get('id', '')
    return f'plugin://plugin.video.rabitewatch/?{urlencode({"action": "open_in_tmdbhelper", "db_id": db_id})}'


def open_in_tmdbhelper(handle, url, params):
    """
    Resolve the TMDB ID for an item (via AniZip for AniList entries) then
    redirect to TMDbHelper's season listing page via Container.Update.

    Only reached when the TMDB ID was not in the DB at render time (typically
    a freshly-added AniList item that hasn't been enriched yet).
    """
    db_id = params.get('db_id')
    if not db_id:
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification('Rabite Watch', 'Item not found', xbmcgui.NOTIFICATION_ERROR, 3000)
        xbmcplugin.endOfDirectory(handle, succeeded=False)
        return

    item        = _resolve_anizip_ids(item)
    service_ids = item.get('service_ids', {})
    tmdb_id     = service_ids.get('tmdb')

    if tmdb_id:
        tmdb_url = (
            f'plugin://plugin.video.themoviedb.helper/'
            f'?info=seasons&tmdb_type=tv&tmdb_id={tmdb_id}'
        )
        xbmc.executebuiltin(f'Container.Update({tmdb_url})')
    else:
        title       = item.get('show_title') or item.get('title', '')
        search_url  = (
            f'plugin://plugin.video.themoviedb.helper/'
            f'?{urlencode({"info": "search", "query": title, "type": "tv"})}'
        )
        xbmc.executebuiltin(f'Container.Update({search_url})')

    xbmcplugin.endOfDirectory(handle, succeeded=False)


def _kodi_media_type(db_media_type, season, episode):
    """
    Map the DB media_type + episode position to the correct Kodi VideoInfoTag
    mediatype string.

    DB stores only 'movie' or 'episode'.  Kodi also uses 'tvshow' for show-level
    items that have no specific episode position (e.g. watchlist entries).

      movie   → 'movie'
      episode with season+episode numbers → 'episode'
      episode without season+episode      → 'tvshow'
    """
    if db_media_type == 'movie':
        return 'movie'
    if season and episode:
        return 'episode'
    return 'tvshow'


def _fmt_seconds(total_s):
    """Format an integer number of seconds as H:MM:SS or MM:SS."""
    total_s = int(total_s)
    h       = total_s // 3600
    m       = (total_s % 3600) // 60
    s       = total_s % 60
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'


def _progress_bar(pct, width=16):
    """Render a coloured Unicode progress bar spanning the info panel column width."""
    pct    = max(0, min(100, int(pct)))
    filled = round(width * pct / 100)
    empty  = width - filled
    bar    = f'[COLOR FFFCC200]{"█" * filled}[/COLOR][COLOR gray]{"░" * empty}[/COLOR]'
    return f'{bar}  {pct}%'


def _do_play(item, seek_to):
    """
    Core playback executor shared by play_item and prompt_resume_dialog.

    Builds a populated ListItem and starts playback via xbmc.Player().play().
    If seek_to > 0 the target position is stored in the shared Window(10000)
    property 'RabiteWatch.PendingSeek' so that the persistent RabiteWatchPlayer
    listener in service.py can apply it once the stream is actually playing —
    even if TMDb Helper shows its own provider-selection dialog in between.
    """
    service_ids = item.get('service_ids', {})
    media_type  = item.get('media_type', 'movie')
    label       = item.get('show_title') or item.get('title') or ''
    duration    = float(item.get('duration') or 0)

    play_url = _get_play_url(service_ids, media_type, item)

    li = xbmcgui.ListItem(label=label, path=play_url)
    li.setProperty('IsPlayable', 'true')

    vi = li.getVideoInfoTag()
    vi.setTitle(item.get('title') or label)
    vi.setMediaType('movie' if media_type == 'movie' else 'episode')
    if duration:
        vi.setDuration(int(duration))
    _set_unique_ids(vi, service_ids, media_type)
    for k, v in service_ids.items():
        if v:
            li.setProperty(f'{k}_id', str(v))
            if media_type == 'episode':
                li.setProperty(f'tvshow.{k}_id', str(v))
    if media_type == 'episode':
        vi.setSeason(item.get('season') or 0)
        vi.setEpisode(item.get('episode') or 0)
        vi.setTvShowTitle(item.get('show_title') or '')
    if item.get('plot'):
        vi.setPlot(item['plot'])

    art = {}
    if item.get('poster'):
        art['thumb']  = item['poster']
        art['poster'] = item['poster']
    if item.get('fanart'):
        art['fanart'] = item['fanart']
    if item.get('landscape'):
        art['landscape'] = item['landscape']
    if item.get('clearlogo'):
        art['clearlogo'] = item['clearlogo']
    if art:
        li.setArt(art)

    # Shared Window(10000) properties let the persistent service.py listener act
    # on events that fire after this short-lived plugin process has exited.
    win = xbmcgui.Window(10000)

    # Always advertise the active DB row so service.py can write local progress
    # on stop/end — giving the widget an instant Netflix-like refresh.
    db_id = item.get('id')
    if db_id:
        win.setProperty('RabiteWatch.ActiveDbId',    str(db_id))
        win.setProperty('RabiteWatch.ActiveDuration', str(float(item.get('duration') or 0)))
    else:
        win.clearProperty('RabiteWatch.ActiveDbId')
        win.clearProperty('RabiteWatch.ActiveDuration')

    # Deferred seek: service.py's onAVStarted applies the seek once the stream
    # is running.  Works through TMDbHelper chains where Kodi's native
    # setResumePoint is unreliable.  seek_to=0 means play from beginning.
    if seek_to > 0:
        win.setProperty('RabiteWatch.PendingSeek', str(seek_to))
    else:
        win.clearProperty('RabiteWatch.PendingSeek')

    xbmc.Player().play(play_url, li)


def _resolve_anizip_ids(item):
    """
    Just-In-Time resolution for AniList items right before playback.
    Fetches TMDB/IMDB/TVDB IDs from api.ani.zip so TMDbHelper can play them directly.
    """
    service_ids = item.get('service_ids', {})
    anilist_id = service_ids.get('anilist')

    # If it's not an AniList item, or it already has a TMDB/IMDB ID, skip it instantly.
    if not anilist_id or service_ids.get('tmdb') or service_ids.get('imdb'):
        return item

    try:
        import requests
        url = f'https://api.ani.zip/mappings?anilist_id={anilist_id}'
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            mappings = resp.json().get('mappings', {})
            if mappings.get('themoviedb_id'):
                service_ids['tmdb'] = str(mappings['themoviedb_id'])
            if mappings.get('imdb_id'):
                service_ids['imdb'] = str(mappings['imdb_id'])
            if mappings.get('thetvdb_id'):
                service_ids['tvdb'] = str(mappings['thetvdb_id'])
            item['service_ids'] = service_ids
    except Exception as e:
        xbmc.log(f'[RabiteWatch] JIT AniZip resolution failed for AniList ID {anilist_id}: {e}', xbmc.LOGWARNING)

    return item


def resolve_item(handle, url, params):
    """
    Playback resolver for Continue Watching items (IsPlayable='true').

    Called by Kodi after the user dismisses the native resume dialog.
    Resolves IDs, enriches metadata, then calls setResolvedUrl so Kodi
    can complete playback through TMDb Helper.  Seeking (if the user
    chose Resume) is handled entirely by Kodi using the resume point
    set on the ListItem at render time.
    """
    db_id = params.get('db_id')
    if not db_id:
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Item not found', xbmcgui.NOTIFICATION_ERROR, 3000
        )
        xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
        return

    item = _resolve_anizip_ids(item)
    item = tmdb_enricher.enrich_item(item)

    service_ids = item.get('service_ids', {})
    media_type  = item.get('media_type', 'movie')
    label       = item.get('show_title') or item.get('title') or ''
    duration    = float(item.get('duration') or 0)

    play_url = _get_play_url(service_ids, media_type, item)
    li = xbmcgui.ListItem(label=label, path=play_url)
    li.setProperty('IsPlayable', 'true')

    vi = li.getVideoInfoTag()
    vi.setTitle(item.get('title') or label)
    vi.setMediaType('movie' if media_type == 'movie' else 'episode')
    if duration:
        vi.setDuration(int(duration))
    _set_unique_ids(vi, service_ids, media_type)
    for k, v in service_ids.items():
        if v:
            li.setProperty(f'{k}_id', str(v))
            if media_type == 'episode':
                li.setProperty(f'tvshow.{k}_id', str(v))
    if media_type == 'episode':
        vi.setSeason(item.get('season') or 0)
        vi.setEpisode(item.get('episode') or 0)
        vi.setTvShowTitle(item.get('show_title') or '')
    if item.get('plot'):
        vi.setPlot(item['plot'])

    art = {}
    if item.get('poster'):
        art['thumb']  = item['poster']
        art['poster'] = item['poster']
    if item.get('fanart'):
        art['fanart'] = item['fanart']
    if item.get('landscape'):
        art['landscape'] = item['landscape']
    if item.get('clearlogo'):
        art['clearlogo'] = item['clearlogo']
    if art:
        li.setArt(art)

    win = xbmcgui.Window(10000)

    # Advertise the active DB row so service.py can track local progress.
    if item.get('id'):
        win.setProperty('RabiteWatch.ActiveDbId',     str(item['id']))
        win.setProperty('RabiteWatch.ActiveDuration', str(duration))
    else:
        win.clearProperty('RabiteWatch.ActiveDbId')
        win.clearProperty('RabiteWatch.ActiveDuration')

    # resolve_item is called by Kodi after the user dismisses its native
    # "Resume / Play from beginning" dialog.  We do NOT set PendingSeek here
    # because we don't know which option the user chose.  Kodi's native
    # mechanism propagates the choice when setResumePoint was set at render
    # time.  For skin-driven resume use play_resume / play_begin instead.
    win.clearProperty('RabiteWatch.PendingSeek')

    xbmcplugin.setResolvedUrl(handle, True, li)


def play_item(handle, url, params):
    """
    Playback entry point called from context-menu RunPlugin items.
    seek_to is pre-determined by the caller and passed as a URL param.
    """
    db_id = params.get('db_id')
    if not db_id:
        return

    seek_to = float(params.get('seek_to') or 0)

    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Item not found in database',
            xbmcgui.NOTIFICATION_ERROR, 3000
        )
        return

    item = _resolve_anizip_ids(item)
    item = tmdb_enricher.enrich_item(item)
    _do_play(item, seek_to)


def play_resume(handle, url, params):
    """
    Skin-driven resume — no dialog.
    Resolves the item and seeks to the stored resume_time via PendingSeek.
    Skin calls: RunPlugin(plugin://plugin.video.rabitewatch/?action=play_resume&db_id=X)
    """
    db_id = params.get('db_id')
    if not db_id:
        return
    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification('Rabite Watch', 'Item not found', xbmcgui.NOTIFICATION_ERROR, 3000)
        return
    item = _resolve_anizip_ids(item)
    item = tmdb_enricher.enrich_item(item)
    _do_play(item, float(item.get('resume_time') or 0))


def play_begin(handle, url, params):
    """
    Skin-driven play from beginning — no dialog, no seek.
    Skin calls: RunPlugin(plugin://plugin.video.rabitewatch/?action=play_begin&db_id=X)
    """
    db_id = params.get('db_id')
    if not db_id:
        return
    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification('Rabite Watch', 'Item not found', xbmcgui.NOTIFICATION_ERROR, 3000)
        return
    item = _resolve_anizip_ids(item)
    item = tmdb_enricher.enrich_item(item)
    _do_play(item, 0.0)


def _fetch_trakt_resume(item):
    """
    Live-fetch the resume position for ONE specific item from Trakt.

    Calls /sync/playback/movies or /sync/playback/episodes (type-filtered so
    we don't pull the other type) and matches against the clicked item's IDs.
    Updates item['resume_time'], item['duration'], item['resume_pct'] in place
    and returns the item.  No-op if Trakt is not authenticated or has no entry.
    """
    service_ids = item.get('service_ids', {})
    media_type  = item.get('media_type', 'movie')
    trakt_svc   = _get_service('trakt')

    if not trakt_svc or not trakt_svc.is_authenticated():
        return item

    trakt_id = service_ids.get('trakt')
    imdb_id  = service_ids.get('imdb')
    tmdb_id  = service_ids.get('tmdb')

    try:
        pb_type = 'movies' if media_type == 'movie' else 'episodes'
        data    = trakt_svc._json(f'/sync/playback/{pb_type}?extended=full')
        if not data:
            xbmc.log('[RabiteWatch] Trakt playback: empty response', xbmc.LOGINFO)
            return item

        for entry in data:
            pct = int(entry.get('progress', 0))
            if pct <= 0 or pct >= 95:
                continue  # skip zero-progress and near-complete entries

            if media_type == 'movie':
                obj     = entry.get('movie', {})
                ids     = obj.get('ids', {})
                matched = (
                    (trakt_id and ids.get('trakt') == trakt_id) or
                    (imdb_id  and ids.get('imdb')  == imdb_id)  or
                    (tmdb_id  and ids.get('tmdb')  == tmdb_id)
                )
                if matched:
                    duration_s  = (obj.get('runtime', 0) or 0) * 60
                    resume_time = int((pct / 100.0) * duration_s) if duration_s else 0
                    item['resume_pct']  = pct
                    item['resume_time'] = float(resume_time)
                    item['duration']    = float(duration_s or item.get('duration', 0))
                    xbmc.log(f'[RabiteWatch] Trakt resume: {pct}% = {resume_time}s / {duration_s}s', xbmc.LOGINFO)
                    return item

            else:  # episode
                show     = entry.get('show', {})
                ep       = entry.get('episode', {})
                show_ids = show.get('ids', {})
                matched  = (
                    (trakt_id and show_ids.get('trakt') == trakt_id) or
                    (imdb_id  and show_ids.get('imdb')  == imdb_id)  or
                    (tmdb_id  and show_ids.get('tmdb')  == tmdb_id)
                )
                if (matched and
                        ep.get('season') == item.get('season') and
                        ep.get('number') == item.get('episode')):
                    duration_s  = (ep.get('runtime', 0) or 0) * 60
                    resume_time = int((pct / 100.0) * duration_s) if duration_s else 0
                    item['resume_pct']  = pct
                    item['resume_time'] = float(resume_time)
                    item['duration']    = float(duration_s or item.get('duration', 0))
                    xbmc.log(
                        f'[RabiteWatch] Trakt resume: S{ep.get("season")}E{ep.get("number")} '
                        f'{pct}% = {resume_time}s / {duration_s}s', xbmc.LOGINFO
                    )
                    return item

        xbmc.log('[RabiteWatch] Trakt: no active playback found for this item', xbmc.LOGINFO)

    except Exception as e:
        xbmc.log(f'[RabiteWatch] Trakt resume fetch failed: {e}', xbmc.LOGWARNING)

    return item


def _fetch_anilist_resume(item):
    """
    Live-fetch this item's AniList media list entry, extract the scrobbler
    notes block, and apply the existing resume-point parsing logic.

    Only updates the item when the scrobbler block ep matches the episode
    the user is about to play.  Returns item unchanged otherwise.
    """
    service_ids = item.get('service_ids', {})
    anilist_id  = service_ids.get('anilist')

    if not anilist_id:
        return item

    anilist_svc = _get_service('anilist')
    if not anilist_svc or not anilist_svc.is_authenticated():
        return item

    ep_to_play = item.get('episode', 1)

    query = '''
    query ($id: Int) {
        Media(id: $id, type: ANIME) {
            duration
            mediaListEntry {
                notes
            }
        }
    }
    '''
    try:
        res = anilist_svc._graphql(query, {'id': int(anilist_id)})
        if not res or not res.get('Media'):
            return item

        media_data = res['Media']
        entry      = media_data.get('mediaListEntry')

        if not entry or not entry.get('notes'):
            xbmc.log(f'[RabiteWatch] AniList: no notes for media {anilist_id}', xbmc.LOGINFO)
            return item

        from resources.lib.services.anilist import AniListPullService
        scrobbler = AniListPullService.parse_resume_point(entry['notes'])

        if not scrobbler:
            xbmc.log(f'[RabiteWatch] AniList: no scrobbler block in notes', xbmc.LOGINFO)
            return item

        if scrobbler.get('ep') != ep_to_play:
            xbmc.log(
                f'[RabiteWatch] AniList: scrobbler ep={scrobbler["ep"]} != playing ep={ep_to_play}',
                xbmc.LOGINFO
            )
            return item

        item['resume_time'] = float(scrobbler['resume'])
        if scrobbler['total'] > 0:
            item['duration'] = float(scrobbler['total'])
        elif media_data.get('duration'):
            item['duration'] = float(media_data['duration'] * 60)

        if item.get('duration', 0) > 0:
            item['resume_pct'] = min(
                int((item['resume_time'] / item['duration']) * 100), 99
            )

        xbmc.log(
            f'[RabiteWatch] AniList scrobbler: ep{ep_to_play} = '
            f'{item["resume_time"]}s / {item.get("duration", 0)}s',
            xbmc.LOGINFO
        )

    except Exception as e:
        xbmc.log(f'[RabiteWatch] AniList resume fetch failed: {e}', xbmc.LOGWARNING)

    return item


def prompt_resume_dialog(handle, url, params):
    """
    Main click handler for Continue Watching items.

    1. Shows a progress bar while fetching the live resume point from the
       tracking service (AniList scrobbler notes or Trakt playback endpoint).
    2. If a resume point is found, shows Resume / Play from beginning dialog.
    3. Launches TMDb Helper; the service.py RabiteWatchPlayer listener applies
       the seek once the stream actually starts playing.
    """
    db_id = params.get('db_id')
    if not db_id:
        return

    db   = get_database()
    item = db.get_by_id(int(db_id))
    if not item:
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Item not found', xbmcgui.NOTIFICATION_ERROR, 3000
        )
        return

    sources    = item.get('sources', [])
    show_title = item.get('show_title') or item.get('title') or 'Loading…'

    # ---- Widget fast-path: no dialogs, no live-fetch ----
    # seek_to was pre-computed at render time from the cached DB resume_time.
    # We still resolve IDs and enrich so TMDbHelper gets correct metadata,
    # but we skip the AniList/Trakt network calls and the choice dialog.
    if params.get('widget') == '1':
        item = _resolve_anizip_ids(item)
        item = tmdb_enricher.enrich_item(item)
        _do_play(item, float(params.get('seek_to') or 0))
        return

    # ---- Progress bar while resolving IDs + fetching live resume ----
    prog      = xbmcgui.DialogProgress()
    cancelled = False
    prog.create('Rabite Watch', show_title)

    try:
        prog.update(10, 'Resolving IDs...')
        item = _resolve_anizip_ids(item)
        if prog.iscanceled():
            cancelled = True

        if not cancelled:
            prog.update(30, 'Loading metadata...')
            item = tmdb_enricher.enrich_item(item)
            if prog.iscanceled():
                cancelled = True

        if not cancelled:
            svc_label = 'AniList' if 'anilist' in sources else 'Trakt' if 'trakt' in sources else 'Simkl'
            prog.update(60, f'Checking {svc_label} for resume point...')
            # AniList scrobbler is the most precise source; Trakt playback is the fallback.
            if 'anilist' in sources:
                item = _fetch_anilist_resume(item)
            if 'trakt' in sources and float(item.get('resume_time') or 0) == 0:
                item = _fetch_trakt_resume(item)
            if prog.iscanceled():
                cancelled = True

        prog.update(100, 'Done')

    except Exception as e:
        xbmc.log(f'[RabiteWatch] prompt_resume_dialog error: {e}', xbmc.LOGWARNING)
    finally:
        prog.close()

    if cancelled:
        return

    resume_time = float(item.get('resume_time') or 0)
    duration    = float(item.get('duration') or 0)

    seek_to = 0.0
    if resume_time > 0:
        dur_str = _fmt_seconds(duration) if duration > 0 else '??:??'
        choice  = xbmcgui.Dialog().contextmenu([
            f'\u25b6 Resume from {_fmt_seconds(resume_time)} / {dur_str}',
            '\u25b6 Play from beginning',
        ])
        if choice == -1:
            return  # Back / Escape — abort
        if choice == 0:
            seek_to = resume_time
        # choice == 1 → seek_to stays 0.0

    _do_play(item, seek_to)


# ===========================================================================
# SHARED NEXT UP RENDERER
# ===========================================================================

def _render_next_up_item(handle, url, title, year, poster, fanart, plot,
                          service_ids, next_season, next_episode,
                          watched_count, total_count, sources=None, source_badge=''):
    """
    Render a single Next Up episode list item.
    source_badge is kept for backward-compat callers but is now ignored in the
    label — service identity is shown via clearlogo art instead.
    sources: list of service names e.g. ['trakt'] used for clearlogo selection.
    """
    tmdb_id = service_ids.get('tmdb')
    imdb_id = service_ids.get('imdb')

    if total_count > 0:
        overall_pct  = int((watched_count / total_count) * 100)
        progress_str = f' [COLOR gold]{watched_count}/{total_count} eps ({overall_pct}%)[/COLOR]'
    elif watched_count > 0:
        progress_str = f' [COLOR gold]{watched_count} eps watched[/COLOR]'
    else:
        progress_str = ''

    label_title = f'{title} ({year})' if year else title
    # No text badge — clearlogo carries the service identity
    label = f'[B]S{next_season:02d}E{next_episode:02d}[/B] {label_title}{progress_str}'

    li = xbmcgui.ListItem(label=label)
    _set_art_with_service_icon(li, poster=poster, fanart=fanart, sources=sources or [],
                               media_type='episode')

    vi = li.getVideoInfoTag()
    vi.setTitle(title)
    vi.setMediaType('episode')
    vi.setSeason(next_season)
    vi.setEpisode(next_episode)
    if year:
        try:
            vi.setYear(int(year))
        except Exception:
            pass
    if plot:
        vi.setPlot(plot)

    # ---- Standard ID registration ----
    _set_unique_ids(vi, service_ids, 'episode')
    for k, v in service_ids.items():
        if v:
            li.setProperty(f'{k}_id', str(v))
            li.setProperty(f'tvshow.{k}_id', str(v))

    if tmdb_id:
        play_url = (f'plugin://plugin.video.themoviedb.helper/'
                    f'?info=play&tmdb_id={tmdb_id}&type=episode'
                    f'&season={next_season}&episode={next_episode}')
        li.setProperty('IsPlayable', 'true')
        is_folder = False
    elif imdb_id:
        play_url  = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
        li.setProperty('IsPlayable', 'false')
        is_folder = True
    else:
        play_url  = f'plugin://plugin.video.themoviedb.helper/?info=search&query={quote_plus(title)}&type=tv'
        li.setProperty('IsPlayable', 'false')
        is_folder = True

    xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=is_folder)


# ===========================================================================
# TRAKT
# ===========================================================================

def show_trakt_menu(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Trakt')
    trakt = _get_service('trakt')

    if trakt and trakt.is_authenticated():
        ud       = _get_user_data(trakt)
        username = ud.get('username', 'Unknown') if ud else 'Unknown'

        li = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)

        li = xbmcgui.ListItem(label='Browse My Lists')
        li.getVideoInfoTag().setPlot('Watchlist, Watching, Watched, Dropped + Next Up')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"trakt_catalogs"})}', li, isFolder=True)

        li = xbmcgui.ListItem(label='Sync Now')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"trakt_sync"})}', li, isFolder=False)

        li = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"trakt_logout"})}', li, isFolder=False)
    else:
        li = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        li = xbmcgui.ListItem(label='Authenticate')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"trakt_auth"})}', li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def show_trakt_catalogs(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Trakt Lists')

    li = xbmcgui.ListItem(label='Next Up')
    li.setArt({'icon': 'DefaultVideoPlaylists.png'})
    li.getVideoInfoTag().setPlot('Next unwatched episode for every show you are currently watching')
    xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"next_up_trakt"})}', li, isFolder=True)

    for name, status, plot in [
        ('Watchlist', 'watchlist', 'Movies and shows you plan to watch'),
        ('Watching',  'watching',  'Movies and shows you are currently watching'),
        ('Watched',   'watched',   'Movies and shows you have completed'),
        ('Dropped',   'dropped',   'Shows hidden from progress tracking'),
    ]:
        li = xbmcgui.ListItem(label=name)
        li.getVideoInfoTag().setPlot(plot)
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"trakt_browse","status":status})}', li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def browse_next_up_trakt(handle, url):
    """Show Next Up episodes fetched live from Trakt."""
    xbmcplugin.setPluginCategory(handle, 'Next Up - Trakt')
    xbmcplugin.setPluginFanart(handle, '')
    trakt = _get_service('trakt')

    if not trakt or not trakt.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Trakt[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    prog = xbmcgui.DialogProgress()
    prog.create('Trakt', 'Loading Next Up...')

    try:
        prog.update(20, 'Fetching watched shows...')
        items = trakt.fetch_next_up()
        prog.close()

        xbmcplugin.setContent(handle, 'episodes')

        if not items:
            li = xbmcgui.ListItem(label='[COLOR gray]No next up episodes found[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        else:
            for item in items:
                _render_next_up_item(
                    handle, url,
                    title=item['title'], year=item.get('year'),
                    poster=item.get('poster'), fanart=item.get('fanart'),
                    plot=item.get('plot', ''),
                    service_ids=item['service_ids'],
                    next_season=item['next_season'], next_episode=item['next_episode'],
                    watched_count=item.get('watched_count', 0),
                    total_count=item.get('total_count', 0),
                    sources=['trakt'],
                )
    except Exception as e:
        try:
            prog.close()
        except Exception:
            pass
        xbmc.log(f'[RabiteWatch] browse_next_up_trakt error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


def browse_trakt_list(handle, url, status, params=None):
    """Browse a specific Trakt list by status (live from API)."""
    labels    = {'watchlist': 'Watchlist', 'watching': 'Watching', 'watched': 'Watched', 'dropped': 'Dropped'}
    is_widget = (params or {}).get('widget') == '1'
    xbmcplugin.setPluginCategory(handle, f'Trakt - {labels.get(status, status.title())}')
    xbmcplugin.setPluginFanart(handle, '')

    trakt = _get_service('trakt')
    if not trakt or not trakt.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Trakt[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    if not is_widget:
        prog = xbmcgui.DialogProgress()
        prog.create('Trakt', f'Loading {labels.get(status, status)} list...')

    try:
        if not is_widget:
            prog.update(30, 'Fetching from Trakt...')
        items = trakt.fetch_list_by_status(status)
        if not is_widget:
            prog.close()

        if not items:
            li = xbmcgui.ListItem(label=f'[COLOR gray]No items in {labels.get(status, status)} list[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
            xbmcplugin.endOfDirectory(handle)
            return

        xbmcplugin.setContent(handle, 'videos')

        for item in items:
            media_type   = item.get('type', 'movie')
            title        = item.get('title') or 'Unknown'
            year         = item.get('year')
            plot         = item.get('plot', '')
            progress_pct = item.get('progress', 0)
            plays        = item.get('plays', 0)
            service_ids  = item.get('service_ids', {})
            tmdb_id      = service_ids.get('tmdb')
            imdb_id      = service_ids.get('imdb')

            label = f'{title} ({year})' if year else title
            if status == 'watching' and progress_pct > 0:
                label += f' [COLOR gold]{progress_pct}%[/COLOR]'
            elif status == 'watched' and plays > 0:
                label += f' [COLOR gray]x{plays}[/COLOR]'

            li = xbmcgui.ListItem(label=label)
            _set_art_with_service_icon(
                li,
                poster=item.get('poster'),
                fanart=item.get('fanart'),
                sources=['trakt'],
                media_type=media_type,
            )

            vi = li.getVideoInfoTag()
            vi.setTitle(title)
            if year:
                try:
                    vi.setYear(int(year))
                except Exception:
                    pass
            if plot:
                vi.setPlot(plot)
            vi.setMediaType('movie' if media_type == 'movie' else 'tvshow')

            _set_unique_ids(vi, service_ids)
            for k, v in service_ids.items():
                if v:
                    li.setProperty(f'{k}_id', str(v))

            # Skin properties
            li.setProperty('RabiteWatch.ListStatus', status)
            li.setProperty('RabiteWatch.MediaType',  media_type)
            li.setProperty('RabiteWatch.Sources',    'trakt')
            li.setProperty('RabiteWatch.ProgressPct', str(progress_pct))

            if media_type == 'movie' and tmdb_id:
                play_url  = f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
                li.setProperty('IsPlayable', 'true')
                is_folder = False
            elif tmdb_id:
                play_url  = f'plugin://plugin.video.themoviedb.helper/?info=details&tmdb_id={tmdb_id}&type=tv'
                li.setProperty('IsPlayable', 'false')
                is_folder = True
            elif imdb_id:
                play_url  = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
                li.setProperty('IsPlayable', 'false')
                is_folder = True
            else:
                search_type = 'movie' if media_type == 'movie' else 'tv'
                play_url    = f'plugin://plugin.video.themoviedb.helper/?info=search&query={quote_plus(title)}&type={search_type}'
                li.setProperty('IsPlayable', 'false')
                is_folder = True

            xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=is_folder)

    except Exception as e:
        if not is_widget:
            try:
                prog.close()
            except Exception:
                pass
        xbmc.log(f'[RabiteWatch] browse_trakt_list error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# SIMKL
# ===========================================================================

def show_simkl_menu(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Simkl')
    simkl = _get_service('simkl')

    if simkl and simkl.is_authenticated():
        ud       = _get_user_data(simkl)
        username = ud.get('username', 'Unknown') if ud else 'Unknown'

        li = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)

        li = xbmcgui.ListItem(label='Browse My Lists')
        li.getVideoInfoTag().setPlot('Watching, Plan to Watch, Completed, On Hold, Dropped + Next Up')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"simkl_catalogs"})}', li, isFolder=True)

        li = xbmcgui.ListItem(label='Sync Now')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"simkl_sync"})}', li, isFolder=False)

        li = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"simkl_logout"})}', li, isFolder=False)
    else:
        li = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        li = xbmcgui.ListItem(label='Connect Simkl')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"simkl_auth"})}', li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def show_simkl_catalogs(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Simkl Lists')

    li = xbmcgui.ListItem(label='Next Up')
    li.setArt({'icon': 'DefaultVideoPlaylists.png'})
    li.getVideoInfoTag().setPlot('Next unwatched episode for every show/anime you are currently watching')
    xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"next_up_simkl"})}', li, isFolder=True)

    for name, status, plot in [
        ('Watching',      'watching',    'Shows, anime, and movies you are currently watching'),
        ('Plan to Watch', 'plantowatch', 'Shows, anime, and movies you plan to watch'),
        ('Completed',     'completed',   'Shows, anime, and movies you have completed'),
        ('On Hold',       'hold',        'Shows, anime, and movies you have on hold'),
        ('Dropped',       'dropped',     'Shows, anime, and movies you have dropped'),
    ]:
        li = xbmcgui.ListItem(label=name)
        li.getVideoInfoTag().setPlot(plot)
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"simkl_browse","status":status})}', li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def browse_next_up_simkl(handle, url):
    """Show Next Up episodes from Simkl watching list."""
    xbmcplugin.setPluginCategory(handle, 'Next Up - Simkl')
    xbmcplugin.setPluginFanart(handle, '')
    simkl = _get_service('simkl')

    if not simkl or not simkl.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Simkl[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    prog = xbmcgui.DialogProgress()
    prog.create('Simkl', 'Loading Next Up...')

    try:
        all_items = []
        for i, content_type in enumerate(['shows', 'anime']):
            prog.update(int((i / 2) * 80), f'Fetching {content_type}...')
            items = simkl.fetch_all_items(content_type, 'watching')
            if items:
                for item in items:
                    item['_content_type'] = content_type
                all_items.extend(items)
        prog.close()

        xbmcplugin.setContent(handle, 'episodes')

        if not all_items:
            li = xbmcgui.ListItem(label='[COLOR gray]No shows in Simkl watching list[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        else:
            for item in all_items:
                show         = item.get('show', {})
                ids          = show.get('ids', {})
                content_type = item.get('_content_type', 'shows')

                title       = show.get('title', 'Unknown')
                year        = show.get('year')
                poster_path = show.get('poster')
                poster      = (f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg'
                               if poster_path else None)

                watched_eps  = item.get('watched_episodes_count', 0)
                total_eps    = item.get('total_episodes_count', 0)
                next_episode = watched_eps + 1
                next_season  = 1

                if total_eps > 0 and next_episode > total_eps:
                    continue

                service_ids = {k: v for k, v in {
                    'tmdb': ids.get('tmdb'), 'imdb': ids.get('imdb'),
                    'tvdb': ids.get('tvdb'), 'mal':  ids.get('mal'),
                    'simkl': ids.get('simkl'), 'anilist': ids.get('anilist'),
                }.items() if v}

                _render_next_up_item(
                    handle, url,
                    title=title, year=year,
                    poster=poster, fanart=poster, plot='',
                    service_ids=service_ids,
                    next_season=next_season, next_episode=next_episode,
                    watched_count=watched_eps, total_count=total_eps,
                    sources=['simkl'],
                )

    except Exception as e:
        try:
            prog.close()
        except Exception:
            pass
        xbmc.log(f'[RabiteWatch] browse_next_up_simkl error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


def browse_simkl_list(handle, url, status, params=None):
    """Browse a specific Simkl list (live from API)."""
    is_widget = (params or {}).get('widget') == '1'
    xbmcplugin.setPluginCategory(handle, f'Simkl - {status.title()}')
    xbmcplugin.setPluginFanart(handle, '')
    simkl = _get_service('simkl')

    if not simkl or not simkl.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    if not is_widget:
        prog = xbmcgui.DialogProgress()
        prog.create('Simkl', f'Loading {status} list...')

    try:
        all_items = []
        content_types = ['shows', 'anime', 'movies']
        for i, ct in enumerate(content_types):
            if not is_widget:
                prog.update(int((i / len(content_types)) * 100), f'Fetching {ct}...')
            items = simkl.fetch_all_items(ct, status)
            if items:
                for item in items:
                    item['_content_type'] = ct
                all_items.extend(items)
        if not is_widget:
            prog.close()

        if not all_items:
            li = xbmcgui.ListItem(label=f'[COLOR gray]No items in {status} list[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        else:
            xbmcplugin.setContent(handle, 'tvshows')
            for item in all_items:
                show         = item.get('show', {})
                content_type = item.get('_content_type', 'shows')
                ids          = show.get('ids', {})
                simkl_id     = ids.get('simkl')
                tmdb_id      = ids.get('tmdb')
                imdb_id      = ids.get('imdb')
                tvdb_id      = ids.get('tvdb')
                mal_id       = ids.get('mal')
                anilist_id   = ids.get('anilist')

                title        = show.get('title', 'Unknown')
                year         = show.get('year')
                poster_path  = show.get('poster')
                watched_eps  = item.get('watched_episodes_count', 0)
                total_eps    = item.get('total_episodes_count', 0)

                label = f'{title} ({year})' if year else title
                if status == 'watching' and total_eps > 0:
                    pct = int((watched_eps / total_eps) * 100)
                    label += f' ({watched_eps}/{total_eps}) [COLOR gold]{pct}%[/COLOR]'
                elif status == 'watching' and watched_eps > 0:
                    label += f' ({watched_eps} eps)'

                li = xbmcgui.ListItem(label=label)

                poster_url = None
                if poster_path:
                    poster_url = f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg'
                _set_art_with_service_icon(li, poster=poster_url, fanart=poster_url, sources=['simkl'],
                                           media_type='movie' if content_type == 'movies' else 'tvshow')

                vi = li.getVideoInfoTag()
                vi.setTitle(title)
                if year:
                    vi.setYear(year)
                vi.setMediaType('movie' if content_type == 'movies' else 'tvshow')

                service_ids = {k: v for k, v in {
                    'simkl': simkl_id, 'tmdb': tmdb_id, 'imdb': imdb_id,
                    'tvdb': tvdb_id, 'mal': mal_id, 'anilist': anilist_id,
                }.items() if v}
                _set_unique_ids(vi, service_ids)
                for k, v in service_ids.items():
                    li.setProperty(f'{k}_id', str(v))

                # Skin properties
                watched_eps = item.get('watched_episodes_count', 0)
                total_eps   = item.get('total_episodes_count', 0)
                pct_str = str(int((watched_eps / total_eps) * 100)) if total_eps > 0 else '0'
                li.setProperty('RabiteWatch.ListStatus',    status)
                li.setProperty('RabiteWatch.MediaType',     'movie' if content_type == 'movies' else 'tvshow')
                li.setProperty('RabiteWatch.Sources',       'simkl')
                li.setProperty('RabiteWatch.ProgressPct',   pct_str)
                li.setProperty('RabiteWatch.WatchedEps',    str(watched_eps))
                li.setProperty('RabiteWatch.TotalEps',      str(total_eps))

                if content_type == 'movies' and tmdb_id:
                    play_url  = f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
                    li.setProperty('IsPlayable', 'true')
                    is_folder = False
                elif tmdb_id:
                    play_url  = f'plugin://plugin.video.themoviedb.helper/?info=details&tmdb_id={tmdb_id}&type=tv'
                    li.setProperty('IsPlayable', 'false')
                    is_folder = True
                elif imdb_id:
                    play_url  = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
                    li.setProperty('IsPlayable', 'false')
                    is_folder = True
                else:
                    search_type = 'movie' if content_type == 'movies' else 'tv'
                    play_url    = f'plugin://plugin.video.themoviedb.helper/?info=search&query={quote_plus(title)}&type={search_type}'
                    li.setProperty('IsPlayable', 'false')
                    is_folder = True

                xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=is_folder)

    except Exception as e:
        if not is_widget:
            try:
                prog.close()
            except Exception:
                pass
        xbmc.log(f'[RabiteWatch] browse_simkl_list error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# ANILIST
# ===========================================================================

def show_anilist_menu(handle, url):
    xbmcplugin.setPluginCategory(handle, 'AniList')
    anilist = _get_service('anilist')

    if anilist and anilist.is_authenticated():
        ud       = _get_user_data(anilist)
        username = ud.get('username', 'Unknown') if ud else 'Unknown'

        li = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)

        li = xbmcgui.ListItem(label='Browse My Lists')
        li.getVideoInfoTag().setPlot('Watching, Planning, Completed, On Hold, Dropped, Repeating + Next Up')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"anilist_catalogs"})}', li, isFolder=True)

        li = xbmcgui.ListItem(label='Sync Now')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"anilist_sync"})}', li, isFolder=False)

        li = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"anilist_logout"})}', li, isFolder=False)
    else:
        li = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        li = xbmcgui.ListItem(label='Connect AniList')
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"anilist_auth"})}', li, isFolder=False)

    xbmcplugin.endOfDirectory(handle)


def show_anilist_catalogs(handle, url):
    xbmcplugin.setPluginCategory(handle, 'AniList Lists')

    li = xbmcgui.ListItem(label='Next Up')
    li.setArt({'icon': 'DefaultVideoPlaylists.png'})
    li.getVideoInfoTag().setPlot('Next unwatched episode for every anime you are currently watching')
    xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"next_up_anilist"})}', li, isFolder=True)

    for name, status, plot in [
        ('Watching',   'CURRENT',   'Anime you are currently watching'),
        ('Planning',   'PLANNING',  'Anime you plan to watch'),
        ('Completed',  'COMPLETED', 'Anime you have completed'),
        ('On Hold',    'PAUSED',    'Anime you have on hold'),
        ('Dropped',    'DROPPED',   'Anime you have dropped'),
        ('Repeating',  'REPEATING', 'Anime you are rewatching'),
    ]:
        li = xbmcgui.ListItem(label=name)
        li.getVideoInfoTag().setPlot(plot)
        xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"anilist_browse","status":status})}', li, isFolder=True)

    xbmcplugin.endOfDirectory(handle)


def browse_next_up_anilist(handle, url):
    """Show Next Up episodes from AniList CURRENT list."""
    xbmcplugin.setPluginCategory(handle, 'Next Up - AniList')
    xbmcplugin.setPluginFanart(handle, '')
    anilist = _get_service('anilist')

    if not anilist or not anilist.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated with AniList[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    prog = xbmcgui.DialogProgress()
    prog.create('AniList', 'Loading Next Up...')

    try:
        ud = _get_user_data(anilist)
        if not ud or not ud.get('user_id'):
            prog.close()
            xbmcgui.Dialog().notification('Rabite Watch', 'Failed to get user data', xbmcgui.NOTIFICATION_ERROR, 3000)
            xbmcplugin.endOfDirectory(handle)
            return

        prog.update(30, 'Fetching CURRENT list...')
        items = anilist.fetch_list_by_status(ud['user_id'], 'CURRENT')
        prog.close()

        xbmcplugin.setContent(handle, 'episodes')

        if not items:
            li = xbmcgui.ListItem(label='[COLOR gray]No anime in AniList CURRENT list[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        else:
            for entry in items:
                import re
                media         = entry.get('media', {})
                anilist_id    = media.get('id')
                mal_id        = media.get('idMal')
                title_data    = media.get('title', {})
                title         = (title_data.get('userPreferred') or
                                 title_data.get('romaji') or
                                 title_data.get('english') or 'Unknown')
                year          = (media.get('startDate') or {}).get('year')
                cover         = media.get('coverImage', {})
                poster        = cover.get('extraLarge') or cover.get('large')
                fanart        = media.get('bannerImage') or poster
                plot          = media.get('description', '')
                if plot:
                    plot = re.sub(r'<[^>]+>', '', plot)

                progress_count = entry.get('progress', 0)
                total_episodes = media.get('episodes') or 0
                next_episode   = progress_count + 1
                next_season    = 1

                if total_episodes > 0 and next_episode > total_episodes:
                    continue

                service_ids = {k: v for k, v in {
                    'anilist': anilist_id, 'mal': mal_id
                }.items() if v}

                _render_next_up_item(
                    handle, url,
                    title=title, year=year,
                    poster=poster, fanart=fanart, plot=plot,
                    service_ids=service_ids,
                    next_season=next_season, next_episode=next_episode,
                    watched_count=progress_count, total_count=total_episodes,
                    sources=['anilist'],
                )

    except Exception as e:
        try:
            prog.close()
        except Exception:
            pass
        xbmc.log(f'[RabiteWatch] browse_next_up_anilist error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


def browse_anilist_list(handle, url, status, params=None):
    """Browse a specific AniList list (live from API)."""
    is_widget = (params or {}).get('widget') == '1'
    xbmcplugin.setPluginCategory(handle, f'AniList - {status}')
    xbmcplugin.setPluginFanart(handle, '')
    anilist = _get_service('anilist')

    if not anilist or not anilist.is_authenticated():
        li = xbmcgui.ListItem(label='[COLOR red]Not authenticated[/COLOR]')
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        xbmcplugin.endOfDirectory(handle)
        return

    if not is_widget:
        prog = xbmcgui.DialogProgress()
        prog.create('AniList', f'Loading {status} list...')

    try:
        ud = _get_user_data(anilist)
        if not ud or not ud.get('user_id'):
            if not is_widget:
                prog.close()
            xbmcgui.Dialog().notification('Rabite Watch', 'Failed to get user data', xbmcgui.NOTIFICATION_ERROR, 3000)
            xbmcplugin.endOfDirectory(handle)
            return

        if not is_widget:
            prog.update(50, 'Fetching anime...')
        items = anilist.fetch_list_by_status(ud['user_id'], status)
        if not is_widget:
            prog.close()

        if not items:
            li = xbmcgui.ListItem(label=f'[COLOR gray]No items in {status} list[/COLOR]')
            xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)
        else:
            xbmcplugin.setContent(handle, 'tvshows')
            for entry in items:
                media           = entry.get('media', {})
                anilist_id      = media.get('id')
                mal_id          = media.get('idMal')
                title_data      = media.get('title', {})
                title           = (title_data.get('userPreferred') or
                                   title_data.get('romaji') or
                                   title_data.get('english') or 'Unknown')
                year_data       = media.get('startDate', {})
                year            = year_data.get('year') if year_data else None
                cover           = media.get('coverImage', {})
                poster          = cover.get('extraLarge') or cover.get('large')
                fanart          = media.get('bannerImage') or poster
                progress_count  = entry.get('progress', 0)
                total_episodes  = media.get('episodes') or 0
                score           = entry.get('score', 0)

                label = f'{title} ({year})' if year else title
                if status == 'CURRENT':
                    if total_episodes > 0:
                        pct = int((progress_count / total_episodes) * 100)
                        label += f' ({progress_count}/{total_episodes}) [COLOR gold]{pct}%[/COLOR]'
                    elif progress_count > 0:
                        label += f' ({progress_count} eps)'
                elif status == 'COMPLETED' and score > 0:
                    label += f' [Score: {score}/10]'
                elif status == 'PLANNING' and total_episodes > 0:
                    label += f' ({total_episodes} eps)'

                li = xbmcgui.ListItem(label=label)
                _set_art_with_service_icon(li, poster=poster, fanart=fanart, sources=['anilist'],
                                           media_type='tvshow')

                vi = li.getVideoInfoTag()
                vi.setTitle(title)
                vi.setMediaType('tvshow')
                if year:
                    vi.setYear(year)

                plot = media.get('description', '')
                if plot:
                    for tag in ('<br>', '</br>', '<i>', '</i>', '<b>', '</b>'):
                        plot = plot.replace(tag, '')
                if status == 'CURRENT' and progress_count > 0:
                    prog_txt = (f'\n\n[B]Progress:[/B] {progress_count}/{total_episodes} episodes'
                                if total_episodes > 0 else f'\n\n[B]Progress:[/B] {progress_count} episodes')
                    plot = (plot or '') + prog_txt
                vi.setPlot(plot)
                if score > 0:
                    vi.setRating(score)

                service_ids = {k: v for k, v in {
                    'anilist': anilist_id, 'mal': mal_id
                }.items() if v}
                _set_unique_ids(vi, service_ids)
                for k, v in service_ids.items():
                    li.setProperty(f'{k}_id', str(v))

                # Skin properties
                pct_str = str(int((progress_count / total_episodes) * 100)) if total_episodes > 0 else '0'
                li.setProperty('RabiteWatch.ListStatus',    status)
                li.setProperty('RabiteWatch.MediaType',     'anime')
                li.setProperty('RabiteWatch.Sources',       'anilist')
                li.setProperty('RabiteWatch.ProgressPct',   pct_str)
                li.setProperty('RabiteWatch.WatchedEps',    str(progress_count))
                li.setProperty('RabiteWatch.TotalEps',      str(total_episodes))
                if score > 0:
                    li.setProperty('RabiteWatch.Score',     str(score))

                play_url  = f'plugin://plugin.video.themoviedb.helper/?info=search&query={quote_plus(title)}&type=tv'
                li.setProperty('IsPlayable', 'false')
                xbmcplugin.addDirectoryItem(handle, play_url, li, isFolder=True)

    except Exception as e:
        if not is_widget:
            try:
                prog.close()
            except Exception:
                pass
        xbmcgui.Dialog().notification('Rabite Watch', f'Error: {e}', xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(handle)


# ===========================================================================
# SERVICE ACTIONS
# ===========================================================================

def _background_sync_service(service_name):
    """
    Pull a single service in a background thread and refresh when done.
    Called after a successful login so the UI is never blocked.
    """
    try:
        get_pull_manager().pull_service(service_name, force=True)
    except Exception as e:
        xbmc.log(f'[RabiteWatch] Background sync error ({service_name}): {e}', xbmc.LOGWARNING)
    xbmc.executebuiltin('Container.Refresh')


def _background_sync_all_after_logout():
    """
    Wipe all cached progress then re-sync every still-authenticated service.
    Called after a logout so the departed service's data is fully removed.
    delete_auth() is already called on the main thread before this runs,
    so pull_all() will naturally skip the logged-out service.
    """
    try:
        get_database().clear_progress()
        get_pull_manager().pull_all(force=True)
    except Exception as e:
        xbmc.log(f'[RabiteWatch] Background post-logout sync error: {e}', xbmc.LOGWARNING)
    xbmc.executebuiltin('Container.Refresh')


def trakt_authenticate():
    t = _get_service('trakt')
    if t:
        if t.authenticate():
            xbmcgui.Dialog().notification(
                'Rabite Watch', 'Trakt: Logged in! Syncing data in background...',
                xbmcgui.NOTIFICATION_INFO, 4000
            )
            threading.Thread(
                target=_background_sync_service, args=('trakt',), daemon=True
            ).start()
        else:
            xbmcgui.Dialog().notification('Rabite Watch', 'Trakt: Auth failed', xbmcgui.NOTIFICATION_ERROR, 3000)


def trakt_sync():
    t = _get_service('trakt')
    if t and t.is_authenticated():
        prog = xbmcgui.DialogProgress()
        prog.create('Rabite Watch', 'Syncing with Trakt...')
        pm = get_pull_manager()
        result = pm.pull_service('trakt')
        prog.close()
        synced = result.get('synced', 0) if result else 0
        xbmcgui.Dialog().notification('Rabite Watch', f'Trakt: Synced {synced} items', xbmcgui.NOTIFICATION_INFO, 3000)
        xbmc.executebuiltin('Container.Refresh')
    else:
        xbmcgui.Dialog().notification('Rabite Watch', 'Please authenticate first', xbmcgui.NOTIFICATION_WARNING, 3000)


def trakt_logout():
    if xbmcgui.Dialog().yesno('Logout', 'Logout from Trakt?'):
        get_database().delete_auth('trakt')
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Logged out from Trakt. Cleaning up data...',
            xbmcgui.NOTIFICATION_INFO, 4000
        )
        threading.Thread(target=_background_sync_all_after_logout, daemon=True).start()


def anilist_authenticate():
    a = _get_service('anilist')
    if a:
        if a.authenticate():
            xbmcgui.Dialog().notification(
                'Rabite Watch', 'AniList: Logged in! Syncing data in background...',
                xbmcgui.NOTIFICATION_INFO, 4000
            )
            threading.Thread(
                target=_background_sync_service, args=('anilist',), daemon=True
            ).start()
        else:
            xbmcgui.Dialog().notification('Rabite Watch', 'AniList: Auth failed', xbmcgui.NOTIFICATION_ERROR, 3000)


def anilist_sync():
    a = _get_service('anilist')
    if a and a.is_authenticated():
        prog = xbmcgui.DialogProgress()
        prog.create('Rabite Watch', 'Syncing with AniList...')
        pm = get_pull_manager()
        result = pm.pull_service('anilist')
        prog.close()
        synced = result.get('synced', 0) if result else 0
        xbmcgui.Dialog().notification('Rabite Watch', f'AniList: Synced {synced} items', xbmcgui.NOTIFICATION_INFO, 3000)
        xbmc.executebuiltin('Container.Refresh')
    else:
        xbmcgui.Dialog().notification('Rabite Watch', 'Please authenticate first', xbmcgui.NOTIFICATION_WARNING, 3000)


def anilist_logout():
    if xbmcgui.Dialog().yesno('Logout', 'Logout from AniList?'):
        get_database().delete_auth('anilist')
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Logged out from AniList. Cleaning up data...',
            xbmcgui.NOTIFICATION_INFO, 4000
        )
        threading.Thread(target=_background_sync_all_after_logout, daemon=True).start()


def simkl_authenticate():
    s = _get_service('simkl')
    if s:
        if s.authenticate():
            xbmcgui.Dialog().notification(
                'Rabite Watch', 'Simkl: Logged in! Syncing data in background...',
                xbmcgui.NOTIFICATION_INFO, 4000
            )
            threading.Thread(
                target=_background_sync_service, args=('simkl',), daemon=True
            ).start()
        else:
            xbmcgui.Dialog().notification('Rabite Watch', 'Simkl: Auth failed', xbmcgui.NOTIFICATION_ERROR, 3000)


def simkl_sync():
    s = _get_service('simkl')
    if s and s.is_authenticated():
        prog = xbmcgui.DialogProgress()
        prog.create('Rabite Watch', 'Syncing with Simkl...')
        pm = get_pull_manager()
        result = pm.pull_service('simkl')
        prog.close()
        synced = result.get('synced', 0) if result else 0
        xbmcgui.Dialog().notification('Rabite Watch', f'Simkl: Synced {synced} items', xbmcgui.NOTIFICATION_INFO, 3000)
        xbmc.executebuiltin('Container.Refresh')
    else:
        xbmcgui.Dialog().notification('Rabite Watch', 'Please authenticate first', xbmcgui.NOTIFICATION_WARNING, 3000)


def simkl_logout():
    if xbmcgui.Dialog().yesno('Logout', 'Logout from Simkl?'):
        get_database().delete_auth('simkl')
        xbmcgui.Dialog().notification(
            'Rabite Watch', 'Logged out from Simkl. Cleaning up data...',
            xbmcgui.NOTIFICATION_INFO, 4000
        )
        threading.Thread(target=_background_sync_all_after_logout, daemon=True).start()


def sync_all():
    prog = xbmcgui.DialogProgress()
    prog.create('Rabite Watch', 'Syncing all services...')
    pm = get_pull_manager()
    result = pm.pull_all()
    prog.close()
    total = result.get('total_synced', 0) if result else 0
    xbmcgui.Dialog().notification('Rabite Watch', f'Synced {total} items', xbmcgui.NOTIFICATION_INFO, 3000)
    xbmc.executebuiltin('Container.Refresh')


def show_db_stats(handle, url):
    xbmcplugin.setPluginCategory(handle, 'Database Stats')
    db    = get_database()
    stats = db.get_stats()

    for label in [
        f'Total items: {stats["total"]}',
        f'In Progress: {stats["in_progress"]}',
        f'Completed: {stats["completed"]}',
        f'Authenticated services: {stats["authenticated_services"]}',
    ]:
        li = xbmcgui.ListItem(label=label)
        xbmcplugin.addDirectoryItem(handle, '', li, isFolder=False)

    li = xbmcgui.ListItem(label='[COLOR red]Clear All Progress Data[/COLOR]')
    xbmcplugin.addDirectoryItem(handle, f'{url}?{urlencode({"action":"clear_db"})}', li, isFolder=False)
    xbmcplugin.endOfDirectory(handle)


def clear_db():
    if xbmcgui.Dialog().yesno('Clear Database', 'This will remove ALL progress data.\nAre you sure?'):
        db = get_database()
        db.clear_progress()
        xbmcgui.Dialog().notification('Rabite Watch', 'Database cleared', xbmcgui.NOTIFICATION_INFO, 3000)
        xbmc.executebuiltin('Container.Refresh')


# ===========================================================================
# ROUTER
# ===========================================================================

def main():
    try:
        handle = int(sys.argv[1])
        url    = sys.argv[0]
        params = dict(parse_qsl(sys.argv[2][1:]))
        action = params.get('action', 'main_menu')
        status = params.get('status', '')

        if   action == 'main_menu':            show_main_menu(handle, url)
        elif action == 'continue_watching':   list_continue_watching(handle, url, params)
        elif action == 'watchlist_menu':       show_watchlist_menu(handle, url)
        elif action == 'watchlist':            list_watchlist(handle, url, params)
        elif action == 'resolve_item':         resolve_item(handle, url, params)
        elif action == 'open_in_tmdbhelper':   open_in_tmdbhelper(handle, url, params)
        elif action == 'prompt_resume_dialog': prompt_resume_dialog(handle, url, params)
        elif action == 'play_item':            play_item(handle, url, params)
        elif action == 'play_resume':          play_resume(handle, url, params)
        elif action == 'play_begin':           play_begin(handle, url, params)

        # Trakt
        elif action == 'trakt_menu':         show_trakt_menu(handle, url)
        elif action == 'trakt_catalogs':     show_trakt_catalogs(handle, url)
        elif action == 'next_up_trakt':      browse_next_up_trakt(handle, url)
        elif action == 'trakt_browse':       browse_trakt_list(handle, url, status, params)
        elif action == 'trakt_auth':         trakt_authenticate()
        elif action == 'trakt_sync':         trakt_sync()
        elif action == 'trakt_logout':       trakt_logout()

        # Simkl
        elif action == 'simkl_menu':         show_simkl_menu(handle, url)
        elif action == 'simkl_catalogs':     show_simkl_catalogs(handle, url)
        elif action == 'next_up_simkl':      browse_next_up_simkl(handle, url)
        elif action == 'simkl_browse':       browse_simkl_list(handle, url, status, params)
        elif action == 'simkl_auth':         simkl_authenticate()
        elif action == 'simkl_sync':         simkl_sync()
        elif action == 'simkl_logout':       simkl_logout()

        # AniList
        elif action == 'anilist_menu':       show_anilist_menu(handle, url)
        elif action == 'anilist_catalogs':   show_anilist_catalogs(handle, url)
        elif action == 'next_up_anilist':    browse_next_up_anilist(handle, url)
        elif action == 'anilist_browse':     browse_anilist_list(handle, url, status, params)
        elif action == 'anilist_auth':       anilist_authenticate()
        elif action == 'anilist_sync':       anilist_sync()
        elif action == 'anilist_logout':     anilist_logout()

        # Global
        elif action == 'sync_all':           sync_all()
        elif action == 'db_stats':           show_db_stats(handle, url)
        elif action == 'clear_db':           clear_db()

        else:
            show_main_menu(handle, url)

    except Exception as e:
        xbmc.log(f'[RabiteWatch] main() error: {e}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)


if __name__ == '__main__':
    main()
