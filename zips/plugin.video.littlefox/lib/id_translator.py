# -*- coding: utf-8 -*-
"""
ID Translator - IMDb to TMDb
Handles translation of IMDb IDs to TMDb IDs for compatibility with other addons

Scenarios:
1. Direct translation: IMDb series ID â†' TMDb series ID
2. Episode handling: IMDb episode ID â†' Parent series IMDb ID â†' TMDb series ID
"""

import re
from bs4 import BeautifulSoup

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
            print(f"[IDTranslator] {msg}")


class IMDbToTMDbTranslator:
    """
    Translates IMDb IDs to TMDb IDs
    
    Handles two scenarios:
    1. Series: Direct translation via TMDb API
    2. Episodes: Scrape IMDb page to find parent series, then translate
    """
    
    def __init__(self, session, tmdb_api_key):
        """
        Initialize translator
        
        Args:
            session: Shared requests.Session object
            tmdb_api_key (str): TMDb API key
        """
        self.session = session
        self.tmdb_api_key = tmdb_api_key
        
        # Cache for translations (avoid repeated API calls)
        self._cache = {}
        
        self._log("IMDbâ†'TMDb Translator initialized", xbmc.LOGINFO)
    
    def translate(self, imdb_id):
        """
        Translate IMDb ID to TMDb ID
        
        This is the main entry point. Automatically detects if it's
        a series or episode and handles appropriately.
        
        Args:
            imdb_id (str): IMDb ID (e.g., 'tt1234567')
        
        Returns:
            int: TMDb ID or None if translation failed
        """
        
        if not imdb_id:
            self._log("Empty IMDb ID provided", xbmc.LOGWARNING)
            return None
        
        # Normalize IMDb ID
        imdb_id = self._normalize_imdb_id(imdb_id)
        
        if not imdb_id:
            self._log("Invalid IMDb ID format", xbmc.LOGERROR)
            return None
        
        self._log(f"Translating IMDb ID: {imdb_id}", xbmc.LOGINFO)
        
        # Check cache first
        if imdb_id in self._cache:
            self._log(f"Cache hit: {imdb_id} â†' {self._cache[imdb_id]}", xbmc.LOGDEBUG)
            return self._cache[imdb_id]
        
        # SCENARIO 1: Try direct translation (works for series)
        tmdb_id = self._direct_translation(imdb_id)
        
        if tmdb_id:
            # SUCCESS - Cache and return
            self._cache[imdb_id] = tmdb_id
            self._log(f"Direct translation: {imdb_id} â†' {tmdb_id}", xbmc.LOGINFO)
            return tmdb_id
        
        # SCENARIO 2: Might be an episode - try to find parent series
        self._log(f"Direct translation failed, trying episode resolution", xbmc.LOGINFO)
        
        parent_imdb_id = self._get_parent_series_imdb(imdb_id)
        
        if not parent_imdb_id:
            self._log(f"Failed to find parent series for {imdb_id}", xbmc.LOGERROR)
            return None
        
        self._log(f"Found parent series: {parent_imdb_id}", xbmc.LOGINFO)
        
        # Translate parent series
        tmdb_id = self._direct_translation(parent_imdb_id)
        
        if tmdb_id:
            # Cache BOTH the episode ID and parent ID
            self._cache[imdb_id] = tmdb_id  # Episode â†' TMDb
            self._cache[parent_imdb_id] = tmdb_id  # Parent â†' TMDb
            
            self._log(f"Episode translation: {imdb_id} â†' {parent_imdb_id} â†' {tmdb_id}", xbmc.LOGINFO)
            return tmdb_id
        
        # All attempts failed
        self._log(f"All translation attempts failed for {imdb_id}", xbmc.LOGERROR)
        return None
    
    # =========================================================================
    # SCENARIO 1: DIRECT TRANSLATION (Series)
    # =========================================================================
    
    def _direct_translation(self, imdb_id):
        """
        Direct translation using TMDb API /find endpoint
        
        This works for series IMDb IDs. Returns None for episode IDs.
        
        Args:
            imdb_id (str): Normalized IMDb ID (e.g., 'tt1234567')
        
        Returns:
            int: TMDb ID or None
        """
        
        try:
            # TMDb API: /find/{external_id}
            url = f"https://api.themoviedb.org/3/find/{imdb_id}"
            
            params = {
                'api_key': self.tmdb_api_key,
                'external_source': 'imdb_id'
            }
            
            self._log(f"Calling TMDb /find API for {imdb_id}", xbmc.LOGDEBUG)
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check tv_results (series)
            tv_results = data.get('tv_results', [])
            
            if tv_results:
                tmdb_id = tv_results[0].get('id')
                
                if tmdb_id:
                    self._log(f"Found TV series: {tmdb_id}", xbmc.LOGDEBUG)
                    return tmdb_id
            
            # Check tv_episode_results (this confirms it's an episode)
            episode_results = data.get('tv_episode_results', [])
            
            if episode_results:
                self._log(f"IMDb ID {imdb_id} is an episode, not a series", xbmc.LOGDEBUG)
                return None  # Signal to try parent series extraction
            
            # Check movie_results (just in case)
            movie_results = data.get('movie_results', [])
            
            if movie_results:
                self._log(f"IMDb ID {imdb_id} is a movie, not a series", xbmc.LOGWARNING)
                return None
            
            # Not found
            self._log(f"No results found for {imdb_id}", xbmc.LOGDEBUG)
            return None
        
        except Exception as e:
            self._log(f"Direct translation error: {e}", xbmc.LOGERROR)
            return None
    
    # =========================================================================
    # SCENARIO 2: EPISODE HANDLING (Find Parent Series)
    # =========================================================================
    
    def _get_parent_series_imdb(self, episode_imdb_id):
        """
        Get parent series IMDb ID from episode IMDb ID
        
        Strategy:
        1. Scrape IMDb episode page with BeautifulSoup
        2. Extract parent series link
        3. Return parent series IMDb ID
        
        Args:
            episode_imdb_id (str): Episode IMDb ID (e.g., 'tt1234567')
        
        Returns:
            str: Parent series IMDb ID or None
        """
        
        try:
            # Build IMDb URL
            imdb_url = f"https://www.imdb.com/title/{episode_imdb_id}/"
            
            self._log(f"Scraping IMDb page: {imdb_url}", xbmc.LOGDEBUG)
            
            # Request episode page
            response = self.session.get(
                imdb_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9'
                },
                timeout=10
            )
            
            response.raise_for_status()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # METHOD 1: Look for series link in hero section
            # Modern IMDb uses data-testid attributes
            series_link = soup.find('a', {'data-testid': 'hero-title-block__series-link'})
            
            if series_link and series_link.get('href'):
                href = series_link['href']
                match = re.search(r'/title/(tt\d+)', href)
                
                if match:
                    parent_imdb_id = match.group(1)
                    self._log(f"Found parent via hero link: {parent_imdb_id}", xbmc.LOGINFO)
                    return parent_imdb_id
            
            # METHOD 2: Look for all episodes link
            # Usually: <a href="/title/tt1234567/episodes">All Episodes</a>
            all_episodes_link = soup.find('a', href=re.compile(r'/title/(tt\d+)/episodes'))
            
            if all_episodes_link:
                href = all_episodes_link['href']
                match = re.search(r'/title/(tt\d+)', href)
                
                if match:
                    parent_imdb_id = match.group(1)
                    
                    # Make sure it's not the same as episode ID
                    if parent_imdb_id != episode_imdb_id:
                        self._log(f"Found parent via episodes link: {parent_imdb_id}", xbmc.LOGINFO)
                        return parent_imdb_id
            
            # METHOD 3: Look in breadcrumb navigation
            breadcrumb = soup.find('nav', {'aria-label': 'Breadcrumb'})
            
            if breadcrumb:
                # Find all links in breadcrumb
                for link in breadcrumb.find_all('a', href=True):
                    href = link['href']
                    match = re.search(r'/title/(tt\d+)', href)
                    
                    if match:
                        parent_imdb_id = match.group(1)
                        
                        # Make sure it's not the episode itself
                        if parent_imdb_id != episode_imdb_id:
                            self._log(f"Found parent via breadcrumb: {parent_imdb_id}", xbmc.LOGINFO)
                            return parent_imdb_id
            
            # METHOD 4: Look for JSON-LD structured data
            json_ld_scripts = soup.find_all('script', {'type': 'application/ld+json'})
            
            for script in json_ld_scripts:
                if script.string:
                    # Look for partOfSeries URL
                    match = re.search(r'"partOfSeries".*?"url"\s*:\s*"https://www\.imdb\.com/title/(tt\d+)', script.string, re.DOTALL)
                    
                    if match:
                        parent_imdb_id = match.group(1)
                        
                        if parent_imdb_id != episode_imdb_id:
                            self._log(f"Found parent via JSON-LD: {parent_imdb_id}", xbmc.LOGINFO)
                            return parent_imdb_id
            
            # No parent found
            self._log(f"Could not extract parent series from {episode_imdb_id}", xbmc.LOGWARNING)
            return None
        
        except Exception as e:
            self._log(f"Error extracting parent series: {e}", xbmc.LOGERROR)
            import traceback
            self._log(traceback.format_exc(), xbmc.LOGDEBUG)
            return None
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _normalize_imdb_id(self, imdb_id):
        """
        Normalize IMDb ID to standard format
        
        Accepts:
        - tt1234567
        - 1234567
        - https://www.imdb.com/title/tt1234567/
        
        Returns:
        - tt1234567 (normalized)
        
        Args:
            imdb_id (str): IMDb ID in any format
        
        Returns:
            str: Normalized IMDb ID or None if invalid
        """
        
        if not imdb_id:
            return None
        
        # Extract IMDb ID from URL
        if 'imdb.com' in imdb_id:
            match = re.search(r'tt\d+', imdb_id)
            if match:
                return match.group(0)
            return None
        
        # Remove whitespace
        imdb_id = str(imdb_id).strip()
        
        # If already has 'tt' prefix
        if imdb_id.startswith('tt'):
            # Validate format
            if re.match(r'^tt\d+$', imdb_id):
                return imdb_id
            return None
        
        # If just numbers, add 'tt' prefix
        if imdb_id.isdigit():
            return f'tt{imdb_id}'
        
        # Invalid format
        return None
    
    def clear_cache(self):
        """Clear translation cache"""
        self._cache.clear()
        self._log("Translation cache cleared", xbmc.LOGDEBUG)
    
    def _log(self, message, level=xbmc.LOGINFO):
        """Log message"""
        if KODI_ENV:
            xbmc.log(f"🦊 IDTranslator: {message}", level)
        else:
            print(f"[IDTranslator] {message}")


