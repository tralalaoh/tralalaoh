# -*- coding: utf-8 -*-
"""
Little Fox - Player Core Orchestrator
Coordinates providers and resolvers for stream resolution

Your clever companion for Turkish series streaming!

Architecture Layer: ORCHESTRATION
Version 2.5.3 - Critical Fixes
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse
import re

try:
    import xbmc
    import xbmcgui
    KODI_ENV = True
except ImportError:
    KODI_ENV = False
    class xbmc:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3
        @staticmethod
        def log(msg, level=1):
            print(f"[PlayerCore] {msg}")
    class xbmcgui:
        class Dialog:
            def select(self, title, items, preselect=0):
                print(f"\n{title}")
                for i, item in enumerate(items):
                    print(f"{i+1}. {item}")
                return 0
            def ok(self, heading, message):
                print(f"\n[OK DIALOG] {heading}\n{message}")
            def notification(self, title, msg, icon, duration):
                print(f"[NOTIFICATION] {title}: {msg}")

try:
    import resolveurl
    RESOLVEURL_AVAILABLE = True
except ImportError:
    RESOLVEURL_AVAILABLE = False
    print("WARNING: ResolveURL not available! Install script.module.resolveurl")

from lib.providers import get_enabled_providers
from lib.resolvers import YouTubeResolver
from lib.id_translator import IMDbToTMDbTranslator
from lib.logger import log as _fox_log


# Quality ranking for sorting
QUALITY_RANK = {
    '1080p': 1,
    '720p': 2,
    'HD': 3,
    '480p': 4,
    'SD': 5,
    'Auto': 6,
    '': 7  # Unknown quality - lowest priority
}


class PlayerCore:
    """
    Core orchestrator for Turkish Series Player
    
    Architecture: Sub-Resolver Pattern
    - Providers: Scrape sites, return embed URLs
    - Resolvers: Extract streams from embeds
    - Core: Orchestrate providers and resolvers
    
    Workflow:
    1. Get enabled providers
    2. Search all providers (parallel or sequential)
    3. Get episode servers from all providers
    4. Enrich server info (detect quality)
    5. Show interactive selection loop
    6. Resolve chosen server (delegate to resolvers)
    7. On failure: show blocking error dialog, remove server, retry
    8. Return stream URL + metadata
    """
    
    def __init__(self, addon):
        """
        Initialize player core with sub-resolvers and ID translator
        
        Args:
            addon: Kodi addon instance
        """
        self.addon = addon
        
        # Load settings
        self.search_mode = addon.getSetting('provider_search_mode') or 'parallel'
        self.max_workers = int(addon.getSetting('max_concurrent_providers') or '3')
        self.provider_timeout = int(addon.getSetting('provider_timeout') or '10')
        
        # Get TMDB API key
        self.tmdb_api_key = addon.getSetting('tmdb_api_key')
        
        # Create shared session for all resolvers
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        })
        
        # Initialize sub-resolvers
        self.yt_resolver = YouTubeResolver(self.session)
        
        # Initialize ID translator
        self.id_translator = IMDbToTMDbTranslator(self.session, self.tmdb_api_key)
        
        # Load enabled providers
        self.providers = get_enabled_providers(addon)
        
        self._log(f"PlayerCore initialized with {len(self.providers)} providers", xbmc.LOGINFO)
        self._log(f"Search mode: {self.search_mode}, Max workers: {self.max_workers}", xbmc.LOGINFO)
        self._log(f"Sub-resolvers loaded: YouTube (Piped API)", xbmc.LOGINFO)
        self._log(f"ID Translator loaded: IMDbâ†'TMDb support enabled", xbmc.LOGINFO)
    
    def resolve_episode(self, tmdb_id, season, episode, title, item_information=None):
        """
        Main entry point - resolve episode to playable stream

        Uses interactive selection loop:
        1. Scrape all providers ONCE
        2. Show server selection dialog
        3. Try to resolve selected server
        4. On failure: show error dialog, remove server, repeat
        5. On success: return stream

        Args:
            tmdb_id (int): TMDB series ID
            season (int): Season number
            episode (int): Episode number
            title (str): Series title (for display)
            item_information (dict): Metadata for the source select dialog
                (title, season, episode, year, rating, plot, poster, fanart)

        Returns:
            dict: {
                'url': '...',
                'is_hls': bool,
                'subtitles': [...],
                'headers': {...}
            } or None
        """
        
        self._log(f"=== RESOLVING EPISODE ===", xbmc.LOGINFO)
        self._log(f"Title: {title}", xbmc.LOGINFO)
        self._log(f"TMDB: {tmdb_id}, S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        if not self.providers:
            self._log("ERROR: No providers enabled!", xbmc.LOGERROR)
            return None
        
        # STAGE 1: Search all providers for series
        self._log("STAGE 1: Searching providers...", xbmc.LOGINFO)
        search_results = self._search_providers(tmdb_id)
        
        if not search_results:
            self._log("No series found on any provider", xbmc.LOGERROR)
            return None
        
        # STAGE 2: Get episode servers from all providers
        self._log("STAGE 2: Getting episode servers...", xbmc.LOGINFO)
        all_servers = self._get_episode_servers_from_all(search_results, season, episode)
        
        if not all_servers:
            self._log("No servers found on any provider", xbmc.LOGERROR)
            return None
        
        # STAGE 3: Enrich server info (detect quality if missing)
        self._log("STAGE 3: Enriching server info...", xbmc.LOGINFO)
        enriched_servers = self._enrich_server_info(all_servers)
        
        if not enriched_servers:
            self._log("ERROR: No servers available!", xbmc.LOGERROR)
            return None
        
        # STAGE 4 & 5: Interactive selection loop
        self._log("STAGE 4: Entering interactive selection loop...", xbmc.LOGINFO)
        
        # Pre-sort servers once (dialog maintains this order)
        sorted_servers = self._sort_servers_by_quality(enriched_servers)
        
        # Try servers until one works or user cancels
        excluded_indices = []  # Track failed servers

        while True:
            # Filter out already-tried failed servers
            available_servers = [
                srv for i, srv in enumerate(sorted_servers)
                if i not in excluded_indices
            ]

            if not available_servers:
                self._log("All servers exhausted", xbmc.LOGERROR)
                if KODI_ENV:
                    xbmcgui.Dialog().ok(
                        'Little Fox',
                        'All servers failed.\n\nTry different episode or enable more providers.'
                    )
                return None

            # Show server selection dialog
            if len(available_servers) == 1 and not excluded_indices:
                # First attempt with single server - auto-select
                self._log("Only one server found, auto-selecting", xbmc.LOGINFO)
                selected_server = available_servers[0]
            else:
                self._log(f"Showing dialog with {len(available_servers)} servers", xbmc.LOGINFO)
                selected_server = self._show_server_selection_dialog(
                    available_servers, item_information
                )

                if not selected_server:
                    self._log("User cancelled server selection", xbmc.LOGWARNING)
                    return None

            # Find original index in sorted_servers (for exclusion tracking)
            original_index = sorted_servers.index(selected_server)
            
            self._log(f"User selected: [{selected_server.get('provider')}] {selected_server.get('server_name')}", xbmc.LOGINFO)
            
            # STAGE 5: Try to resolve selected server
            self._log("STAGE 5: Resolving with appropriate resolver...", xbmc.LOGINFO)
            
            stream_result = self._resolve_source(selected_server)
            
            if stream_result:
                # SUCCESS!
                self._log(f"SUCCESS: Stream resolved!", xbmc.LOGINFO)
                return stream_result
            
            # FAILED - mark this server as failed and show blocking error dialog
            excluded_indices.append(original_index)
            
            self._log(f"Resolution failed, showing error dialog", xbmc.LOGWARNING)
            
            # Show blocking error dialog
            if KODI_ENV:
                dialog = xbmcgui.Dialog()
                
                provider = selected_server.get('provider', 'Unknown')
                server_name = selected_server.get('server_name', 'Stream')
                
                error_message = (
                    f"Failed to resolve stream from:\n"
                    f"[{provider}] {server_name}\n\n"
                    f"Possible reasons:\n"
                    f"- Server offline or removed\n"
                    f"- Geo-restriction or captcha\n"
                    f"- Resolver not available\n\n"
                    f"Try another server."
                )
                
                dialog.ok('Stream Resolution Failed', error_message)
            
            # Loop continues - dialog will re-appear with remaining servers
            remaining_count = len(available_servers) - 1
            self._log(f"Retrying with {remaining_count} remaining servers...", xbmc.LOGINFO)
    
    # =========================================================================
    # STAGE 1: SEARCH PROVIDERS
    # =========================================================================
    
    def _search_providers(self, tmdb_id):
        """
        Search all providers for series
        
        Returns:
            dict: {provider_instance: [search_results]}
        """
        
        if self.search_mode == 'parallel':
            return self._search_providers_parallel(tmdb_id)
        else:
            return self._search_providers_sequential(tmdb_id)
    
    def _search_providers_parallel(self, tmdb_id):
        """Search providers in parallel"""
        
        results = {}
        
        def search_single_provider(provider):
            try:
                self._log(f"Searching {provider.get_name()}...", xbmc.LOGINFO)
                
                # Get TMDB names for this provider's languages
                names = provider.get_tmdb_names(tmdb_id)
                
                if not names:
                    self._log(f"{provider.get_name()}: No names found", xbmc.LOGWARNING)
                    return provider, []
                
                # Search
                search_results = provider.search_series(names)
                
                self._log(f"{provider.get_name()}: Found {len(search_results)} results", xbmc.LOGINFO)
                
                return provider, search_results
            
            except Exception as e:
                self._log(f"{provider.get_name()} search error: {e}", xbmc.LOGERROR)
                return provider, []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(search_single_provider, p) for p in self.providers]
            
            for future in as_completed(futures, timeout=self.provider_timeout):
                try:
                    provider, search_results = future.result()
                    if search_results:
                        results[provider] = search_results
                except Exception as e:
                    self._log(f"Provider search failed: {e}", xbmc.LOGERROR)
        
        return results
    
    def _search_providers_sequential(self, tmdb_id):
        """Search providers sequentially"""
        
        results = {}
        
        for provider in self.providers:
            try:
                self._log(f"Searching {provider.get_name()}...", xbmc.LOGINFO)
                
                # Get TMDB names
                names = provider.get_tmdb_names(tmdb_id)
                
                if not names:
                    continue
                
                # Search
                search_results = provider.search_series(names)
                
                if search_results:
                    results[provider] = search_results
                    self._log(f"{provider.get_name()}: Found {len(search_results)} results", xbmc.LOGINFO)
            
            except Exception as e:
                self._log(f"{provider.get_name()} search error: {e}", xbmc.LOGERROR)
        
        return results
    
    # =========================================================================
    # STAGE 2: GET EPISODE SERVERS
    # =========================================================================
    
    def _get_episode_servers_from_all(self, search_results, season, episode):
        """
        Get episode servers from all providers
        
        Args:
            search_results (dict): {provider: [results]}
            season (int): Season number
            episode (int): Episode number
        
        Returns:
            list: All servers from all providers
        """
        
        all_servers = []
        
        for provider, results in search_results.items():
            if not results:
                continue
            
            try:
                # Use first search result (typically most relevant)
                series_url = results[0]['series_url']
                
                self._log(f"Getting servers from {provider.get_name()}...", xbmc.LOGINFO)
                
                # Get servers
                servers = provider.get_episode_servers(series_url, season, episode)
                
                if servers:
                    # Add provider info to each server
                    for server in servers:
                        server['provider'] = provider.get_name()
                        server['audio_lang'] = provider.get_audio_language()
                    
                    all_servers.extend(servers)
                    self._log(f"{provider.get_name()}: Found {len(servers)} servers", xbmc.LOGINFO)
            
            except Exception as e:
                self._log(f"{provider.get_name()} get_episode_servers error: {e}", xbmc.LOGERROR)
        
        return all_servers
    
    # =========================================================================
    # STAGE 3: ENRICH SERVER INFO
    # =========================================================================
    
    def _enrich_server_info(self, servers):
        """
        Enrich server info - detect quality if missing
        
        NO FILTERING - shows ALL servers to user!
        
        Args:
            servers (list): Server list
        
        Returns:
            list: Enriched servers (all of them!)
        """
        
        enriched = []
        
        for idx, server in enumerate(servers, 1):
            # Detect quality if not provided
            if not server.get('quality'):
                server['quality'] = self._detect_quality(server)
            
            # Detect host type (for display)
            host_type = self._detect_host_type(server['embed_url'])
            server['host_type'] = host_type
            
            enriched.append(server)
        
        self._log(f"Enrichment complete: kept all {len(enriched)} servers", xbmc.LOGINFO)
        return enriched
    
    def _detect_quality(self, server):
        """Detect quality from server info"""
        
        embed_url = server.get('embed_url', '').lower()
        server_name = server.get('server_name', '').lower()
        
        # Check URL
        if '1080' in embed_url or 'fhd' in embed_url:
            return '1080p'
        elif '720' in embed_url or 'hd' in embed_url:
            return '720p'
        elif '480' in embed_url or 'sd' in embed_url:
            return '480p'
        
        # Check server name
        if '1080' in server_name:
            return '1080p'
        elif '720' in server_name or 'hd' in server_name:
            return 'HD'
        elif '480' in server_name or 'sd' in server_name:
            return 'SD'
        
        # Check host type
        host_type = self._detect_host_type(embed_url)
        if host_type == 'ok.ru':
            return 'HD'
        elif host_type == 'youtube':
            return 'HD'
        
        return 'Auto'  # Default
    
    def _detect_host_type(self, embed_url):
        """Detect host type from embed URL"""
        
        url_lower = embed_url.lower()
        
        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'ok.ru' in url_lower:
            return 'ok.ru'
        elif 'shadwo' in url_lower:
            return 'shadwo'
        elif 'tukipasti' in url_lower:
            return 'tukipasti'
        elif 'dwish' in url_lower:
            return 'dwish'
        elif 'uqload' in url_lower:
            return 'uqload'
        elif 'doodstream' in url_lower:
            return 'doodstream'
        elif 'streamtape' in url_lower:
            return 'streamtape'
        elif 'turboviplay' in url_lower:
            return 'turboviplay'
        elif 'vidspeed' in url_lower:
            return 'vidspeed'
        
        return 'other'
    
    # =========================================================================
    # STAGE 4: SERVER SELECTION DIALOG
    # =========================================================================
    
    def _show_server_selection_dialog(self, servers, item_information=None):
        """
        Show premium server selection dialog (WindowXMLDialog).

        Falls back to Kodi's built-in Dialog().select() outside Kodi.

        Args:
            servers (list): Server list (already sorted by caller)
            item_information (dict): Metadata for right panel (poster, plot, etc.)

        Returns:
            dict: The selected server, or None if cancelled
        """
        if not KODI_ENV:
            # Non-Kodi fallback (testing / CLI)
            display_items = [self._build_server_display_text(s) for s in servers]
            idx = xbmcgui.Dialog().select('Select Server', display_items, preselect=0)
            return servers[idx] if idx >= 0 else None

        try:
            import xbmcaddon
            from lib.gui.source_select import ServerSelectDialog

            addon      = xbmcaddon.Addon()
            addon_path = addon.getAddonInfo('path')

            dialog = ServerSelectDialog(
                'source_select.xml',
                addon_path,
                item_information=item_information or {},
                servers=servers,
            )
            selected_url = dialog.doModal()

            if not selected_url:
                self._log("User cancelled server selection", xbmc.LOGWARNING)
                return None

            # Match embed_url back to a server dict
            for server in servers:
                if server.get('embed_url') == selected_url:
                    self._log(
                        f"User selected: [{server.get('provider')}] "
                        f"{server.get('server_name')} ({server.get('quality')})",
                        xbmc.LOGINFO,
                    )
                    return server

            self._log(f"Selected URL not matched: {selected_url[:80]}", xbmc.LOGWARNING)
            return None

        except Exception as e:
            self._log(f"Premium dialog failed ({e}), falling back to built-in", xbmc.LOGWARNING)
            import traceback
            self._log(traceback.format_exc(), xbmc.LOGDEBUG)

            # Fallback to plain dialog
            display_items = [self._build_server_display_text(s) for s in servers]
            idx = xbmcgui.Dialog().select('Select Server', display_items, preselect=0)
            return servers[idx] if idx >= 0 else None
    
    def _sort_servers_by_quality(self, servers):
        """
        Sort servers by:
        1. Quality rank (higher quality first)
        2. Provider name (alphabetically)
        """
        
        def sort_key(server):
            # Quality rank
            quality = server.get('quality', '')
            quality_rank = QUALITY_RANK.get(quality, 99)
            
            # Provider name
            provider = server.get('provider', '')
            
            return (quality_rank, provider)
        
        return sorted(servers, key=sort_key)
    
    def _build_server_display_text(self, server):
        """
        Build display text for server
        
        Format: [Provider] Quality - Server | Language
        Example: [Qrmzi] 1080p - Server 1 | Arabic
        
        CRITICAL: ASCII ONLY - No Unicode symbols, no Arabic text
        """
        
        provider = server.get('provider', 'Unknown')
        quality = server.get('quality', 'Auto')
        server_name = server.get('server_name', 'Stream')
        audio_lang = server.get('audio_lang', 'Unknown')
        
        # Map language codes to display names (ASCII only)
        lang_display = {
            'ar': 'Arabic',
            'en': 'English Subs',
            'tr': 'Turkish'
        }.get(audio_lang, audio_lang)
        
        # Format: [Provider] Quality - Server | Language
        # ASCII ONLY - No symbols like âœ", âœ…, âŒ, etc.
        display = f"[{provider}] {quality}"
        
        if server_name and server_name != 'Stream':
            display += f" - {server_name}"
        
        display += f" | {lang_display}"
        
        return display
    
    # =========================================================================
    # STAGE 5: RESOLVE WITH RESOLVERS / RESOLVEURL
    # =========================================================================
    
    def _resolve_source(self, server):
        """
        Resolve server to playable stream
        
        SWITCHBOARD: Detects host type and delegates to appropriate resolver
        
        Args:
            server (dict): Server info with embed_url
        
        Returns:
            dict: {
                'url': '...',
                'is_hls': bool,
                'subtitles': [...],
                'headers': {...}
            } or None
        """
        
        embed_url = server['embed_url']
        referer = server.get('referer', '')
        
        # =====================================================================
        # PATH 1: YOUTUBE -> Delegate to plugin.video.youtube addon
        # =====================================================================

        if 'youtube.com' in embed_url.lower() or 'youtu.be' in embed_url.lower():
            self._log("YouTube URL detected - delegating to plugin.video.youtube", xbmc.LOGINFO)

            video_id = self.yt_resolver._extract_video_id(embed_url)

            if not video_id:
                self._log("Failed to extract YouTube video ID", xbmc.LOGERROR)
                return None

            self._log(f"Launching via plugin.video.youtube: {video_id}", xbmc.LOGINFO)

            return {
                'url': f'plugin://plugin.video.youtube/play/?video_id={video_id}',
                'is_hls': False,
                'subtitles': [],
                'headers': {}
            }
        
        # =====================================================================
        # PATH 2: DIRECT LINK BYPASS
        # =====================================================================
        
        if any(ext in embed_url.lower() for ext in ['.m3u8', '.mp4', '.mkv']):
            self._log(f"Direct link detected", xbmc.LOGINFO)
            
            result = {
                'url': embed_url,
                'is_hls': '.m3u8' in embed_url.lower(),
                'subtitles': [],
                'headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': referer if referer else embed_url,
                    'Accept': '*/*'
                }
            }
            
            return result
        
        # =====================================================================
        # PATH 3: RESOLVEURL RESOLUTION
        # =====================================================================
        
        if not RESOLVEURL_AVAILABLE:
            self._log("ERROR: ResolveURL not available!", xbmc.LOGERROR)
            return None
        
        # Normalize domain
        normalized_url = self._universal_normalize(embed_url)
        
        if normalized_url != embed_url:
            self._log(f"Domain normalized", xbmc.LOGINFO)
        
        self._log(f"Resolving with ResolveURL...", xbmc.LOGINFO)
        
        try:
            # Create HostedMediaFile object — pass clean URL only (no $$ hacks)
            hmf = resolveurl.HostedMediaFile(url=normalized_url)

            # Validate URL is supported (bool check calls valid_url() internally)
            if not hmf:
                self._log("ResolveURL: Not a hosted media file", xbmc.LOGWARNING)
                return None

            # Resolve to stream URL (with subtitle support)
            resolved = hmf.resolve()

            if not resolved:
                self._log("ResolveURL: Resolution failed (empty result)", xbmc.LOGERROR)
                return None

            self._log(f"SUCCESS: Resolved with ResolveURL", xbmc.LOGINFO)

            # Resolver may return a dict with url + subs, or a plain string
            if isinstance(resolved, dict):
                resolved_url = resolved.get('url', '')
                resolver_subs = list(resolved.get('subs', {}).values()) if resolved.get('subs') else []
            else:
                resolved_url = resolved
                resolver_subs = []

            if not resolved_url:
                self._log("ResolveURL: Resolution returned empty URL", xbmc.LOGERROR)
                return None

            # Some resolvers embed headers in the URL using Kodi's pipe format: url|Header=Value
            # Only inject our own headers when the resolver hasn't already done so
            if '|' in resolved_url:
                headers = {}
            else:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Referer': referer if referer else normalized_url,
                    'Accept': '*/*'
                }

            result = {
                'url': resolved_url,
                'is_hls': '.m3u8' in resolved_url.lower(),
                'subtitles': resolver_subs,
                'headers': headers
            }

            return result
        
        except Exception as e:
            self._log(f"ResolveURL error: {e}", xbmc.LOGERROR)
            return None
    
    def _universal_normalize(self, embed_url):
        """
        Normalize embed URL for ResolveURL compatibility
        
        Uses keyword matching instead of exact domain lists
        
        Args:
            embed_url (str): Original embed URL
        
        Returns:
            str: Normalized URL for ResolveURL
        """
        
        try:
            parsed = urlparse(embed_url)
            domain = parsed.netloc.lower()
            
            new_domain = None
            
            # vidspeed family â†' vidspeed.cc
            if 'vidspeed' in domain and 'vidspeeds' not in domain:
                new_domain = 'vidspeed.cc'
            
            # vidspeeds (plural) â†' vidspeeds.com
            elif 'vidspeeds' in domain:
                new_domain = 'vidspeeds.com'
            
            # vidroba â†' vidroba.com
            elif 'vidroba' in domain:
                new_domain = 'vidroba.com'
            
            # turboviplay family â†' turboviplay.com
            elif 'turboviplay' in domain or 'turbovid' in domain:
                new_domain = 'turboviplay.com'
            
            # albrq family â†' albrq.cc
            elif 'albrq' in domain:
                new_domain = 'albrq.cc'
            
            # vidoba family â†' vidoba.site
            elif 'vidoba' in domain:
                new_domain = 'vidoba.site'
            
            # If normalization needed
            if new_domain and new_domain != domain:
                self._log(f"Normalized: {domain} â†' {new_domain}", xbmc.LOGDEBUG)
                
                # Rebuild URL with new domain
                normalized = parsed._replace(netloc=new_domain)
                return urlunparse(normalized)
            
            # No normalization needed
            return embed_url
        
        except Exception as e:
            self._log(f"Domain normalization error: {e}", xbmc.LOGDEBUG)
            return embed_url
    
    def _log(self, message, level=xbmc.LOGINFO):
        """Log message via logger module."""
        if KODI_ENV:
            level_map = {
                xbmc.LOGDEBUG:   'debug',
                xbmc.LOGINFO:    'info',
                xbmc.LOGWARNING: 'warning',
                xbmc.LOGERROR:   'error',
            }
            _fox_log(message, level_map.get(level, 'info'))
        else:
            print(f"[PlayerCore] {message}")
