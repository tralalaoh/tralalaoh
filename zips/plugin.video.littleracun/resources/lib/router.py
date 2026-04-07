#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Router module - Handles URL parameter parsing and routing to appropriate functions.
FIXED: Now passes plot, poster, fanart, thumbnail to play_item
"""

import xbmc
import xbmcplugin
from .utils import log, log_error, parse_params, get_plugin_handle
from .settings import Settings
from .plugin import Plugin
from .player import play_item


def route(argv):
    """
    Main routing function - parses URL parameters and calls appropriate handlers.

    Args:
        argv: sys.argv from Kodi (contains plugin URL and parameters)
    """
    try:
        # Parse parameters first
        params = parse_params(argv)
        mode = params.get('mode', '')

        log("=" * 50)
        log(f"🦝 Little Racun - Router")
        log(f"Mode: {mode}")
        log(f"Params: {params}")
        log("=" * 50)

        # Play mode doesn't need plugin handle (just executes command)
        if mode == 'play':
            # Play content with ALL metadata
            title = params.get('title', 'Unknown')
            ids = params.get('ids', '{}')
            item_type = params.get('type', 'movie')
            year = params.get('year', None)
            season = params.get('season', None)
            episode = params.get('episode', None)

            # Extract metadata for player URL template
            plot = params.get('plot', None)
            poster = params.get('poster', None)
            fanart = params.get('fanart', None)
            thumbnail = params.get('thumbnail', None)
            logo = params.get('logo', None)
            rating = params.get('rating', None)

            # 🎯 TRANSLATE IDs FOR ANIME (ARM API)
            import json
            try:
                ids_dict = json.loads(ids)
            except:
                ids_dict = {}

            log(f"IDs before translation: {len(ids_dict)}")

            # Translate using ARM API (only for anime with Kitsu ID)
            log("[ARM] Checking if translation needed...")
            try:
                # Create plugin instance to use translate method
                plugin_temp = Plugin(-1)
                ids_dict = plugin_temp.translate_ids_for_play(ids_dict, item_type)

                log(f"[ARM] Translation complete - {len(ids_dict)} total IDs")
                for id_type, id_value in ids_dict.items():
                    log(f"  → {id_type}: {id_value}")
            except Exception as e:
                log(f"[ARM] Translation failed: {str(e)}")

            # Convert back to JSON string for play_item
            ids = json.dumps(ids_dict)

            play_item(title, ids, item_type, year, season, episode, plot, poster, fanart, thumbnail, logo, rating)
            return

        # Filter dialog doesn't need plugin handle (uses Container.Update)
        if mode == 'show_filter_dialog':
            # Show genre filter dialog
            catalog_id = params.get('catalog_id', '')
            catalog_type = params.get('catalog_type', 'movie')
            catalog_source = params.get('catalog_source', 'aiometadata')
            catalog_name = params.get('catalog_name', '')
            catalog_extras = params.get('catalog_extras', '[]')

            # Create plugin with dummy handle (won't be used)
            plugin = Plugin(-1)
            plugin.show_filter_dialog(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras)
            return

        # Search dialog doesn't need plugin handle (uses Container.Update)
        if mode == 'show_search_dialog':
            # Show search input dialog
            catalog_id = params.get('catalog_id', '')
            catalog_type = params.get('catalog_type', 'movie')
            catalog_source = params.get('catalog_source', 'aiometadata')
            catalog_name = params.get('catalog_name', '')
            catalog_extras = params.get('catalog_extras', '[]')

            # Create plugin with dummy handle (won't be used)
            plugin = Plugin(-1)
            plugin.show_search_dialog(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras)
            return

        # Settings and generate UUID don't need plugin handle
        if mode == 'settings':
            Settings.open_settings()
            return

        if mode == 'generate_uuid':
            Settings.generate_uuid()
            return

        # Download player doesn't need plugin handle (uses dialogs)
        if mode == 'download_player':
            plugin = Plugin(-1)  # Dummy handle for dialog-only method
            plugin.download_player_from_url()
            return

        # View players doesn't need plugin handle (uses dialogs)
        if mode == 'view_players':
            plugin = Plugin(-1)  # Dummy handle for dialog-only method
            plugin.view_installed_players()
            return

        # Get plugin handle for directory operations
        plugin_handle = get_plugin_handle(argv)

        if plugin_handle < 0:
            log("Invalid plugin handle", level=xbmc.LOGERROR)
            return

        # Create plugin instance
        plugin = Plugin(plugin_handle)

        # Route to appropriate handler
        if mode == '':
            # Main menu
            plugin.create_main_menu()

        elif mode == 'list_items':
            # List catalog items
            catalog_id = params.get('catalog_id', '')
            catalog_type = params.get('catalog_type', 'movie')
            catalog_source = params.get('catalog_source', 'aiometadata')
            catalog_name = params.get('catalog_name', '')
            catalog_extras = params.get('catalog_extras', '[]')
            extra = params.get('extra', None)
            plugin.list_items(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras, extra)

        elif mode == 'show_metadata_provider':
            # Show metadata provider submenu (TMDB, TVDB, MAL, etc.)
            provider = params.get('provider', '')
            catalogs = params.get('catalogs', '[]')
            plugin.show_metadata_provider(provider, catalogs)

        elif mode == 'show_provider_category':
            # Show provider category submenu (e.g., TMDB → Trending → Movies/Series)
            provider = params.get('provider', '')
            category = params.get('category', '')
            catalogs = params.get('catalogs', '[]')
            plugin.show_provider_category(provider, category, catalogs)

        elif mode == 'show_provider':
            # Show streaming provider submenu (Netflix, HBO Max, etc.)
            provider_name = params.get('provider_name', '')
            provider_catalogs = params.get('provider_catalogs', '[]')
            plugin.show_provider(provider_name, provider_catalogs)

        elif mode == 'show_movie':
            # Show movie detail page with full metadata (TMDB Helper-style)
            content_id = params.get('content_id', '')
            content_type = params.get('content_type', 'movie')
            title = params.get('title', 'Unknown')
            year = params.get('year', None)
            ids = params.get('ids', '{}')
            poster = params.get('poster', '')
            fanart = params.get('fanart', '')
            logo = params.get('logo', '')
            rating = params.get('rating', '')
            plugin.show_movie(content_id, content_type, title, year, ids, poster, fanart, logo, rating)

        elif mode == 'show_episodes':
            # Show episodes for series/anime
            content_id = params.get('content_id', '')
            content_type = params.get('content_type', 'series')
            title = params.get('title', 'Unknown')
            year = params.get('year', None)
            ids = params.get('ids', '{}')
            plugin.show_episodes(content_id, content_type, title, year, ids)

        elif mode == 'show_season':
            # Show episodes for a specific season
            content_id = params.get('content_id', '')
            content_type = params.get('content_type', 'series')
            title = params.get('title', 'Unknown')
            year = params.get('year', None)
            ids = params.get('ids', '{}')
            season = params.get('season', '1')
            show_metadata = params.get('show_metadata', None)
            plugin.show_season(content_id, content_type, title, year, ids, season, show_metadata)

        elif mode == 'show_collection':
            # Show movies in a collection (franchise)
            collection_id = params.get('collection_id', '')
            collection_type = params.get('collection_type', 'tvdb')
            title = params.get('title', 'Collection')
            ids = params.get('ids', '{}')
            plugin.show_collection(collection_id, collection_type, title, ids)

        else:
            log(f"Unknown mode: {mode}", level=xbmc.LOGWARNING)
            plugin.create_main_menu()

    except Exception as e:
        log_error("CRITICAL ERROR in router", e)
        try:
            plugin_handle = get_plugin_handle(argv)
            if plugin_handle >= 0:
                xbmcplugin.endOfDirectory(plugin_handle, succeeded=False)
        except:
            pass