# =============================================================================
# TESTING (Optional)
# =============================================================================

if __name__ == '__main__':
    """
    Quick test of ID translator
    Run: python id_translator.py
    """
    
    import requests
    
    # Create session
    session = requests.Session()
    
    # TMDb API key
    api_key = "c8578981f94591042c8a9b9837571314"
    
    # Initialize translator
    translator = IMDbToTMDbTranslator(session, api_key)
    
    print("\n=== Testing ID Translator ===\n")
    
    # TEST 1: Direct series translation
    print("TEST 1: Direct series translation")
    print("-" * 50)
    series_imdb = "tt5523010"  # Veliaht (The Heir)
    tmdb_id = translator.translate(series_imdb)
    print(f"IMDb: {series_imdb} â†' TMDb: {tmdb_id}")
    print()
    
    # TEST 2: Various formats
    print("TEST 2: Various formats")
    print("-" * 50)
    test_ids = [
        "tt5523010",
        "5523010",
        "https://www.imdb.com/title/tt5523010/",
    ]
    
    for test_id in test_ids:
        tmdb_id = translator.translate(test_id)
        print(f"Input: '{test_id}' â†' TMDb: {tmdb_id}")
    print()
    
    # TEST 3: Cache test
    print("TEST 3: Cache test (should be instant)")
    print("-" * 50)
    import time
    start = time.time()
    tmdb_id = translator.translate(series_imdb)
    elapsed = time.time() - start
    print(f"Cached: {series_imdb} â†' TMDb: {tmdb_id} ({elapsed:.4f}s)")
    print()
    
    print("Cache contents:", translator._cache)
