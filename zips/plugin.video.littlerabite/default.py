# -*- coding: utf-8 -*-
"""
Little Rabite - Plugin Entry Point (WITH RICH METADATA)
Displays Continue Watching menu from local database with posters, fanart, and descriptions.
Supports Trakt, AniList, and Simkl integration.
"""

import sys
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
from urllib.parse import urlencode, parse_qsl

# Add lib directory to path
addon = xbmcaddon.Addon()
addon_path = addon.getAddonInfo('path')
import xbmcvfs
lib_path = xbmcvfs.translatePath(f'{addon_path}/resources/lib')
sys.path.insert(0, lib_path)

from resources.lib.database import get_database
from resources.lib.managers.sync_manager import get_sync_manager
from resources.lib.services import TraktService, AniListService, SimklService
from resources.lib.library_linker import get_library_linker
from resources.lib.database_cleanup import (
    deduplicate_continue_watching,
    remove_from_continue_watching,
    clear_continue_watching,
    get_duplicate_count
)


def list_continue_watching(addon_handle, addon_url):
    """
    List Continue Watching items from LOCAL DATABASE with RICH METADATA.
    NO API calls - instant loading.

    Items are:
    - Sorted by last_watched_at DESC (most recent first)
    - Filtered by completed=0 and progress>0 (in-progress items)
    - Displayed with posters, fanart, plot, and year
    """
    xbmcplugin.setPluginCategory(addon_handle, 'Continue Watching')

    # Get database
    db = get_database()

    # Query local database (already sorted and filtered)
    items = db.get_continue_watching(limit=50)

    if not items:
        # Empty state
        xbmcplugin.setContent(addon_handle, 'videos')
        list_item = xbmcgui.ListItem(label='[COLOR gray]No items in Continue Watching[/COLOR]')
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot('Watch something to see it here!')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
    else:
        # Determine predominant content type for view mode
        movie_count = sum(1 for item in items if item.get('type') == 'movie')
        episode_count = len(items) - movie_count

        # Set content type
        if movie_count > episode_count:
            xbmcplugin.setContent(addon_handle, 'movies')
        elif episode_count > 0:
            xbmcplugin.setContent(addon_handle, 'episodes')
        else:
            xbmcplugin.setContent(addon_handle, 'videos')

        # Create list items with rich metadata
        for item in items:
            title = item.get('title', 'Unknown')
            progress = item.get('progress', 0)
            media_type = item.get('type', 'video')
            year = item.get('year')

            if media_type == 'episode':
                season = item.get('season', 0)
                episode = item.get('episode', 0)
                label = f'{title} - S{season:02d}E{episode:02d}'
            else:
                if year:
                    label = f'{title} ({year})'
                else:
                    label = title

            list_item = xbmcgui.ListItem(label=label)

            # Set artwork
            poster = item.get('poster')
            fanart = item.get('fanart')

            art = {}
            if poster:
                art['thumb'] = poster
                art['poster'] = poster
                art['icon'] = poster
            if fanart:
                art['fanart'] = fanart

            if art:
                list_item.setArt(art)

            # Set video info
            plot = item.get('plot')
            if plot:
                plot_text = plot
            else:
                plot_text = f'Resume watching from {progress}%'

            if progress > 0:
                plot_text += f'\n\n[B]Progress:[/B] {progress}%'

            video_info = list_item.getVideoInfoTag()
            video_info.setTitle(title)
            video_info.setPlot(plot_text)
            video_info.setMediaType('movie' if media_type == 'movie' else 'episode')
            video_info.setPlaycount(0)

            if year:
                video_info.setYear(year)

            if media_type == 'episode':
                video_info.setSeason(item.get('season', 0))
                video_info.setEpisode(item.get('episode', 0))
                video_info.setTvShowTitle(title)

            # Set resume point
            resume_time = item.get('resume_time', 0)
            duration = item.get('duration', 0)

            if resume_time > 0 and duration > 0:
                video_info.setResumePoint(resume_time, duration)

            if progress > 0:
                list_item.setProperty('percentplayed', str(progress))

            # Get playable URL
            service_ids = item.get('service_ids', {})
            url = get_playable_url(service_ids, media_type, item, addon_url)

            list_item.setProperty('IsPlayable', 'true')

            xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def get_playable_url(service_ids, media_type, item, addon_url):
    """Get playable URL for item."""
    if 'tmdb' in service_ids:
        tmdb_id = service_ids['tmdb']

        if media_type == 'movie':
            return f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
        elif media_type == 'episode':
            season = item.get('season', 1)
            episode = item.get('episode', 1)
            return f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=episode&season={season}&episode={episode}'

    title = item.get('title', '')
    if title:
        search_type = 'movie' if media_type == 'movie' else 'tv'
        query = urlencode({'info': 'search', 'query': title, 'type': search_type})
        return f'plugin://plugin.video.themoviedb.helper/?{query}'

    return ''


# ============================================================================
# SERVICE MENUS AND ACTIONS
# ============================================================================

