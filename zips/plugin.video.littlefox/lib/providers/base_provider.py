# -*- coding: utf-8 -*-
"""
Base Provider Abstract Class
Defines interface for all streaming providers
"""

from abc import ABC, abstractmethod
import requests

try:
    import xbmc
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
            print(f"[Provider] {msg}")


class BaseProvider(ABC):
    """
    Abstract base class for streaming providers
    
    Providers only handle:
    1. Searching for series
    2. Finding episode pages
    3. Extracting UNRESOLVED embed URLs
    
    ResolveURL handles all stream resolution!
    """
    
    # Must be set by child class
    SEARCH_LANGUAGES = []  # e.g., ['ar'] or ['en', 'tr']
    
    # Regional configuration
    CONTENT_REGIONS = []  # e.g., ['TR', 'AR'] or [] for all regions
    IS_REGIONAL_SPECIFIC = False  # True if provider only works for specific regions
    
    # Priority order for search names
    SEARCH_PRIORITY = ['original', 'ar', 'en', 'tr']
    
    def __init__(self):
        """Initialize provider"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        })
        
        # TMDB API key - set by provider registry from addon settings
        self.tmdb_api_key = ""
    
    @abstractmethod
    def get_name(self):
        """
        Get provider name for display
        
        Returns:
            str: Provider name (e.g., '3SK', 'Qrmzi', 'Turkish123')
        """
        pass
    
    @abstractmethod
    def get_audio_language(self):
        """
        Get audio language provided by this provider
        
        Returns:
            str: Language code ('ar', 'en', 'tr')
        """
        pass
    
    @abstractmethod
    def search_series(self, series_names):
        """
        Search for series using multiple name variants
        
        Args:
            series_names (list): List of series names to try
        
        Returns:
            list: Search results
                [
                    {
                        'series_url': 'https://...',
                        'series_title': 'Series Name'
                    },
                    ...
                ]
        """
        pass
    
    def search_series_with_context(self, context):
        """
        NEW: Search with RegionalSearchContext (optional override)
        
        SMART DEFAULT: Automatically uses cached Arabic names for Turkish content
        
        Providers can override this for even smarter regional search.
        Default implementation uses traditional search_series().
        
        Args:
            context (RegionalSearchContext): Regional search context
        
        Returns:
            list: Search results
        """
        
        # SMART CACHE: For Arabic providers on Turkish content
        # Automatically use Arabic name discovered by EgyDead
        if 'ar' in self.SEARCH_LANGUAGES and context.is_turkish_content():
            # Check if EgyDead (or any provider) found verified Arabic name
            verified_ar = None
            
            # Priority 1: EgyDead's discovery
            if 'egydead' in context.verified_names:
                verified_ar = context.verified_names['egydead'].get('ar')
            
            # Priority 2: Any cached Arabic name
            if not verified_ar:
                for provider_name, names_dict in context.name_cache.items():
                    if 'ar' in names_dict:
                        verified_ar = names_dict['ar']
                        break
            
            # Use verified name if available
            if verified_ar:
                self._log(f"✓ Using cached Arabic name for Turkish content: {verified_ar}", xbmc.LOGINFO)
                
                # Try cached name first
                try:
                    cached_results = self.search_series([verified_ar])
                    if cached_results:
                        self._log(f"✓ Found using cached Arabic name", xbmc.LOGINFO)
                        return cached_results
                except Exception as e:
                    self._log(f"Cached name search failed: {e}", xbmc.LOGDEBUG)
                    # Continue to fallback
        
        # FALLBACK: Get prioritized names for this provider
        names = context.get_search_names_prioritized(self.SEARCH_LANGUAGES)
        
        # Use traditional search
        return self.search_series(names)
    
    def supports_region(self, region):
        """
        Check if provider supports content from specific region
        
        Args:
            region (str): Region code (TR, AR, US, etc.)
        
        Returns:
            bool: True if provider supports this region
        """
        # If no specific regions defined, supports all
        if not self.CONTENT_REGIONS:
            return True
        
        # Check if region in supported list
        return region in self.CONTENT_REGIONS
    
    def cache_discovered_names(self, context, names_dict):
        """
        Cache names discovered during search
        
        Args:
            context (RegionalSearchContext): Context to update
            names_dict (dict): {'ar': 'name', 'en': 'name', etc.}
        """
        provider_name = self.get_name()
        context.cache_provider_names(provider_name, names_dict)
    
    @abstractmethod
    def get_episode_servers(self, series_url, season, episode):
        """
        Get UNRESOLVED embed URLs for episode
        
        This is the KEY change - providers NO LONGER resolve streams!
        They only extract embed URLs (iframes, etc.)
        
        Args:
            series_url (str): Series URL from search_series()
            season (int): Season number
            episode (int): Episode number
        
        Returns:
            list: Server options with UNRESOLVED URLs
                [
                    {
                        'embed_url': 'https://ok.ru/videoembed/...',
                        'referer': 'https://provider.com/episode-page',
                        'server_name': 'Server 1',
                        'quality': '1080p'  # OPTIONAL - can be empty
                    },
                    ...
                ]
        """
        pass
    
    # =========================================================================
    # BUILT-IN HELPER METHODS
    # =========================================================================
    
    def get_tmdb_names(self, tmdb_id):
        """
        Fetch series names from TMDB for configured search languages
        
        Uses SEARCH_LANGUAGES to determine which names to fetch
        
        Args:
            tmdb_id (int): TMDB series ID
        
        Returns:
            list: Series names in priority order
        """
        
        if not self.SEARCH_LANGUAGES:
            self._log("WARNING: SEARCH_LANGUAGES not set!", xbmc.LOGWARNING)
            return []
        
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
        
        try:
            response = self.session.get(url, params={
                'api_key': self.tmdb_api_key,
                'append_to_response': 'alternative_titles,translations'
            }, timeout=10)
            
            response.raise_for_status()
            data = response.json()
            
        except Exception as e:
            self._log(f"TMDB API error: {e}", xbmc.LOGERROR)
            return []
        
        names = []
        
        # Original name (always include)
        if data.get('original_name'):
            names.append(data['original_name'])
        
        # Primary name
        if data.get('name') and data['name'] != data.get('original_name'):
            names.append(data['name'])
        
        # Translations for configured languages
        translations = data.get('translations', {}).get('translations', [])
        
        for lang in self.SEARCH_LANGUAGES:
            for trans in translations:
                if trans.get('iso_639_1') == lang:
                    trans_name = trans.get('data', {}).get('name', '')
                    if trans_name and trans_name not in names:
                        names.append(trans_name)
        
        # Alternative titles
        for alt in data.get('alternative_titles', {}).get('results', []):
            title = alt.get('title', '')
            if title and title not in names:
                # Filter by language if possible
                if not self.SEARCH_LANGUAGES or not alt.get('iso_3166_1'):
                    names.append(title)
        
        self._log(f"Got {len(names)} name variants for TMDB {tmdb_id}", xbmc.LOGINFO)
        
        return names
    
    def get_tmdb_original_name(self, tmdb_id):
        """
        Get TMDB original name for verification purposes
        
        Args:
            tmdb_id (int): TMDB series ID
        
        Returns:
            str: Original name or None
        """
        
        url = f"https://api.themoviedb.org/3/tv/{tmdb_id}"
        
        try:
            response = self.session.get(url, params={
                'api_key': self.tmdb_api_key
            }, timeout=10)
            
            response.raise_for_status()
            data = response.json()
            
            return data.get('original_name')
            
        except Exception as e:
            self._log(f"TMDB API error: {e}", xbmc.LOGERROR)
            return None
    
    def _is_arabic(self, text):
        """
        Check if text contains Arabic characters
        
        Args:
            text (str): Text to check
        
        Returns:
            bool: True if Arabic text detected
        """
        if not text:
            return False
        return any('\u0600' <= c <= '\u06FF' or '\u0750' <= c <= '\u077F' for c in text)
    
    def _log(self, message, level=xbmc.LOGINFO):
        """
        Log message
        
        Args:
            message (str): Message to log
            level: Log level
        """
        provider_name = self.__class__.__name__
        
        if KODI_ENV:
            xbmc.log(f"{provider_name}: {message}", level)
        else:
            print(f"[{provider_name}] {message}")
