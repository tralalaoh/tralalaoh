# -*- coding: utf-8 -*-
"""
EgyDead Provider (Multi-Regional Content)
Acts as reference provider for Turkish content Arabic name discovery

Enhanced with regional context support
"""

import re
from urllib.parse import urljoin, quote
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
            print(f"[EgyDead] {msg}")

from .base_provider import BaseProvider


class ProviderEgyDead(BaseProvider):
    """
    EgyDead provider - Multi-regional content
    
    Special role for Turkish content:
    - Searches with original Turkish name
    - Discovers and caches Arabic name
    - Other Arabic providers can reuse this discovery
    """
    
    SEARCH_LANGUAGES = ['ar', 'tr']  # Arabic and Turkish
    CONTENT_REGIONS = []  # Supports all regions (multi-regional)
    IS_REGIONAL_SPECIFIC = False
    
    # For Turkish content, prioritize original name
    SEARCH_PRIORITY = ['original', 'tr', 'ar', 'en']
    
    def __init__(self):
        """Initialize EgyDead provider"""
        super().__init__()
        
        self.base_url = "https://egydead.rip"
        
        self.session.headers.update({
            'Accept-Language': 'ar,en-US;q=0.7,en;q=0.3',
            'Referer': self.base_url + '/'
        })
        
        self._log("EgyDead Provider initialized (Multi-Regional Reference)", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "EgyDead"
    
    def get_audio_language(self):
        """Get audio language"""
        return "ar"  # Primary: Arabic dubbed or Arabic subs
    
    def search_series_with_context(self, context):
        """
        SMART SEARCH with regional intelligence
        
        For Turkish content:
        1. Search with original Turkish name
        2. Extract Arabic name from results
        3. Cache Arabic name for other providers
        
        For other content:
        4. Use standard search
        """
        
        self._log(f"Searching with regional context - Region: {context.content_region}", xbmc.LOGINFO)
        
        # TURKISH CONTENT STRATEGY
        if context.is_turkish_content():
            self._log("Turkish content detected - using original name search", xbmc.LOGINFO)
            
            # Get original Turkish name
            original_name = context.names.get('original')
            
            if original_name:
                results = self._search_by_name(original_name)
                
                if results:
                    # Extract and cache Arabic name
                    arabic_name = self._extract_arabic_name_from_result(results[0])
                    
                    if arabic_name:
                        self._log(f"✓ Discovered Arabic name: {arabic_name}", xbmc.LOGINFO)
                        
                        # Cache for other providers!
                        self.cache_discovered_names(context, {
                            'ar': arabic_name,
                            'tr': original_name
                        })
                        
                        # Store as verified
                        context.verified_names['egydead'] = {
                            'ar': arabic_name,
                            'tr': original_name
                        }
                    
                    return results
            
            # Fallback to Turkish names from TMDB
            tr_names = context.get_names_for_language('tr')
            for name in tr_names:
                results = self._search_by_name(name)
                if results:
                    return results
        
        # STANDARD SEARCH for non-Turkish content
        return super().search_series_with_context(context)
    
    def search_series(self, series_names):
        """
        Traditional search (backwards compatibility)
        """
        
        self._log(f"Searching EgyDead with {len(series_names)} names", xbmc.LOGINFO)
        
        results = []
        
        for name in series_names:
            # Skip English names - EgyDead uses Turkish and Arabic
            if self._is_english_name(name):
                self._log(f"Skipping English name: {name}", xbmc.LOGDEBUG)
                continue
            
            search_results = self._search_by_name(name)
            if search_results:
                results.extend(search_results)
        
        # Deduplicate
        return self._deduplicate_results(results)
    
    def _search_by_name(self, search_query):
        """
        Execute search with single name
        
        Args:
            search_query (str): Name to search
        
        Returns:
            list: Search results
        """
        
        self._log(f"Searching for: {search_query[:30]}...", xbmc.LOGINFO)
        
        search_url = f"{self.base_url}/?s={quote(search_query)}"
        
        try:
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find all search results
            items = soup.find_all('li', class_='movieItem')
            
            self._log(f"Found {len(items)} results", xbmc.LOGINFO)
            
            results = []
            
            for item in items[:10]:  # Limit to first 10
                try:
                    link = item.find('a')
                    if not link:
                        continue
                    
                    href = link.get('href')
                    title_elem = link.find('h1', class_='BottomTitle')
                    
                    if href and title_elem:
                        result_title = title_elem.text.strip()
                        
                        # Detect if dubbed or subtitled
                        is_dubbed = 'مدبلج' in result_title
                        is_subbed = 'مترجم' in result_title
                        
                        # Determine audio type
                        if is_dubbed:
                            audio_type = 'dubbed'
                            audio_label = 'مدبلج (Arabic Audio)'
                        elif is_subbed:
                            audio_type = 'subbed'
                            audio_label = 'مترجم (Arabic Subs)'
                        else:
                            audio_type = 'unknown'
                            audio_label = 'Unknown'
                        
                        results.append({
                            'series_url': href,
                            'series_title': result_title,
                            'audio_type': audio_type,
                            'audio_label': audio_label
                        })
                        
                        self._log(f"Found: {result_title[:40]}... [{audio_label}]", xbmc.LOGDEBUG)
                
                except Exception as e:
                    self._log(f"Error parsing result: {e}", xbmc.LOGERROR)
                    continue
            
            return results
        
        except Exception as e:
            self._log(f"Search error: {e}", xbmc.LOGERROR)
            return []
    
    def _extract_arabic_name_from_result(self, result):
        """
        Extract Arabic name from search result title
        
        EgyDead titles format:
        - Dubbed: "الوريث مدبلج" (Arabic name + مدبلج)
        - Subbed: "Veliaht مترجم" (Turkish name + مترجم)
        
        Args:
            result (dict): Search result
        
        Returns:
            str: Arabic name or None
        """
        
        title = result.get('series_title', '')
        
        # Remove markers
        title = title.replace('مدبلج', '').replace('مترجم', '').strip()
        
        # If title is Arabic, return it
        if self._is_arabic(title):
            return title
        
        # Otherwise, try to extract Arabic part
        # (some titles might be mixed)
        words = title.split()
        arabic_words = [w for w in words if self._is_arabic(w)]
        
        if arabic_words:
            return ' '.join(arabic_words)
        
        return None
    
    def _is_english_name(self, text):
        """Check if name is English (to skip it)"""
        
        if not text:
            return False
        
        # If it has Arabic characters, it's not English
        if self._is_arabic(text):
            return False
        
        # If it has Turkish special characters, it's Turkish (not English)
        turkish_chars = ['ç', 'ğ', 'ı', 'ö', 'ş', 'ü', 'Ç', 'Ğ', 'İ', 'Ö', 'Ş', 'Ü']
        if any(char in text for char in turkish_chars):
            return False
        
        # Check for common English words/patterns
        english_indicators = [
            'the ', ' the ', 'a ', ' a ',
            ' and ', ' or ', ' of ',
            ' in ', ' on ', ' at ',
        ]
        
        text_lower = text.lower()
        for indicator in english_indicators:
            if indicator in text_lower:
                return True
        
        return False
    
    def _deduplicate_results(self, results):
        """Deduplicate results by URL but keep different audio types"""
        
        seen = {}
        unique_results = []
        
        for r in results:
            url = r['series_url']
            audio_type = r.get('audio_type', 'unknown')
            key = (url, audio_type)
            
            if key not in seen:
                seen[key] = True
                unique_results.append(r)
        
        return unique_results
    
    def get_episode_servers(self, series_url, season, episode):
        """Get UNRESOLVED embed URLs for episode"""
        
        self._log(f"Getting servers for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Handle dict format (with audio_type)
        audio_type = 'unknown'
        audio_label = ''
        
        if isinstance(series_url, dict):
            audio_type = series_url.get('audio_type', 'unknown')
            audio_label = series_url.get('audio_label', '')
            episode_url = series_url.get('series_url', series_url)
        else:
            episode_url = series_url
        
        servers = self._extract_servers_from_episode(episode_url, audio_type, audio_label)
        
        self._log(f"Found {len(servers)} servers ({audio_label})", xbmc.LOGINFO)
        
        return servers
    
    def _extract_servers_from_episode(self, episode_url, audio_type='unknown', audio_label=''):
        """Extract server URLs from episode page"""
        
        try:
            # GET request
            response = self.session.get(episode_url, timeout=10)
            response.raise_for_status()
            
            # POST with View=1
            post_response = self.session.post(
                episode_url, 
                data={'View': '1'},
                timeout=10
            )
            post_response.raise_for_status()
            
            html_content = post_response.content
            
        except Exception as e:
            self._log(f"Error fetching episode: {e}", xbmc.LOGERROR)
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        servers = []
        
        # Method 1: serversList
        servers_list = soup.find('ul', class_='serversList')
        if servers_list:
            for li in servers_list.find_all('li'):
                server_url = li.get('data-link')
                server_name = li.get_text(strip=True)
                if server_url:
                    display_name = f"{server_name}"
                    if audio_label:
                        display_name += f" - {audio_label}"
                    
                    servers.append({
                        'embed_url': server_url,
                        'referer': episode_url,
                        'server_name': display_name,
                        'quality': '',
                        'audio_type': audio_type
                    })
            
            if servers:
                return servers
        
        # Method 2: watchAreaMaster iframes
        watch_area = soup.find('div', class_='watchAreaMaster')
        if watch_area:
            iframes = watch_area.find_all('iframe')
            for idx, iframe in enumerate(iframes, 1):
                src = iframe.get('src') or iframe.get('data-src')
                if src:
                    display_name = f'Server {idx}'
                    if audio_label:
                        display_name += f" - {audio_label}"
                    
                    servers.append({
                        'embed_url': src,
                        'referer': episode_url,
                        'server_name': display_name,
                        'quality': '',
                        'audio_type': audio_type
                    })
            
            if servers:
                return servers
        
        # Method 3: server buttons
        server_buttons = soup.find_all(['button', 'a'], class_=re.compile(r'server|watch|play', re.I))
        for idx, button in enumerate(server_buttons, 1):
            url = button.get('data-link') or button.get('data-url') or button.get('href')
            name = button.get_text(strip=True)
            if url and url.startswith('http'):
                display_name = name or f'Server {idx}'
                if audio_label:
                    display_name += f" - {audio_label}"
                
                servers.append({
                    'embed_url': url,
                    'referer': episode_url,
                    'server_name': display_name,
                    'quality': '',
                    'audio_type': audio_type
                })
        
        return servers
