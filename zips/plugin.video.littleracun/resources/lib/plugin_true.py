#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Plugin module - Enhanced with smart two-tier metadata extraction
- FAST catalog browsing (basic metadata only)
- COMPREHENSIVE extraction when user clicks (all IDs and metadata)
"""

import json
import os
import re
import xbmc
import xbmcgui
import xbmcplugin

from .utils import log, log_error, build_url, ADDON_PATH, ADDON_ID
from .settings import settings, Settings
from .api import api


# ==================== SEASON DETECTOR ====================
class SeasonDetector:
    """Detects season numbers from titles for anime"""

    # Season patterns in titles
    SEASON_PATTERNS = [
        (r'[Ss]eason\s*(\d+)', 1),           # "Season 2"
        (r'\b[Ss](\d+)\b', 1),                # "S2"
        (r'(\d+)(?:st|nd|rd|th)\s+[Ss]eason', 1),  # "2nd Season"
        (r'[Pp]art\s*(\d+)', 1),              # "Part 2"
        (r'[Cc]our\s*(\d+)', 1),              # "Cour 2"
        (r'\b([IVX]+)\b$', 'roman'),          # "II", "III"
        (r'(\d+)期', 1),                       # "2期" (Japanese)
    ]

    ROMAN_TO_INT = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
    }

    @staticmethod
    def detect_season_from_title(title, content_type='series'):
        """Detect season number from title - Returns: int or None"""
        if not title or content_type not in ['anime', 'series']:
            return None

        for pattern, group in SeasonDetector.SEASON_PATTERNS:
            match = re.search(pattern, title)
            if match:
                if group == 'roman':
                    roman = match.group(1)
                    season_num = SeasonDetector.ROMAN_TO_INT.get(roman)
                    if season_num:
                        return season_num
                else:
                    try:
                        season_num = int(match.group(group))
                        if 1 <= season_num <= 50:
                            return season_num
                    except (ValueError, IndexError):
                        continue
        return None

    @staticmethod
    def should_apply_offset(title, content_type, videos):
        """
        Determine if season offset should be applied for anime
        Returns: (should_apply: bool, offset: int)
        """
        if content_type not in ['anime', 'series']:
            return False, 0

        detected_season = SeasonDetector.detect_season_from_title(title, content_type)

        if not detected_season or detected_season == 1:
            return False, 0

        # Check if all episodes are marked as season 1
        if videos:
            unique_seasons = set(v.get('season', 1) for v in videos)
            if unique_seasons == {1}:
                # Title says "Season 2" but JSON episodes are all "season 1"
                offset = detected_season - 1
                log(f"[ANIME] Season offset detected: '{title}' → offset +{offset}")
                return True, offset

        return False, 0
# ==================== END SEASON DETECTOR ====================


# ==================== ARM API ID TRANSLATOR ====================
class ARMTranslator:
    """Translates anime IDs using ARM (Anime Relations Mapper) API"""

    ARM_API_URL = "https://arm.haglund.dev/api/v2/ids"

    SOURCE_MAP = {
        'mal': 'myanimelist',
        'myanimelist': 'myanimelist',
        'anilist': 'anilist',
        'kitsu': 'kitsu',
        'anidb': 'anidb',
        'imdb': 'imdb',
        'tmdb': 'themoviedb',
        'thetvdb': 'thetvdb',
        'tvdb': 'thetvdb'
    }

    @staticmethod
    def translate_ids(source_type, source_id, timeout=5):
        """
        Translate a single ID to ALL other anime database IDs
        Returns: dict with all available IDs or None
        """
        try:
            import requests

            # Map short code to API name
            api_source = ARMTranslator.SOURCE_MAP.get(source_type.lower())
            if not api_source:
                log(f"[ARM] Unknown source type: {source_type}")
                return None

            params = {
                'source': api_source,
                'id': str(source_id)
            }

            log(f"[ARM] Translating {source_type}:{source_id}...")

            response = requests.get(
                ARMTranslator.ARM_API_URL,
                params=params,
                timeout=timeout
            )

            if response.status_code == 200:
                data = response.json()
                log(f"[ARM] Translation successful: {len(data)} IDs found")
                return data
            elif response.status_code == 404:
                log(f"[ARM] ID not found in ARM database")
                return None
            else:
                log(f"[ARM] API returned status {response.status_code}")
                return None

        except Exception as e:
            log(f"[ARM] Translation failed: {str(e)}")
            return None

    @staticmethod
    def enhance_ids(existing_ids, content_type='series'):
        """
        Enhance existing IDs by translating via ARM API
        Prioritizes Kitsu for anime, adds MAL and AniList
        """
        if content_type not in ['anime', 'series']:
            return existing_ids

        enhanced = dict(existing_ids)

        # Try Kitsu first (best for anime)
        if 'kitsu' in existing_ids and existing_ids['kitsu']:
            arm_ids = ARMTranslator.translate_ids('kitsu', existing_ids['kitsu'])
            if arm_ids:
                for key, value in arm_ids.items():
                    if value and key not in enhanced:
                        enhanced[key] = str(value)
                        log(f"[ARM] Added {key} = {value}")
                        # Also map myanimelist to mal
                        if key == 'myanimelist' and 'mal' not in enhanced:
                            enhanced['mal'] = str(value)
                            log(f"[ARM] Added mal = {value}")
                return enhanced

        # Try MAL if no Kitsu
        if 'mal' in existing_ids and existing_ids['mal']:
            arm_ids = ARMTranslator.translate_ids('mal', existing_ids['mal'])
            if arm_ids:
                for key, value in arm_ids.items():
                    if value and key not in enhanced:
                        enhanced[key] = str(value)
                        log(f"[ARM] Added {key} = {value}")
                        # Also map myanimelist to mal
                        if key == 'myanimelist' and 'mal' not in enhanced:
                            enhanced['mal'] = str(value)
                            log(f"[ARM] Added mal = {value}")
                return enhanced

        # Try AniList
        if 'anilist' in existing_ids and existing_ids['anilist']:
            arm_ids = ARMTranslator.translate_ids('anilist', existing_ids['anilist'])
            if arm_ids:
                for key, value in arm_ids.items():
                    if value and key not in enhanced:
                        enhanced[key] = str(value)
                        log(f"[ARM] Added {key} = {value}")
                        # Also map myanimelist to mal
                        if key == 'myanimelist' and 'mal' not in enhanced:
                            enhanced['mal'] = str(value)
                            log(f"[ARM] Added mal = {value}")
                return enhanced

        return enhanced
# ==================== END ARM API ====================



# Provider grouping configuration
PROVIDER_CONFIG = {
    'streaming': {
        'Netflix': 'Netflix',
        'HBO Max': 'HBO Max',
        'Disney+': 'Disney+',
        'Prime Video': 'Prime Video',
        'Apple TV+': 'Apple TV+',
        'Paramount+': 'Paramount+',
        'Peacock Premium': 'Peacock Premium',
        'Hulu': 'Hulu',
        'Crunchyroll': 'Crunchyroll',
        'Starz': 'Starz'
    },
    'metadata': {
        'TMDB': {
            'prefix': 'tmdb.',
            'display': 'TMDB',
            'keywords': ['TMDB'],
            'group_by_category': True
        },
        'TVDB': {
            'prefix': 'tvdb.',
            'display': 'TVDB',
            'keywords': ['TVDB'],
            'group_by_category': True
        },
        'MAL': {
            'prefix': 'mal.',
            'display': 'MAL',
            'keywords': ['MAL'],
            'group_by_category': True
        },
        'TVmaze': {
            'prefix': 'tvmaze.',
            'display': 'TVmaze',
            'keywords': ['TVmaze'],
            'group_by_category': False
        }
    }
}


class Plugin:
    """Main plugin class with smart two-tier metadata extraction"""

    def __init__(self, plugin_handle):
        self.handle = plugin_handle
        self.api = api

    def get_type_prefix(self, catalog_type):
        """Get display prefix for catalog type"""
        type_map = {
            'movie': 'Movies',
            'series': 'Series',
            'anime': 'Anime',
            'tvshow': 'Series'
        }
        return type_map.get(catalog_type, '')

    def create_main_menu(self):
        """Create main menu with extended provider grouping"""
        log("Creating main menu with extended grouping")

        try:
            if not Settings.check_configured():
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            config_data = self.api.get_config()
            catalogs = config_data.get('config', {}).get('catalogs', [])

            filtered_catalogs = [
                catalog for catalog in catalogs
                if catalog.get('enabled', False) and catalog.get('showInHome', False)
            ]

            log(f"Found {len(filtered_catalogs)} catalogs to display")

            if len(filtered_catalogs) == 0:
                log("No catalogs to display", level=xbmc.LOGWARNING)

                manifest_url = f"{settings.server_url}/stremio/{settings.user_uuid}/manifest.json"
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "No catalogs available![CR][CR]"
                    f"Configure your UUID at:[CR]{manifest_url}"
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            self._add_settings_item()

            grouped = self._group_catalogs(filtered_catalogs)

            self._add_search_catalogs(grouped['search'])
            self._add_metadata_groups(grouped['metadata'])
            self._add_streaming_groups(grouped['streaming'])
            self._add_user_catalogs(grouped['user'])
            self._add_standalone_catalogs(grouped['standalone'])

            xbmcplugin.endOfDirectory(self.handle)

        except Exception as e:
            log_error("Error in create_main_menu", e)
            xbmcgui.Dialog().notification(
                "Little Racun",
                "Error creating main menu",
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _add_settings_item(self):
        """Add settings menu item"""
        list_item = xbmcgui.ListItem(label="Settings")
        list_item.setArt({'icon': 'DefaultAddonService.png'})
        url = build_url({'mode': 'settings'})
        xbmcplugin.addDirectoryItem(
            handle=self.handle,
            url=url,
            listitem=list_item,
            isFolder=False
        )

    def _group_catalogs(self, catalogs):
        """Group catalogs by type"""
        groups = {
            'streaming': {},
            'metadata': {},
            'search': [],
            'user': [],
            'standalone': []
        }

        for catalog in catalogs:
            catalog_name = catalog.get('name', '')
            catalog_id = catalog.get('id', '')
            catalog_extras = catalog.get('extra', [])

            if self._is_search_catalog(catalog_extras):
                groups['search'].append(catalog)
                continue

            if self._is_user_catalog(catalog_name):
                groups['user'].append(catalog)
                continue

            streaming_provider = self._get_streaming_provider(catalog_name)
            if streaming_provider:
                if streaming_provider not in groups['streaming']:
                    groups['streaming'][streaming_provider] = []
                groups['streaming'][streaming_provider].append(catalog)
                continue

            metadata_provider = self._get_metadata_provider(catalog_name, catalog_id)
            if metadata_provider:
                if metadata_provider not in groups['metadata']:
                    groups['metadata'][metadata_provider] = []
                groups['metadata'][metadata_provider].append(catalog)
                continue

            groups['standalone'].append(catalog)

        return groups

    def _is_search_catalog(self, extras):
        """Check if catalog is a search catalog"""
        return any(ex.get('name') == 'search' for ex in extras)

    def _is_user_catalog(self, catalog_name):
        """Check if catalog is a user catalog"""
        user_keywords = ['Favorites', 'Watchlist']
        return any(keyword in catalog_name for keyword in user_keywords)

    def _get_streaming_provider(self, catalog_name):
        """Get streaming provider name (AUTO-DETECTION)"""
        for provider in PROVIDER_CONFIG['streaming'].keys():
            if provider in catalog_name:
                return provider

        streaming_keywords = [
            'Netflix', 'HBO', 'Disney', 'Prime', 'Apple TV', 'Paramount',
            'Peacock', 'Hulu', 'Crunchyroll', 'Starz', 'Max', 'Plus',
            'Showtime', 'ESPN', 'Discovery', 'AMC', 'FX', 'Vudu',
            'Tubi', 'Pluto', 'Roku', 'Shudder', 'BritBox', 'Acorn'
        ]

        for keyword in streaming_keywords:
            if keyword.lower() in catalog_name.lower():
                provider = catalog_name.split('(')[0].split('-')[0].strip()
                log(f"Auto-detected NEW streaming provider: {provider}")
                return provider

        return None

    def _get_metadata_provider(self, catalog_name, catalog_id):
        """Get metadata provider name"""
        for provider, config in PROVIDER_CONFIG['metadata'].items():
            if catalog_id.startswith(config['prefix']):
                return provider
            for keyword in config['keywords']:
                if keyword in catalog_name:
                    return provider
        return None

    def _add_search_catalogs(self, search_catalogs):
        """Add search catalogs"""
        for catalog in search_catalogs:
            try:
                catalog_id = catalog.get('id', '')
                catalog_name = catalog.get('name', 'Search')
                catalog_type = catalog.get('type', 'movie')
                catalog_source = catalog.get('source', 'aiometadata')
                catalog_extras = catalog.get('extra', [])

                list_item = xbmcgui.ListItem(label=catalog_name)
                list_item.setArt({'icon': 'DefaultAddonSearch.png'})
                list_item.setProperty('IsPlayable', 'false')

                url = build_url({
                    'mode': 'list_items',
                    'catalog_id': catalog_id,
                    'catalog_type': catalog_type,
                    'catalog_source': catalog_source,
                    'catalog_name': catalog_name,
                    'catalog_extras': json.dumps(catalog_extras)
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=True
                )
            except Exception as e:
                log_error(f"Error adding search catalog", e)

    def _add_metadata_groups(self, metadata_groups):
        """Add metadata provider groups"""
        for provider, catalogs in sorted(metadata_groups.items()):
            try:
                config = PROVIDER_CONFIG['metadata'][provider]

                list_item = xbmcgui.ListItem(label=config['display'])
                list_item.setArt({'icon': 'DefaultVideo.png', 'thumb': 'DefaultVideo.png'})
                list_item.setProperty('IsPlayable', 'false')

                url = build_url({
                    'mode': 'show_metadata_provider',
                    'provider': provider,
                    'catalogs': json.dumps([{
                        'id': c.get('id'),
                        'name': c.get('name'),
                        'type': c.get('type'),
                        'source': c.get('source'),
                        'extra': c.get('extra', [])
                    } for c in catalogs])
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=True
                )
            except Exception as e:
                log_error(f"Error creating metadata group: {provider}", e)

    def _add_streaming_groups(self, streaming_groups):
        """Add streaming provider groups"""
        for provider, catalogs in sorted(streaming_groups.items()):
            try:
                display_name = PROVIDER_CONFIG['streaming'].get(provider, provider)

                list_item = xbmcgui.ListItem(label=display_name)
                list_item.setArt({'icon': 'DefaultVideo.png', 'thumb': 'DefaultVideo.png'})
                list_item.setProperty('IsPlayable', 'false')

                url = build_url({
                    'mode': 'show_provider',
                    'provider_name': provider,
                    'provider_catalogs': json.dumps([{
                        'id': c.get('id'),
                        'name': c.get('name'),
                        'type': c.get('type'),
                        'source': c.get('source'),
                        'extra': c.get('extra', [])
                    } for c in catalogs])
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=True
                )
            except Exception as e:
                log_error(f"Error creating streaming group: {provider}", e)

    def _add_user_catalogs(self, user_catalogs):
        """Add user catalogs"""
        for catalog in user_catalogs:
            self._add_standalone_catalog(catalog)

    def _add_standalone_catalogs(self, standalone_catalogs):
        """Add standalone catalogs"""
        for catalog in standalone_catalogs:
            self._add_standalone_catalog(catalog)

    def _add_standalone_catalog(self, catalog):
        """Add a single catalog"""
        try:
            catalog_id = catalog.get('id', '')
            catalog_name = catalog.get('name', 'Unknown')
            catalog_type = catalog.get('type', 'movie')
            catalog_source = catalog.get('source', 'aiometadata')
            catalog_extras = catalog.get('extra', [])

            type_prefix = self.get_type_prefix(catalog_type)
            display_name = f"{type_prefix} - {catalog_name}"

            list_item = xbmcgui.ListItem(label=display_name)
            icon = self._get_icon_for_source(catalog_source)
            list_item.setArt({'icon': icon, 'thumb': icon})
            list_item.setProperty('IsPlayable', 'false')

            url = build_url({
                'mode': 'list_items',
                'catalog_id': catalog_id,
                'catalog_type': catalog_type,
                'catalog_source': catalog_source,
                'catalog_name': catalog_name,
                'catalog_extras': json.dumps(catalog_extras)
            })

            xbmcplugin.addDirectoryItem(
                handle=self.handle,
                url=url,
                listitem=list_item,
                isFolder=True
            )
        except Exception as e:
            log_error(f"Error adding standalone catalog", e)

    def _get_icon_for_source(self, source):
        """Get icon based on source with custom image support"""
        import os
        from .utils import ADDON_PATH

        # Map source to custom icon name
        icon_name_map = {
            'tmdb': 'category_tmdb',
            'tvdb': 'category_tvdb',
            'mal': 'category_mal',
            'kitsu': 'category_kitsu',
            'streaming': 'category_streaming',
            'tvmaze': 'category_tvmaze',
            'aiometadata': 'category_aiometadata',
            'user': 'category_user',
            'mdblist': 'category_mdblist',
            'trakt': 'category_trakt'
        }

        # Try custom icon first
        icon_name = icon_name_map.get(source, f'category_{source}')
        custom_path = os.path.join(ADDON_PATH, 'resources', 'media', f'{icon_name}.png')

        if os.path.exists(custom_path):
            log(f"Using custom icon for {source}: {custom_path}")
            return custom_path

        # Fallback to Kodi default icons
        fallback_icons = {
            'tmdb': 'DefaultVideo.png',
            'tvdb': 'DefaultTVShows.png',
            'mal': 'DefaultVideo.png',
            'kitsu': 'DefaultVideo.png',
            'streaming': 'DefaultMovies.png',
            'tvmaze': 'DefaultTVShows.png',
            'aiometadata': 'DefaultVideo.png',
            'user': 'DefaultUser.png',
            'mdblist': 'DefaultMovies.png',
            'trakt': 'DefaultVideo.png'
        }

        return fallback_icons.get(source, 'DefaultFolder.png')

    def show_metadata_provider(self, provider, catalogs_json):
        """Show metadata provider submenu"""
        try:
            catalogs = json.loads(catalogs_json)
            categories = self._group_by_category(catalogs)

            for category_name, category_catalogs in sorted(categories.items()):
                types = set(c.get('type') for c in category_catalogs)

                if len(types) > 1:
                    list_item = xbmcgui.ListItem(label=category_name)
                    list_item.setArt({'icon': 'DefaultFolder.png'})
                    list_item.setProperty('IsPlayable', 'false')

                    url = build_url({
                        'mode': 'show_provider_category',
                        'provider': provider,
                        'category': category_name,
                        'catalogs': json.dumps(category_catalogs)
                    })

                    xbmcplugin.addDirectoryItem(
                        handle=self.handle,
                        url=url,
                        listitem=list_item,
                        isFolder=True
                    )
                else:
                    catalog = category_catalogs[0]
                    self._add_catalog_item(catalog, use_category_name=True, category_name=category_name)

            xbmcplugin.endOfDirectory(self.handle)
        except Exception as e:
            log_error("Error in show_metadata_provider", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _group_by_category(self, catalogs):
        """Group catalogs by category"""
        categories = {}

        for catalog in catalogs:
            name = catalog.get('name', '')
            parts = name.split(' - ')
            if len(parts) > 1:
                category = parts[-1]
            else:
                for provider in ['TMDB', 'TVDB', 'MAL', 'TVmaze']:
                    if name.startswith(provider):
                        category = name[len(provider):].strip()
                        break
                else:
                    category = name

            if category not in categories:
                categories[category] = []
            categories[category].append(catalog)

        return categories

    def show_provider_category(self, provider, category, catalogs_json):
        """Show provider category submenu"""
        try:
            catalogs = json.loads(catalogs_json)

            by_type = {}
            for catalog in catalogs:
                catalog_type = catalog.get('type', 'movie')
                if catalog_type not in by_type:
                    by_type[catalog_type] = []
                by_type[catalog_type].append(catalog)

            for catalog_type, type_catalogs in sorted(by_type.items()):
                catalog = type_catalogs[0]

                type_prefix = self.get_type_prefix(catalog_type)
                display_name = type_prefix.split(' - ')[0]

                list_item = xbmcgui.ListItem(label=display_name)
                list_item.setArt({'icon': self._get_icon_for_source(catalog.get('source'))})
                list_item.setProperty('IsPlayable', 'false')

                url = build_url({
                    'mode': 'list_items',
                    'catalog_id': catalog.get('id', ''),
                    'catalog_type': catalog_type,
                    'catalog_source': catalog.get('source', 'aiometadata'),
                    'catalog_name': catalog.get('name', category),
                    'catalog_extras': json.dumps(catalog.get('extra', []))
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=True
                )

            xbmcplugin.endOfDirectory(self.handle)
        except Exception as e:
            log_error("Error in show_provider_category", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def show_provider(self, provider_name, provider_catalogs_json):
        """Show streaming provider submenu"""
        try:
            catalogs = json.loads(provider_catalogs_json)

            by_type = {}
            for catalog in catalogs:
                catalog_type = catalog.get('type', 'movie')
                if catalog_type not in by_type:
                    by_type[catalog_type] = []
                by_type[catalog_type].append(catalog)

            for catalog_type, type_catalogs in sorted(by_type.items()):
                catalog = type_catalogs[0]

                type_prefix = self.get_type_prefix(catalog_type)
                display_name = type_prefix.split(' - ')[0]

                list_item = xbmcgui.ListItem(label=display_name)
                list_item.setArt({'icon': self._get_icon_for_source(catalog.get('source'))})
                list_item.setProperty('IsPlayable', 'false')

                url = build_url({
                    'mode': 'list_items',
                    'catalog_id': catalog.get('id', ''),
                    'catalog_type': catalog_type,
                    'catalog_source': catalog.get('source', 'aiometadata'),
                    'catalog_name': catalog.get('name', provider_name),
                    'catalog_extras': json.dumps(catalog.get('extra', []))
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=True
                )

            xbmcplugin.endOfDirectory(self.handle)
        except Exception as e:
            log_error("Error in show_provider", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _add_catalog_item(self, catalog, use_category_name=False, category_name=None):
        """Add catalog as directory item"""
        try:
            catalog_id = catalog.get('id', '')
            catalog_name = category_name if use_category_name else catalog.get('name', 'Unknown')
            catalog_type = catalog.get('type', 'movie')
            catalog_source = catalog.get('source', 'aiometadata')
            catalog_extras = catalog.get('extra', [])

            list_item = xbmcgui.ListItem(label=catalog_name)
            list_item.setArt({'icon': self._get_icon_for_source(catalog_source)})
            list_item.setProperty('IsPlayable', 'false')

            url = build_url({
                'mode': 'list_items',
                'catalog_id': catalog_id,
                'catalog_type': catalog_type,
                'catalog_source': catalog_source,
                'catalog_name': catalog_name,
                'catalog_extras': json.dumps(catalog_extras)
            })

            xbmcplugin.addDirectoryItem(
                handle=self.handle,
                url=url,
                listitem=list_item,
                isFolder=True
            )
        except Exception as e:
            log_error("Error adding catalog item", e)

    def list_items(self, catalog_id, catalog_type, catalog_source, catalog_name='', catalog_extras='[]', extra=None):
        """List items for a catalog - FAST browsing with basic metadata"""
        log(f"Listing items: {catalog_id} (type: {catalog_type}, extra: {extra})")

        try:
            try:
                extras_list = json.loads(catalog_extras)
            except:
                extras_list = []

            search_extra = next((ex for ex in extras_list if ex.get('name') == 'search'), None)
            is_search_catalog = search_extra is not None

            if is_search_catalog and not extra:
                log("Search catalog detected - showing search dialog")
                self.show_search_dialog(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras)
                return

            genre_extra = next((ex for ex in extras_list if ex.get('name') == 'genre'), None)
            has_genres = genre_extra is not None

            if not is_search_catalog and has_genres:
                self._add_filter_entry(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras)

            self._fetch_and_display_catalog(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras, extra)

        except Exception as e:
            log_error("Error in list_items", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _add_filter_entry(self, catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras):
        """Add filter entry at top of catalog"""
        filter_item = xbmcgui.ListItem(label="ðŸ” FILTER")

        filter_poster = os.path.join(ADDON_PATH, 'resources/media', 'Filter.png')
        if not os.path.exists(filter_poster):
            filter_poster = 'DefaultAddonService.png'

        filter_item.setArt({
            'icon': filter_poster,
            'thumb': filter_poster,
            'poster': filter_poster,
            'fanart': filter_poster
        })

        # Use InfoTagVideo
        video_info = filter_item.getVideoInfoTag()
        video_info.setTitle('FILTER')
        video_info.setPlot('Click to filter by genre')
        video_info.setYear(1900)
        video_info.setMediaType('video')

        filter_item.setProperty('IsPlayable', 'false')

        filter_url = build_url({
            'mode': 'show_filter_dialog',
            'catalog_id': catalog_id,
            'catalog_type': catalog_type,
            'catalog_source': catalog_source,
            'catalog_name': catalog_name,
            'catalog_extras': catalog_extras
        })

        xbmcplugin.addDirectoryItem(
            handle=self.handle,
            url=filter_url,
            listitem=filter_item,
            isFolder=False
        )

    def _fetch_and_display_catalog(self, catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras, extra=None, is_search_results=False):
        """Fetch catalog and display items with BASIC metadata for fast browsing"""
        try:
            progress = xbmcgui.DialogProgress()
            progress.create("Little Racun", f"Loading {catalog_name}...")

            data = self.api.get_catalog(catalog_id, catalog_type, extra)
            progress.close()

            if not data:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "Failed to fetch catalog",
                    xbmcgui.NOTIFICATION_ERROR,
                    5000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            metas = data.get('metas', [])

            if not metas:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "No results found" if is_search_results else "No items found",
                    xbmcgui.NOTIFICATION_INFO,
                    3000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            log(f"Found {len(metas)} items in catalog")

            # Create list items with BASIC metadata (fast)
            for item in metas:
                try:
                    self._create_list_item_basic(item, catalog_type)
                except Exception as e:
                    log_error("Error creating list item", e)

            # Add "Next Page" button if catalog has more items
            self._add_next_page_button(
                metas,
                catalog_id,
                catalog_type,
                catalog_source,
                catalog_name,
                catalog_extras,
                extra
            )

            if catalog_type == 'movie':
                xbmcplugin.setContent(self.handle, 'movies')
            elif catalog_type == 'series':
                xbmcplugin.setContent(self.handle, 'tvshows')
            else:
                xbmcplugin.setContent(self.handle, 'videos')

            xbmcplugin.endOfDirectory(self.handle)

        except Exception as e:
            log_error("Error in _fetch_and_display_catalog", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _get_custom_icon(self, icon_name):
        """Get custom icon path or fall back to default"""
        import os
        from .utils import ADDON_PATH

        # Try custom icon first
        custom_path = os.path.join(ADDON_PATH, 'resources', 'media', f'{icon_name}.png')
        if os.path.exists(custom_path):
            log(f"Using custom icon: {custom_path}")
            return custom_path

        # Fallback to Kodi default icons
        fallback_icons = {
            'next_page': 'DefaultFolderSquare.png',
            'category_movie': 'DefaultMovies.png',
            'category_series': 'DefaultTVShows.png',
            'category_anime': 'DefaultVideo.png'
        }

        return fallback_icons.get(icon_name, 'DefaultFolder.png')

    def _add_next_page_button(self, metas, catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras, extra):
        """Add 'Next Page' button if catalog has more items"""
        log(f"[PAGINATION-DEBUG] Method called! Items: {len(metas)}, Extra: {extra}")

        try:
            # Parse current skip value
            current_skip = 0
            page_number = 1

            if extra:
                import re
                skip_match = re.search(r'skip=(\d+)', extra)
                if skip_match:
                    current_skip = int(skip_match.group(1))
                    # Calculate page number (assuming 50 items per page)
                    page_number = (current_skip // 50) + 1

            log(f"[PAGINATION] Items: {len(metas)}, Skip: {current_skip}, Page: {page_number}")

            # If we got a full page, there might be more
            if len(metas) >= 20:  # Threshold for showing next page
                next_skip = current_skip + len(metas)
                next_page_number = page_number + 1

                log(f"[PAGINATION] ADDING BUTTON: Page {page_number} -> {next_page_number}")

                # Build new extra with updated skip
                if extra:
                    if 'skip=' in extra:
                        new_extra = re.sub(r'skip=\d+', f'skip={next_skip}', extra)
                    else:
                        new_extra = f"{extra}&skip={next_skip}"
                else:
                    new_extra = f"skip={next_skip}"

                log(f"[PAGINATION] New extra: {new_extra}")

                # Create "Next Page" list item
                next_page_item = xbmcgui.ListItem(label=f"▶️ Next Page ({next_page_number})")

                # Use custom icon if available
                next_page_icon = self._get_custom_icon('next_page')
                log(f"[PAGINATION] Icon: {next_page_icon}")

                next_page_item.setArt({
                    'icon': next_page_icon,
                    'thumb': next_page_icon,
                    'poster': next_page_icon
                })

                # Use InfoTagVideo for proper metadata
                video_info = next_page_item.getVideoInfoTag()
                video_info.setTitle(f'Next Page ({next_page_number})')
                video_info.setPlot(f'Load page {next_page_number} with next {len(metas)} items')

                next_page_item.setProperty('IsPlayable', 'false')

                # Build URL to load next page
                next_page_url = build_url({
                    'mode': 'list_items',
                    'catalog_id': catalog_id,
                    'catalog_type': catalog_type,
                    'catalog_source': catalog_source,
                    'catalog_name': catalog_name,
                    'catalog_extras': catalog_extras,
                    'extra': new_extra
                })

                log(f"[PAGINATION] URL built: {next_page_url[:100]}...")

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=next_page_url,
                    listitem=next_page_item,
                    isFolder=True
                )

                log(f"[PAGINATION] ✅ Button added to directory!")
            else:
                log(f"[PAGINATION] Skipping button (only {len(metas)} items, need >=20)")

        except Exception as e:
            log_error("[PAGINATION] ERROR in method", e)

    def _create_list_item_basic(self, item, catalog_type):
        """
        TIER 1: Create list item with BASIC metadata for FAST catalog browsing
        Only extract: title, year, poster, plot, rating, basic IDs
        """
        item_title = item.get('name') or item.get('title', 'Unknown')

        # Extract ONLY basic IDs (fast)
        ids = self._parse_ids_basic(item)

        # Check if collection
        is_collection = 'tvdbc' in ids or catalog_type == 'collection'

        if is_collection:
            self._create_collection_item_basic(item, ids)
            return

        # Basic info only
        title = item.get('name') or item.get('title', 'Unknown')
        year = item.get('releaseInfo', '')
        poster = item.get('poster', '')
        description = item.get('description', '')
        background = item.get('background', '')
        logo = item.get('logo', '')
        item_type = item.get('type', catalog_type)

        # Handle year - can be string or int
        if year:
            year = str(year)  # Convert to string first
            if '-' in year:
                year = year.split('-')[0]
        else:
            year = ''

        display_title = title
        if settings.show_year and year:
            display_title = f"{title} ({year})"

        list_item = xbmcgui.ListItem(label=display_title)

        # Use InfoTagVideo (modern API)
        video_info = list_item.getVideoInfoTag()
        video_info.setTitle(title)
        video_info.setPlot(description)
        video_info.setMediaType('movie' if item_type == 'movie' else 'tvshow')

        if year:
            try:
                video_info.setYear(int(year))
            except:
                pass

        if settings.show_rating:
            rating = item.get('imdbRating') or item.get('rating')
            if rating:
                try:
                    video_info.setRating(float(rating))
                except:
                    pass

        # Basic art
        art = {}
        if poster:
            art['icon'] = poster
            art['thumb'] = poster
            art['poster'] = poster
        if background and settings.show_fanart:
            art['fanart'] = background

        if art:
            list_item.setArt(art)

        list_item.setProperty('IsPlayable', 'false')

        # Determine URL - this is where COMPREHENSIVE extraction happens (on click)
        if item_type in ['series', 'anime']:
            item_id = item.get('id', '')
            url = build_url({
                'mode': 'show_episodes',
                'content_id': item_id,
                'content_type': item_type,
                'title': title,
                'year': year,
                'ids': json.dumps(ids)
            })
            is_folder = True
        else:
            # Get rating for metadata
            rating = item.get('imdbRating') or item.get('rating', '')

            url = build_url({
                'mode': 'play',
                'title': title,
                'year': year,
                'ids': json.dumps(ids),
                'type': item_type,
                # Add metadata
                'plot': description if description else '',
                'poster': poster if poster else '',
                'fanart': background if background else '',
                'logo': logo if logo else '',
                'clearlogo': logo if logo else '',
                'rating': str(rating) if rating else ''
            })
            is_folder = False

        xbmcplugin.addDirectoryItem(
            handle=self.handle,
            url=url,
            listitem=list_item,
            isFolder=is_folder
        )

    def _parse_ids_basic(self, item):
        """TIER 1: Extract ONLY basic IDs for fast catalog browsing"""
        ids = {}

        try:
            # Parse main ID field
            item_id = item.get('id', '')

            if item_id:
                if item_id.startswith('tt'):
                    ids['imdb'] = item_id
                elif ':' in item_id:
                    prefix, id_value = item_id.split(':', 1)
                    ids[prefix] = id_value
                else:
                    ids['generic_id'] = item_id

            # Check most common explicit ID fields
            common_id_mappings = [
                ('imdb_id', 'imdb'),
                ('moviedb_id', 'tmdb'),
                ('tvdb_id', 'tvdb'),
                ('tvdbc_id', 'tvdbc'),
                ('mal_id', 'mal'),
                ('kitsu_id', 'kitsu'),
                ('anilist_id', 'anilist')
            ]

            for field_name, id_key in common_id_mappings:
                if field_name in item and item[field_name]:
                    ids[id_key] = str(item[field_name])

            # Check nested IDs (most reliable)
            if 'ids' in item and isinstance(item['ids'], dict):
                for key, value in item['ids'].items():
                    if value and str(value) != 'None':
                        ids[key] = str(value)

        except Exception as e:
            log_error("Error parsing basic IDs", e)

        return ids

    def _create_collection_item_basic(self, item, ids):
        """Create basic collection folder"""
        title = item.get('name') or item.get('title', 'Unknown')
        poster = item.get('poster', '')
        description = item.get('description', '')
        background = item.get('background', '')

        list_item = xbmcgui.ListItem(label=f"ðŸ“ [Collection] {title}")

        # Use InfoTagVideo
        video_info = list_item.getVideoInfoTag()
        video_info.setTitle(title)
        video_info.setPlot(description)
        video_info.setMediaType('set')

        art = {}
        if poster:
            art.update({'icon': poster, 'thumb': poster, 'poster': poster})
        if background and settings.show_fanart:
            art['fanart'] = background

        if art:
            list_item.setArt(art)

        list_item.setProperty('IsPlayable', 'false')

        collection_id = ids.get('tvdbc', item.get('id', ''))
        url = build_url({
            'mode': 'show_collection',
            'collection_id': collection_id,
            'collection_type': 'tvdb',
            'title': title,
            'ids': json.dumps(ids)
        })

        xbmcplugin.addDirectoryItem(
            handle=self.handle,
            url=url,
            listitem=list_item,
            isFolder=True
        )

    # ========== TIER 2: COMPREHENSIVE METADATA EXTRACTION (ON CLICK) ==========

    def show_episodes(self, content_id, content_type, title, year, ids):
        """
        TIER 2: When user clicks on show - COMPREHENSIVE metadata extraction
        This is where we get EVERYTHING for the external player
        """
        log(f"ðŸŽ¯ USER CLICKED on show: {title} - COMPREHENSIVE extraction started")

        try:
            progress = xbmcgui.DialogProgress()
            progress.create("Little Racun", f"Loading {title}...")

            # Fetch full metadata
            meta_data = self.api.get_meta(content_type, content_id)
            progress.close()

            if not meta_data:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "Failed to fetch episodes",
                    xbmcgui.NOTIFICATION_ERROR,
                    5000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            meta = meta_data.get('meta', {})
            videos = meta.get('videos', [])

            if not videos:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "No episodes found",
                    xbmcgui.NOTIFICATION_INFO,
                    3000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            log(f"Found {len(videos)} episodes")

            # Parse IDs
            try:
                ids_dict = json.loads(ids)
            except:
                ids_dict = {}

            # ðŸš€ COMPREHENSIVE ID EXTRACTION from full metadata
            comprehensive_ids = self._extract_all_ids_comprehensive(meta, ids_dict)
            log(f"âœ“ Extracted {len(comprehensive_ids)} IDs: {list(comprehensive_ids.keys())}")

            # EXTRACT ALL SHOW-LEVEL METADATA (Netflix-style)
            show_metadata = self._extract_show_metadata(meta)
            log(f"Extracted show metadata: {list(show_metadata.keys())}")

            # Group episodes by season (no offset - external player handles it)
            seasons = {}
            for video in videos:
                season_num = video.get('season', 1)
                if season_num not in seasons:
                    seasons[season_num] = []
                seasons[season_num].append(video)

            log(f"Grouped into {len(seasons)} seasons")

            # If only one season, show episodes directly
            if len(seasons) == 1:
                # Get the actual season number (might be offset)
                actual_season_num = list(seasons.keys())[0]
                self._show_season_episodes(
                    list(seasons.values())[0],
                    title,
                    year,
                    comprehensive_ids,
                    content_type,
                    show_metadata
                )
            else:
                # Multiple seasons - create season folders
                for season_num in sorted(seasons.keys()):
                    episode_count = len(seasons[season_num])

                    season_label = f"Season {season_num} ({episode_count} episodes)"

                    list_item = xbmcgui.ListItem(label=season_label)

                    # Add show-level art to season folders (Netflix-style)
                    art = {}
                    if show_metadata.get('poster'):
                        art['poster'] = show_metadata['poster']
                        art['thumb'] = show_metadata['poster']
                    if show_metadata.get('background') and settings.show_fanart:
                        art['fanart'] = show_metadata['background']
                    if show_metadata.get('logo'):
                        art['clearlogo'] = show_metadata['logo']
                    if show_metadata.get('banner'):
                        art['banner'] = show_metadata['banner']

                    if art:
                        list_item.setArt(art)
                    else:
                        list_item.setArt({'icon': 'DefaultFolder.png'})

                    list_item.setProperty('IsPlayable', 'false')

                    url = build_url({
                        'mode': 'show_season',
                        'content_id': content_id,
                        'content_type': content_type,
                        'title': title,
                        'year': year,
                        'ids': json.dumps(comprehensive_ids),
                        'season': str(season_num),
                        'show_metadata': json.dumps(show_metadata)
                    })

                    xbmcplugin.addDirectoryItem(
                        handle=self.handle,
                        url=url,
                        listitem=list_item,
                        isFolder=True
                    )

            xbmcplugin.setContent(self.handle, 'seasons' if len(seasons) > 1 else 'episodes')
            xbmcplugin.endOfDirectory(self.handle)

        except Exception as e:
            log_error("Error in show_episodes", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _extract_all_ids_comprehensive(self, meta, existing_ids):
        """
        TIER 2: COMPREHENSIVE ID extraction from full metadata response
        Extracts ALL available IDs for maximum player compatibility
        """
        ids = dict(existing_ids)  # Start with what we have

        try:
            # Extract from all possible ID fields
            id_field_mappings = {
                'moviedb_id': 'tmdb',
                'tvdb_id': 'tvdb',
                'tvdbc_id': 'tvdbc',
                'imdb_id': 'imdb',
                'kitsu_id': 'kitsu',
                'mal_id': 'mal',
                'anilist_id': 'anilist',
                'anidb_id': 'anidb',
                'trakt_id': 'trakt',
                'tvmaze_id': 'tvmaze',
                'slug': 'slug',
                'youtube_id': 'youtube',
                'simkl_id': 'simkl',
                'anisearch_id': 'anisearch',
                'livechart_id': 'livechart',
                'notify_id': 'notify',
                'myanimelist_id': 'mal',
                'themoviedb_id': 'tmdb',
                'thetvdb_id': 'tvdb'
            }

            for field_name, id_key in id_field_mappings.items():
                if field_name in meta and meta[field_name]:
                    id_value = str(meta[field_name])
                    if id_value and id_value != 'None':
                        ids[id_key] = id_value
                        log(f"  Comprehensive ID: {id_key} = {id_value}")

            # Extract from nested IDs object
            if 'ids' in meta and isinstance(meta['ids'], dict):
                for key, value in meta['ids'].items():
                    if value and str(value) != 'None':
                        ids[key] = str(value)
                        log(f"  Comprehensive nested ID: {key} = {value}")

            # Extract from links (backup)
            if 'links' in meta and isinstance(meta['links'], list):
                for link in meta['links']:
                    if isinstance(link, dict):
                        link_url = link.get('url', '')

                        # Extract IDs from URLs
                        if 'imdb.com' in link_url:
                            imdb_match = re.search(r'tt\d+', link_url)
                            if imdb_match and 'imdb' not in ids:
                                ids['imdb'] = imdb_match.group()
                                log(f"  Extracted from URL: imdb = {ids['imdb']}")
                        elif 'themoviedb.org' in link_url:
                            tmdb_match = re.search(r'/(\d+)', link_url)
                            if tmdb_match and 'tmdb' not in ids:
                                ids['tmdb'] = tmdb_match.group(1)
                                log(f"  Extracted from URL: tmdb = {ids['tmdb']}")
                        elif 'thetvdb.com' in link_url:
                            tvdb_match = re.search(r'/series/(\d+)', link_url)
                            if tvdb_match and 'tvdb' not in ids:
                                ids['tvdb'] = tvdb_match.group(1)
                                log(f"  Extracted from URL: tvdb = {ids['tvdb']}")
                        elif 'myanimelist.net' in link_url:
                            mal_match = re.search(r'/anime/(\d+)', link_url)
                            if mal_match and 'mal' not in ids:
                                ids['mal'] = mal_match.group(1)
                                log(f"  Extracted from URL: mal = {ids['mal']}")

        except Exception as e:
            log_error("Error in comprehensive ID extraction", e)

        return ids

    def _extract_show_metadata(self, meta):
        """
        Extract ALL show-level metadata from JSON for Netflix-style rich experience
        Returns a dictionary with all available metadata fields
        """
        metadata = {}

        try:
            # Basic info
            metadata['title'] = meta.get('name') or meta.get('title', '')
            metadata['plot'] = meta.get('description', '')
            metadata['year'] = meta.get('releaseInfo', '')
            metadata['rating'] = meta.get('imdbRating') or meta.get('rating', '')
            metadata['status'] = meta.get('status', '')
            metadata['runtime'] = meta.get('runtime', '')
            metadata['country'] = meta.get('country', '')
            metadata['language'] = meta.get('language', '')

            # Art/Images
            metadata['poster'] = meta.get('poster', '')
            metadata['background'] = meta.get('background', '')
            metadata['logo'] = meta.get('logo', '')
            metadata['banner'] = meta.get('banner', '')

            # Arrays
            metadata['genres'] = meta.get('genres', [])
            metadata['cast'] = meta.get('cast', [])
            metadata['director'] = meta.get('director', [])
            metadata['writer'] = meta.get('writer', [])
            metadata['awards'] = meta.get('awards', '')

            # Additional metadata
            metadata['popularity'] = meta.get('popularity', '')
            metadata['trailers'] = meta.get('trailers', [])
            metadata['website'] = meta.get('website', '')
            metadata['links'] = meta.get('links', [])
            metadata['behaviorHints'] = meta.get('behaviorHints', {})

            log(f"Extracted show metadata fields: {', '.join([k for k, v in metadata.items() if v])}")

        except Exception as e:
            log_error("Error extracting show metadata", e)

        return metadata

    def show_season(self, content_id, content_type, title, year, ids, season, show_metadata=None):
        """Show episodes for a specific season"""
        try:
            progress = xbmcgui.DialogProgress()
            progress.create("Little Racun", f"Loading Season {season}...")

            meta_data = self.api.get_meta(content_type, content_id)
            progress.close()

            if not meta_data:
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            meta = meta_data.get('meta', {})
            videos = meta.get('videos', [])

            try:
                ids_dict = json.loads(ids)
            except:
                ids_dict = {}

            season_num = int(season)
            season_episodes = [v for v in videos if v.get('season', 1) == season_num]

            log(f"Found {len(season_episodes)} episodes in season {season_num}")

            # Parse show metadata if provided
            try:
                if show_metadata:
                    metadata_dict = json.loads(show_metadata)
                else:
                    metadata_dict = self._extract_show_metadata(meta)
            except:
                metadata_dict = {}

            self._show_season_episodes(season_episodes, title, year, ids_dict, content_type, metadata_dict)

        except Exception as e:
            log_error("Error in show_season", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def _show_season_episodes(self, episodes, title, year, ids_dict, content_type, show_metadata=None):
        """Display episodes with ALL IDs passed to player"""
        for video in episodes:
            try:
                episode_title = video.get('title', 'Episode')
                season = video.get('season', 1)
                episode = video.get('episode', 1)
                overview = video.get('overview', video.get('description', ''))
                thumbnail = video.get('thumbnail', '')
                released = video.get('released', '')
                rating = video.get('rating', '')

                if content_type == 'anime':
                    display_title = f"Ep {episode}: {episode_title}"
                else:
                    display_title = f"S{season:02d}E{episode:02d} - {episode_title}"

                list_item = xbmcgui.ListItem(label=display_title)

                # Use InfoTagVideo with ALL available metadata (Netflix-style)
                video_info = list_item.getVideoInfoTag()
                video_info.setTitle(episode_title)
                video_info.setPlot(overview)
                video_info.setSeason(season)
                video_info.setEpisode(episode)
                video_info.setMediaType('episode')

                # Add show-level metadata to episodes
                if show_metadata:
                    if show_metadata.get('title'):
                        video_info.setTvShowTitle(show_metadata['title'])
                    if show_metadata.get('genres'):
                        video_info.setGenres(show_metadata['genres'])
                    if show_metadata.get('cast'):
                        video_info.setCast([{'name': c} if isinstance(c, str) else c for c in show_metadata['cast']])
                    if show_metadata.get('director'):
                        video_info.setDirectors(show_metadata['director'] if isinstance(show_metadata['director'], list) else [show_metadata['director']])
                    if show_metadata.get('writer'):
                        video_info.setWriters(show_metadata['writer'] if isinstance(show_metadata['writer'], list) else [show_metadata['writer']])
                    if show_metadata.get('status'):
                        video_info.setTvShowStatus(show_metadata['status'])

                # Episode-specific rating
                if rating:
                    try:
                        video_info.setRating(float(rating))
                    except:
                        pass
                elif show_metadata and show_metadata.get('rating'):
                    try:
                        video_info.setRating(float(show_metadata['rating']))
                    except:
                        pass

                # Episode air date
                if released:
                    try:
                        # Parse date if in format YYYY-MM-DD
                        if '-' in released:
                            year_val = int(released.split('-')[0])
                            video_info.setYear(year_val)
                    except:
                        pass

                # Art - combine episode and show-level
                art = {}
                if thumbnail:
                    art['thumb'] = thumbnail
                    art['icon'] = thumbnail
                if show_metadata:
                    if show_metadata.get('poster') and not thumbnail:
                        art['thumb'] = show_metadata['poster']
                    if show_metadata.get('background') and settings.show_fanart:
                        art['fanart'] = show_metadata['background']
                    if show_metadata.get('logo'):
                        art['clearlogo'] = show_metadata['logo']
                    if show_metadata.get('banner'):
                        art['banner'] = show_metadata['banner']

                if art:
                    list_item.setArt(art)

                # Set ALL IDs as properties for external access
                for id_type, id_value in ids_dict.items():
                    list_item.setProperty(f"{id_type}_id", str(id_value))
                    log(f"  Episode property: {id_type}_id = {id_value}")

                list_item.setProperty('IsPlayable', 'false')

                # Build play URL with ALL IDs and metadata
                url = build_url({
                    'mode': 'play',
                    'title': title,
                    'year': year,
                    'ids': json.dumps(ids_dict),
                    'type': content_type,
                    'season': str(season),
                    'episode': str(episode),
                    # Add metadata
                    'plot': overview if overview else '',
                    'poster': show_metadata.get('poster', '') if show_metadata else '',
                    'fanart': show_metadata.get('background', '') if show_metadata else '',
                    'thumbnail': thumbnail if thumbnail else '',
                    'logo': show_metadata.get('logo', '') if show_metadata else '',
                    'clearlogo': show_metadata.get('logo', '') if show_metadata else '',
                    'rating': str(rating) if rating else (str(show_metadata.get('rating', '')) if show_metadata else '')
                })

                xbmcplugin.addDirectoryItem(
                    handle=self.handle,
                    url=url,
                    listitem=list_item,
                    isFolder=False
                )
            except Exception as e:
                log_error("Error creating episode item", e)

        xbmcplugin.setContent(self.handle, 'episodes')
        xbmcplugin.endOfDirectory(self.handle)


    def translate_ids_for_play(self, ids_dict, content_type):
        """
        Translate IDs only when user clicks PLAY
        Only for anime/kitsu content
        """
        if content_type not in ['anime', 'series']:
            log("[ARM] Not anime - skipping translation")
            return ids_dict

        # Only translate if we have Kitsu ID
        if 'kitsu' not in ids_dict or not ids_dict['kitsu']:
            log("[ARM] No Kitsu ID - skipping translation")
            return ids_dict

        try:
            log(f"[ARM] User clicked PLAY - translating Kitsu:{ids_dict['kitsu']}")
            enhanced = ARMTranslator.enhance_ids(ids_dict, content_type)
            log(f"[ARM] Translation complete - {len(enhanced)} total IDs")
            return enhanced
        except Exception as e:
            log(f"[ARM] Translation failed: {str(e)} - using original IDs")
            return ids_dict

    def show_collection(self, collection_id, collection_type, title, ids):
        """Show movies in collection"""
        try:
            progress = xbmcgui.DialogProgress()
            progress.create("Little Racun", f"Loading {title}...")

            try:
                if collection_type == 'tvdb':
                    meta_data = self.api.get_meta('movie', f"tvdbc:{collection_id}")
                else:
                    meta_data = self.api.get_meta('collection', collection_id)
            except Exception as e:
                log_error(f"Error fetching collection meta", e)
                meta_data = None

            progress.close()

            if not meta_data:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "Failed to fetch collection",
                    xbmcgui.NOTIFICATION_ERROR,
                    5000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            meta = meta_data.get('meta', {})
            videos = meta.get('videos', [])

            if not videos:
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "No items found in collection",
                    xbmcgui.NOTIFICATION_INFO,
                    3000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            log(f"Found {len(videos)} items in collection")

            for video in videos:
                try:
                    movie_title = video.get('title') or video.get('name', 'Unknown')
                    year = video.get('releaseInfo', video.get('year', ''))
                    overview = video.get('overview', video.get('description', ''))
                    thumbnail = video.get('thumbnail', video.get('poster', ''))

                    if year and '-' in str(year):
                        year = str(year).split('-')[0]

                    display_title = f"{movie_title} ({year})" if year else movie_title

                    list_item = xbmcgui.ListItem(label=display_title)

                    # Use InfoTagVideo
                    video_info = list_item.getVideoInfoTag()
                    video_info.setTitle(movie_title)
                    video_info.setPlot(overview)
                    video_info.setMediaType('movie')

                    if year:
                        try:
                            video_info.setYear(int(year))
                        except:
                            pass

                    if thumbnail:
                        list_item.setArt({
                            'thumb': thumbnail,
                            'icon': thumbnail,
                            'poster': thumbnail
                        })

                    # Extract IDs from video item
                    video_ids = self._parse_ids_basic(video)

                    # Set as properties
                    for id_type, id_value in video_ids.items():
                        list_item.setProperty(f"{id_type}_id", str(id_value))

                    list_item.setProperty('IsPlayable', 'false')

                    url = build_url({
                        'mode': 'play',
                        'title': movie_title,
                        'year': year,
                        'ids': json.dumps(video_ids),
                        'type': 'movie',
                        # Add metadata
                        'plot': overview if overview else '',
                        'poster': thumbnail if thumbnail else '',
                        'fanart': thumbnail if thumbnail else '',
                        'clearlogo': ''
                    })

                    xbmcplugin.addDirectoryItem(
                        handle=self.handle,
                        url=url,
                        listitem=list_item,
                        isFolder=False
                    )
                except Exception as e:
                    log_error("Error creating collection item", e)

            xbmcplugin.setContent(self.handle, 'movies')
            xbmcplugin.endOfDirectory(self.handle)

        except Exception as e:
            log_error("Error in show_collection", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    # ========== DIALOG METHODS ==========

    def show_search_dialog(self, catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras):
        """Show search input dialog"""
        try:
            keyboard = xbmc.Keyboard('', f'Search {catalog_name}')
            keyboard.doModal()

            if not keyboard.isConfirmed():
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            search_query = keyboard.getText()

            if not search_query or search_query.strip() == '':
                xbmcgui.Dialog().notification(
                    "Little Racun",
                    "Search query cannot be empty",
                    xbmcgui.NOTIFICATION_WARNING,
                    3000
                )
                xbmcplugin.endOfDirectory(self.handle, succeeded=False)
                return

            from urllib.parse import quote
            search_query_encoded = quote(search_query)
            extra = f"search={search_query_encoded}"

            xbmcgui.Dialog().notification(
                "Little Racun",
                f"Searching for: {search_query}",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )

            self._fetch_and_display_catalog(catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras, extra, is_search_results=True)

        except Exception as e:
            log_error("Error in show_search_dialog", e)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def show_filter_dialog(self, catalog_id, catalog_type, catalog_source, catalog_name, catalog_extras):
        """Show genre filter dialog"""
        try:
            try:
                extras_list = json.loads(catalog_extras)
            except:
                extras_list = []

            genre_extra = next((ex for ex in extras_list if ex.get('name') == 'genre'), None)

            if not genre_extra:
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "Filter Not Available[CR][CR]"
                    "This catalog does not support genre filtering."
                )
                return

            genres = genre_extra.get('options', [])

            if not genres:
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "No Genres Available"
                )
                return

            menu_items = ["All / Top"] + genres
            selected = xbmcgui.Dialog().select("Filter Category", menu_items)

            if selected < 0:
                return

            if selected == 0:
                extra = None
            else:
                genre = genres[selected - 1]
                extra = f"genre={genre}"

            params = {
                'mode': 'list_items',
                'catalog_id': catalog_id,
                'catalog_type': catalog_type,
                'catalog_source': catalog_source,
                'catalog_name': catalog_name,
                'catalog_extras': catalog_extras
            }

            if extra:
                params['extra'] = extra

            from urllib.parse import urlencode
            new_url = f"plugin://plugin.video.littleracun/?{urlencode(params)}"

            xbmc.executebuiltin(f'Container.Update({new_url})')

            message = "Showing all items" if selected == 0 else f"Filtered by: {menu_items[selected]}"
            xbmcgui.Dialog().notification(
                "Little Racun",
                message,
                xbmcgui.NOTIFICATION_INFO,
                2000
            )

        except Exception as e:
            log_error("Error in show_filter_dialog", e)

    # ========== PLAYER MANAGEMENT METHODS ==========

    def download_player_from_url(self):
        """Download player configuration from URL"""
        log("Download player from URL requested")

        keyboard = xbmc.Keyboard('', 'Enter Player JSON URL')
        keyboard.doModal()

        if not keyboard.isConfirmed():
            return

        url = keyboard.getText().strip()

        if not url:
            xbmcgui.Dialog().notification(
                "Little Racun",
                "No URL provided",
                xbmcgui.NOTIFICATION_WARNING,
                3000
            )
            return

        progress = xbmcgui.DialogProgress()
        progress.create("Little Racun", "Downloading player configuration...")

        try:
            import requests
            from urllib.parse import urlparse

            response = requests.get(url, timeout=10)
            response.raise_for_status()

            progress.update(50, "Validating player configuration...")

            try:
                player_data = response.json()

                if 'name' not in player_data:
                    raise ValueError("Player JSON missing 'name' field")

                if 'play_movie' not in player_data and 'play_episode' not in player_data:
                    raise ValueError("Player JSON missing 'play_movie' or 'play_episode' field")

                player_name = player_data['name']

            except json.JSONDecodeError as e:
                progress.close()
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "Error: Invalid JSON file[CR][CR]"
                    "The URL must point to a valid player JSON file."
                )
                return
            except ValueError as e:
                progress.close()
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    f"Error: Invalid player configuration[CR][CR]{str(e)}"
                )
                return

            progress.update(75, "Saving player configuration...")

            parsed_url = urlparse(url)
            url_filename = os.path.basename(parsed_url.path)

            if url_filename.endswith('.json'):
                filename = url_filename
            else:
                safe_name = "".join(c for c in player_name.lower() if c.isalnum() or c in (' ', '-', '_')).strip()
                safe_name = safe_name.replace(' ', '_')
                filename = f"{safe_name}.json"

            import xbmcvfs
            players_dir = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/resources/players/")

            if not os.path.exists(players_dir):
                os.makedirs(players_dir, exist_ok=True)

            player_path = os.path.join(players_dir, filename)

            with open(player_path, 'w', encoding='utf-8') as f:
                json.dump(player_data, f, indent=2)

            progress.close()

            xbmcgui.Dialog().ok(
                "Little Racun",
                f"Player Downloaded Successfully![CR][CR]"
                f"Name: {player_name}[CR]"
                f"File: {filename}[CR][CR]"
                f"The player is now available for use."
            )

        except requests.RequestException as e:
            progress.close()
            xbmcgui.Dialog().ok(
                "Little Racun",
                f"Error downloading player:[CR][CR]{str(e)}[CR][CR]"
                "Please check the URL and try again."
            )
        except Exception as e:
            progress.close()
            log_error("Error downloading player", e)
            xbmcgui.Dialog().ok(
                "Little Racun",
                f"Error:[CR][CR]{str(e)}"
            )

    def view_installed_players(self):
        """View and manage installed players"""
        try:
            import xbmcvfs
            players_dir = xbmcvfs.translatePath(f"special://home/addons/{ADDON_ID}/resources/players/")

            if not os.path.exists(players_dir):
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "No Players Installed[CR][CR]"
                    "Use 'Download Player from URL' to add players."
                )
                return

            player_files = [f for f in os.listdir(players_dir) if f.endswith('.json')]

            if not player_files:
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "No Players Installed[CR][CR]"
                    "Use 'Download Player from URL' to add players."
                )
                return

            players_info = []
            for filename in player_files:
                try:
                    filepath = os.path.join(players_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        player_data = json.load(f)
                        player_name = player_data.get('name', filename)
                        players_info.append({
                            'name': player_name,
                            'filename': filename,
                            'filepath': filepath,
                            'data': player_data
                        })
                except Exception as e:
                    log(f"Error loading {filename}: {str(e)}")

            if not players_info:
                xbmcgui.Dialog().ok(
                    "Little Racun",
                    "No Valid Players Found[CR][CR]"
                    "All player files have errors."
                )
                return

            while True:
                display_items = []
                for player in players_info:
                    name = player['name']
                    has_movie = 'play_movie' in player['data']
                    has_episode = 'play_episode' in player['data']

                    types = []
                    if has_movie:
                        types.append('Movies')
                    if has_episode:
                        types.append('Episodes')

                    type_str = ', '.join(types) if types else 'Unknown'
                    display_items.append(f"{name} ({type_str})")

                selected = xbmcgui.Dialog().select(
                    f"Installed Players ({len(players_info)})",
                    display_items
                )

                if selected < 0:
                    break

                player = players_info[selected]

                options = [
                    "View Details",
                    "Delete Player"
                ]

                choice = xbmcgui.Dialog().select(
                    player['name'],
                    options
                )

                if choice == 0:
                    self._show_player_details(player)
                elif choice == 1:
                    confirm = xbmcgui.Dialog().yesno(
                        "Delete Player",
                        f"Are you sure you want to delete:[CR][CR]{player['name']}[CR][CR]"
                        f"File: {player['filename']}"
                    )

                    if confirm:
                        try:
                            os.remove(player['filepath'])

                            xbmcgui.Dialog().notification(
                                "Little Racun",
                                f"Deleted: {player['name']}",
                                xbmcgui.NOTIFICATION_INFO,
                                3000
                            )

                            players_info.remove(player)

                            if not players_info:
                                xbmcgui.Dialog().ok(
                                    "Little Racun",
                                    "All players deleted"
                                )
                                break

                        except Exception as e:
                            log_error("Error deleting player", e)
                            xbmcgui.Dialog().ok(
                                "Little Racun",
                                f"Error deleting player:[CR][CR]{str(e)}"
                            )

        except Exception as e:
            log_error("Error viewing players", e)
            xbmcgui.Dialog().ok(
                "Little Racun",
                f"Error:[CR][CR]{str(e)}"
            )

    def _show_player_details(self, player):
        """Show detailed information about a player"""
        data = player['data']

        details = []
        details.append(f"Name: {player['name']}")
        details.append(f"File: {player['filename']}")
        details.append("")

        if 'id' in data:
            details.append(f"ID: {data['id']}")
        if 'plugin' in data:
            details.append(f"Plugin: {data['plugin']}")
        if 'priority' in data:
            details.append(f"Priority: {data['priority']}")

        details.append("")
        details.append("Supports:")
        if 'play_movie' in data:
            details.append("â€¢ Movies")
        if 'play_episode' in data:
            details.append("â€¢ Episodes")

        if 'description' in data:
            details.append("")
            details.append(f"Description: {data['description']}")

        xbmcgui.Dialog().textviewer(
            player['name'],
            '\n'.join(details)
        )
