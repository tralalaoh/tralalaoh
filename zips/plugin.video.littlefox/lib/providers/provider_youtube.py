# -*- coding: utf-8 -*-
"""
YouTube Provider (Turkish Content)
Searches YouTube for Turkish TV episodes with proper season/episode format

Based on episode_finder.py
"""

import re
import json
import urllib.parse

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
            print(f"[YouTube] {msg}")

from .base_provider import BaseProvider


class ProviderYouTube(BaseProvider):
    """
    YouTube provider - Turkish content
    
    Searches YouTube with Turkish episode patterns:
    - "{series} {season}. sezon {episode}. bölüm"
    - "{series} {episode}. bölüm tek parça"
    
    Regional Support: Multi-regional (focuses on Turkish but works globally)
    """
    
    SEARCH_LANGUAGES = ['tr', 'en']  # Turkish + English
    CONTENT_REGIONS = []  # Supports all regions (YouTube is global)
    IS_REGIONAL_SPECIFIC = False  # Multi-regional provider
    
    def __init__(self):
        """Initialize YouTube provider"""
        super().__init__()
        
        self.base_url = "https://www.youtube.com"
        
        self.session.headers.update({
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        })
        
        self._log("YouTube Provider initialized", xbmc.LOGINFO)
    
    def get_name(self):
        """Get provider name"""
        return "YouTube"
    
    def get_audio_language(self):
        """Get audio language"""
        return "tr"  # Turkish
    
    def search_series(self, series_names):
        """
        Store series names for later use in get_episode_servers()
        
        YouTube doesn't search for series, it searches per episode
        """
        
        self._log(f"Storing {len(series_names)} series names for episode search", xbmc.LOGINFO)
        
        # Return a result that contains the series names
        # We'll use series_url as a JSON string to pass the data
        return [{
            'series_url': json.dumps({
                'type': 'youtube_search',
                'names': series_names
            }),
            'series_title': series_names[0] if series_names else 'Unknown'
        }]
    
    def get_episode_servers(self, series_url, season, episode):
        """
        Search YouTube for specific episode with Turkish patterns
        
        Args:
            series_url: JSON string containing series names
            season: Season number
            episode: Episode number
        """
        
        self._log(f"Searching YouTube for S{season:02d}E{episode:02d}", xbmc.LOGINFO)
        
        # Extract series names from JSON
        try:
            data = json.loads(series_url)
            series_names = data.get('names', [])
        except:
            self._log("Failed to extract series names from series_url", xbmc.LOGERROR)
            return []
        
        if not series_names:
            self._log("No series names available for YouTube search", xbmc.LOGWARNING)
            return []
        
        # Search YouTube with Turkish patterns
        servers = self._search_youtube_episode(series_names, season, episode)
        
        self._log(f"Found {len(servers)} YouTube videos", xbmc.LOGINFO)
        
        return servers
    
    def _build_search_queries(self, series_names, season, episode):
        """
        Build Turkish search queries
        
        Patterns from episode_finder.py:
        - "{name} {season}. sezon {episode}. bolum"
        - "{name} {season} sezon {episode} bolum tek parca"
        - "{name} {episode}. bolum tek parca"
        - "{name} {episode} bolum full"
        """
        
        queries = []
        
        for name in series_names[:3]:  # Use top 3 names
            # Turkish queries
            if season and season > 0:
                queries.append(f"{name} {season}. sezon {episode}. bolum")
                queries.append(f"{name} {season} sezon {episode} bolum tek parca")

            queries.append(f"{name} {episode}. bolum tek parca")
            queries.append(f"{name} {episode} bolum full")
            
            # English queries (fallback)
            if season and season > 0:
                queries.append(f"{name} season {season} episode {episode}")
            queries.append(f"{name} episode {episode}")
        
        return queries
    
    def _search_youtube_episode(self, series_names, season, episode):
        """
        Search YouTube for episode with Turkish patterns
        
        Based on episode_finder.py logic
        """
        
        results = []
        queries = self._build_search_queries(series_names, season, episode)
        
        self._log(f"Will try {len(queries)} search queries", xbmc.LOGDEBUG)
        
        for query in queries[:3]:  # Try first 3 queries
            if len(results) >= 3:
                break
            
            try:
                encoded_query = urllib.parse.quote(query)
                yt_url = f"{self.base_url}/results?search_query={encoded_query}"
                
                self._log(f"Searching: {query}", xbmc.LOGDEBUG)
                
                response = self.session.get(yt_url, timeout=15)
                
                # Extract JSON data from YouTube page
                json_match = re.search(r'var ytInitialData = ({.+?});', response.text)
                if not json_match:
                    self._log("No ytInitialData found", xbmc.LOGDEBUG)
                    continue
                
                yt_data = json.loads(json_match.group(1))
                
                # Navigate YouTube's JSON structure
                contents = (yt_data.get('contents', {})
                           .get('twoColumnSearchResultsRenderer', {})
                           .get('primaryContents', {})
                           .get('sectionListRenderer', {})
                           .get('contents', []))
                
                for section in contents:
                    items = section.get('itemSectionRenderer', {}).get('contents', [])
                    
                    for item in items:
                        if len(results) >= 3:
                            break
                        
                        video_data = item.get('videoRenderer', {})
                        if not video_data:
                            continue
                        
                        video_id = video_data.get('videoId')
                        if not video_id:
                            continue
                        
                        # Extract metadata
                        title_runs = video_data.get('title', {}).get('runs', [])
                        title = title_runs[0].get('text', '') if title_runs else ''
                        
                        duration_text = video_data.get('lengthText', {}).get('simpleText', '')
                        
                        channel_runs = video_data.get('ownerText', {}).get('runs', [])
                        channel = channel_runs[0].get('text', '') if channel_runs else ''
                        
                        # CRITICAL: Verify series name matches
                        title_lower = title.lower()
                        series_match = any(name.lower() in title_lower for name in series_names)
                        
                        if not series_match:
                            continue
                        
                        # CRITICAL: Verify episode number matches
                        title_episode = self._extract_episode_number(title)
                        if title_episode != episode:
                            continue
                        
                        # Extract season from title
                        title_season = self._extract_season_number(title)
                        
                        # Season matching logic
                        season_match = False
                        season_penalty = 0
                        
                        if season and season > 0:
                            if title_season == season:
                                season_match = True
                            elif title_season is None:
                                # No season in title - might be OK
                                season_match = True
                                season_penalty = 2  # Small penalty
                            else:
                                # Wrong season - skip
                                continue
                        else:
                            # No season specified - any season OK
                            season_match = True
                        
                        if not season_match:
                            continue
                        
                        # Build quality score (from episode_finder.py)
                        quality_score = 0
                        
                        # Check if "tek parca" (single part) - IMPORTANT!
                        if 'tek parca' in title_lower or 'tek parça' in title_lower:
                            quality_score += 2
                        
                        # Check duration (prefer 90-150 minutes for Turkish episodes)
                        if duration_text:
                            duration_match = re.match(r'(\d+):(\d+):(\d+)', duration_text)
                            if duration_match:
                                hours = int(duration_match.group(1))
                                mins = int(duration_match.group(2))
                                total_mins = hours * 60 + mins
                                
                                if 90 <= total_mins <= 150:
                                    quality_score += 5  # Perfect duration
                                elif total_mins >= 60:
                                    quality_score += 2  # OK duration
                        
                        # Check for HD keywords
                        if 'hd' in title_lower or '1080p' in title_lower or '720p' in title_lower:
                            quality_score += 1
                        
                        # Official channels bonus
                        if any(kw in channel.lower() for kw in ['resmi', 'official', 'atv', 'fox', 'show tv', 'kanal d']):
                            quality_score += 2
                        
                        # Apply season penalty (if any)
                        quality_score = max(0, quality_score - season_penalty)
                        
                        url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        # Check if already added
                        if any(r['embed_url'] == url for r in results):
                            continue
                        
                        # Detect quality from title
                        quality = self._detect_quality_from_title(title)
                        
                        # Build server name with channel and duration
                        server_name = f'{channel}'
                        if duration_text:
                            server_name += f' - {duration_text}'
                        
                        results.append({
                            'embed_url': url,  # YouTube URL - ResolveURL handles it
                            'referer': self.base_url,
                            'server_name': server_name,
                            'quality': quality,
                            'quality_score': quality_score  # For internal sorting
                        })
                        
                        self._log(f"Found: {title[:50]}... (score: {quality_score})", xbmc.LOGDEBUG)
            
            except Exception as e:
                self._log(f"Search error for '{query}': {e}", xbmc.LOGERROR)
                continue
        
        # Sort by quality score (highest first)
        results.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        # Remove quality_score from final results (internal use only)
        for result in results:
            result.pop('quality_score', None)
        
        return results
    
    def _extract_episode_number(self, text):
        """
        Extract episode number from Turkish title
        
        Patterns:
        - "15. bolum"
        - "bolum 15"
        - "episode 15"
        """
        
        patterns = [
            r'(\d+)\s*\.?\s*b[oö]l[uü]m',     # "15. bolum", "15. bölüm"
            r'b[oö]l[uü]m\s*[:-]?\s*(\d+)',    # "bolum 15", "bölüm: 15"
            r'episode\s*[:-]?\s*(\d+)',        # "episode 15"
            r'ep\s*[:-]?\s*(\d+)',             # "ep 15"
            r'\b(\d+)\b'                        # Any standalone number
        ]
        
        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return int(match.group(1))
        
        return None
    
    def _extract_season_number(self, text):
        """
        Extract season number from Turkish title
        
        Patterns:
        - "2. sezon"
        - "sezon 2"
        - "season 2"
        - "S2E15"
        """
        
        patterns = [
            r'(\d+)\s*\.?\s*sezon',           # "2. sezon", "2 sezon"
            r'sezon\s*[:-]?\s*(\d+)',          # "sezon 2", "sezon: 2"
            r'season\s*[:-]?\s*(\d+)',         # "season 2"
            r's(\d+)e\d+',                      # "S02E15"
            r's(\d+)\s',                        # "S2 "
        ]
        
        text_lower = text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                return int(match.group(1))
        
        return None
    
    def _detect_quality_from_title(self, title):
        """Detect quality from YouTube title"""
        
        title_lower = title.lower()
        
        if '1080p' in title_lower or 'fhd' in title_lower:
            return '1080p'
        elif '720p' in title_lower or 'hd' in title_lower:
            return '720p'
        elif '480p' in title_lower:
            return '480p'
        
        return 'HD'  # Default for YouTube


# ============================================================================
# TESTING (Optional)
# ============================================================================

if __name__ == '__main__':
    """
    Quick test of YouTube provider
    Run: python provider_youtube.py
    """
    
    provider = ProviderYouTube()
    
    # Test with known Turkish series
    print("\n=== Testing YouTube Search ===")
    
    series_names = ['Kurulus Osman', 'Kuruluş Osman']
    season = 5
    episode = 120
    
    # Simulate search_series call
    search_results = provider.search_series(series_names)
    print(f"Search results: {search_results[0]['series_title']}")
    
    # Get episode servers
    series_url = search_results[0]['series_url']
    servers = provider.get_episode_servers(series_url, season, episode)
    
    print(f"\nFound {len(servers)} videos:\n")
    
    for idx, server in enumerate(servers, 1):
        print(f"{idx}. {server['server_name']}")
        print(f"   Quality: {server['quality']}")
        print(f"   URL: {server['embed_url']}")
        print()

