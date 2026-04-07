# -*- coding: utf-8 -*-
"""
EXAMPLE Provider Template

Copy this file to create your own provider!
File name MUST start with "provider_" (e.g., provider_mysite.py)

This provider will be auto-discovered by the registry.
"""

import re
from urllib.parse import urljoin, quote_plus
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
            print(f"🦊 [ExampleProvider] {msg}")

from .base_provider import BaseProvider


class ProviderExample(BaseProvider):
    """
    Example Provider - Replace with your site name
    
    This provider extracts UNRESOLVED embed URLs only.
    ResolveURL handles all stream resolution!
    """
    
    # STEP 1: Set search languages
    # Options: 'ar' (Arabic), 'en' (English), 'tr' (Turkish)
    SEARCH_LANGUAGES = ['en']  # Change this based on your site
    
    def __init__(self):
        """Initialize your provider"""
        super().__init__()
        
        # STEP 2: Set your site's base URL
        self.base_url = "https://www.example.com"
        
        # STEP 3: Set any custom headers (optional)
        self.session.headers.update({
            'Referer': self.base_url + '/'
        })
        
        self._log("Example Provider initialized", xbmc.LOGINFO)
    
    def get_name(self):
        """
        STEP 4: Return provider name for display
        
        This appears in the server selection dialog
        """
        return "Example"  # Change to your site name
    
    def get_audio_language(self):
        """
        STEP 5: Return audio language
        
        Options:
        - 'ar' = Arabic audio
        - 'en' = English subtitles
        - 'tr' = Turkish audio
        """
        return "en"  # Change based on your site
    
    def search_series(self, series_names):
        """
        STEP 6: Search for series using TMDB names
        
        Args:
            series_names (list): List of series names from TMDB
                                 Based on SEARCH_LANGUAGES
        
        Returns:
            list: Search results
                [
                    {
                        'series_url': 'https://example.com/series/show-name',
                        'series_title': 'Show Name'
                    },
                    ...
                ]
        
        IMPLEMENTATION OPTIONS:
        
        Option A: If your site has a search function:
        """
        
        self._log(f"Searching with {len(series_names)} names", xbmc.LOGINFO)
        
        results = []
        
        for name in series_names:
            # Skip if wrong language
            if self._is_arabic(name) and 'ar' not in self.SEARCH_LANGUAGES:
                continue
            
            # Build search URL
            search_url = f"{self.base_url}/search?q={quote_plus(name)}"
            
            try:
                response = self.session.get(search_url, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # CUSTOMIZE: Update selectors for your site
                items = soup.select('.search-result-item')
                
                for item in items:
                    link = item.select_one('a')
                    title_tag = item.select_one('.title')
                    
                    if not link or not title_tag:
                        continue
                    
                    series_url = urljoin(self.base_url, link.get('href', ''))
                    series_title = title_tag.text.strip()
                    
                    results.append({
                        'series_url': series_url,
                        'series_title': series_title
                    })
                
            except Exception as e:
                self._log(f"Search error for '{name}': {e}", xbmc.LOGERROR)
                continue
        
        self._log(f"Found {len(results)} results", xbmc.LOGINFO)
        return results
        
        """
        Option B: If your site uses predictable URLs (like Qrmzi):
        
        results = []
        
        for name in series_names:
            # Generate URL from series name
            clean_name = name.strip().replace(' ', '-').lower()
            series_url = f"{self.base_url}/series/{clean_name}/"
            
            results.append({
                'series_url': series_url,
                'series_title': name
            })
        
        return results
        """
    
    def get_episode_servers(self, series_url, season, episode):
        """
        STEP 7: Get UNRESOLVED embed URLs for episode
        
        THIS IS THE MOST IMPORTANT METHOD!
        
        Args:
            series_url (str): Series URL from search_series()
            season (int): Season number
            episode (int): Episode number
        
        Returns:
            list: Server options with UNRESOLVED embed URLs
                [
                    {
                        'embed_url': 'https://ok.ru/videoembed/...',  # REQUIRED
                        'referer': 'https://example.com/episode-page',  # REQUIRED
                        'server_name': 'Server 1',  # OPTIONAL
                        'quality': '1080p'  # OPTIONAL (can be empty)
                    },
                    ...
                ]
        
        CRITICAL:
        - Return UNRESOLVED URLs (embed URLs, iframe sources, etc.)
        - Do NOT try to resolve to final video URLs
        - ResolveURL will handle all resolution
        """
        
        self._log(f"Getting servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # STEP 7A: Build episode URL
        # CUSTOMIZE: Update based on your site's URL structure
        episode_url = f"{series_url}/season-{season}/episode-{episode}/"
        
        try:
            response = self.session.get(episode_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # STEP 7B: Extract embed URLs
            # CUSTOMIZE: Update selectors based on your site
            
            servers = []
            
            # Method 1: Find iframes
            iframes = soup.find_all('iframe')
            
            for idx, iframe in enumerate(iframes, 1):
                embed_url = iframe.get('src', '')
                
                if not embed_url:
                    continue
                
                # Make absolute URL
                if not embed_url.startswith('http'):
                    embed_url = urljoin(episode_url, embed_url)
                
                # STEP 7C: Unwrap if needed
                # If your site uses internal wrappers, unwrap them here
                real_embed_url = self._unwrap_if_needed(embed_url, episode_url)
                
                if real_embed_url:
                    servers.append({
                        'embed_url': real_embed_url,
                        'referer': episode_url,
                        'server_name': f'Server {idx}',
                        'quality': self._detect_quality_from_url(real_embed_url)
                    })
            
            # Method 2: Find embed URLs in JavaScript (if applicable)
            script_tags = soup.find_all('script')
            for script in script_tags:
                script_text = script.string or ''
                
                # Look for common video host patterns
                patterns = [
                    r'(https?://[^"\']+ok\.ru[^"\']+)',
                    r'(https?://[^"\']+uqload\.[^"\']+)',
                    r'(https?://[^"\']+doodstream\.[^"\']+)',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, script_text)
                    for match in matches:
                        if match not in [s['embed_url'] for s in servers]:
                            servers.append({
                                'embed_url': match,
                                'referer': episode_url,
                                'server_name': f'Server {len(servers) + 1}',
                                'quality': ''
                            })
            
            self._log(f"Found {len(servers)} servers", xbmc.LOGINFO)
            return servers
            
        except Exception as e:
            self._log(f"Error getting servers: {e}", xbmc.LOGERROR)
            return []
    
    # =========================================================================
    # HELPER METHODS (Optional - customize as needed)
    # =========================================================================
    
    def _unwrap_if_needed(self, embed_url, referer):
        """
        Unwrap internal URLs to get real video host
        
        Some sites use internal wrappers/redirects that need unwrapping.
        If your site does this, implement unwrapping here.
        
        Args:
            embed_url (str): Initial embed URL
            referer (str): Referer URL
        
        Returns:
            str: Real host URL or original URL
        """
        
        # Check if this is an internal wrapper
        if self.base_url in embed_url:
            # This is an internal URL - try to unwrap it
            self._log(f"Unwrapping internal URL: {embed_url[:60]}...", xbmc.LOGDEBUG)
            
            try:
                response = self.session.get(embed_url, headers={'Referer': referer}, timeout=10)
                
                # Look for nested iframe
                nested_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', response.text, re.IGNORECASE)
                
                if nested_match:
                    nested_url = nested_match.group(1)
                    
                    if not nested_url.startswith('http'):
                        nested_url = urljoin(embed_url, nested_url)
                    
                    self._log(f"Found nested URL: {nested_url[:60]}...", xbmc.LOGINFO)
                    return nested_url
                
            except Exception as e:
                self._log(f"Unwrap error: {e}", xbmc.LOGERROR)
        
        # Not a wrapper or unwrap failed - return original
        return embed_url
    
    def _detect_quality_from_url(self, url):
        """
        Try to detect quality from URL
        
        Returns empty string if can't detect
        """
        
        url_lower = url.lower()
        
        if '1080' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        
        return ''  # Unknown quality


# ============================================================================
# TESTING YOUR PROVIDER (Optional)
# ============================================================================

if __name__ == '__main__':
    """
    Quick test of your provider
    Run: python provider_example.py
    """
    
    provider = ProviderExample()
    
    # Test search
    print("\n=== Testing Search ===")
    results = provider.search_series(['Breaking Bad', 'Game of Thrones'])
    
    for result in results[:3]:
        print(f"Title: {result['series_title']}")
        print(f"URL: {result['series_url']}")
        print()
    
    # Test get servers (update with real series URL from above)
    if results:
        print("\n=== Testing Get Servers ===")
        servers = provider.get_episode_servers(results[0]['series_url'], season=1, episode=1)
        
        for server in servers[:3]:
            print(f"Server: {server['server_name']}")
            print(f"Embed URL: {server['embed_url'][:80]}...")
            print(f"Quality: {server.get('quality', 'Unknown')}")
            print()
