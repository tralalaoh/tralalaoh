# -*- coding: utf-8 -*-
"""
Qrmzi Provider (Arabic Audio - Turkish Content Specialist)
Uses cached Arabic names from EgyDead for Turkish content

Enhanced with regional context support
"""

import re
import unicodedata
from urllib.parse import urljoin
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
            print(f"[Qrmzi] {msg}")

from .base_provider import BaseProvider


class ProviderQrmzi(BaseProvider):
    """
    Qrmzi provider - Turkish content specialist
    
    Smart search for Turkish content:
    - Uses verified Arabic name from EgyDead cache
    - Falls back to TMDB Arabic names
    - URL generation based on Arabic name
    """
    
    SEARCH_LANGUAGES = ['ar']  # Arabic only
    CONTENT_REGIONS = ['TR']  # Turkish content only
    IS_REGIONAL_SPECIFIC = True
    
    def __init__(self):
        """Initialize Qrmzi provider"""
        super().__init__()
        
        self.base_url = "https://www.qrmzi.tv"
        self.session.headers.update({
            'Referer': self.base_url + '/'
        })
        
        self._log("Qrmzi Provider initialized (Turkish Content Specialist)", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "Qrmzi"
    
    def get_audio_language(self):
        """Get audio language"""
        return "ar"  # Arabic
    
    def search_series_with_context(self, context):
        """
        SMART SEARCH using EgyDead's cached Arabic name
        
        For Turkish content:
        1. Check if EgyDead found Arabic name
        2. Use that name for search
        3. Fallback to TMDB Arabic names
        """
        
        self._log(f"Searching with regional context - Region: {context.content_region}", xbmc.LOGINFO)
        
        # Only works for Turkish content
        if not context.is_turkish_content():
            self._log("Not Turkish content - Qrmzi skipping", xbmc.LOGINFO)
            return []
        
        # Check for verified Arabic name from EgyDead
        verified_ar = context.verified_names.get('egydead', {}).get('ar')
        
        if verified_ar:
            self._log(f"✓ Using verified Arabic name from EgyDead: {verified_ar}", xbmc.LOGINFO)
            
            # Generate URL and search
            results = self._search_by_arabic_name(verified_ar)
            
            if results:
                # Cache the name for future use
                self.cache_discovered_names(context, {'ar': verified_ar})
                return results
        
        # Fallback: Try TMDB Arabic names
        self._log("No verified name from EgyDead, trying TMDB Arabic names", xbmc.LOGINFO)
        
        ar_names = context.get_names_for_language('ar')
        
        for name in ar_names:
            results = self._search_by_arabic_name(name)
            if results:
                return results
        
        self._log("No results found", xbmc.LOGWARNING)
        return []
    
    def search_series(self, series_names):
        """
        Traditional search (backwards compatibility)
        """
        
        self._log(f"Generating Qrmzi URLs from {len(series_names)} names", xbmc.LOGINFO)
        
        results = []
        
        for name in series_names:
            if not self._is_arabic(name):
                continue
            
            result = self._search_by_arabic_name(name)
            if result:
                results.extend(result)
        
        return results
    
    def _search_by_arabic_name(self, arabic_name):
        """
        Search using Arabic name (URL generation)
        
        Args:
            arabic_name (str): Arabic series name
        
        Returns:
            list: Search results
        """
        
        # Generate series URL
        clean_name = arabic_name.strip().replace(' ', '-')
        series_url = f"{self.base_url}/series/{clean_name}/"
        
        self._log(f"Generated URL: {series_url[:60]}...", xbmc.LOGDEBUG)
        
        # Verify URL exists
        if self._verify_series_exists(series_url):
            return [{
                'series_url': series_url,
                'series_title': arabic_name
            }]
        
        return []
    
    def _verify_series_exists(self, series_url):
        """
        Quick check if series URL exists
        
        Args:
            series_url (str): Series URL to check
        
        Returns:
            bool: True if series exists
        """
        try:
            response = self.session.head(series_url, timeout=5, allow_redirects=True)
            return response.status_code == 200
        except:
            return False
    
    def get_episode_servers(self, series_url, season, episode):
        """Get UNRESOLVED embed URLs with unwrapping"""
        
        self._log(f"Getting servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Extract series name from URL
        series_name = series_url.rstrip('/').split('/')[-1]
        
        # Generate episode URLs
        potential_urls = [
            f"{self.base_url}/episode/مسلسل-{series_name}-الحلقة-{episode}/",
            f"{self.base_url}/episode/{series_name}-الحلقة-{episode}/"
        ]
        
        # Try each URL
        for url in potential_urls:
            servers = self._extract_servers_from_page(url)
            if servers:
                return servers
        
        self._log("No servers found", xbmc.LOGWARNING)
        return []
    
    def _extract_servers_from_page(self, page_url):
        """Extract embed URLs from episode page with unwrapping"""
        
        try:
            self._log(f"Checking: {page_url[:60]}...", xbmc.LOGDEBUG)
            
            response = self.session.get(page_url, timeout=5, allow_redirects=True)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find iframe embed
            embed = soup.select_one('.getEmbed iframe')
            
            if not embed:
                self._log("No iframe found", xbmc.LOGDEBUG)
                return []
            
            embed_url = embed.get('src', '')
            
            if not embed_url:
                self._log("Empty iframe src", xbmc.LOGDEBUG)
                return []
            
            # Make absolute URL
            if not embed_url.startswith('http'):
                embed_url = urljoin(self.base_url, embed_url)
            
            self._log(f"Found initial embed: {embed_url[:60]}...", xbmc.LOGINFO)
            
            # Unwrap to get real host
            real_embed_url = self._unwrap_qrmzi_url(embed_url, page_url)
            
            if not real_embed_url:
                self._log("Failed to unwrap", xbmc.LOGWARNING)
                return []
            
            return [{
                'embed_url': real_embed_url,
                'referer': page_url,
                'server_name': 'Qrmzi Stream',
                'quality': 'HD'
            }]
            
        except Exception as e:
            self._log(f"Error extracting servers: {e}", xbmc.LOGERROR)
            return []
    
    def _unwrap_qrmzi_url(self, embed_url, referer):
        """
        Unwrap Qrmzi embed URLs to get real video host
        
        Args:
            embed_url (str): Initial embed URL
            referer (str): Referer URL
        
        Returns:
            str: Real host URL or original URL
        """
        
        # Check if URL is a known wrapper
        wrappers = ['shadwo.pro', 'qrmzi.tv']
        
        is_wrapper = any(w in embed_url.lower() for w in wrappers)
        
        if not is_wrapper:
            self._log(f"URL is external host: {embed_url[:40]}", xbmc.LOGDEBUG)
            return embed_url
        
        # Try to unwrap
        self._log(f"Unwrapping wrapper: {embed_url[:60]}...", xbmc.LOGDEBUG)
        
        try:
            response = self.session.get(
                embed_url,
                headers={
                    'Referer': str(referer),
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                },
                timeout=10,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                self._log(f"Wrapper returned {response.status_code}", xbmc.LOGDEBUG)
                return embed_url
            
            # Decode as UTF-8
            html = response.content.decode('utf-8', errors='ignore')
            
            # Look for nested iframe
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            
            if iframe_match:
                nested_url = iframe_match.group(1)
                
                # Make absolute
                if not nested_url.startswith('http'):
                    nested_url = urljoin(embed_url, nested_url)
                
                # Skip javascript/about
                if not nested_url.startswith('javascript:') and not nested_url.startswith('about:'):
                    # Quote non-ASCII characters
                    try:
                        from urllib.parse import quote, urlparse, urlunparse
                        parsed = urlparse(nested_url)
                        
                        if not all(ord(c) < 128 for c in parsed.path):
                            safe_path = quote(parsed.path.encode('utf-8'), safe='/:')
                            nested_url = urlunparse(parsed._replace(path=safe_path))
                    except:
                        pass
                    
                    self._log(f"Found nested iframe: {nested_url[:60]}...", xbmc.LOGINFO)
                    return nested_url
            
            # Fallback: Look for common video hosts
            host_patterns = [
                r'(https?://[^"\s]+ok\.ru[^"\s]+)',
                r'(https?://[^"\s]+uqload\.[^"\s]+)',
                r'(https?://[^"\s]+doodstream\.[^"\s]+)',
                r'(https?://[^"\s]+streamtape\.[^"\s]+)',
            ]
            
            for pattern in host_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    host_url = match.group(1)
                    self._log(f"Found host via pattern: {host_url[:60]}...", xbmc.LOGINFO)
                    return host_url
            
            self._log("No nested URL found, using original", xbmc.LOGDEBUG)
            return embed_url
            
        except Exception as e:
            self._log(f"Unwrap error: {repr(e)}", xbmc.LOGDEBUG)
            return embed_url
