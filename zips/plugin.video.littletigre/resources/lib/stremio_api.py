"""Stremio addon API handler - WITH AniList absolute episode support."""

import re
import json
import requests
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
from resources.lib.settings import Settings
from resources.lib.logger import log, log_error, log_debug
from resources.lib.stream_scorer import StreamAnalyzer
from resources.lib.stream_parser import StreamParser
from resources.lib.anime_resolver import AnimeResolver


class StremioAPI:
    """Handle Stremio addon API requests with anime absolute episode support."""

    def __init__(self):
        """Initialize API handler."""
        self.timeout = Settings.get_addon_timeout()
        self.max_results = Settings.get_max_results()
        self.debrid_service = Settings.get_debrid_service()
        self.debrid_key = Settings.get_debrid_api_key()
        self.use_parallel = Settings.use_parallel_queries()
        self.anime_resolver = AnimeResolver()

    def get_streams_with_anime_support(self, search_id, id_type, content_type='movie', season=None, episode=None, params=None):
        """
        Get streams from all enabled addons WITH ANIME ABSOLUTE EPISODE SUPPORT.

        CRITICAL: Episode parameter should already be absolute episode (resolved in playback_engine).
        """
        addons = Settings.get_enabled_addons()

        if not addons:
            log_error("No addons enabled")
            return []

        is_anime = self.anime_resolver.detect_content_type(params)

        # Extract title for query enhancement
        title = None
        if params:
            title = params.get('title', params.get('showtitle', params.get('tvshowtitle')))
            if title:
                from urllib.parse import unquote_plus
                title = unquote_plus(str(title))

        log(f"Searching for streams: {search_id} (type: {id_type}, is_anime: {is_anime})")
        log(f"Using debrid service: {self.debrid_service.upper()}")

        if title:
            log_debug(f"Title for query enhancement: {title}")

        if is_anime and episode:
            log(f"🎌 Anime episode query: Episode {episode} (absolute)")

        # Get IMDB ID as fallback (most reliable for non-anime addons)
        imdb_id = None
        if id_type == 'imdb':
            imdb_id = search_id
        elif params:
            imdb_id = params.get('imdb_id', '').strip()

        all_streams = []

        if self.use_parallel:
            with ThreadPoolExecutor(max_workers=min(len(addons), 8)) as executor:
                futures = {}

                for addon in addons:
                    # Smart ID selection per addon
                    addon_id, addon_id_type = self._get_smart_addon_id(
                        addon,
                        search_id,
                        id_type,
                        imdb_id,
                        params,
                        is_anime
                    )

                    futures[executor.submit(
                        self._query_addon_with_id,
                        addon,
                        content_type,
                        addon_id,
                        addon_id_type,
                        season,
                        episode,
                        is_anime,
                        title  # NEW: Pass title for query enhancement
                    )] = addon

                for future in as_completed(futures):
                    addon = futures[future]
                    try:
                        streams = future.result()
                        if streams:
                            all_streams.extend(streams)
                            log(f"{addon['name']}: Found {len(streams)} streams")
                        else:
                            log_debug(f"{addon['name']}: No streams found")
                    except Exception as e:
                        log_error(f"{addon['name']} query failed", e)
        else:
            for addon in addons:
                try:
                    # Smart ID selection per addon
                    addon_id, addon_id_type = self._get_smart_addon_id(
                        addon,
                        search_id,
                        id_type,
                        imdb_id,
                        params,
                        is_anime
                    )

                    streams = self._query_addon_with_id(
                        addon,
                        content_type,
                        addon_id,
                        addon_id_type,
                        season,
                        episode,
                        is_anime,
                        title  # NEW: Pass title for query enhancement
                    )

                    if streams:
                        all_streams.extend(streams)
                        log(f"{addon['name']}: Found {len(streams)} streams")
                    else:
                        log_debug(f"{addon['name']}: No streams found")
                except Exception as e:
                    log_error(f"{addon['name']} query failed", e)

        log(f"Total streams found: {len(all_streams)}")
        return all_streams



    def get_streams_multi_query(self, search_id, id_type, content_type, queries, params=None):
        """
        Query all enabled addons for MULTIPLE episode queries in ONE parallel batch.

        Instead of two sequential rounds (absolute then season), submits all
        addon × query combinations to a single ThreadPoolExecutor so both
        rounds run concurrently.

        Args:
            queries: list of {'season': str|None, 'episode': str, 'label': str}
        """
        addons = Settings.get_enabled_addons()
        if not addons:
            log_error("No addons enabled")
            return []

        is_anime = self.anime_resolver.detect_content_type(params)

        title = None
        if params:
            title = params.get('title', params.get('showtitle', params.get('tvshowtitle')))
            if title:
                from urllib.parse import unquote_plus
                title = unquote_plus(str(title))

        imdb_id = None
        if id_type == 'imdb':
            imdb_id = search_id
        elif params:
            imdb_id = params.get('imdb_id', '').strip()

        total_tasks = len(addons) * len(queries)
        max_workers = min(total_tasks, 10)
        log(f"Multi-query: {len(addons)} addons x {len(queries)} queries = {total_tasks} parallel tasks")

        all_streams = []
        seen_urls = set()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for addon in addons:
                addon_id, addon_id_type = self._get_smart_addon_id(
                    addon, search_id, id_type, imdb_id, params, is_anime
                )
                for query in queries:
                    future = executor.submit(
                        self._query_addon_with_id,
                        addon,
                        content_type,
                        addon_id,
                        addon_id_type,
                        query.get('season'),
                        query['episode'],
                        is_anime,
                        title
                    )
                    futures[future] = (addon, query.get('label', ''))

            for future in as_completed(futures):
                addon, label = futures[future]
                try:
                    streams = future.result()
                    if streams:
                        new_streams = []
                        for stream in streams:
                            url = stream.get('url', '')
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                stream['query_type'] = label
                                new_streams.append(stream)
                        all_streams.extend(new_streams)
                        log(f"{addon['name']} ({label}): +{len(new_streams)} streams")
                    else:
                        log_debug(f"{addon['name']} ({label}): No streams")
                except Exception as e:
                    log_error(f"{addon['name']} ({label}) query failed", e)

        log(f"Multi-query total: {len(all_streams)} unique streams")
        return all_streams

    def _get_smart_addon_id(self, addon, search_id, id_type, imdb_fallback, params, is_anime):
        """
        SMART PER-ADDON ID SELECTION for maximum results!

        Each addon has preferred ID formats. This method selects the BEST ID
        for each specific addon, overriding user preference when needed.

        Addon Preferences (based on real-world testing):
        - Torrentio: IMDB > Kitsu (IMDB gives more results)
        - Comet: Kitsu/MAL > IMDB (native anime support)
        - StremThru: IMDB > Kitsu (universal support)
        - MediaFusion: IMDB > Kitsu (prefers IMDB)
        - AIO Streams: ANY (wraps all addons, user preference)
        """
        addon_name = addon['name'].lower()

        # Check if smart selection is enabled
        use_smart_selection = Settings.use_smart_addon_id_selection()

        if not use_smart_selection:
            # Respect user preference for all addons
            log(f"{addon['name']}: Using user preference {id_type.upper()}: {search_id}")
            return search_id, id_type

        # === CUSTOM ADDON: derive preferences from manifest id_prefixes ===
        if addon.get('is_custom'):
            prefix_to_type = {
                'tt': 'imdb',
                'kitsu:': 'kitsu',
                'mal:': 'mal',
                'anilist:': 'anilist',
            }
            addon_prefs = []
            for prefix in addon.get('id_prefixes', ['tt']):
                t = prefix_to_type.get(prefix)
                if t and t not in addon_prefs:
                    addon_prefs.append(t)
            if not addon_prefs:
                addon_prefs = ['imdb']
            log_debug(f"{addon['name']}: Custom addon prefs derived from manifest: {addon_prefs}")
        else:
            # === BUILT-IN ADDON-SPECIFIC PREFERENCES ===

            ADDON_PREFERENCES = {
                'torrentio': ['imdb', 'kitsu', 'mal'],
                'comet': ['kitsu', 'mal', 'anilist', 'imdb'],
                'stremthru': ['imdb', 'kitsu', 'mal'],
                'mediafusion': ['imdb', 'kitsu', 'mal'],
                'aio': ['user_preference'],
                'aiostreams': ['user_preference'],
            }

            addon_prefs = None
            for addon_key, prefs in ADDON_PREFERENCES.items():
                if addon_key in addon_name:
                    addon_prefs = prefs
                    break

        # If addon not in preferences or wants user preference, use current ID
        if not addon_prefs or 'user_preference' in addon_prefs:
            log(f"{addon['name']}: Using user preference {id_type.upper()}: {search_id}")
            return search_id, id_type

        # === NON-ANIME: Always prefer IMDB ===
        if not is_anime:
            if imdb_fallback:
                log(f"{addon['name']}: Non-anime - using IMDB: {imdb_fallback}")
                return imdb_fallback, 'imdb'
            else:
                log(f"{addon['name']}: Non-anime - using {id_type}: {search_id}")
                return search_id, id_type

        # === ANIME: Try addon's preferred formats in order ===

        # Collect available IDs
        available_ids = {}

        if params:
            anilist_id = params.get('anilist_id', '').strip()
            if anilist_id:
                available_ids['anilist'] = anilist_id

            kitsu_id = params.get('kitsu_id', '').strip()
            if kitsu_id:
                available_ids['kitsu'] = f"kitsu:{kitsu_id}"

            mal_id = params.get('mal_id', '').strip()
            if mal_id:
                available_ids['mal'] = f"mal:{mal_id}"

            imdb_id = params.get('imdb_id', '').strip()
            if imdb_id:
                available_ids['imdb'] = imdb_id

        # Try each preference in order
        for pref_type in addon_prefs:
            if pref_type in available_ids:
                preferred_id = available_ids[pref_type]
                log(f"{addon['name']}: ⭐ Using PREFERRED {pref_type.upper()}: {preferred_id}")
                return preferred_id, pref_type

        # Fallback: use what we have
        log(f"{addon['name']}: ⚠️ Using fallback {id_type.upper()}: {search_id}")
        return search_id, id_type

    def _query_addon_with_id(self, addon, content_type, search_id, id_type, season=None, episode=None, is_anime=False, title=None):
        """
        Query a single Stremio addon with a specific ID.

        CRITICAL: Episode parameter is already absolute for anime.
        NEW: Title parameter for query enhancement (fallback matching).
        """
        stream_id = self._build_stream_id(search_id, content_type, season, episode)
        return self._query_addon(addon, content_type, stream_id, title)

    def _query_addon(self, addon, content_type, stream_id, title=None):
        """Query a single Stremio addon with optional title for fallback matching."""
        addon_name = addon['name']
        custom_url = addon.get('custom_url', '').strip()

        if custom_url:
            custom_url = unquote(custom_url)
            if '/manifest.json' in custom_url:
                addon_url = custom_url.rsplit('/manifest.json', 1)[0]
            else:
                addon_url = custom_url.rstrip('/')
            log_debug(f"{addon_name}: Using custom URL")
        else:
            base_url = addon['url'].rstrip('/')
            if self.debrid_key:
                addon_url = self._build_addon_url(base_url, addon_name)
            else:
                addon_url = base_url

        stream_url = f"{addon_url}/stream/{content_type}/{stream_id}.json"

        # NEW: Add title as query parameter for fallback matching
        if title and content_type == 'series':
            from urllib.parse import quote_plus
            # Clean title - remove URL encoding artifacts
            clean_title = title.replace('+', ' ').strip()
            stream_url += f"?title={quote_plus(clean_title)}"
            log_debug(f"{addon_name}: Enhanced query with title: {clean_title}")

        log_debug(f"Querying {addon_name}: {stream_url}")

        max_retries = 2
        retry_delays = [0, 0.5]

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    log(f"{addon_name}: Retry attempt {attempt + 1}/{max_retries}")
                    import time
                    time.sleep(retry_delays[attempt])

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate',
                    'Origin': 'https://web.stremio.com',
                    'Referer': 'https://web.stremio.com/',
                }

                response = requests.get(stream_url, headers=headers, timeout=self.timeout)
                response.raise_for_status()

                if not response.content or len(response.content) == 0:
                    log_debug(f"{addon_name}: Empty response - no streams available")
                    return []

                content_type_header = response.headers.get('Content-Type', '')
                if 'application/json' not in content_type_header and 'text/json' not in content_type_header:
                    log(f"{addon_name}: Response is not JSON (Content-Type: {content_type_header})", 'warning')
                    return []

                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    log_error(f"{addon_name}: Invalid JSON response", e)
                    return []

                streams = data.get('streams', [])

                if not streams:
                    log_debug(f"{addon_name}: No streams in response")
                    return []

                # === FIX: Add detailed logging ===
                log(f"{addon_name}: API returned {len(streams)} raw streams")
                log_debug(f"{addon_name}: Will process up to {self.max_results} streams")

                parsed_streams = []
                failed_count = 0
                for stream in streams[:self.max_results]:
                    parsed = self._parse_stream(stream, addon_name)
                    if parsed:
                        parsed_streams.append(parsed)
                    else:
                        failed_count += 1

                log(f"{addon_name}: ✓ Parsed {len(parsed_streams)} streams, ❌ {failed_count} failed parsing")
                return parsed_streams

            except requests.Timeout:
                if attempt == max_retries - 1:
                    log_error(f"{addon_name}: Request timeout after {max_retries} attempts")
                else:
                    log(f"{addon_name}: Request timeout, will retry...")
                continue
            except requests.RequestException as e:
                log_error(f"{addon_name}: Request failed", e)
                break
            except Exception as e:
                log_error(f"{addon_name}: Unexpected error", e)
                break

        return []

    def _build_addon_url(self, base_url, addon_name):
        """Build addon URL with debrid configuration."""
        debrid_configs = {
            'comet': {
                'realdebrid': f"{base_url}/{self.debrid_key}/manifest.json",
                'torbox': f"{base_url}/torbox/{self.debrid_key}/manifest.json",
            },
            'mediafusion': {
                'realdebrid': f"{base_url}/{self.debrid_key}/manifest.json",
                'torbox': f"{base_url}/torbox/{self.debrid_key}/manifest.json",
            },
            'torrentio': {
                'realdebrid': f"{base_url}/realdebrid={self.debrid_key}/manifest.json",
                'torbox': f"{base_url}/torbox={self.debrid_key}/manifest.json",
            }
        }

        addon_lower = addon_name.lower()
        if addon_lower in debrid_configs:
            config = debrid_configs[addon_lower].get(self.debrid_service)
            if config:
                return config.replace('/manifest.json', '')

        return base_url

    def _parse_stream(self, stream, addon_name):
        """Parse a Stremio stream object."""
        try:
            # Get title - try both 'title' and 'name' fields
            title = stream.get('title', stream.get('name', 'Unknown'))

            # === FIX: Better URL detection ===
            url = None
            if 'url' in stream:
                url = stream['url']
            elif 'infoHash' in stream:
                url = f"magnet:?xt=urn:btih:{stream['infoHash']}"
            elif 'externalUrl' in stream:
                url = stream['externalUrl']

            if not url:
                # === FIX: Use log() instead of log_debug() to always see these ===
                log(f"❌ {addon_name}: Stream rejected - no URL found")
                log_debug(f"   Title: {title}")
                log_debug(f"   Keys: {list(stream.keys())}")
                return None

            log_debug(f"✓ {addon_name}: Parsing '{title[:50]}...'")

            description = stream.get('description', '')
            if not description:
                description = title

            # Full AIOStreams-style metadata extraction
            stream_meta = StreamParser.parse_stream(stream)

            # Service / cached: prefer StreamParser result, fall back to old helpers
            cached = (stream_meta['service']['cached'] if stream_meta.get('service')
                      else self._is_cached_enhanced(title, stream))
            debrid_service = (stream_meta['service']['id'] if stream_meta.get('service')
                              else self._detect_debrid_service(url, title, stream))

            # Seeders: StreamParser extracts from emoji (👤N); also try text patterns
            seeders = stream_meta.get('seeders') or self._extract_seeders(title, stream)

            # Size: prefer StreamParser (handles behaviorHints.videoSize), else old helper
            size_gb = stream_meta.get('size_gb') or self._extract_size(title, stream, description)

            parsed = {
                'title': title,
                'description': description,
                'url': url,
                'addon': addon_name,
                'cached': cached,
                'debrid_service': debrid_service,
                'seeders': seeders,
                'size_gb': size_gb,
                # Legacy compat fields (used by StreamScorer scoring)
                'quality': stream_meta.get('resolution') or StreamAnalyzer.extract_quality(title),
                'source': stream_meta.get('quality') or StreamAnalyzer.extract_source(title),
                'codec': stream_meta.get('encode') or StreamAnalyzer.extract_codec(title),
                # Rich parsed metadata for source_select.py display
                'parsed': stream_meta,
                'behaviorHints': stream.get('behaviorHints', {}),
                'subtitles': stream.get('subtitles', []),
                'infoHash': stream.get('infoHash', '')
            }

            return parsed

        except Exception as e:
            # === FIX: More detailed error logging ===
            stream_title = stream.get('title', stream.get('name', 'Unknown'))
            log_error(f"❌ {addon_name}: Parse failed for '{stream_title[:50]}' - {str(e)}", e)
            return None

    def _is_cached_enhanced(self, title, stream):
        """Enhanced cached detection (NO EMOJI - prevents encoding issues)."""
        title_lower = title.lower()

        # Text indicators only (NO EMOJI to avoid encoding issues)
        text_indicators = [
            '[cached]', '[rd]', '[real-debrid]', 'real-debrid',
            '[pm]', '[premiumize]', 'premiumize',
            '[ad]', '[alldebrid]', 'alldebrid',
            '[tb]', '[torbox]', 'torbox',
            'cached', '(cached)',
        ]

        for indicator in text_indicators:
            if indicator in title_lower:
                log_debug(f"Cached detected via text '{indicator}'")
                return True

        # Check URL for debrid domains
        url = stream.get('url', '')
        if url:
            debrid_domains = [
                'torbox.app', 'tb-cdn.st', 'real-debrid.com',
                'premiumize.me', 'alldebrid.com', '/files/', '/download/'
            ]

            for domain in debrid_domains:
                if domain in url.lower():
                    log_debug(f"Cached detected via URL domain '{domain}'")
                    return True

        # Check behaviorHints
        behavior_hints = stream.get('behaviorHints', {})

        if behavior_hints.get('notWebReady') is False:
            log_debug("Cached detected via behaviorHints.notWebReady=False")
            return True

        if 'filename' in behavior_hints:
            log_debug("Cached detected via behaviorHints.filename")
            return True

        return False

    def _detect_debrid_service(self, url, title, stream):
        """Detect which debrid service this stream is from."""
        url_lower = url.lower()

        # Check URL first
        if 'real-debrid.com' in url_lower or 'download.real-debrid.com' in url_lower:
            log_debug("Debrid service: Real-Debrid (from URL)")
            return 'realdebrid'
        elif 'torbox.app' in url_lower or 'tb-cdn.st' in url_lower:
            log_debug("Debrid service: Torbox (from URL)")
            return 'torbox'
        elif 'premiumize.me' in url_lower:
            log_debug("Debrid service: Premiumize (from URL)")
            return 'premiumize'
        elif 'alldebrid.com' in url_lower:
            log_debug("Debrid service: AllDebrid (from URL)")
            return 'alldebrid'

        # Check title
        title_lower = title.lower()

        if '[rd' in title_lower or 'real-debrid' in title_lower:
            log_debug("Debrid service: Real-Debrid (from title)")
            return 'realdebrid'
        elif '[tb' in title_lower or 'torbox' in title_lower:
            log_debug("Debrid service: Torbox (from title)")
            return 'torbox'
        elif '[pm' in title_lower or 'premiumize' in title_lower:
            log_debug("Debrid service: Premiumize (from title)")
            return 'premiumize'
        elif '[ad' in title_lower or 'alldebrid' in title_lower:
            log_debug("Debrid service: AllDebrid (from title)")
            return 'alldebrid'

        # Infer from enabled services
        enabled_services = Settings.get_enabled_debrid_services()
        if enabled_services:
            if len(enabled_services) == 1 and self._is_cached_enhanced(title, stream):
                service_name = enabled_services[0]['name']
                log_debug(f"Debrid service inferred: {service_name}")
                return service_name

        return None

    def _extract_seeders(self, title, stream):
        """Extract seeder count from stream (NO EMOJI)."""
        patterns = [
            r'[Ss]eeders?:?\s*(\d+)',
            r'\(S:\s*(\d+)\)',
            r'S:\s*(\d+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass

        if 'seeders' in stream:
            return stream['seeders']

        return 0

    def _extract_size(self, title, stream, description=''):
        """Extract file size from stream."""
        patterns = [
            r'(\d+\.?\d*)\s*GB',
            r'(\d+\.?\d*)\s*MB',
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                size = float(match.group(1))
                if 'MB' in pattern:
                    size = size / 1024
                return size

        if description:
            for pattern in patterns:
                match = re.search(pattern, description, re.IGNORECASE)
                if match:
                    size = float(match.group(1))
                    if 'MB' in pattern:
                        size = size / 1024
                    return size

        behavior_hints = stream.get('behaviorHints', {})
        if 'videoSize' in behavior_hints:
            try:
                size_bytes = int(behavior_hints['videoSize'])
                size_gb = size_bytes / (1024 * 1024 * 1024)
                return size_gb
            except (ValueError, TypeError):
                pass

        if 'size' in stream:
            return StreamAnalyzer.parse_size(str(stream['size']))

        return 0

    def _build_stream_id(self, search_id, content_type, season, episode):
        """
        Build stream ID for Stremio API.

        CRITICAL FIX: Kitsu/MAL/AniList use ABSOLUTE episode numbers only!
        - Kitsu: kitsu:49016:13 (NOT kitsu:49016:3:13)
        - MAL: mal:16498:13 (NOT mal:16498:3:13)
        - AniList: 16498:13 (NOT 16498:3:13)
        - IMDB/TMDB: tt12345:3:13 (with season)
        """
        if content_type == 'series' and episode:
            # Check if this is an anime ID (kitsu/mal/anilist)
            search_id_lower = str(search_id).lower()
            is_anime_id = any(prefix in search_id_lower for prefix in ['kitsu:', 'mal:', 'anilist:'])

            # For anime IDs: ALWAYS use absolute episode (no season)
            if is_anime_id:
                stream_id = f"{search_id}:{episode}"
                log_debug(f"Built stream ID (anime absolute): {stream_id}")
                return stream_id

            # For IMDB/TMDB: Use season:episode format
            if season:
                stream_id = f"{search_id}:{season}:{episode}"
                log_debug(f"Built stream ID (season): {stream_id}")
            else:
                # Fallback: absolute episode
                stream_id = f"{search_id}:{episode}"
                log_debug(f"Built stream ID (absolute): {stream_id}")
            return stream_id

        return search_id

    def test_addon(self, addon):
        """Test if an addon is accessible."""
        try:
            url = f"{addon['url']}/manifest.json"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            return True, data.get('name', addon['name'])
        except Exception as e:
            return False, str(e)
