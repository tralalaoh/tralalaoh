"""Anime ID resolution - AniList GraphQL with SPLIT-COUR detection."""

import requests
import re
from resources.lib.logger import log, log_error, log_debug
from resources.lib.settings import Settings


class AnimeResolver:
    """
    Resolve anime absolute episode numbers AND season metadata using AniList GraphQL API.

    CRITICAL FIX: Handles Split-Cour anime (Part 1/Part 2, Cour 1/Cour 2)

    Example: Fire Force Season 3 Part 2 Episode 1
    - AniList sees it as a separate entry (Season 4 in AniList's count)
    - Torrents/TMDb see it as Season 3 Episode 13 (Part 1 had 12 episodes)

    Solution: Detect "Part 2" in title, merge with Part 1, calculate correct episode offset.
    """

    ANILIST_API_URL = "https://graphql.anilist.co"
    ANIZIP_API_URL  = "https://api.ani.zip/mappings"

    # AniZip query parameter names per source type
    _ANIZIP_QUERY_PARAM = {
        'anilist': 'anilist_id',
        'mal':     'myanimelist_id',
        'kitsu':   'kitsu_id',
        'imdb':    'imdb_id',
        'tmdb':    'themoviedb_id',
        'tvdb':    'thetvdb_id',
    }

    # AniZip 'mappings' response key aliases - mirrors the scrobbler's _ID_MAP.
    # For each canonical name, keys are tried in order; first match wins.
    _ANIZIP_KEY_MAP = {
        'anilist': ('anilist_id',),
        'mal':     ('myanimelist_id',),
        'kitsu':   ('kitsu_id',),
        'imdb':    ('imdb_id',),
        'tmdb':    ('themoviedb_id',),
        'tvdb':    ('thetvdb_id',),
    }

    # Patterns to detect split-cour anime
    PART_2_PATTERNS = [
        r'part\s*2',
        r'part\s*ii',
        r'cour\s*2',
        r'2nd\s*cour',
        r'2nd\s*part',
        r'season\s*\d+\s*part\s*2',
    ]

    def __init__(self):
        """Initialize resolver."""
        self.timeout = 10
        self.cache = {}

    @staticmethod
    def _is_valid_id(id_value):
        """
        Check if ID is valid (not empty, not '_', not None).

        CRITICAL: TMDb Helper uses '_' for missing IDs!
        """
        if not id_value:
            return False
        id_str = str(id_value).strip()
        return id_str and id_str != '_' and id_str.lower() != 'none'

    @staticmethod
    def _extract_anizip_id(mappings, canonical_name):
        """Extract an ID from an AniZip 'mappings' dict using the key alias map."""
        if not mappings:
            return None
        for key in AnimeResolver._ANIZIP_KEY_MAP.get(canonical_name, ()):
            value = mappings.get(key)
            if value:
                return value
        return None

    def _fetch_anizip_mappings(self, source_type, id_value):
        """
        Query AniZip API and return the 'mappings' dict, or None on failure.
        One call returns ALL ID types at once.
        """
        param = self._ANIZIP_QUERY_PARAM.get(source_type)
        if not param:
            log_error(f"Unknown AniZip source type: {source_type}")
            return None

        # Ensure IMDB IDs have the tt prefix
        if source_type == 'imdb' and not str(id_value).startswith('tt'):
            id_value = f"tt{str(id_value).zfill(7)}"

        try:
            response = requests.get(
                self.ANIZIP_API_URL,
                params={param: id_value},
                timeout=self.timeout
            )
            if response.status_code == 200:
                return response.json().get('mappings')
            log_debug(f"AniZip status {response.status_code} for {source_type}={id_value}")
        except Exception as e:
            log_error(f"AniZip API request failed ({source_type}={id_value})", e)
        return None

    def get_absolute_episode_and_season(self, anilist_id, relative_episode, title=""):
        """
        Convert relative episode to absolute episode AND get real season number.

        HANDLES SPLIT-COUR: If title contains "Part 2", merges with Part 1.

        Args:
            anilist_id: AniList anime ID
            relative_episode: Season-relative episode number
            title: Anime title (CRITICAL for Part 2 detection!)

        Returns:
            dict: {
                'absolute_episode': int,
                'real_season': int,
                'offset': int,
                'is_split_cour': bool
            }
        """
        try:
            anilist_id = int(anilist_id)
            relative_episode = int(relative_episode)
        except (ValueError, TypeError):
            log_error(f"Invalid input: anilist_id={anilist_id}, relative_episode={relative_episode}")
            return {
                'absolute_episode': relative_episode,
                'real_season': 1,
                'offset': 0,
                'is_split_cour': False,
                'split_cour_offset': 0
            }

        log(f"Calculating absolute episode for AniList {anilist_id}, ep {relative_episode}")
        log(f"Title: {title}")

        # === CRITICAL: Detect if this is "Part 2" or "Cour 2" ===
        is_part_2 = self._detect_part_2(title)

        if is_part_2:
            log("SPLIT-COUR detected: this is Part 2 / Cour 2")

        result = self._calculate_api_offset_and_season(anilist_id, title, is_part_2)

        if result:
            absolute = result['offset'] + relative_episode
            log(f"API strategy: offset={result['offset']}, season={result['season']}, split-cour={result['is_split_cour']} -> ep {absolute}")
            return {
                'absolute_episode': absolute,
                'real_season': result['season'],
                'offset': result['offset'],
                'is_split_cour': result['is_split_cour'],
                'split_cour_offset': result.get('split_cour_offset', 0)
            }

        # Fallback: Regex parsing
        log("API strategy failed, trying regex fallback...")
        offset = self._calculate_regex_offset(title)
        absolute = offset + relative_episode
        log(f"Regex strategy: offset={offset} -> ep {absolute}")

        return {
            'absolute_episode': absolute,
            'real_season': 1,
            'offset': offset,
            'is_split_cour': False,
            'split_cour_offset': 0
        }

    def get_absolute_episode(self, anilist_id, relative_episode, title=""):
        """Backward compatibility method."""
        result = self.get_absolute_episode_and_season(anilist_id, relative_episode, title)
        return result['absolute_episode']

    def _detect_part_2(self, title):
        """
        Detect if title indicates "Part 2" or "Cour 2".

        Examples:
        - "Fire Force Season 3 Part 2" -> True
        - "Demon Slayer: Swordsmith Village Arc Part 2" -> True
        - "Attack on Titan Season 2" -> False (just season 2, not part 2)
        """
        if not title:
            return False

        title_lower = title.lower()

        for pattern in self.PART_2_PATTERNS:
            if re.search(pattern, title_lower):
                log(f"Part 2 pattern matched: '{pattern}'")
                return True

        return False

    def _calculate_api_offset_and_season(self, anilist_id, title, is_part_2=False):
        """
        Calculate episode offset AND real season number via AniList API.

        CRITICAL ENHANCEMENT: Handles split-cour anime.

        If is_part_2 == True:
        1. Find the immediate prequel (Part 1)
        2. DO NOT increment season count (Part 1 and Part 2 are same season!)
        3. ADD Part 1's episode count to offset
        4. Continue recursion from Part 1's prequels
        """
        cache_key = f"offset_season_{anilist_id}"
        if cache_key in self.cache:
            log_debug("Cache hit for offset+season calculation")
            return self.cache[cache_key]

        current_id = anilist_id
        total_offset = 0
        season_number = 1
        visited = set()
        is_split_cour = False
        split_cour_offset = 0

        query = '''
        query ($id: Int) {
          Media (id: $id, type: ANIME) {
            id
            title {
              romaji
              english
            }
            episodes
            season
            seasonYear
            relations {
              edges {
                relationType
                node {
                  id
                  title {
                    romaji
                    english
                  }
                  episodes
                  format
                  type
                  season
                  seasonYear
                }
              }
            }
          }
        }
        '''

        first_iteration = True

        for iteration in range(10):
            if current_id in visited:
                log_debug(f"Circular reference detected at {current_id}")
                break

            visited.add(current_id)
            log_debug(f"Iteration {iteration + 1}: querying AniList ID {current_id}")

            try:
                response = requests.post(
                    self.ANILIST_API_URL,
                    json={'query': query, 'variables': {'id': current_id}},
                    timeout=self.timeout
                )

                if response.status_code != 200:
                    log_error(f"AniList API returned status {response.status_code}")
                    break

                data = response.json()

                if 'errors' in data:
                    log_error(f"AniList API errors: {data['errors']}")
                    break

                media = data.get('data', {}).get('Media')
                if not media:
                    log_error("No Media data in AniList response")
                    break

                current_title = media.get('title', {}).get('romaji', 'Unknown')
                log_debug(f"Current anime: {current_title}")

                relations = media.get('relations', {}).get('edges', [])
                prequel_found = False

                for edge in relations:
                    if edge.get('relationType') == 'PREQUEL':
                        prequel = edge.get('node', {})
                        prequel_id = prequel.get('id')
                        prequel_episodes = prequel.get('episodes')
                        prequel_format = prequel.get('format')
                        prequel_type = prequel.get('type')
                        prequel_title = prequel.get('title', {}).get('romaji', 'Unknown')

                        if not prequel_id:
                            log_debug("Prequel has no ID")
                            continue

                        if prequel_type != 'ANIME':
                            log_debug(f"Prequel {prequel_id} is not ANIME type")
                            continue

                        if prequel_format in ['MOVIE', 'SPECIAL', 'OVA', 'ONA']:
                            log_debug(f"Prequel {prequel_id} is {prequel_format}, skipping")
                            continue

                        if not prequel_episodes or prequel_episodes <= 0:
                            log_debug(f"Prequel {prequel_id} has no episodes")
                            continue

                        # === CRITICAL SPLIT-COUR LOGIC ===
                        if first_iteration and is_part_2:
                            log(f"SPLIT-COUR: Part 1 is '{prequel_title}' ({prequel_episodes} eps)")
                            log("MERGING: Part 1 and Part 2 are the same season")

                            total_offset += prequel_episodes
                            split_cour_offset = prequel_episodes
                            is_split_cour = True
                            current_id = prequel_id
                            prequel_found = True
                            first_iteration = False
                            break

                        else:
                            log(f"Found prequel: '{prequel_title}' ({prequel_episodes} eps)")
                            total_offset += prequel_episodes
                            season_number += 1
                            current_id = prequel_id
                            prequel_found = True
                            first_iteration = False
                            break

                if not prequel_found:
                    log("Reached beginning of series (no more prequels)")
                    break

            except requests.RequestException as e:
                log_error("AniList API request failed", e)
                return None
            except Exception as e:
                log_error("Unexpected error in API offset calculation", e)
                break

        result = {
            'offset': total_offset,
            'season': season_number,
            'is_split_cour': is_split_cour,
            'split_cour_offset': split_cour_offset
        }

        log(f"Total offset: {total_offset} eps, season: {season_number}, split-cour: {is_split_cour}")
        if is_split_cour:
            log(f"Split-cour Part 1 offset: {split_cour_offset} eps")

        self.cache[cache_key] = result
        return result

    def _calculate_regex_offset(self, title):
        """
        Calculate offset by parsing title for "Part X", "Season X", "Cour X".

        Assumes 12 episodes per part (standard anime cour length).
        """
        if not title:
            return 0

        title_lower = title.lower()

        patterns = [
            r'part\s*(\d+)',
            r'season\s*(\d+)',
            r'cour\s*(\d+)',
            r's(\d+)',
            r'(\d+)(st|nd|rd|th)\s*(season|part|cour)',
        ]

        for pattern in patterns:
            match = re.search(pattern, title_lower)
            if match:
                try:
                    part_number = int(match.group(1))
                    if part_number > 1:
                        offset = (part_number - 1) * 12
                        log(f"Regex found: Part {part_number} -> offset={offset}")
                        return offset
                except (ValueError, IndexError):
                    continue

        log_debug("No part/season indicators found in title")
        return 0

    # ========================================
    # ID CONVERSION METHODS
    # ========================================

    def convert_anilist_to_kitsu(self, anilist_id):
        """Convert AniList ID to Kitsu ID via AniZip."""
        cache_key = f"anilist_to_kitsu_{anilist_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        mappings = self._fetch_anizip_mappings('anilist', anilist_id)
        kitsu_id = self._extract_anizip_id(mappings, 'kitsu')

        if kitsu_id:
            log(f"AniList {anilist_id} -> Kitsu {kitsu_id}")
        self.cache[cache_key] = kitsu_id
        return kitsu_id

    def convert_anilist_to_imdb(self, anilist_id):
        """Convert AniList ID to IMDB ID via AniZip."""
        cache_key = f"anilist_to_imdb_{anilist_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        mappings = self._fetch_anizip_mappings('anilist', anilist_id)
        imdb_id = self._extract_anizip_id(mappings, 'imdb')

        if imdb_id:
            log(f"AniList {anilist_id} -> IMDB {imdb_id}")
        self.cache[cache_key] = imdb_id
        return imdb_id

    def convert_anilist_to_mal(self, anilist_id):
        """Convert AniList ID to MAL ID via AniZip."""
        cache_key = f"anilist_to_mal_{anilist_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        mappings = self._fetch_anizip_mappings('anilist', anilist_id)
        mal_id = self._extract_anizip_id(mappings, 'mal')

        if mal_id:
            log(f"AniList {anilist_id} -> MAL {mal_id}")
        self.cache[cache_key] = mal_id
        return mal_id

    # ========================================
    # REVERSE ID CONVERSION
    # ========================================

    def convert_imdb_to_anilist(self, imdb_id):
        """Convert IMDB ID to AniList ID via AniZip."""
        cache_key = f"imdb_to_anilist_{imdb_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        log(f"Converting IMDB -> AniList: {imdb_id}")
        mappings = self._fetch_anizip_mappings('imdb', imdb_id)
        anilist_id = self._extract_anizip_id(mappings, 'anilist')

        if anilist_id:
            log(f"IMDB {imdb_id} -> AniList {anilist_id}")
        self.cache[cache_key] = anilist_id
        return anilist_id

    def convert_tmdb_to_anilist(self, tmdb_id):
        """Convert TMDB ID to AniList ID via AniZip."""
        cache_key = f"tmdb_to_anilist_{tmdb_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        log(f"Converting TMDB -> AniList: {tmdb_id}")
        mappings = self._fetch_anizip_mappings('tmdb', tmdb_id)
        anilist_id = self._extract_anizip_id(mappings, 'anilist')

        if anilist_id:
            log(f"TMDB {tmdb_id} -> AniList {anilist_id}")
        self.cache[cache_key] = anilist_id
        return anilist_id

    def convert_tvdb_to_anilist(self, tvdb_id):
        """Convert TVDB ID to AniList ID via AniZip."""
        cache_key = f"tvdb_to_anilist_{tvdb_id}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        log(f"Converting TVDB -> AniList: {tvdb_id}")
        mappings = self._fetch_anizip_mappings('tvdb', tvdb_id)
        anilist_id = self._extract_anizip_id(mappings, 'anilist')

        if anilist_id:
            log(f"TVDB {tvdb_id} -> AniList {anilist_id}")
        self.cache[cache_key] = anilist_id
        return anilist_id

    def auto_detect_and_convert_anime(self, params):
        """
        AUTO-CONVERT: Try IMDB/TMDB/TVDB -> AniList -> derive Kitsu & MAL.

        CRITICAL FIX: Use _is_valid_id to properly detect missing anime IDs

        Returns params dict with anime IDs added if successful.
        """
        anilist_id = params.get('anilist_id', '')
        mal_id = params.get('mal_id', '')
        kitsu_id = params.get('kitsu_id', '')

        has_valid_anime_id = (
            self._is_valid_id(anilist_id) or
            self._is_valid_id(mal_id) or
            self._is_valid_id(kitsu_id)
        )

        if has_valid_anime_id:
            log("Already have valid anime IDs - no conversion needed")
            return params

        log("No valid anime IDs found - attempting auto-conversion via AniZip...")

        # Try each available standard ID in priority order.
        # AniZip returns ALL mappings in one call, so we get anilist + kitsu + mal together.
        mappings = None

        imdb_id = params.get('imdb_id', '')
        if self._is_valid_id(imdb_id):
            log(f"Querying AniZip with IMDB {imdb_id}...")
            mappings = self._fetch_anizip_mappings('imdb', imdb_id)

        if not mappings:
            tmdb_id = params.get('tmdb_id', '')
            if self._is_valid_id(tmdb_id):
                log(f"Querying AniZip with TMDB {tmdb_id}...")
                mappings = self._fetch_anizip_mappings('tmdb', tmdb_id)

        if not mappings:
            tvdb_id = params.get('tvdb_id', '')
            if self._is_valid_id(tvdb_id):
                log(f"Querying AniZip with TVDB {tvdb_id}...")
                mappings = self._fetch_anizip_mappings('tvdb', tvdb_id)

        if not mappings:
            log("Auto-conversion failed - no mapping found in AniZip")
            return params

        converted_anilist = self._extract_anizip_id(mappings, 'anilist')
        if not converted_anilist:
            log("AniZip response has no AniList ID")
            return params

        params['anilist_id'] = str(converted_anilist)
        log(f"Auto-converted AniList ID: {converted_anilist}")

        converted_kitsu = self._extract_anizip_id(mappings, 'kitsu')
        if converted_kitsu:
            params['kitsu_id'] = str(converted_kitsu)
            log(f"Derived Kitsu ID: {converted_kitsu}")

        converted_mal = self._extract_anizip_id(mappings, 'mal')
        if converted_mal:
            params['mal_id'] = str(converted_mal)
            log(f"Derived MAL ID: {converted_mal}")

        return params

    def get_search_id_for_addon(self, params, preferred_id_type):
        """
        Get search ID in user's preferred format.

        Args:
            params: Metadata parameters
            preferred_id_type: 'anilist', 'kitsu', 'imdb', or 'mal'

        Returns:
            Tuple: (search_id, id_type)
        """
        anilist_id = params.get('anilist_id', '').strip()
        kitsu_id = params.get('kitsu_id', '').strip()
        imdb_id = params.get('imdb_id', '').strip()
        mal_id = params.get('mal_id', '').strip()

        log(f"Getting search ID in format: {preferred_id_type.upper()}")

        # === ANILIST ===
        if preferred_id_type == 'anilist':
            if anilist_id:
                log(f"Using AniList ID: {anilist_id}")
                return anilist_id, 'anilist'
            elif imdb_id:
                log("No AniList ID, falling back to IMDB")
                return imdb_id, 'imdb'

        # === KITSU ===
        elif preferred_id_type == 'kitsu':
            if kitsu_id:
                log(f"Using Kitsu ID: {kitsu_id}")
                return f"kitsu:{kitsu_id}", 'kitsu'
            elif anilist_id:
                converted_kitsu = self.convert_anilist_to_kitsu(anilist_id)
                if converted_kitsu:
                    return f"kitsu:{converted_kitsu}", 'kitsu'
                else:
                    log("Kitsu conversion failed, falling back to AniList")
                    return anilist_id, 'anilist'

        # === IMDB ===
        elif preferred_id_type == 'imdb':
            if imdb_id:
                log(f"Using IMDB ID: {imdb_id}")
                return imdb_id, 'imdb'
            elif anilist_id:
                converted_imdb = self.convert_anilist_to_imdb(anilist_id)
                if converted_imdb:
                    return converted_imdb, 'imdb'
                else:
                    log("IMDB conversion failed, falling back to AniList")
                    return anilist_id, 'anilist'

        # === MAL ===
        elif preferred_id_type == 'mal':
            if mal_id:
                log(f"Using MAL ID: {mal_id}")
                return f"mal:{mal_id}", 'mal'
            elif anilist_id:
                converted_mal = self.convert_anilist_to_mal(anilist_id)
                if converted_mal:
                    return f"mal:{converted_mal}", 'mal'
                else:
                    log("MAL conversion failed, falling back to AniList")
                    return anilist_id, 'anilist'

        # === FALLBACK ===
        log("Preferred ID type not available, using fallback")
        if anilist_id:
            return anilist_id, 'anilist'
        elif imdb_id:
            return imdb_id, 'imdb'
        elif kitsu_id:
            return f"kitsu:{kitsu_id}", 'kitsu'
        elif mal_id:
            return f"mal:{mal_id}", 'mal'

        log_error("No anime IDs available!")
        return None, None

    def detect_content_type(self, params):
        """
        Detect if content is anime.

        CRITICAL FIX: Use _is_valid_id to properly check for valid anime IDs
        """
        anilist_id = params.get('anilist_id', '')
        mal_id = params.get('mal_id', '')
        kitsu_id = params.get('kitsu_id', '')

        has_anime_id = (
            self._is_valid_id(anilist_id) or
            self._is_valid_id(mal_id) or
            self._is_valid_id(kitsu_id)
        )

        if has_anime_id:
            log_debug("Content detected as anime (has valid anime IDs)")
            return True

        return False

    def resolve_to_search_id(self, params):
        """
        Resolve any ID to best search ID WITH AUTO-CONVERSION.

        NEW: If anime detected but no anime IDs, tries to convert!
        """
        params = self.auto_detect_and_convert_anime(params)

        anilist_id = params.get('anilist_id', '').strip()
        imdb_id = params.get('imdb_id', '').strip()
        tmdb_id = params.get('tmdb_id', '').strip()
        mal_id = params.get('mal_id', '').strip()
        kitsu_id = params.get('kitsu_id', '').strip()

        is_anime = self.detect_content_type(params)

        if is_anime:
            log("Anime content detected")

            if anilist_id:
                log(f"Using AniList ID: {anilist_id}")
                return anilist_id, 'anilist'

            if mal_id:
                log(f"Using MAL ID: {mal_id}")
                return mal_id, 'mal'

            if kitsu_id:
                log(f"Using Kitsu ID: {kitsu_id}")
                return kitsu_id, 'kitsu'

        if imdb_id and imdb_id.startswith('tt'):
            log(f"Using IMDB ID: {imdb_id}")
            return imdb_id, 'imdb'

        if tmdb_id:
            log(f"Using TMDB ID: tmdb:{tmdb_id}")
            return f"tmdb:{tmdb_id}", 'tmdb'

        log_error("No valid IDs provided")
        return None, None


class AnimeIDResolver(AnimeResolver):
    """Backward compatibility alias."""
    pass