def show_trakt_menu(addon_handle, addon_url):
    """Show Trakt menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'Trakt')

    sync_manager = get_sync_manager()
    trakt = sync_manager.get_service('trakt')

    if trakt and trakt.is_authenticated():
        user_data = trakt.get_user_data()
        username = user_data.get('username', 'Unknown') if user_data else 'Unknown'

        list_item = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='Browse My Lists')
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot('Browse your Trakt watchlist, watching, watched, and dropped')
        url = f'{addon_url}?{urlencode({"action": "trakt_catalogs"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

        list_item = xbmcgui.ListItem(label='Sync Now')
        url = f'{addon_url}?{urlencode({"action": "trakt_sync"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        url = f'{addon_url}?{urlencode({"action": "trakt_logout"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)
    else:
        list_item = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='Authenticate')
        url = f'{addon_url}?{urlencode({"action": "trakt_auth"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def show_trakt_catalogs(addon_handle, addon_url):
    """Show Trakt catalog categories."""
    xbmcplugin.setPluginCategory(addon_handle, 'Trakt Lists')

    # Next Up at the top
    list_item = xbmcgui.ListItem(label='Next Up')
    list_item.setArt({'icon': 'DefaultVideoPlaylists.png'})
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Next unwatched episode for every show you are currently watching')
    url = f'{addon_url}?{urlencode({"action": "next_up_trakt"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    catalogs = [
        {
            'name': 'Watchlist',
            'status': 'watchlist',
            'icon': 'DefaultFolder.png',
            'plot': 'Movies and shows you plan to watch'
        },
        {
            'name': 'Watching',
            'status': 'watching',
            'icon': 'DefaultVideoPlaylists.png',
            'plot': 'Movies and shows you are currently watching'
        },
        {
            'name': 'Watched',
            'status': 'watched',
            'icon': 'DefaultAddonService.png',
            'plot': 'Movies and shows you have completed'
        },
        {
            'name': 'Dropped',
            'status': 'dropped',
            'icon': 'DefaultAddonService.png',
            'plot': 'Shows hidden from progress tracking (dropped)'
        },
    ]

    for catalog in catalogs:
        list_item = xbmcgui.ListItem(label=catalog['name'])
        list_item.setArt({'icon': catalog['icon']})
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot(catalog['plot'])
        url = f'{addon_url}?{urlencode({"action": "trakt_browse", "status": catalog["status"]})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def browse_trakt_list(addon_handle, addon_url, status):
    """
    Browse a specific Trakt list by status.
    Fetches LIVE from Trakt API (same pattern as Simkl/AniList).
    """
    import json
    from urllib.parse import quote_plus

    status_labels = {
        'watchlist': 'Watchlist',
        'watching':  'Watching',
        'watched':   'Watched',
        'dropped':   'Dropped',
    }
    xbmcplugin.setPluginCategory(addon_handle, f'Trakt - {status_labels.get(status, status.title())}')

    sync_manager = get_sync_manager()
    trakt = sync_manager.get_service('trakt')

    if not trakt or not trakt.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Trakt[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    progress_dialog = xbmcgui.DialogProgress()
    progress_dialog.create('Trakt', f'Loading {status_labels.get(status, status)} list...')

    try:
        progress_dialog.update(30, 'Fetching from Trakt...')
        items = trakt.fetch_list_by_status(status)
        progress_dialog.close()

        if not items:
            list_item = xbmcgui.ListItem(label=f'[COLOR gray]No items in {status_labels.get(status, status)} list[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
            xbmcplugin.endOfDirectory(addon_handle)
            return

        xbmcplugin.setContent(addon_handle, 'videos')

        for item in items:
            media_type = item.get('type', 'movie')   # 'movie' or 'show'
            title      = item.get('title') or 'Unknown'
            year       = item.get('year')
            plot       = item.get('plot', '')
            poster     = item.get('poster')
            fanart     = item.get('fanart')
            progress_pct = item.get('progress', 0)
            plays      = item.get('plays', 0)
            service_ids = item.get('service_ids', {})

            tmdb_id = service_ids.get('tmdb')
            imdb_id = service_ids.get('imdb')
            tvdb_id = service_ids.get('tvdb')
            trakt_id = service_ids.get('trakt')

            # Build label
            label = f'{title} ({year})' if year else title

            if status == 'watching' and progress_pct > 0:
                label += f' [COLOR gold]{progress_pct}%[/COLOR]'
            elif status == 'watched' and plays > 0:
                label += f' [COLOR gray]x{plays}[/COLOR]'

            list_item = xbmcgui.ListItem(label=label)

            # Artwork
            art = {}
            if poster:
                art.update({'thumb': poster, 'poster': poster, 'icon': poster})
            if fanart:
                art['fanart'] = fanart
            elif poster:
                art['fanart'] = poster
            if art:
                list_item.setArt(art)

            # Video info
            video_info = list_item.getVideoInfoTag()
            video_info.setTitle(title)
            if year:
                try:
                    video_info.setYear(int(year))
                except Exception:
                    pass
            if plot:
                video_info.setPlot(plot)
            if imdb_id:
                video_info.setIMDBNumber(str(imdb_id))
            video_info.setMediaType('movie' if media_type == 'movie' else 'tvshow')

            # Store all IDs as properties
            for id_key, id_val in service_ids.items():
                if id_val:
                    list_item.setProperty(f'{id_key}_id', str(id_val))

            # Navigation URL via TMDbHelper
            if media_type == 'movie' and tmdb_id:
                url = f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
                list_item.setProperty('IsPlayable', 'true')
                is_folder = False
            elif tmdb_id:
                url = f'plugin://plugin.video.themoviedb.helper/?info=details&tmdb_id={tmdb_id}&type=tv'
                list_item.setProperty('IsPlayable', 'false')
                is_folder = True
            elif imdb_id:
                url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
                list_item.setProperty('IsPlayable', 'false')
                is_folder = True
            else:
                search_type = 'movie' if media_type == 'movie' else 'tv'
                url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={quote_plus(title)}&type={search_type}'
                list_item.setProperty('IsPlayable', 'false')
                is_folder = True

            xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=is_folder)

    except Exception as e:
        try:
            progress_dialog.close()
        except Exception:
            pass
        xbmc.log(f'[LittleRabite] browse_trakt_list error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            'Little Rabite', f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR, 3000
        )

    xbmcplugin.endOfDirectory(addon_handle)


def show_anilist_menu(addon_handle, addon_url):
    """Show AniList menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'AniList')

    sync_manager = get_sync_manager()
    anilist = sync_manager.get_service('anilist')

    if anilist and anilist.is_authenticated():
        user_data = anilist.get_user_data()
        username = user_data.get('username', 'Unknown') if user_data else 'Unknown'

        list_item = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        # Add catalog browsing options
        list_item = xbmcgui.ListItem(label='Browse My Lists')
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot('Browse your AniList watching lists, plan to watch, completed, and more')
        url = f'{addon_url}?{urlencode({"action": "anilist_catalogs"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

        list_item = xbmcgui.ListItem(label='Sync Now')
        url = f'{addon_url}?{urlencode({"action": "anilist_sync"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        url = f'{addon_url}?{urlencode({"action": "anilist_logout"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)
    else:
        list_item = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='Authenticate')
        url = f'{addon_url}?{urlencode({"action": "anilist_auth"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def show_simkl_menu(addon_handle, addon_url):
    """Show Simkl menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'Simkl')

    sync_manager = get_sync_manager()
    simkl = sync_manager.get_service('simkl')

    if simkl and simkl.is_authenticated():
        user_data = simkl.get_user_data()
        username = user_data.get('username', 'Unknown') if user_data else 'Unknown'

        list_item = xbmcgui.ListItem(label=f'[COLOR green]Logged in as: {username}[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        # Add catalog browsing options
        list_item = xbmcgui.ListItem(label='Browse My Lists')
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot('Browse your Simkl watching lists, plan to watch, completed, and more')
        url = f'{addon_url}?{urlencode({"action": "simkl_catalogs"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

        list_item = xbmcgui.ListItem(label='Sync Now')
        url = f'{addon_url}?{urlencode({"action": "simkl_sync"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='[COLOR red]Logout[/COLOR]')
        url = f'{addon_url}?{urlencode({"action": "simkl_logout"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)
    else:
        list_item = xbmcgui.ListItem(label='[COLOR yellow]Not logged in[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)

        list_item = xbmcgui.ListItem(label='Authenticate')
        url = f'{addon_url}?{urlencode({"action": "simkl_auth"})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def show_simkl_catalogs(addon_handle, addon_url):
    """Show Simkl catalog categories."""
    xbmcplugin.setPluginCategory(addon_handle, 'Simkl Lists')

    # Next Up at the top
    list_item = xbmcgui.ListItem(label='Next Up')
    list_item.setArt({'icon': 'DefaultVideoPlaylists.png'})
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Next unwatched episode for every show/anime you are currently watching')
    url = f'{addon_url}?{urlencode({"action": "next_up_simkl"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Define available catalogs
    catalogs = [
        {
            'name': 'Watching',
            'content_types': ['shows', 'anime', 'movies'],
            'status': 'watching',
            'icon': 'DefaultVideoPlaylists.png',
            'plot': 'Shows, anime, and movies you are currently watching'
        },
        {
            'name': 'Plan to Watch',
            'content_types': ['shows', 'anime', 'movies'],
            'status': 'plantowatch',
            'icon': 'DefaultFolder.png',
            'plot': 'Shows, anime, and movies you plan to watch'
        },
        {
            'name': 'Completed',
            'content_types': ['shows', 'anime', 'movies'],
            'status': 'completed',
            'icon': 'DefaultAddonService.png',
            'plot': 'Shows, anime, and movies you have completed'
        },
        {
            'name': 'On Hold',
            'content_types': ['shows', 'anime', 'movies'],
            'status': 'hold',
            'icon': 'DefaultAddonService.png',
            'plot': 'Shows, anime, and movies you have on hold'
        },
        {
            'name': 'Dropped',
            'content_types': ['shows', 'anime', 'movies'],
            'status': 'dropped',
            'icon': 'DefaultAddonService.png',
            'plot': 'Shows, anime, and movies you have dropped'
        }
    ]

    for catalog in catalogs:
        list_item = xbmcgui.ListItem(label=catalog['name'])
        list_item.setArt({'icon': catalog['icon']})

        # Use InfoTagVideo instead of deprecated setInfo
        video_info = list_item.getVideoInfoTag()
        video_info.setPlot(catalog['plot'])

        url = f'{addon_url}?{urlencode({"action": "simkl_browse", "status": catalog["status"]})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def show_anilist_catalogs(addon_handle, addon_url):
    """Show AniList catalog categories."""
    xbmcplugin.setPluginCategory(addon_handle, 'AniList Lists')

    # Next Up at the top
    list_item = xbmcgui.ListItem(label='Next Up')
    list_item.setArt({'icon': 'DefaultVideoPlaylists.png'})
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Next unwatched episode for every anime you are currently watching')
    url = f'{addon_url}?{urlencode({"action": "next_up_anilist"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Define available catalogs (AniList statuses)
    catalogs = [
        {
            'name': 'Watching',
            'status': 'CURRENT',
            'icon': 'DefaultVideoPlaylists.png',
            'plot': 'Anime you are currently watching'
        },
        {
            'name': 'Planning',
            'status': 'PLANNING',
            'icon': 'DefaultFolder.png',
            'plot': 'Anime you plan to watch'
        },
        {
            'name': 'Completed',
            'status': 'COMPLETED',
            'icon': 'DefaultAddonService.png',
            'plot': 'Anime you have completed'
        },
        {
            'name': 'On Hold',
            'status': 'PAUSED',
            'icon': 'DefaultAddonService.png',
            'plot': 'Anime you have on hold'
        },
        {
            'name': 'Dropped',
            'status': 'DROPPED',
            'icon': 'DefaultAddonService.png',
            'plot': 'Anime you have dropped'
        },
        {
            'name': 'Repeating',
            'status': 'REPEATING',
            'icon': 'DefaultAddonService.png',
            'plot': 'Anime you are rewatching'
        }
    ]

    for catalog in catalogs:
        list_item = xbmcgui.ListItem(label=catalog['name'])
        list_item.setArt({'icon': catalog['icon']})

        video_info = list_item.getVideoInfoTag()
        video_info.setPlot(catalog['plot'])

        url = f'{addon_url}?{urlencode({"action": "anilist_browse", "status": catalog["status"]})}'
        xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    xbmcplugin.endOfDirectory(addon_handle)


def browse_simkl_list(addon_handle, addon_url, status):
    """Browse a specific Simkl list."""
    xbmcplugin.setPluginCategory(addon_handle, f'Simkl - {status.title()}')

    sync_manager = get_sync_manager()
    simkl = sync_manager.get_service('simkl')

    if not simkl or not simkl.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('Simkl', f'Loading {status} list...')

    try:
        # Fetch all content types
        content_types = ['shows', 'anime', 'movies']
        all_items = []

        for i, content_type in enumerate(content_types):
            progress.update(int((i / len(content_types)) * 100), f'Fetching {content_type}...')

            items = simkl.fetch_all_items(content_type, status)
            if items:
                # Add content type to each item for display
                for item in items:
                    item['_content_type'] = content_type
                all_items.extend(items)

        progress.close()

        if not all_items:
            list_item = xbmcgui.ListItem(label=f'[COLOR gray]No items in {status} list[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        else:
            # Set content type based on what we're displaying
            xbmcplugin.setContent(addon_handle, 'tvshows')

            # Display items
            for item in all_items:
                show = item.get('show', {})
                content_type = item.get('_content_type', 'shows')

                # Get ALL available IDs
                ids = show.get('ids', {})
                simkl_id = ids.get('simkl')
                tmdb_id = ids.get('tmdb')
                imdb_id = ids.get('imdb')
                tvdb_id = ids.get('tvdb')
                mal_id = ids.get('mal')
                anilist_id = ids.get('anilist')
                kitsu_id = ids.get('kitsu')

                # Get metadata
                title = show.get('title', 'Unknown')
                year = show.get('year')
                poster_path = show.get('poster')

                # Get episode info if available
                watched_episodes = item.get('watched_episodes_count', 0)
                total_episodes = item.get('total_episodes_count', 0)

                # Build label
                if year:
                    label = f'{title} ({year})'
                else:
                    label = title

                # Add content type badge
                type_badge = {
                    'shows': '[TV]',
                    'anime': '[ANIME]',
                    'movies': '[MOVIE]'
                }.get(content_type, '')

                label = f'{type_badge} {label}'

                # Add progress info if watching
                if status == 'watching' and total_episodes > 0:
                    pct = int((watched_episodes / total_episodes) * 100)
                    label += f' ({watched_episodes}/{total_episodes}) [COLOR gold]{pct}%[/COLOR]'
                elif status == 'watching' and watched_episodes > 0:
                    label += f' ({watched_episodes} eps)'

                # Create list item
                list_item = xbmcgui.ListItem(label=label)

                # Set artwork
                if poster_path:
                    poster_url = f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg'
                    list_item.setArt({
                        'thumb': poster_url,
                        'poster': poster_url,
                        'icon': poster_url,
                        'fanart': poster_url
                    })

                # Use InfoTagVideo (modern API)
                video_info = list_item.getVideoInfoTag()
                video_info.setTitle(title)

                if year:
                    video_info.setYear(year)

                # Set media type
                if content_type == 'movies':
                    video_info.setMediaType('movie')
                else:
                    video_info.setMediaType('tvshow')

                # Set plot if available
                plot = show.get('overview', '')
                if plot:
                    video_info.setPlot(plot)

                # Set IMDb ID
                if imdb_id:
                    video_info.setIMDBNumber(imdb_id)

                # Store ALL IDs as properties for later use
                if simkl_id:
                    list_item.setProperty('simkl_id', str(simkl_id))
                if tmdb_id:
                    list_item.setProperty('tmdb_id', str(tmdb_id))
                if imdb_id:
                    list_item.setProperty('imdb_id', str(imdb_id))
                if tvdb_id:
                    list_item.setProperty('tvdb_id', str(tvdb_id))
                if mal_id:
                    list_item.setProperty('mal_id', str(mal_id))
                if anilist_id:
                    list_item.setProperty('anilist_id', str(anilist_id))
                if kitsu_id:
                    list_item.setProperty('kitsu_id', str(kitsu_id))

                # Store progress info
                if watched_episodes > 0:
                    list_item.setProperty('watched_episodes', str(watched_episodes))
                if total_episodes > 0:
                    list_item.setProperty('total_episodes', str(total_episodes))

                # Create playable URL
                if content_type == 'movies' and tmdb_id:
                    # Direct movie playback
                    url = f'plugin://plugin.video.themoviedb.helper/?info=play&tmdb_id={tmdb_id}&type=movie'
                    list_item.setProperty('IsPlayable', 'true')
                    is_folder = False
                elif tmdb_id:
                    # TV show details
                    url = f'plugin://plugin.video.themoviedb.helper/?info=details&tmdb_id={tmdb_id}&type=tv'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True
                elif imdb_id:
                    # Fallback to IMDB search
                    url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True
                elif mal_id:
                    # Fallback to title search with MAL context
                    url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={title}&type=tv'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True
                else:
                    # Last resort: title search
                    search_type = 'movie' if content_type == 'movies' else 'tv'
                    url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={title}&type={search_type}'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True

                xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=is_folder)

    except Exception as e:
        progress.close()
        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR,
            3000
        )

    xbmcplugin.endOfDirectory(addon_handle)


def browse_anilist_list(addon_handle, addon_url, status):
    """Browse a specific AniList list."""
    xbmcplugin.setPluginCategory(addon_handle, f'AniList - {status}')

    sync_manager = get_sync_manager()
    anilist = sync_manager.get_service('anilist')

    if not anilist or not anilist.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    # Show progress dialog
    progress = xbmcgui.DialogProgress()
    progress.create('AniList', f'Loading {status} list...')

    try:
        # Get user ID
        user_data = anilist.get_user_data()
        if not user_data or not user_data.get('user_id'):
            progress.close()
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Failed to get user data',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
            xbmcplugin.endOfDirectory(addon_handle)
            return

        user_id = user_data['user_id']

        # Fetch items for this status
        progress.update(50, f'Fetching anime...')
        items = anilist.fetch_list_by_status(user_id, status)

        progress.close()

        if not items:
            list_item = xbmcgui.ListItem(label=f'[COLOR gray]No items in {status} list[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        else:
            # Set content type
            xbmcplugin.setContent(addon_handle, 'tvshows')

            # Display items
            for entry in items:
                media = entry.get('media', {})

                # Get IDs
                anilist_id = media.get('id')
                mal_id = media.get('idMal')

                # Get metadata
                title_data = media.get('title', {})
                title = (title_data.get('userPreferred') or
                        title_data.get('romaji') or
                        title_data.get('english') or
                        'Unknown')

                year_data = media.get('startDate', {})
                year = year_data.get('year') if year_data else None

                # Get poster
                cover_image = media.get('coverImage', {})
                poster = cover_image.get('extraLarge') or cover_image.get('large')

                # Get fanart (banner)
                fanart = media.get('bannerImage') or poster

                # Get progress from ENTRY (not media)
                progress_count = entry.get('progress', 0)
                total_episodes = media.get('episodes') or 0

                # Get score
                score = entry.get('score', 0)

                # Build label with progress
                if year:
                    label = f'{title} ({year})'
                else:
                    label = title

                # Add [ANIME] badge
                label = f'[ANIME] {label}'

                # Add progress info based on status
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

                # Create list item
                list_item = xbmcgui.ListItem(label=label)

                # Set artwork
                if poster:
                    list_item.setArt({
                        'thumb': poster,
                        'poster': poster,
                        'icon': poster,
                        'fanart': fanart or poster
                    })

                # Set video info
                video_info = list_item.getVideoInfoTag()
                video_info.setTitle(title)
                video_info.setMediaType('tvshow')

                if year:
                    video_info.setYear(year)

                # Set plot with progress info
                plot = media.get('description', '')
                if plot:
                    # Clean HTML from description
                    plot = plot.replace('<br>', '\n')
                    plot = plot.replace('<i>', '').replace('</i>', '')
                    plot = plot.replace('<b>', '').replace('</b>', '')

                # Add progress to plot
                if status == 'CURRENT' and progress_count > 0:
                    if total_episodes > 0:
                        progress_text = f'\n\n[B]Progress:[/B] {progress_count}/{total_episodes} episodes'
                    else:
                        progress_text = f'\n\n[B]Progress:[/B] {progress_count} episodes watched'
                    plot = (plot or '') + progress_text
                elif status == 'COMPLETED' and score > 0:
                    plot = (plot or '') + f'\n\n[B]Your Score:[/B] {score}/10'

                video_info.setPlot(plot)

                # Set user rating if available
                if score > 0:
                    video_info.setRating(score)

                # Store IDs as properties
                if anilist_id:
                    list_item.setProperty('anilist_id', str(anilist_id))
                if mal_id:
                    list_item.setProperty('mal_id', str(mal_id))

                # Store progress info
                if progress_count > 0:
                    list_item.setProperty('watched_episodes', str(progress_count))
                if total_episodes > 0:
                    list_item.setProperty('total_episodes', str(total_episodes))

                # Create playable URL
                # Try to use MAL ID for TMDB Helper search
                if mal_id:
                    url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={title}&type=tv'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True
                else:
                    # Fallback to title search
                    url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={title}&type=tv'
                    list_item.setProperty('IsPlayable', 'false')
                    is_folder = True

                xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=is_folder)

    except Exception as e:
        progress.close()
        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR,
            3000
        )

    xbmcplugin.endOfDirectory(addon_handle)


# ============================================================================
# SERVICE ACTIONS
# ============================================================================

def trakt_authenticate():
    """Authenticate with Trakt."""
    sync_manager = get_sync_manager()
    trakt = sync_manager.get_service('trakt')

    if trakt:
        if trakt.authenticate():
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Trakt authentication successful!',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Trakt authentication failed',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )


def trakt_sync():
    """Sync with Trakt."""
    sync_manager = get_sync_manager()
    trakt = sync_manager.get_service('trakt')

    if trakt and trakt.is_authenticated():
        progress = xbmcgui.DialogProgress()
        progress.create('Little Rabite', 'Syncing with Trakt...')

        result = trakt.sync_pull()

        progress.close()

        if result and result.get('success'):
            synced = result.get('synced', 0)
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Synced {synced} items from Trakt',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            errors = result.get('errors', []) if result else ['Unknown error']
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Sync failed: {errors[0] if errors else "Unknown error"}',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
    else:
        xbmcgui.Dialog().notification(
            'Little Rabite',
            'Please authenticate first',
            xbmcgui.NOTIFICATION_WARNING,
            3000
        )


def trakt_logout():
    """Logout from Trakt."""
    if xbmcgui.Dialog().yesno('Logout', 'Logout from Trakt?'):
        sync_manager = get_sync_manager()
        trakt = sync_manager.get_service('trakt')

        if trakt:
            trakt.logout()
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Logged out from Trakt',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')


def anilist_authenticate():
    """Authenticate with AniList."""
    sync_manager = get_sync_manager()
    anilist = sync_manager.get_service('anilist')

    if anilist:
        if anilist.authenticate():
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'AniList authentication successful!',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'AniList authentication failed',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )


def anilist_sync():
    """Sync with AniList."""
    sync_manager = get_sync_manager()
    anilist = sync_manager.get_service('anilist')

    if anilist and anilist.is_authenticated():
        progress = xbmcgui.DialogProgress()
        progress.create('Little Rabite', 'Syncing with AniList...')

        result = anilist.sync_pull()

        progress.close()

        if result and result.get('success'):
            synced = result.get('synced', 0)
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Synced {synced} items from AniList',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            errors = result.get('errors', []) if result else ['Unknown error']
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Sync failed: {errors[0] if errors else "Unknown error"}',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
    else:
        xbmcgui.Dialog().notification(
            'Little Rabite',
            'Please authenticate first',
            xbmcgui.NOTIFICATION_WARNING,
            3000
        )


def anilist_logout():
    """Logout from AniList."""
    if xbmcgui.Dialog().yesno('Logout', 'Logout from AniList?'):
        sync_manager = get_sync_manager()
        anilist = sync_manager.get_service('anilist')

        if anilist:
            anilist.logout()
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Logged out from AniList',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')


def simkl_authenticate():
    """Authenticate with Simkl."""
    sync_manager = get_sync_manager()
    simkl = sync_manager.get_service('simkl')

    if simkl:
        if simkl.authenticate():
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Simkl authentication successful!',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Simkl authentication failed',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )


def simkl_sync():
    """Sync with Simkl."""
    sync_manager = get_sync_manager()
    simkl = sync_manager.get_service('simkl')

    if simkl and simkl.is_authenticated():
        progress = xbmcgui.DialogProgress()
        progress.create('Little Rabite', 'Syncing with Simkl...')

        result = simkl.sync_pull()

        progress.close()

        if result and result.get('success'):
            synced = result.get('synced', 0)
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Synced {synced} items from Simkl',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')
        else:
            errors = result.get('errors', []) if result else ['Unknown error']
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Sync failed: {errors[0] if errors else "Unknown error"}',
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
    else:
        xbmcgui.Dialog().notification(
            'Little Rabite',
            'Please authenticate first',
            xbmcgui.NOTIFICATION_WARNING,
            3000
        )


def simkl_logout():
    """Logout from Simkl."""
    if xbmcgui.Dialog().yesno('Logout', 'Logout from Simkl?'):
        sync_manager = get_sync_manager()
        simkl = sync_manager.get_service('simkl')

        if simkl:
            simkl.logout()
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Logged out from Simkl',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            xbmc.executebuiltin('Container.Refresh')


# ============================================================================
# LIBRARY AND CLEANUP
# ============================================================================

def library_scan():
    """Scan library and link items."""
    linker = get_library_linker()

    progress = xbmcgui.DialogProgress()
    progress.create('Library Scan', 'Scanning Kodi library...')

    try:
        result = linker.scan_and_link_library(progress_callback=progress.update)

        progress.close()

        if result:
            linked = result.get('linked', 0)
            xbmcgui.Dialog().notification(
                'Little Rabite',
                f'Linked {linked} library items',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
        else:
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'Library scan completed',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
    except Exception as e:
        progress.close()
        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR,
            3000
        )


def show_library_menu(addon_handle, addon_url):
    """Show library menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'Library')

    list_item = xbmcgui.ListItem(label='Scan Library')
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Scan your Kodi library and link items to sync services.')
    url = f'{addon_url}?{urlencode({"action": "library_scan"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def cleanup_duplicates():
    """Remove duplicate entries."""
    db = get_database()

    try:
        dup_count = get_duplicate_count(db)

        if dup_count == 0:
            xbmcgui.Dialog().notification(
                'Little Rabite',
                'No duplicates found!',
                xbmcgui.NOTIFICATION_INFO,
                3000
            )
            return

        if not xbmcgui.Dialog().yesno(
            'Remove Duplicates',
            f'Found approximately {dup_count} duplicate entries.\nRemove duplicates now?'
        ):
            return

        progress = xbmcgui.DialogProgress()
        progress.create('Removing Duplicates', 'Processing...')

        removed = deduplicate_continue_watching(db)

        progress.close()

        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Removed {removed} duplicate entries',
            xbmcgui.NOTIFICATION_INFO,
            3000
        )

        xbmc.executebuiltin('Container.Refresh')

    except Exception as e:
        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR,
            3000
        )


