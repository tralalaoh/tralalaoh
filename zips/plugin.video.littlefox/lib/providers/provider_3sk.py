# -*- coding: utf-8 -*-
"""
3SK Provider (Arabic Audio)
Simplified version - only extracts embed URLs, NO resolution
"""

import re
import urllib.parse
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
            print(f"[3SK] {msg}")

from .base_provider import BaseProvider


# Configuration from working 3SK addon
SITE_CONFIG = {
    "DOMAINS": [
        "https://esheaq.onl",
        "https://x.esheaq.onl",
        "https://3sk.media",
        "https://u.3sk.media"
    ],
    "SELECTORS": {
        "series_container": "article.postEp",
        "series_title": "div.title",
        "series_url": "a",
        "episode_list_container": "#epiList",
        "episode_item": "article.postEp",
        "episode_num": "div.episodeNum span:nth-of-type(2)",
        "episode_link": "a",
        "server_list": "ul.serversList li",
        "server_attr": "data-src"
    }
}


class Provider3SK(BaseProvider):
    """
    3SK provider - extracts embed URLs only
    
    KEY CHANGE: NO resolution logic - just returns embed URLs!
    
    Regional Support: Multi-regional (Turkish, Arabic, and other content)
    """
    
    SEARCH_LANGUAGES = ['ar']  # Arabic only
    CONTENT_REGIONS = []  # Supports all regions (multi-regional)
    IS_REGIONAL_SPECIFIC = False  # Works for any region
    
    def __init__(self):
        """Initialize 3SK provider"""
        super().__init__()
        
        # Find active domain
        self.base_url = self._find_active_domain()
        
        self.session.headers.update({
            'Referer': 'https://google.com/'
        })
        
        self._log(f"3SK Provider initialized: {self.base_url}", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "3SK"
    
    def get_audio_language(self):
        """Get audio language"""
        return "ar"  # Arabic
    
    def search_series(self, series_names):
        """
        Search 3SK for series
        """
        
        self._log(f"Searching 3SK with {len(series_names)} names", xbmc.LOGINFO)
        
        all_results = []
        
        for name in series_names:
            if not self._is_arabic(name):
                continue
            
            self._log(f"Searching for: {name[:30]}...", xbmc.LOGINFO)
            
            search_url = f"{self.base_url}/?s={urllib.parse.quote(name)}"
            
            response = self._request(search_url)
            if not response:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.select('article.post')[:5]  # Limit to first 5
            
            for article in articles:
                try:
                    link = article.find('a')
                    if not link:
                        continue
                    
                    series_url = self._fix_url(link.get('href', ''))
                    if not series_url:
                        continue
                    
                    # Get title
                    title_div = article.select_one('.title')
                    title = title_div.text.strip() if title_div else "Unknown"
                    
                    all_results.append({
                        'series_url': series_url,
                        'series_title': title
                    })
                    
                except Exception as e:
                    self._log(f"Error parsing result: {e}", xbmc.LOGERROR)
                    continue
        
        # Deduplicate by URL
        seen = set()
        unique_results = []
        for r in all_results:
            if r['series_url'] not in seen:
                seen.add(r['series_url'])
                unique_results.append(r)
        
        self._log(f"Found {len(unique_results)} unique series results", xbmc.LOGINFO)
        
        return unique_results
    
    def get_episode_servers(self, series_url, season, episode):
        """
        Get UNRESOLVED embed URLs for episode
        
        Strategy:
        1. Navigate to episode page
        2. Go to /see/ page
        3. Extract ALL server embed URLs
        4. Return unresolved URLs for ResolveURL
        """
        
        self._log(f"Getting 3SK servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Get episode page
        episode_url = self._find_episode_url(series_url, season, episode)
        
        if not episode_url:
            self._log("Episode not found", xbmc.LOGWARNING)
            return []
        
        # Build /see/ URL
        see_url = episode_url.rstrip('/') + '/see/'
        
        # Extract servers from /see/ page
        servers = self._extract_servers_from_see_page(see_url)
        
        self._log(f"Found {len(servers)} servers on 3SK", xbmc.LOGINFO)
        
        return servers
    
    def _find_episode_url(self, series_url, season, episode):
        """
        Find specific episode URL
        
        3SK strategy: Any episode page has list of all episodes
        """
        
        # Get series page
        response = self._request(series_url)
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try #epiList first
        epi_list = soup.select_one('#epiList')
        if epi_list:
            items = epi_list.select('article.postEp')
        else:
            items = soup.select('article.postEp')
        
        # Find matching episode
        for item in items:
            try:
                # Get episode number
                num_tag = item.select_one('.episodeNum')
                if num_tag:
                    num_text = num_tag.text.strip()
                    ep_match = re.search(r'(\d+)', num_text)
                    if ep_match:
                        ep_num = int(ep_match.group(1))
                        
                        if ep_num == episode:
                            # Found it!
                            a_tag = item.select_one('a')
                            if a_tag:
                                return self._fix_url(a_tag['href'])
                
            except Exception as e:
                continue
        
        return None
    
    def _extract_servers_from_see_page(self, see_url):
        """
        Extract ALL server embed URLs from /see/ page
        
        IMPORTANT: Unwraps internal 3SK URLs to get real host URLs
        """
        
        self._log(f"Extracting servers from: {see_url[:60]}...", xbmc.LOGDEBUG)
        
        response = self._request(see_url)
        if not response:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get server list
        servers = soup.select(SITE_CONFIG["SELECTORS"]["server_list"])
        
        if not servers:
            self._log("No servers found on /see/ page", xbmc.LOGWARNING)
            return []
        
        self._log(f"Found {len(servers)} server options", xbmc.LOGINFO)
        
        # Extract and unwrap embed URLs
        server_list = []
        
        for idx, server in enumerate(servers, 1):
            embed_url = server.get(SITE_CONFIG["SELECTORS"]["server_attr"])
            
            if not embed_url:
                continue
            
            embed_url = self._fix_url(embed_url)
            
            # CRITICAL: Unwrap internal 3SK URLs to get real host
            real_embed_url = self._unwrap_internal_url(embed_url)
            
            if not real_embed_url:
                self._log(f"Server {idx}: Failed to unwrap, skipping", xbmc.LOGDEBUG)
                continue
            
            # Try to detect quality from URL or attributes
            quality = self._detect_quality(real_embed_url, server)
            
            server_list.append({
                'embed_url': real_embed_url,  # Real host URL, not wrapper
                'referer': see_url,
                'server_name': f'Server {idx}',
                'quality': quality  # May be empty
            })
        
        return server_list
    
    def _unwrap_internal_url(self, url):
        """
        Unwrap internal 3SK URLs to get real video host
        
        3SK uses internal wrappers like:
        - https://x.esheeg.onl/?emb=true&id=...
        - https://esheaq.onl/watch/.../?emb=true
        
        These need to be unwrapped to get the real host (OK.RU, Uqload, etc.)
        
        Args:
            url (str): Potentially wrapped URL
        
        Returns:
            str: Real host URL or None
        """
        
        # Check if this is an internal 3SK URL
        is_internal = any(d in url for d in SITE_CONFIG["DOMAINS"]) or "emb=true" in url
        
        if not is_internal:
            # Already a real host URL
            self._log(f"URL is external host, no unwrapping needed", xbmc.LOGDEBUG)
            return url
        
        # Unwrap internal URL
        self._log(f"Unwrapping internal URL: {url[:60]}...", xbmc.LOGDEBUG)
        
        try:
            response = self._request(url)
            if not response:
                return None
            
            html = response.text
            
            # Look for iframe in the wrapper page
            iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
            
            if iframe_match:
                iframe_url = iframe_match.group(1)
                
                # Make absolute URL
                if not iframe_url.startswith('http'):
                    iframe_url = urllib.parse.urljoin(url, iframe_url)
                
                # Skip javascript: and about: URLs
                if iframe_url.startswith('javascript:') or iframe_url.startswith('about:'):
                    self._log("Iframe is javascript/about, trying direct extraction", xbmc.LOGDEBUG)
                else:
                    self._log(f"Found iframe: {iframe_url[:60]}...", xbmc.LOGINFO)
                    return iframe_url
            
            # Fallback: Look for common video host patterns in the HTML
            host_patterns = [
                r'(https?://[^"\s]+ok\.ru[^"\s]+)',
                r'(https?://[^"\s]+uqload\.[^"\s]+)',
                r'(https?://[^"\s]+doodstream\.[^"\s]+)',
                r'(https?://[^"\s]+streamtape\.[^"\s]+)',
                r'(https?://[^"\s]+voe\.[^"\s]+)',
            ]
            
            for pattern in host_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    host_url = match.group(1)
                    self._log(f"Found host URL via pattern: {host_url[:60]}...", xbmc.LOGINFO)
                    return host_url
            
            self._log("No host URL found in wrapper page", xbmc.LOGWARNING)
            return None
            
        except Exception as e:
            self._log(f"Error unwrapping URL: {e}", xbmc.LOGERROR)
            return None
    
    def _detect_quality(self, embed_url, server_element):
        """
        Try to detect quality from URL or server element
        
        Returns empty string if can't detect
        """
        
        url_lower = embed_url.lower()
        
        # Check URL for quality hints
        if '1080' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        
        # Check server element text
        try:
            server_text = server_element.get_text().lower()
            if '1080' in server_text:
                return '1080p'
            elif '720' in server_text or 'hd' in server_text:
                return 'HD'
            elif '480' in server_text or 'sd' in server_text:
                return 'SD'
        except:
            pass
        
        return ''  # Unknown quality
    
    def _find_active_domain(self):
        """Find active domain from list"""
        self._log("Checking 3SK domains...", xbmc.LOGINFO)
        
        for domain in SITE_CONFIG["DOMAINS"]:
            try:
                r = self.session.head(domain, timeout=5, allow_redirects=True)
                if r.status_code < 400:
                    self._log(f"Active domain: {domain}", xbmc.LOGINFO)
                    return domain
            except:
                continue
        
        # Fallback to first domain
        return SITE_CONFIG["DOMAINS"][0]
    
    def _request(self, url):
        """Make HTTP request"""
        try:
            self._log(f"Request: {url[:80]}", xbmc.LOGDEBUG)
            return self.session.get(url, timeout=30, allow_redirects=True)
        except Exception as e:
            self._log(f"Request failed: {e}", xbmc.LOGERROR)
            return None
    
    def _fix_url(self, url):
        """Fix relative URLs"""
        if url.startswith("http"):
            return url
        return urllib.parse.urljoin(self.base_url, url)
