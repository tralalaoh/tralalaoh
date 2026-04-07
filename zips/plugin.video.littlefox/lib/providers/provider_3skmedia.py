# -*- coding: utf-8 -*-
"""
3SK Media Provider (Arabic Audio)
Based on z.3sk.media scraper with AlbaPlayer support

Based on 3sk-media-server__backup.py
"""

import re
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
            print(f"[3SKMedia] {msg}")

from .base_provider import BaseProvider


class Provider3SKMedia(BaseProvider):
    """
    3SK Media provider - z.3sk.media
    
    This is different from the regular 3SK provider:
    - Uses z.3sk.media domain
    - Has series browsing
    - Supports AlbaPlayer with multiple servers
    - Different unwrapping logic
    
    Regional Support: Multi-regional (Turkish, Arabic, and other content)
    """
    
    SEARCH_LANGUAGES = ['ar']  # Arabic only
    CONTENT_REGIONS = []  # Supports all regions (multi-regional)
    IS_REGIONAL_SPECIFIC = False  # Works for any region
    
    def __init__(self):
        """Initialize 3SK Media provider"""
        super().__init__()
        
        self.base_url = "https://z.3sk.media"
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Referer': self.base_url + '/'
        })
        
        self._log("3SK Media Provider initialized", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "3SKMedia"
    
    def get_audio_language(self):
        """Get audio language"""
        return "ar"  # Arabic
    
    def search_series(self, series_names):
        """
        Search 3SK Media for series
        
        Note: 3SK Media doesn't have search, so we browse series list
        and try to match by name
        """
        
        self._log(f"Searching 3SK Media with {len(series_names)} names", xbmc.LOGINFO)
        
        # Get series from homepage
        series_list = self._get_series_list()
        
        if not series_list:
            self._log("No series found on homepage", xbmc.LOGWARNING)
            return []
        
        # Try to match series names
        results = []
        
        for serie in series_list:
            serie_title_lower = serie['series_title'].lower()
            
            for name in series_names:
                name_lower = name.lower()
                
                # Check if name matches
                if name_lower in serie_title_lower or serie_title_lower in name_lower:
                    results.append(serie)
                    self._log(f"Match found: {serie['series_title']}", xbmc.LOGINFO)
                    break
        
        if not results:
            self._log("No matching series found", xbmc.LOGWARNING)
            # Return all series as fallback (user can browse)
            return series_list[:10]  # Return top 10
        
        return results
    
    def _get_series_list(self, page=1):
        """
        Get series list from 3SK Media homepage
        
        Based on ThreeSkScraper.get_series()
        """
        
        url = f"{self.base_url}/series/" if page == 1 else f"{self.base_url}/series/page/{page}/"
        
        self._log(f"Loading series page: {url[:60]}...", xbmc.LOGDEBUG)
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
        except Exception as e:
            self._log(f"Error loading series page: {e}", xbmc.LOGERROR)
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        series = []
        for article in soup.select('article.postEp'):
            try:
                link = article.select_one('a[href]')
                if not link:
                    continue
                
                serie_url = link['href']
                title = article.select_one('div.title')
                title_text = title.text.strip() if title else ""
                
                series.append({
                    'series_url': serie_url,
                    'series_title': title_text
                })
                
            except Exception as e:
                self._log(f"Error parsing series: {e}", xbmc.LOGERROR)
                continue
        
        self._log(f"Found {len(series)} series on page", xbmc.LOGINFO)
        
        return series
    
    def get_episode_servers(self, series_url, season, episode):
        """
        Get UNRESOLVED embed URLs for episode
        
        Strategy:
        1. Get episodes list from series page
        2. Find the specific episode
        3. Extract stream URL with AlbaPlayer support
        4. Return as server
        """
        
        self._log(f"Getting 3SK Media servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Get episodes list
        episodes = self._get_episodes_list(series_url)
        
        if not episodes:
            self._log("No episodes found", xbmc.LOGWARNING)
            return []
        
        # Find the specific episode
        target_episode = None
        for ep in episodes:
            if ep['number'] == episode:
                target_episode = ep
                break
        
        if not target_episode:
            self._log(f"Episode {episode} not found", xbmc.LOGWARNING)
            return []
        
        # Extract stream URL
        stream_url = self._get_stream_url(target_episode['url'])
        
        if not stream_url:
            self._log("Failed to extract stream URL", xbmc.LOGERROR)
            return []
        
        # Return as server
        return [{
            'embed_url': stream_url,
            'referer': target_episode['url'],
            'server_name': '3SK Media Player',
            'quality': 'HD'  # 3SK Media typically has HD
        }]
    
    def _get_episodes_list(self, serie_url):
        """
        Get episodes list from series page
        
        Based on ThreeSkScraper.get_episodes()
        """
        
        self._log(f"Loading episodes: {serie_url[:60]}...", xbmc.LOGDEBUG)
        
        try:
            response = self.session.get(serie_url, timeout=10)
            response.raise_for_status()
            
        except Exception as e:
            self._log(f"Error loading series page: {e}", xbmc.LOGERROR)
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        episodes = []
        ep_links = soup.select('ul.eplist a.epNum')
        
        self._log(f"Found {len(ep_links)} episode links", xbmc.LOGINFO)
        
        for idx, link in enumerate(ep_links):
            try:
                ep_url = link['href']
                number_span = link.select_one('span')
                number = int(number_span.text) if number_span else (idx + 1)
                
                episodes.append({
                    'number': number,
                    'url': ep_url
                })
                
            except Exception as e:
                self._log(f"Error parsing episode: {e}", xbmc.LOGERROR)
                continue
        
        # Reverse so newest first
        episodes.reverse()
        
        return episodes
    
    def _get_stream_url(self, episode_url):
        """
        Extract stream URL from episode page
        
        Based on ThreeSkScraper.get_stream_url()
        Supports AlbaPlayer with multiple servers
        """
        
        self._log(f"Extracting stream from: {episode_url[:60]}...", xbmc.LOGINFO)
        
        # Add ?do=watch if not present
        if '?do=watch' not in episode_url:
            episode_url += '?do=watch'
        
        # Load episode page
        try:
            response = self.session.get(episode_url, timeout=10)
            response.raise_for_status()
            html = response.text
            
        except Exception as e:
            self._log(f"Error loading episode page: {e}", xbmc.LOGERROR)
            return None
        
        # Find iframe
        iframe_match = re.search(r'iframe\s+[^>]*src="([^"]+)"', html)
        
        if not iframe_match:
            self._log("No iframe found", xbmc.LOGERROR)
            return None
        
        first_iframe = iframe_match.group(1)
        
        self._log(f"Found iframe: {first_iframe[:60]}...", xbmc.LOGINFO)
        
        # Check if AlbaPlayer
        is_albaplayer = 'albaplayer' in first_iframe.lower()
        
        if is_albaplayer:
            self._log("AlbaPlayer detected - testing servers", xbmc.LOGINFO)
            
            # Try multiple AlbaPlayer servers
            for serv_num in range(1, 10):
                try:
                    # Build server URL
                    if '?serv=' in first_iframe:
                        test_url = re.sub(r'\?serv=\d+', f'?serv={serv_num}', first_iframe)
                    else:
                        separator = '&' if '?' in first_iframe else '?'
                        test_url = f"{first_iframe}{separator}serv={serv_num}"
                    
                    self._log(f"Testing AlbaPlayer server {serv_num}...", xbmc.LOGDEBUG)
                    
                    # Load AlbaPlayer page
                    alba_response = self.session.get(test_url, timeout=5)
                    alba_html = alba_response.text
                    
                    # Look for nested iframe
                    nested_match = re.search(r'iframe[^>]+src="([^"]+)"', alba_html, re.IGNORECASE)
                    
                    if nested_match:
                        nested_url = nested_match.group(1)
                        
                        # Skip javascript: and about: URLs
                        if nested_url.startswith('javascript:') or nested_url.startswith('about:'):
                            continue
                        
                        # Make absolute URL
                        if not nested_url.startswith('http'):
                            nested_url = urljoin(test_url, nested_url)
                        
                        self._log(f"Found working server {serv_num}: {nested_url[:60]}...", xbmc.LOGINFO)
                        return nested_url
                    
                except Exception as e:
                    self._log(f"Server {serv_num} failed: {e}", xbmc.LOGDEBUG)
                    continue
            
            self._log("No working AlbaPlayer servers found", xbmc.LOGWARNING)
            return None
        
        else:
            # Not AlbaPlayer - might be direct embed
            self._log("Non-AlbaPlayer iframe - checking for nested iframe", xbmc.LOGINFO)
            
            try:
                # Load iframe page
                iframe_response = self.session.get(first_iframe, timeout=5)
                iframe_html = iframe_response.text
                
                # Look for nested iframe
                nested_match = re.search(r'iframe[^>]+src="([^"]+)"', iframe_html, re.IGNORECASE)
                
                if nested_match:
                    nested_url = nested_match.group(1)
                    
                    # Skip javascript: and about: URLs
                    if not nested_url.startswith('javascript:') and not nested_url.startswith('about:'):
                        # Make absolute URL
                        if not nested_url.startswith('http'):
                            nested_url = urljoin(first_iframe, nested_url)
                        
                        self._log(f"Found nested iframe: {nested_url[:60]}...", xbmc.LOGINFO)
                        return nested_url
                
                # No nested iframe - use first iframe directly
                self._log("No nested iframe - using first iframe", xbmc.LOGINFO)
                return first_iframe
                
            except Exception as e:
                self._log(f"Error checking nested iframe: {e}", xbmc.LOGERROR)
                # Fallback to first iframe
                return first_iframe


# ============================================================================
# TESTING (Optional)
# ============================================================================

if __name__ == '__main__':
    """
    Quick test of 3SK Media provider
    Run: python provider_3skmedia.py
    """
    
    provider = Provider3SKMedia()
    
    # Test get series list
    print("\n=== Testing Series List ===")
    series_list = provider._get_series_list()
    
    for serie in series_list[:5]:
        print(f"Title: {serie['series_title']}")
        print(f"URL: {serie['series_url']}")
        print()
    
    # Test search
    print("\n=== Testing Search ===")
    results = provider.search_series(['Al-Warith'])  # Arabic test name
    
    for result in results[:3]:
        print(f"Title: {result['series_title']}")
        print(f"URL: {result['series_url']}")
        print()
    
    # Test get servers (if we have results)
    if results:
        print("\n=== Testing Get Servers ===")
        servers = provider.get_episode_servers(results[0]['series_url'], season=1, episode=1)
        
        for server in servers:
            print(f"Server: {server['server_name']}")
            print(f"Embed URL: {server['embed_url'][:80]}...")
            print(f"Quality: {server.get('quality', 'Unknown')}")
            print()
