"""Stream deduplication - Remove duplicate streams intelligently."""

import re
from resources.lib.settings import Settings
from resources.lib.logger import log, log_debug


class StreamDeduplicator:
    """Deduplicate streams from multiple addons intelligently."""
    
    def __init__(self):
        """Initialize deduplicator with settings."""
        self.enabled = Settings.get_bool('enable_deduplication', True)
        self.strategy = Settings.get('deduplication_strategy', 'aggressive')
        self.stats = {
            'total': 0,
            'unique': 0,
            'duplicates': 0
        }
    
    def deduplicate(self, streams):
        """
        Remove duplicate streams, keeping the best version.
        
        Args:
            streams: List of stream dicts
        
        Returns:
            List of unique streams (best versions)
        """
        if not self.enabled:
            log_debug("Deduplication disabled, returning all streams")
            return streams
        
        self.stats['total'] = len(streams)
        
        if len(streams) <= 1:
            self.stats['unique'] = len(streams)
            return streams
        
        log(f"Deduplicating {len(streams)} streams (strategy: {self.strategy})")
        
        # Group streams by unique key
        seen = {}  # key -> best stream
        
        for stream in streams:
            key = self._get_dedup_key(stream)
            
            if not key:
                # Can't deduplicate this stream, keep it
                continue
            
            if key not in seen:
                # First time seeing this stream
                seen[key] = stream
            else:
                # Duplicate detected! Keep better version
                if self._is_better(stream, seen[key]):
                    log_debug(f"Replacing duplicate with better version: {key[:20]}...")
                    seen[key] = stream
                else:
                    log_debug(f"Skipping inferior duplicate: {key[:20]}...")
        
        unique_streams = list(seen.values())
        self.stats['unique'] = len(unique_streams)
        self.stats['duplicates'] = self.stats['total'] - self.stats['unique']
        
        log(f"Deduplication complete: {self.stats['unique']} unique streams ({self.stats['duplicates']} duplicates removed)")
        
        return unique_streams
    
    def _get_dedup_key(self, stream):
        """
        Generate unique key for deduplication.
        
        Priority:
        1. infoHash (most reliable)
        2. Cleaned filename
        3. URL (fallback)
        """
        # Try infoHash first (most reliable)
        info_hash = stream.get('infoHash')
        if info_hash:
            return f"hash:{info_hash.lower()}"
        
        # Try to extract hash from URL
        url = stream.get('url', '')
        if 'magnet:' in url:
            hash_match = re.search(r'btih:([a-fA-F0-9]{40})', url)
            if hash_match:
                return f"hash:{hash_match.group(1).lower()}"
        
        # Try filename from behaviorHints
        behavior_hints = stream.get('behaviorHints', {})
        filename = behavior_hints.get('filename')
        if filename:
            cleaned = self._clean_filename(filename)
            if cleaned:
                return f"file:{cleaned}"
        
        # Try title as fallback
        title = stream.get('title', '')
        if title:
            cleaned = self._clean_filename(title)
            if cleaned:
                return f"title:{cleaned}"
        
        # Can't create key, return None (don't deduplicate)
        return None
    
    def _clean_filename(self, filename):
        """
        Clean filename for comparison.
        
        Remove:
        - Service tags ([RD], [TB], etc.)
        - Seeders info
        - File size
        - Emojis
        - Extra whitespace
        """
        if not filename:
            return None
        
        # Remove common service tags
        cleaned = re.sub(r'\[(RD|TB|PM|AD|MF|ST|TR|Comet|MediaFusion|StremThru|Torrentio)\s*[\u26a1\u2714\u2705]?\]', '', filename, flags=re.IGNORECASE)

        # Remove seeder counts
        cleaned = re.sub(r'\[S:\s*\d+\]', '', cleaned)
        cleaned = re.sub(u'\U0001F464\\s*\\d+', '', cleaned)

        # Remove file size
        cleaned = re.sub(r'\d+\.?\d*\s*(GB|MB|TB)', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(u'\U0001F4BE\\s*\\d+\\.?\\d*\\s*(GB|MB)', '', cleaned, flags=re.IGNORECASE)
        
        # Remove emojis
        emoji_pattern = re.compile(
            "["
            u"\U0001F600-\U0001F64F"
            u"\U0001F300-\U0001F5FF"
            u"\U0001F680-\U0001F6FF"
            u"\U0001F1E0-\U0001F1FF"
            u"\U00002600-\U000027BF"
            u"\U0001F900-\U0001F9FF"
            u"\U00002702-\U000027B0"
            u"\U000024C2-\U0001F251"
            "]+", 
            flags=re.UNICODE
        )
        cleaned = emoji_pattern.sub('', cleaned)
        
        # Remove extra whitespace
        cleaned = ' '.join(cleaned.split())
        
        # Convert to lowercase for comparison
        cleaned = cleaned.lower().strip()
        
        return cleaned if cleaned else None
    
    def _is_better(self, new_stream, old_stream):
        """
        Determine if new stream is better than old stream.
        
        Priority (in order):
        1. Cached > Uncached (HIGHEST PRIORITY)
        2. Resolution (2160p > 1080p > 720p > 480p)
        3. Quality (REMUX > BluRay > WEB-DL > WEBRip > HDTV)
        4. Size (larger is usually better for same quality)
        5. Seeders (more is better for uncached)
        6. Addon (prefer certain sources)
        """
        # Strategy: aggressive = strict rules, conservative = looser rules
        aggressive = self.strategy == 'aggressive'
        
        # RULE 1: Cached always wins (unless both are cached)
        new_cached = new_stream.get('cached', False)
        old_cached = old_stream.get('cached', False)
        
        if new_cached != old_cached:
            return new_cached  # Cached wins
        
        # Both cached or both uncached - compare other factors
        
        # RULE 2: Resolution
        new_res = self._get_resolution_rank(new_stream)
        old_res = self._get_resolution_rank(old_stream)
        
        if new_res != old_res:
            # In aggressive mode, resolution is king
            # In conservative mode, only big differences matter
            if aggressive or abs(new_res - old_res) >= 2:
                return new_res > old_res
        
        # RULE 3: Quality (source type)
        new_quality = self._get_quality_rank(new_stream)
        old_quality = self._get_quality_rank(old_stream)
        
        if new_quality != old_quality:
            if aggressive or abs(new_quality - old_quality) >= 2:
                return new_quality > old_quality
        
        # RULE 4: File size (larger usually means better quality)
        new_size = new_stream.get('size_gb', 0)
        old_size = old_stream.get('size_gb', 0)
        
        if new_size > 0 and old_size > 0:
            size_diff = abs(new_size - old_size) / max(old_size, 1)
            if size_diff > 0.3:  # More than 30% difference
                return new_size > old_size
        
        # RULE 5: Seeders (for uncached torrents)
        if not new_cached and not old_cached:
            new_seeders = new_stream.get('seeders', 0)
            old_seeders = old_stream.get('seeders', 0)
            
            if abs(new_seeders - old_seeders) >= 20:
                return new_seeders > old_seeders
        
        # RULE 6: Addon preference (optional)
        # Prefer certain addons if configured
        addon_preference = Settings.get('addon_preference', '')
        if addon_preference:
            new_addon = new_stream.get('addon', '').lower()
            old_addon = old_stream.get('addon', '').lower()
            
            if addon_preference.lower() in new_addon:
                return True
            if addon_preference.lower() in old_addon:
                return False
        
        # No clear winner, keep old stream (first seen)
        return False
    
    def _get_resolution_rank(self, stream):
        """Get resolution rank (higher is better)."""
        title = stream.get('title', '').lower()
        description = stream.get('description', '').lower()
        text = f"{title} {description}"
        
        if '2160p' in text or '4k' in text or 'uhd' in text:
            return 4
        elif '1440p' in text:
            return 3
        elif '1080p' in text or 'fhd' in text:
            return 2
        elif '720p' in text or 'hd' in text:
            return 1
        elif '480p' in text or 'sd' in text:
            return 0
        else:
            return 1  # Unknown, assume 720p
    
    def _get_quality_rank(self, stream):
        """Get quality/source rank (higher is better)."""
        title = stream.get('title', '').lower()
        description = stream.get('description', '').lower()
        text = f"{title} {description}"
        
        if 'remux' in text or 'bdremux' in text:
            return 6
        elif 'bluray' in text or 'blu-ray' in text or 'brrip' in text or 'bdrip' in text:
            return 5
        elif 'web-dl' in text or 'webdl' in text:
            return 4
        elif 'webrip' in text or 'web-rip' in text:
            return 3
        elif 'hdtv' in text:
            return 2
        elif 'dvdrip' in text:
            return 1
        elif 'cam' in text or 'ts' in text or 'tc' in text:
            return 0
        else:
            return 2  # Unknown, assume HDTV quality
    
    def get_stats(self):
        """Get deduplication statistics."""
        return self.stats.copy()
    
    def get_stats_message(self):
        """Get human-readable stats message."""
        if not self.enabled:
            return "Deduplication disabled"
        
        if self.stats['total'] == 0:
            return "No streams to deduplicate"
        
        return f"Removed {self.stats['duplicates']} duplicates ({self.stats['unique']}/{self.stats['total']} unique)"


