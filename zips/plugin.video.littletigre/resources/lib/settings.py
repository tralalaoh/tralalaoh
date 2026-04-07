"""Settings management for Stremio Bridge addon - WITH ANIME PREFERENCES."""

import xbmc
import xbmcaddon

# Get addon instance
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = 'Little Tigre'
ADDON_VERSION = ADDON.getAddonInfo('version')


class Settings:
    """Manage addon settings."""

    @staticmethod
    def get(setting_id, default=None):
        """Get a setting value with error handling for invalid types."""
        try:
            value = ADDON.getSetting(setting_id)
            if not value and default is not None:
                return default
            return value
        except Exception as e:
            # Handle "Invalid setting type" errors from Kodi
            xbmc.log(f'[{ADDON_NAME}] Error reading setting {setting_id}: {str(e)}, using default', xbmc.LOGWARNING)
            if default is not None:
                return default
            return ''

    @staticmethod
    def get_bool(setting_id, default=False):
        """Get a boolean setting with error handling."""
        try:
            value = Settings.get(setting_id, '')
            if value == '':
                return default
            return value.lower() in ('true', '1', 'yes')
        except Exception as e:
            xbmc.log(f'[{ADDON_NAME}] Error reading bool setting {setting_id}: {str(e)}, using default', xbmc.LOGWARNING)
            return default

    @staticmethod
    def get_int(setting_id, default=0):
        """Get an integer setting with error handling."""
        try:
            value = Settings.get(setting_id, '')
            if value == '':
                return default
            return int(value)
        except Exception as e:
            xbmc.log(f'[{ADDON_NAME}] Error reading int setting {setting_id}: {str(e)}, using default', xbmc.LOGWARNING)
            return default

    @staticmethod
    def set(setting_id, value):
        """Set a setting value."""
        if isinstance(value, bool):
            ADDON.setSettingBool(setting_id, value)
        elif isinstance(value, int):
            ADDON.setSettingInt(setting_id, value)
        else:
            ADDON.setSetting(setting_id, str(value))

    @staticmethod
    def open():
        """Open settings dialog."""
        ADDON.openSettings()

    # ========================================
    # ANIME SETTINGS
    # ========================================

    @staticmethod
    def get_anime_search_strategy():
        """
        Get user preference for anime search strategy.
        Maps XML values to internal values expected by playback engine.

        XML values: 'absolute', 'season', 'both'
        Returns: 'absolute_only', 'season_only', 'both'
        """
        # FIXED: Use correct ID 'anime_season_strategy' from settings.xml
        strategy = Settings.get('anime_season_strategy', 'both')

        # Map settings.xml values to internal logic values
        mapping = {
            'absolute': 'absolute_only',
            'season': 'season_only',
            'both': 'both'
        }

        mapped_strategy = mapping.get(strategy, 'both')
        return mapped_strategy

    @staticmethod
    def get_anime_search_id_type():
        """
        Get user preference for anime addon search ID type.
        """
        id_type = Settings.get('anime_search_id_type', 'anilist')

        valid_types = ['anilist', 'kitsu', 'imdb', 'mal']
        if id_type not in valid_types:
            return 'anilist'

        return id_type

    @staticmethod
    def get_anime_season_strategy():
        """
        Alias for get_anime_search_strategy to maintain compatibility.
        """
        return Settings.get_anime_search_strategy()

    # ========================================
    # DEBRID SETTINGS (Multi-Debrid Support)
    # ========================================

    @staticmethod
    def get_enabled_debrid_services():
        """Get list of enabled debrid services."""
        services = []

        if Settings.get_bool('enable_realdebrid', False):
            api_key = Settings.get_realdebrid_api_key()
            if api_key:
                services.append({
                    'name': 'realdebrid',
                    'label': 'Real-Debrid',
                    'code': 'RD',
                    'api_key': api_key
                })

        if Settings.get_bool('enable_torbox', True):
            api_key = Settings.get_torbox_api_key()
            if api_key:
                services.append({
                    'name': 'torbox',
                    'label': 'Torbox',
                    'code': 'TB',
                    'api_key': api_key
                })

        return services

    @staticmethod
    def get_debrid_service():
        """Get primary debrid service."""
        services = Settings.get_enabled_debrid_services()
        if services:
            return services[0]['name']
        return 'torbox'

    @staticmethod
    def get_torbox_api_key():
        return Settings.get('torbox_api_key', '')

    @staticmethod
    def get_realdebrid_api_key():
        return Settings.get('realdebrid_api_key', '')

    @staticmethod
    def get_debrid_api_key(service=None):
        if service is None:
            service = Settings.get_debrid_service()

        if service == 'torbox':
            return Settings.get_torbox_api_key()
        elif service == 'realdebrid':
            return Settings.get_realdebrid_api_key()
        return ''

    # Addon Settings
    @staticmethod
    def get_enabled_addons():
        """Get list of enabled Stremio addons."""
        addons = []

        debrid_service = Settings.get_debrid_service()
        debrid_key = Settings.get_debrid_api_key(debrid_service)

        # Comet
        if Settings.get_bool('enable_comet', True):
            custom_url = Settings.get('comet_custom_url', '').strip()
            if not custom_url and debrid_key:
                custom_url = Settings._build_comet_url(debrid_service, debrid_key)

            addons.append({
                'name': 'Comet',
                'url': Settings.get('comet_url', 'https://comet.elfhosted.com'),
                'custom_url': custom_url,
                'debrid_service': debrid_service,
                'debrid_key': debrid_key
            })

        # StremThru
        if Settings.get_bool('enable_stremthru', True):
            custom_url = Settings.get('stremthru_custom_url', '').strip()
            if not custom_url and debrid_key:
                custom_url = Settings._build_stremthru_url(debrid_service, debrid_key)

            addons.append({
                'name': 'StremThru',
                'url': Settings.get('stremthru_url', 'https://stremthru.elfhosted.com'),
                'custom_url': custom_url,
                'debrid_service': debrid_service,
                'debrid_key': debrid_key
            })

        # Torrentio
        # FIXED: Use correct method name get_anime_search_id_type
        anime_priority = Settings.get_anime_search_id_type()
        torrentio_default = True if anime_priority == 'imdb' else False

        if Settings.get_bool('enable_torrentio', torrentio_default):
            custom_url = Settings.get('torrentio_custom_url', '').strip()
            if not custom_url and debrid_key:
                custom_url = Settings._build_torrentio_url(debrid_service, debrid_key)

            addons.append({
                'name': 'Torrentio',
                'url': Settings.get('torrentio_url', 'https://torrentio.strem.fun'),
                'custom_url': custom_url,
                'debrid_service': debrid_service,
                'debrid_key': debrid_key
            })

        # MediaFusion
        if Settings.get_bool('enable_mediafusion', False):
            custom_url = Settings.get('mediafusion_custom_url', '').strip()
            if custom_url:
                addons.append({
                    'name': 'MediaFusion',
                    'url': 'https://mediafusion.elfhosted.com',
                    'custom_url': custom_url,
                    'debrid_service': debrid_service,
                    'debrid_key': debrid_key
                })

        # AIO Streams
        if Settings.get_bool('enable_aiostreams', False):
            aio_url = Settings.get('aiostreams_url', '').strip()
            if aio_url:
                addons.append({
                    'name': 'AIO Streams',
                    'url': 'https://aiostreams.elfhosted.com',
                    'custom_url': aio_url,
                    'debrid_service': debrid_service,
                    'debrid_key': debrid_key
                })

        # Custom user-added scrapers (from addon registry)
        try:
            from resources.lib.addon_registry import AddonRegistry
            for custom in AddonRegistry.get_enabled():
                addons.append({
                    'name': custom['name'],
                    'url': custom['base_url'],
                    'custom_url': custom['manifest_url'],
                    'debrid_service': None,
                    'debrid_key': None,
                    'id_prefixes': custom.get('id_prefixes', ['tt']),
                    'is_custom': True,
                })
        except Exception as e:
            from resources.lib.logger import log_error
            log_error('Settings: Failed to load custom addons from registry', e)

        return addons

    @staticmethod
    def _build_comet_url(debrid_service, api_key):
        import base64
        import json
        service_map = {'torbox': 'torbox', 'realdebrid': 'realdebrid'}
        config = {
            "debridService": service_map.get(debrid_service, debrid_service),
            "debridApiKey": api_key,
            "maxResultsPerResolution": 0,
            "maxSize": 0,
            "cachedOnly": False,
            "sortCachedBySize": True
        }
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        return f"https://comet.elfhosted.com/{encoded}/manifest.json"

    @staticmethod
    def _build_stremthru_url(debrid_service, api_key):
        import base64
        import json
        service_map = {'torbox': 'tb', 'realdebrid': 'rd'}
        service_code = service_map.get(debrid_service, 'rd')
        config = {"indexers": None, "stores": [{"c": service_code, "t": api_key}]}
        encoded = base64.b64encode(json.dumps(config).encode()).decode()
        return f"https://stremthru.elfhosted.com/stremio/torz/{encoded}/manifest.json"

    @staticmethod
    def _build_torrentio_url(debrid_service, api_key):
        service_map = {'realdebrid': 'realdebrid', 'torbox': 'torbox'}
        service = service_map.get(debrid_service, debrid_service)
        return f"https://torrentio.strem.fun/{service}={api_key}/manifest.json"

    @staticmethod
    def get_addon_timeout():
        return Settings.get_int('addon_timeout', 20)

    @staticmethod
    def get_max_results():
        # === FIX: Increase default from 50 to 150 ===
        return Settings.get_int('max_results_per_addon', 150)

    @staticmethod
    def use_parallel_queries():
        return Settings.get_bool('use_parallel_queries', True)

    # Safety Settings
    @staticmethod
    def get_safety_level():
        return Settings.get('safety_level', 'standard')

    @staticmethod
    def should_check_tmdb_adult():
        return Settings.get_bool('tmdb_adult_check', True)

    @staticmethod
    def should_exclude_adult():
        return Settings.get_bool('exclude_adult_content', True)

    @staticmethod
    def get_custom_blacklist():
        blacklist = Settings.get('custom_blacklist', '')
        if blacklist:
            return [k.strip().lower() for k in blacklist.split(',') if k.strip()]
        return []

    @staticmethod
    def should_exclude_cam():
        return Settings.get_bool('exclude_cam', True)

    @staticmethod
    def is_hd_only():
        return Settings.get_bool('hd_only', False)

    @staticmethod
    def get_min_quality():
        return Settings.get('min_quality', 'any')

    # Display Settings
    @staticmethod
    def show_cached_first():
        return Settings.get_bool('show_cached_first', True)

    @staticmethod
    def get_uncached_display():
        return Settings.get('uncached_display', 'show_all')

    @staticmethod
    def get_min_seeders():
        return Settings.get_int('min_seeders_uncached', 10)

    @staticmethod
    def show_file_size():
        return Settings.get_bool('show_file_size', True)

    @staticmethod
    def show_seeders():
        return Settings.get_bool('show_seeders', True)

    @staticmethod
    def show_confidence_icons():
        return Settings.get_bool('show_confidence_icons', True)

    @staticmethod
    def group_by_confidence():
        return Settings.get_bool('group_by_confidence', True)

    # Filtering Settings
    @staticmethod
    def is_whitelist_mode():
        return Settings.get_bool('whitelist_mode', False)

    @staticmethod
    def require_trusted_sources():
        return Settings.get_bool('trusted_sources_only', False)

    @staticmethod
    def is_debrid_cached_only():
        return Settings.get_bool('debrid_cached_only', False)

    @staticmethod
    def get_max_file_size():
        return Settings.get_int('max_file_size_gb', 0)

    @staticmethod
    def get_language_filter():
        langs = Settings.get('language_filter', '')
        if langs:
            return [l.strip().lower() for l in langs.split(',') if l.strip()]
        return []

    @staticmethod
    def get_sort_by():
        return Settings.get('sort_by', 'confidence')

    # Advanced Settings
    @staticmethod
    def should_log_filtered():
        return Settings.get_bool('log_filtered_streams', True)

    @staticmethod
    def should_show_filter_count():
        return Settings.get_bool('show_filter_count', True)

    @staticmethod
    def is_debug_enabled():
        return Settings.get_bool('enable_debug', False)

    @staticmethod
    def should_cache_results():
        return Settings.get_bool('cache_results', True)

    @staticmethod
    def get_cache_duration():
        return Settings.get_int('cache_duration_minutes', 30)

    # Deduplication Settings
    @staticmethod
    def is_deduplication_enabled():
        return Settings.get_bool('enable_deduplication', True)

    @staticmethod
    def get_deduplication_strategy():
        return Settings.get('deduplication_strategy', 'aggressive')

    @staticmethod
    def get_bypass_filter_addons():
        """Get list of addon names that should bypass quality filtering."""
        # Default: AIO Streams (has built-in filtering)
        default_bypass = 'aio streams,aiostreams'
        bypass_list = Settings.get('bypass_filter_addons', default_bypass)
        if bypass_list:
            return [name.strip().lower() for name in bypass_list.split(',') if name.strip()]
        return []

    @staticmethod
    def use_smart_addon_id_selection():
        """
        Enable smart per-addon ID selection for maximum results.

        When enabled:
        - Torrentio gets IMDB (better results)
        - Comet gets Kitsu/MAL (native anime support)
        - StremThru gets IMDB (universal)
        - AIO Streams respects user preference

        When disabled:
        - All addons get user's global preference
        """
        return Settings.get_bool('smart_addon_id_selection', True)
