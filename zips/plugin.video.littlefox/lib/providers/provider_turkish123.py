# -*- coding: utf-8 -*-
"""
Turkish123 Provider (English Subtitles)
Simplified version - only extracts embed URLs, NO resolution
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
            print(f"[Turkish123] {msg}")

from .base_provider import BaseProvider


class ProviderTurkish123(BaseProvider):
    """
    Turkish123 provider - extracts embed URLs only
    
    KEY CHANGE: NO resolution logic - just returns embed URLs!
    
    Regional Support: Turkish content only (English subtitles)
    """
    
    SEARCH_LANGUAGES = ['en', 'tr']  # English and Turkish
    CONTENT_REGIONS = ['TR']  # Turkish content only
    IS_REGIONAL_SPECIFIC = True  # Region-specific provider
    
    def __init__(self):
        """Initialize Turkish123 provider"""
        super().__init__()
        
        self.base_url = "https://www2.turkish123.org"
        
        self.session.headers.update({
            'Referer': self.base_url + '/'
        })
        
        self._log("Turkish123 Provider initialized (embed extraction only)", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "Turkish123"
    
    def get_audio_language(self):
        """Get audio language"""
        return "en"  # English subtitles
    
    def search_series(self, series_names):
        """
        Search Turkish123 for series
        """
        
        self._log(f"Searching Turkish123 with {len(series_names)} names", xbmc.LOGINFO)
        
        for name in series_names:
            # Skip Arabic names
            if self._is_arabic(name):
                continue
            
            # Normalize name
            query = self._normalize_for_search(name)
            if not query:
                continue
            
            self._log(f"Searching for: {query}", xbmc.LOGINFO)
            
            search_url = f"{self.base_url}/?s={quote_plus(query)}"
            
            response = self._request(search_url)
            if not response:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select("div.ml-item")
            
            self._log(f"Found {len(items)} search results", xbmc.LOGINFO)
            
            for item in items:
                link_tag = item.select_one("a")
                title_tag = item.select_one("h2")
                
                if not link_tag or not title_tag:
                    continue
                
                found_title = self._normalize_for_search(title_tag.text.strip())
                
                if query in found_title:
                    series_url = urljoin(self.base_url, link_tag.get('href', ''))
                    self._log(f"Found match: {title_tag.text.strip()}", xbmc.LOGINFO)
                    
                    return [{
                        'series_url': series_url,
                        'series_title': title_tag.text.strip()
                    }]
        
        self._log("No matching series found", xbmc.LOGWARNING)
        return []
    
    def get_episode_servers(self, series_url, season, episode):
        """
        Get UNRESOLVED embed URLs for episode
        
        Turkish123 uses direct episode URLs:
        https://www2.turkish123.org/series-slug-episode-N/
        """
        
        self._log(f"Getting Turkish123 servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Extract series slug from URL
        slug = series_url.rstrip('/').split('/')[-1]
        
        # Build episode URL
        episode_url = f"{self.base_url}/{slug}-episode-{episode}/"
        
        self._log(f"Episode URL: {episode_url}", xbmc.LOGINFO)
        
        # Extract servers from episode page
        servers = self._extract_servers_from_episode(episode_url)
        
        self._log(f"Found {len(servers)} servers on Turkish123", xbmc.LOGINFO)
        
        return servers
    
    def _extract_servers_from_episode(self, episode_url):
        """
        Extract ALL embed URLs from episode page
        
        IMPORTANT: Unwraps wrapper URLs to get real hosts
        """
        
        response = self._request(episode_url)
        if not response:
            return []
        
        html = response.text
        
        # Find embed URLs using patterns
        embed_patterns = [
            r'https://tukipasti\.[^\s\'"]+',
            r'https://dwish\.[^\s\'"]+',
        ]
        
        embed_urls = []
        for pattern in embed_patterns:
            matches = re.findall(pattern, html)
            embed_urls.extend(matches)
        
        # Also look for iframe sources
        iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        embed_urls.extend(iframe_matches)
        
        if not embed_urls:
            self._log("No embed URLs found on episode page", xbmc.LOGWARNING)
            return []
        
        # Remove duplicates
        unique_embeds = list(set(embed_urls))
        
        self._log(f"Found {len(unique_embeds)} unique embed URLs", xbmc.LOGINFO)
        
        # Build server list with unwrapping
        servers = []
        
        for idx, embed_url in enumerate(unique_embeds, 1):
            # Make absolute URL
            if not embed_url.startswith('http'):
                embed_url = urljoin(episode_url, embed_url)
            
            # Unwrap to get real host
            real_embed_url = self._unwrap_turkish123_url(embed_url, episode_url)
            
            if not real_embed_url:
                self._log(f"Server {idx}: Failed to unwrap, skipping", xbmc.LOGDEBUG)
                continue
            
            # Try to detect quality
            quality = self._detect_quality(real_embed_url)
            
            servers.append({
                'embed_url': real_embed_url,
                'referer': episode_url,
                'server_name': f'Server {idx}',
                'quality': quality  # May be empty
            })
        
        return servers
    
    def _unwrap_turkish123_url(self, embed_url, referer):
        """
        Unwrap Turkish123 embed URLs to get real video host
        
        Turkish123 uses wrappers like tukipasti, dwish that need unwrapping
        
        Args:
            embed_url (str): Initial embed URL
            referer (str): Referer URL
        
        Returns:
            str: Real host URL or None
        """
        
        # Check if URL is a known wrapper
        wrappers = ['tukipasti', 'dwish', 'turkish123']
        
        is_wrapper = any(w in embed_url.lower() for w in wrappers)
        
        if not is_wrapper:
            # Already a known host
            self._log(f"URL is external host: {embed_url[:40]}", xbmc.LOGDEBUG)
            return embed_url
        
        # Try to unwrap
        self._log(f"Unwrapping wrapper URL: {embed_url[:60]}...", xbmc.LOGDEBUG)
        
        try:
            response = self.session.get(
                embed_url,
                headers={'Referer': referer},
                timeout=5,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                self._log(f"Wrapper returned {response.status_code}", xbmc.LOGDEBUG)
                return None
            
            html = response.text
            
            # Look for nested iframe
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            
            if iframe_match:
                nested_url = iframe_match.group(1)
                
                # Make absolute
                if not nested_url.startswith('http'):
                    nested_url = urljoin(embed_url, nested_url)
                
                # Skip javascript/about
                if not nested_url.startswith('javascript:') and not nested_url.startswith('about:'):
                    self._log(f"Found nested iframe: {nested_url[:60]}...", xbmc.LOGINFO)
                    return nested_url
            
            # Fallback: Look for common video hosts
            host_patterns = [
                r'(https?://[^"\s]+ok\.ru[^"\s]+)',
                r'(https?://[^"\s]+uqload\.[^"\s]+)',
                r'(https?://[^"\s]+doodstream\.[^"\s]+)',
                r'(https?://[^"\s]+streamtape\.[^"\s]+)',
                r'(https?://[^"\s]+\.m3u8[^"\s]*)',
            ]
            
            for pattern in host_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    host_url = match.group(1)
                    self._log(f"Found host via pattern: {host_url[:60]}...", xbmc.LOGINFO)
                    return host_url
            
            # No host found
            self._log("No host URL found in wrapper", xbmc.LOGWARNING)
            return None
            
        except Exception as e:
            self._log(f"Unwrap error: {e}", xbmc.LOGERROR)
            return None
    
    def _detect_quality(self, embed_url):
        """
        Try to detect quality from URL
        
        Returns empty string if can't detect
        """
        
        url_lower = embed_url.lower()
        
        if '1080' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        
        return ''  # Unknown quality
    
    def _normalize_for_search(self, text):
        """Normalize Turkish text for searching"""
        if not text:
            return ""
        
        text = text.lower()
        
        # Turkish character replacements
        replacements = {
            'ç': 'c', 'ğ': 'g', 'ı': 'i',
            'ö': 'o', 'ş': 's', 'ü': 'u'
        }
        
        for tr_char, en_char in replacements.items():
            text = text.replace(tr_char, en_char)
        
        # Remove special characters
        text = re.sub(r'[^a-z0-9\s]', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def _request(self, url):
        """Make HTTP request"""
        if not url.startswith('http'):
            url = urljoin(self.base_url, url)
        
        try:
            self._log(f"Request: {url[:100]}...", xbmc.LOGDEBUG)
            response = self.session.get(url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            return response
        except Exception as e:
            self._log(f"Request failed: {e}", xbmc.LOGERROR)
            return None