def clear_all_continue_watching():
    """Clear all items."""
    db = get_database()

    if not xbmcgui.Dialog().yesno(
        'Clear Continue Watching',
        'This will remove ALL items from Continue Watching.\nAre you sure?'
    ):
        return

    try:
        count = clear_continue_watching(db)

        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Cleared {count} items',
            xbmcgui.NOTIFICATION_INFO,
            3000
        )

        xbmc.executebuiltin('Container.Refresh')

    except Exception as e:
        xbmcgui.Dialog().notification(
            'Little Rabite',
            f'Error: {str(e)}',
            xbmcgui.NOTIFICATION_ERROR,
            3000
        )


def show_cleanup_menu(addon_handle, addon_url):
    """Show cleanup menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'Cleanup')

    db = get_database()

    try:
        dup_count = get_duplicate_count(db)
    except:
        dup_count = 0

    list_item = xbmcgui.ListItem(label=f'Remove Duplicates ({dup_count} found)')
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Find and remove duplicate entries in Continue Watching.')
    url = f'{addon_url}?{urlencode({"action": "cleanup_duplicates"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    list_item = xbmcgui.ListItem(label='[COLOR red]Clear All Continue Watching[/COLOR]')
    video_info = list_item.getVideoInfoTag()
    video_info.setPlot('Remove ALL items from Continue Watching.\nWARNING: This cannot be undone!')
    url = f'{addon_url}?{urlencode({"action": "clear_continue_watching"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def _render_next_up_item(addon_handle, addon_url, title, year, poster, fanart, plot,
                          service_ids, next_season, next_episode,
                          watched_count, total_count, source_badge=''):
    """Helper: render a single Next Up episode list item."""
    from urllib.parse import quote_plus

    tmdb_id = service_ids.get('tmdb')
    imdb_id = service_ids.get('imdb')

    # Progress label
    if total_count > 0:
        overall_pct = int((watched_count / total_count) * 100)
        progress_str = f' [COLOR gold]{watched_count}/{total_count} eps ({overall_pct}%)[/COLOR]'
    elif watched_count > 0:
        progress_str = f' [COLOR gold]{watched_count} eps watched[/COLOR]'
    else:
        progress_str = ''

    label_title = f'{title} ({year})' if year else title
    label = f'{source_badge}[B]S{next_season:02d}E{next_episode:02d}[/B] {label_title}{progress_str}'

    list_item = xbmcgui.ListItem(label=label)

    art = {}
    if poster:
        art.update({'thumb': poster, 'poster': poster, 'icon': poster})
    if fanart:
        art['fanart'] = fanart
    elif poster:
        art['fanart'] = poster
    if art:
        list_item.setArt(art)

    video_info = list_item.getVideoInfoTag()
    video_info.setTitle(title)
    video_info.setMediaType('episode')
    video_info.setSeason(next_season)
    video_info.setEpisode(next_episode)
    if year:
        try:
            video_info.setYear(int(year))
        except Exception:
            pass
    if plot:
        video_info.setPlot(plot)
    if imdb_id:
        video_info.setIMDBNumber(str(imdb_id))

    for id_key, id_val in service_ids.items():
        if id_val:
            list_item.setProperty(f'{id_key}_id', str(id_val))

    # Direct episode URL via TMDbHelper
    if tmdb_id:
        url = (f'plugin://plugin.video.themoviedb.helper/'
               f'?info=play&tmdb_id={tmdb_id}&type=episode'
               f'&season={next_season}&episode={next_episode}')
        list_item.setProperty('IsPlayable', 'true')
        is_folder = False
    elif imdb_id:
        url = f'plugin://plugin.video.themoviedb.helper/?info=search&query={imdb_id}'
        list_item.setProperty('IsPlayable', 'false')
        is_folder = True
    else:
        url = (f'plugin://plugin.video.themoviedb.helper/'
               f'?info=search&query={quote_plus(title)}&type=tv')
        list_item.setProperty('IsPlayable', 'false')
        is_folder = True

    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=is_folder)


def browse_next_up_trakt(addon_handle, addon_url):
    """Show Next Up episodes fetched live from Trakt."""
    xbmcplugin.setPluginCategory(addon_handle, 'Next Up - Trakt')

    sync_manager = get_sync_manager()
    trakt = sync_manager.get_service('trakt')

    if not trakt or not trakt.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Trakt[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    progress_dialog = xbmcgui.DialogProgress()
    progress_dialog.create('Trakt', 'Loading Next Up...')

    try:
        progress_dialog.update(20, 'Fetching watched shows...')
        items = trakt.fetch_next_up()
        progress_dialog.close()

        xbmcplugin.setContent(addon_handle, 'episodes')

        if not items:
            list_item = xbmcgui.ListItem(label='[COLOR gray]No next up episodes found[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        else:
            for item in items:
                _render_next_up_item(
                    addon_handle, addon_url,
                    title=item['title'], year=item.get('year'),
                    poster=item.get('poster'), fanart=item.get('fanart'),
                    plot=item.get('plot', ''),
                    service_ids=item['service_ids'],
                    next_season=item['next_season'], next_episode=item['next_episode'],
                    watched_count=item.get('watched_count', 0),
                    total_count=item.get('total_count', 0),
                    source_badge='[Trakt] ',
                )
    except Exception as e:
        try:
            progress_dialog.close()
        except Exception:
            pass
        xbmc.log(f'[LittleRabite] browse_next_up_trakt error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Little Rabite', f'Error: {str(e)}',
                                       xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(addon_handle)


def browse_next_up_simkl(addon_handle, addon_url):
    """Show Next Up episodes from Simkl watching list."""
    xbmcplugin.setPluginCategory(addon_handle, 'Next Up - Simkl')

    sync_manager = get_sync_manager()
    simkl = sync_manager.get_service('simkl')

    if not simkl or not simkl.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated with Simkl[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    progress_dialog = xbmcgui.DialogProgress()
    progress_dialog.create('Simkl', 'Loading Next Up...')

    try:
        all_items = []
        for i, content_type in enumerate(['shows', 'anime']):
            progress_dialog.update(int((i / 2) * 80), f'Fetching {content_type}...')
            items = simkl.fetch_all_items(content_type, 'watching')
            if items:
                for item in items:
                    item['_content_type'] = content_type
                all_items.extend(items)
        progress_dialog.close()

        xbmcplugin.setContent(addon_handle, 'episodes')

        if not all_items:
            list_item = xbmcgui.ListItem(label='[COLOR gray]No shows in Simkl watching list[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        else:
            for item in all_items:
                show = item.get('show', {})
                ids  = show.get('ids', {})
                tmdb_id   = ids.get('tmdb')
                imdb_id   = ids.get('imdb')
                tvdb_id   = ids.get('tvdb')
                mal_id    = ids.get('mal')
                simkl_id  = ids.get('simkl')
                anilist_id = ids.get('anilist')
                content_type = item.get('_content_type', 'shows')

                title  = show.get('title', 'Unknown')
                year   = show.get('year')
                poster_path = show.get('poster')
                poster = (f'https://wsrv.nl/?url=https://simkl.in/posters/{poster_path}_m.jpg'
                          if poster_path else None)

                watched_eps = item.get('watched_episodes_count', 0)
                total_eps   = item.get('total_episodes_count', 0)

                # Next episode is the one after the last watched
                next_episode = watched_eps + 1
                next_season  = 1  # Simkl anime uses flat episode numbering

                if total_eps > 0 and next_episode > total_eps:
                    continue  # Fully watched

                service_ids = {k: v for k, v in {
                    'tmdb': tmdb_id, 'imdb': imdb_id, 'tvdb': tvdb_id,
                    'mal': mal_id, 'simkl': simkl_id, 'anilist': anilist_id
                }.items() if v}

                badge = '[ANIME] ' if content_type == 'anime' else '[TV] '

                _render_next_up_item(
                    addon_handle, addon_url,
                    title=title, year=year,
                    poster=poster, fanart=poster,
                    plot='',
                    service_ids=service_ids,
                    next_season=next_season, next_episode=next_episode,
                    watched_count=watched_eps, total_count=total_eps,
                    source_badge=badge,
                )
    except Exception as e:
        try:
            progress_dialog.close()
        except Exception:
            pass
        xbmc.log(f'[LittleRabite] browse_next_up_simkl error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Little Rabite', f'Error: {str(e)}',
                                       xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(addon_handle)


def browse_next_up_anilist(addon_handle, addon_url):
    """Show Next Up episodes from AniList CURRENT list."""
    xbmcplugin.setPluginCategory(addon_handle, 'Next Up - AniList')

    sync_manager = get_sync_manager()
    anilist = sync_manager.get_service('anilist')

    if not anilist or not anilist.is_authenticated():
        list_item = xbmcgui.ListItem(label='[COLOR red]Not authenticated with AniList[/COLOR]')
        xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        xbmcplugin.endOfDirectory(addon_handle)
        return

    progress_dialog = xbmcgui.DialogProgress()
    progress_dialog.create('AniList', 'Loading Next Up...')

    try:
        user_data = anilist.get_user_data()
        if not user_data or not user_data.get('user_id'):
            progress_dialog.close()
            xbmcgui.Dialog().notification('Little Rabite', 'Failed to get user data',
                                           xbmcgui.NOTIFICATION_ERROR, 3000)
            xbmcplugin.endOfDirectory(addon_handle)
            return

        progress_dialog.update(30, 'Fetching CURRENT list...')
        items = anilist.fetch_list_by_status(user_data['user_id'], 'CURRENT')
        progress_dialog.close()

        xbmcplugin.setContent(addon_handle, 'episodes')

        if not items:
            list_item = xbmcgui.ListItem(label='[COLOR gray]No anime in AniList CURRENT list[/COLOR]')
            xbmcplugin.addDirectoryItem(addon_handle, '', list_item, isFolder=False)
        else:
            for entry in items:
                media = entry.get('media', {})

                anilist_id   = media.get('id')
                mal_id       = media.get('idMal')
                title_data   = media.get('title', {})
                title        = (title_data.get('userPreferred') or
                                title_data.get('romaji') or
                                title_data.get('english') or 'Unknown')
                year         = (media.get('startDate') or {}).get('year')
                cover        = media.get('coverImage', {})
                poster       = cover.get('extraLarge') or cover.get('large')
                fanart       = media.get('bannerImage') or poster
                plot         = media.get('description', '')
                if plot:
                    import re
                    plot = re.sub(r'<[^>]+>', '', plot)

                progress_count = entry.get('progress', 0)
                total_episodes = media.get('episodes') or 0

                next_episode = progress_count + 1
                next_season  = 1  # AniList uses flat episode numbers

                if total_episodes > 0 and next_episode > total_episodes:
                    continue  # Fully watched

                service_ids = {k: v for k, v in {
                    'anilist': anilist_id, 'mal': mal_id
                }.items() if v}

                _render_next_up_item(
                    addon_handle, addon_url,
                    title=title, year=year,
                    poster=poster, fanart=fanart, plot=plot,
                    service_ids=service_ids,
                    next_season=next_season, next_episode=next_episode,
                    watched_count=progress_count, total_count=total_episodes,
                    source_badge='[ANIME] ',
                )
    except Exception as e:
        try:
            progress_dialog.close()
        except Exception:
            pass
        xbmc.log(f'[LittleRabite] browse_next_up_anilist error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Little Rabite', f'Error: {str(e)}',
                                       xbmcgui.NOTIFICATION_ERROR, 3000)

    xbmcplugin.endOfDirectory(addon_handle)


def show_main_menu(addon_handle, addon_url):
    """Show main menu."""
    xbmcplugin.setPluginCategory(addon_handle, 'Little Rabite')

    # Continue Watching
    list_item = xbmcgui.ListItem(label='Continue Watching')
    list_item.setArt({'icon': 'DefaultVideoPlaylists.png'})
    url = f'{addon_url}?{urlencode({"action": "continue_watching"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Library
    list_item = xbmcgui.ListItem(label='Library')
    list_item.setArt({'icon': 'DefaultFolder.png'})
    url = f'{addon_url}?{urlencode({"action": "library_menu"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Cleanup
    list_item = xbmcgui.ListItem(label='Cleanup')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = f'{addon_url}?{urlencode({"action": "cleanup_menu"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Trakt
    list_item = xbmcgui.ListItem(label='Trakt')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = f'{addon_url}?{urlencode({"action": "trakt_menu"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # AniList
    list_item = xbmcgui.ListItem(label='AniList')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = f'{addon_url}?{urlencode({"action": "anilist_menu"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Simkl
    list_item = xbmcgui.ListItem(label='Simkl')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = f'{addon_url}?{urlencode({"action": "simkl_menu"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=True)

    # Settings
    list_item = xbmcgui.ListItem(label='Settings')
    list_item.setArt({'icon': 'DefaultAddonService.png'})
    url = f'{addon_url}?{urlencode({"action": "settings"})}'
    xbmcplugin.addDirectoryItem(addon_handle, url, list_item, isFolder=False)

    xbmcplugin.endOfDirectory(addon_handle)


def main():
    """Main entry point."""
    try:
        addon_handle = int(sys.argv[1])
        addon_url = sys.argv[0]
        params = dict(parse_qsl(sys.argv[2][1:]))

        action = params.get('action', 'main_menu')

        # Route actions
        if action == 'main_menu':
            show_main_menu(addon_handle, addon_url)

        elif action == 'continue_watching':
            list_continue_watching(addon_handle, addon_url)

        elif action == 'next_up_trakt':
            browse_next_up_trakt(addon_handle, addon_url)

        elif action == 'next_up_simkl':
            browse_next_up_simkl(addon_handle, addon_url)

        elif action == 'next_up_anilist':
            browse_next_up_anilist(addon_handle, addon_url)

        elif action == 'library_menu':
            show_library_menu(addon_handle, addon_url)

        elif action == 'library_scan':
            library_scan()

        elif action == 'cleanup_menu':
            show_cleanup_menu(addon_handle, addon_url)

        elif action == 'cleanup_duplicates':
            cleanup_duplicates()

        elif action == 'clear_continue_watching':
            clear_all_continue_watching()

        # Trakt actions
        elif action == 'trakt_menu':
            show_trakt_menu(addon_handle, addon_url)

        elif action == 'trakt_auth':
            trakt_authenticate()

        elif action == 'trakt_sync':
            trakt_sync()

        elif action == 'trakt_logout':
            trakt_logout()

        elif action == 'trakt_catalogs':
            show_trakt_catalogs(addon_handle, addon_url)

        elif action == 'trakt_browse':
            status = params.get('status', 'watchlist')
            browse_trakt_list(addon_handle, addon_url, status)

        # AniList actions
        elif action == 'anilist_menu':
            show_anilist_menu(addon_handle, addon_url)

        elif action == 'anilist_catalogs':
            show_anilist_catalogs(addon_handle, addon_url)

        elif action == 'anilist_browse':
            status = params.get('status', 'CURRENT')
            browse_anilist_list(addon_handle, addon_url, status)

        elif action == 'anilist_auth':
            anilist_authenticate()

        elif action == 'anilist_sync':
            anilist_sync()

        elif action == 'anilist_logout':
            anilist_logout()

        # Simkl actions
        elif action == 'simkl_menu':
            show_simkl_menu(addon_handle, addon_url)

        elif action == 'simkl_catalogs':
            show_simkl_catalogs(addon_handle, addon_url)

        elif action == 'simkl_browse':
            status = params.get('status', 'watching')
            browse_simkl_list(addon_handle, addon_url, status)

        elif action == 'simkl_auth':
            simkl_authenticate()

        elif action == 'simkl_sync':
            simkl_sync()

        elif action == 'simkl_logout':
            simkl_logout()

        elif action == 'settings':
            addon.openSettings()

        else:
            show_main_menu(addon_handle, addon_url)

    except Exception as e:
        xbmc.log(f'[LittleRabite] Error: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(traceback.format_exc(), xbmc.LOGERROR)


if __name__ == '__main__':
    main()
