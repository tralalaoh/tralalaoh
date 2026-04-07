# -*- coding: utf-8 -*-
"""
YouTube Resolver - Sub-Resolver Pattern
Extracts playable stream URLs from YouTube videos using Piped API

Architecture Layer: EXTRACTION (Resolvers)
"""

import re

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
            print(f"[YouTubeResolver] {msg}")


class YouTubeResolver:
    """
    YouTube stream resolver using Piped API
    
    This resolver extracts HLS (.m3u8) streams from YouTube videos
    using public Piped instances as the primary engine.
    
    Features:
    - Multi-instance failover (tries multiple Piped servers)
    - HLS stream extraction
    - Auto-translate subtitles (Turkish to English)
    - Returns standardized format for PlayerCore
    """
    
    # Public Piped instances (in priority order)
    PIPED_INSTANCES = [
        'https://pipedapi.kavin.rocks',
        'https://api.piped.victr.me',
        'https://pipedapi.tokhmi.xyz',
        'https://pipedapi.moomoo.me',
        'https://api-piped.mha.fi',
    ]
    
    def __init__(self, session):
        """
        Initialize YouTube resolver
        
        Args:
            session: Shared requests.Session object from PlayerCore
        """
        self.session = session
        self._log("YouTube Resolver initialized with Piped API", xbmc.LOGINFO)
    
    def resolve(self, embed_url):
        """
        Resolve YouTube URL to playable stream
        
        This is the main entry point called by PlayerCore.
        
        Args:
            embed_url (str): YouTube URL (any format)
        
        Returns:
            dict: {
                'url': 'https://.../.m3u8',
                'is_hls': True,
                'subtitles': ['https://...'],
                'headers': {...}
            }
            OR None if resolution fails
        """
        
        self._log(f"Resolving YouTube URL: {embed_url[:60]}...", xbmc.LOGINFO)
        
        # Step 1: Extract Video ID
        video_id = self._extract_video_id(embed_url)
        
        if not video_id:
            self._log("Failed to extract video ID", xbmc.LOGERROR)
            return None
        
        self._log(f"Video ID: {video_id}", xbmc.LOGINFO)
        
        # Step 2: Build subtitle URL (works for all engines)
        subtitle_url = self._build_subtitle_url(video_id)
        
        # Step 3: Try Piped API (primary engine)
        stream_url = self._try_piped_api(video_id)
        
        if not stream_url:
            self._log("All Piped instances failed", xbmc.LOGERROR)
            return None
        
        # Step 4: Build result
        result = {
            'url': stream_url,
            'is_hls': True,  # Piped always returns HLS
            'subtitles': [subtitle_url],
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Origin': 'https://www.youtube.com',
                'Referer': f'https://www.youtube.com/watch?v={video_id}'
            }
        }
        
        self._log("SUCCESS: Stream resolved via Piped API", xbmc.LOGINFO)
        
        return result
    
    # =========================================================================
    # PIPED API ENGINE
    # =========================================================================
    
    def _try_piped_api(self, video_id):
        """
        Try to extract stream using Piped API
        
        Loops through multiple Piped instances until one succeeds.
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            str: HLS stream URL or None
        """
        
        self._log("ENGINE: Piped API (Primary)", xbmc.LOGINFO)
        
        for instance in self.PIPED_INSTANCES:
            try:
                self._log(f"Trying Piped instance: {instance}", xbmc.LOGDEBUG)
                
                # Build API URL
                api_url = f"{instance}/streams/{video_id}"
                
                # Make request
                response = self.session.get(
                    api_url,
                    timeout=10,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'application/json'
                    }
                )
                
                # Check status
                if response.status_code != 200:
                    self._log(f"Instance {instance} returned {response.status_code}", xbmc.LOGDEBUG)
                    continue
                
                # Parse JSON
                data = response.json()
                
                # Extract HLS stream URL
                hls_url = data.get('hls')
                
                if not hls_url:
                    self._log(f"Instance {instance} has no HLS stream", xbmc.LOGDEBUG)
                    continue
                
                # SUCCESS!
                self._log(f"SUCCESS: Got HLS stream from {instance}", xbmc.LOGINFO)
                self._log(f"Stream URL: {hls_url[:80]}...", xbmc.LOGDEBUG)
                
                return hls_url
            
            except Exception as e:
                self._log(f"Instance {instance} failed: {e}", xbmc.LOGDEBUG)
                continue
        
        # All instances failed
        return None
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _extract_video_id(self, url):
        """
        Extract YouTube video ID from various URL formats
        
        Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID
        
        Args:
            url (str): YouTube URL
        
        Returns:
            str: Video ID or None
        """
        
        try:
            # Pattern 1: ?v=VIDEO_ID
            if 'v=' in url:
                video_id = url.split('v=')[-1].split('&')[0].split('#')[0]
                if len(video_id) >= 10:
                    return video_id
            
            # Pattern 2: youtu.be/VIDEO_ID
            if 'youtu.be/' in url:
                video_id = url.split('youtu.be/')[-1].split('?')[0].split('#')[0]
                if len(video_id) >= 10:
                    return video_id
            
            # Pattern 3: /embed/VIDEO_ID
            if '/embed/' in url:
                video_id = url.split('/embed/')[-1].split('?')[0].split('#')[0]
                if len(video_id) >= 10:
                    return video_id
            
            # Pattern 4: /v/VIDEO_ID
            if '/v/' in url:
                video_id = url.split('/v/')[-1].split('?')[0].split('#')[0]
                if len(video_id) >= 10:
                    return video_id
            
            return None
        
        except Exception as e:
            self._log(f"Error extracting video ID: {e}", xbmc.LOGERROR)
            return None
    
    def _build_subtitle_url(self, video_id):
        """
        Build YouTube TimedText API URL for auto-translated subtitles
        
        This returns Turkish auto-generated captions translated to English.
        
        Args:
            video_id (str): YouTube video ID
        
        Returns:
            str: Subtitle URL
        """
        
        return f"https://www.youtube.com/api/timedtext?v={video_id}&lang=tr&kind=asr&tlang=en&fmt=vtt"
    
    def _log(self, message, level=xbmc.LOGINFO):
        """
        Log message
        
        Args:
            message (str): Message to log
            level: Log level (xbmc.LOGINFO, xbmc.LOGERROR, etc.)
        """
        
        if KODI_ENV:
            xbmc.log(f"YouTubeResolver: {message}", level)
        else:
            print(f"[YouTubeResolver] {message}")


# =============================================================================
# TESTING (Optional)
# =============================================================================

if __name__ == '__main__':
    """
    Quick test of YouTube resolver
    Run: python youtube_resolver.py
    """
    
    import requests
    
    # Create session
    session = requests.Session()
    
    # Initialize resolver
    resolver = YouTubeResolver(session)
    
    # Test video ID
    test_url = "https://www.youtube.com/watch?v=hiXEiB_Y8wA"
    
    print("\n=== Testing YouTube Resolver ===")
    print(f"Test URL: {test_url}\n")
    
    # Resolve
    result = resolver.resolve(test_url)
    
    if result:
        print("SUCCESS!")
        print(f"Stream URL: {result['url'][:100]}...")
        print(f"Is HLS: {result['is_hls']}")
        print(f"Subtitles: {result['subtitles'][0][:100]}...")
        print(f"Headers: {list(result['headers'].keys())}")
    else:
        print("FAILED: Could not resolve stream")
