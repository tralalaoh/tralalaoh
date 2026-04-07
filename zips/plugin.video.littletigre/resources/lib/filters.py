"""Stream filtering and safety module."""

import re
from resources.lib.settings import Settings
from resources.lib.logger import log


class StreamFilter:
    """Filter streams based on safety and quality criteria."""

    # Comprehensive adult content keywords
    ADULT_KEYWORDS = [
        'xxx', 'adult', 'porn', '18+', 'nsfw', 'hentai', 'erotic',
        'mature', 'x-rated', 'uncensored', 'uncut rated', 'av-',
        'jav', 'milf', 'anal', 'bdsm', 'fetish', 'hardcore',
        'softcore', 'lesbian', 'xxx-', '-xxx', '.xxx'
    ]

    # CAM and low quality keywords
    CAM_KEYWORDS = [
        'cam', 'ts', 'hdts', 'screener', 'r5', 'dvdscr',
        'workprint', 'telecine', 'telesync', 'pdvd', 'predvdrip',
        'vhsrip', 'hdcam'
    ]

    # Trusted release groups
    TRUSTED_GROUPS = [
        'yts', 'yify', 'rarbg', 'eztv', 'ettv', 'tgx', 'galaxyrg',
        'psarips', 'pahe', 'sparks', 'cmrg', 'ntg', 'ion10',
        'tigole', 'qxr', 'scene', 'vxt', 'momentum', 'flux'
    ]

    # Suspicious patterns
    SUSPICIOUS_PATTERNS = [
        r'\d{2,3}[xX]\d{2,3}',      # Episode-like patterns (18x24)
        r'\b[Aa][Vv][\s-]',          # AV- prefix
        r'\[.*?(adult|xxx).*?\]',    # Adult tags in brackets
        r'\b[Ee][Pp]?\s?\d+\b(?!.*[Ss]\d+)'  # Suspicious episode numbering
    ]

    # Quality patterns
    QUALITY_PATTERNS = {
        '2160p': ['2160p', '4k', 'uhd'],
        '1080p': ['1080p', 'fhd'],
        '720p': ['720p', 'hd'],
        '480p': ['480p', 'sd'],
        'unknown': []
    }

    # === FIX: Addons that have their own filtering ===
    # These addons pre-filter results, so we should NOT apply additional filters
    BYPASS_FILTER_ADDONS = [
        'aio streams',
        'aiostreams',
    ]

    def __init__(self):
        """Initialize filter with current settings."""
        self.safety_level = Settings.get_safety_level()
        self.exclude_adult = Settings.should_exclude_adult()
        self.custom_blacklist = Settings.get_custom_blacklist()
        self.exclude_cam = Settings.should_exclude_cam()
        self.hd_only = Settings.is_hd_only()
        self.min_quality = Settings.get_min_quality()
        self.whitelist_mode = Settings.is_whitelist_mode()
        self.trusted_only = Settings.require_trusted_sources()
        self.min_seeders = Settings.get_min_seeders()
        self.max_file_size = Settings.get_max_file_size()
        self.language_filter = Settings.get_language_filter()

        self.filtered_count = {
            'adult': 0,
            'cam': 0,
            'quality': 0,
            'seeders': 0,
            'size': 0,
            'trusted': 0,
            'suspicious': 0,
            'language': 0,
            'bypassed': 0  # Track bypassed streams
        }

    def filter_streams(self, streams):
        """Filter streams based on all criteria."""
        filtered = []

        for stream in streams:
            if self._should_filter(stream):
                continue
            filtered.append(stream)

        if Settings.should_log_filtered():
            self._log_filter_stats(len(streams), len(filtered))

        return filtered

    def _should_filter(self, stream):
        """Check if stream should be filtered out."""
        title = stream.get('title', '').lower()
        addon_name = stream.get('addon', '').lower()

        # === FIX: Bypass filters for addons with built-in filtering ===
        if any(bypass_addon in addon_name for bypass_addon in self.BYPASS_FILTER_ADDONS):
            self.filtered_count['bypassed'] += 1
            log(f"Filter bypass: {stream.get('addon')} (has own filters) - {title[:50]}", 'debug')
            return False  # Don't filter!

        # Adult content check (HIGHEST PRIORITY)
        if self.exclude_adult and self._is_adult_content(title):
            self.filtered_count['adult'] += 1
            log(f"Filtered adult content: {stream.get('title')}", 'debug')
            return True

        # Suspicious pattern check
        if self.safety_level in ['strict', 'paranoid']:
            if self._has_suspicious_patterns(title):
                self.filtered_count['suspicious'] += 1
                log(f"Filtered suspicious pattern: {stream.get('title')}", 'debug')
                return True

        # CAM quality check
        if self.exclude_cam and self._is_cam_quality(title):
            self.filtered_count['cam'] += 1
            return True

        # Quality check
        if not self._meets_quality_requirements(title):
            self.filtered_count['quality'] += 1
            return True

        # Seeders check (for torrents)
        seeders = stream.get('seeders', 0)
        if not stream.get('cached', False) and seeders < self.min_seeders:
            self.filtered_count['seeders'] += 1
            return True

        # File size check
        if self.max_file_size > 0:
            size_gb = stream.get('size_gb', 0)
            if size_gb > self.max_file_size:
                self.filtered_count['size'] += 1
                return True

        # Whitelist mode - require trusted sources
        if self.whitelist_mode or self.trusted_only:
            if not self._is_trusted_source(title):
                self.filtered_count['trusted'] += 1
                return True

        # Language filter
        if self.language_filter:
            if not self._matches_language(stream):
                self.filtered_count['language'] += 1
                return True

        return False

    def _is_adult_content(self, title):
        """Check if title contains adult content keywords."""
        # Check built-in keywords
        for keyword in self.ADULT_KEYWORDS:
            if keyword in title:
                return True

        # Check custom blacklist
        for keyword in self.custom_blacklist:
            if keyword in title:
                return True

        return False

    def _has_suspicious_patterns(self, title):
        """Check for suspicious patterns in title."""
        for pattern in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, title):
                return True
        return False

    def _is_cam_quality(self, title):
        """Check if title indicates CAM quality."""
        for keyword in self.CAM_KEYWORDS:
            if keyword in title:
                return True
        return False

    def _meets_quality_requirements(self, title):
        """Check if stream meets quality requirements."""
        # === FIX: Simplified logic with proper fallthrough ===

        # No quality restrictions
        if self.min_quality == 'any' and not self.hd_only:
            log(f"Quality filter: PASS (no restrictions)", 'debug')
            return True

        title_lower = title.lower()

        # HD only mode - reject SD content
        if self.hd_only:
            hd_indicators = ['720p', '1080p', '2160p', '4k', 'uhd', 'fhd']
            has_hd = any(indicator in title_lower for indicator in hd_indicators)
            if not has_hd:
                log(f"Quality filter: REJECT (HD only, no HD indicator) - {title[:50]}", 'debug')
                return False

        # Specific quality requirement (e.g., '1080p')
        if self.min_quality != 'any':
            quality_keywords = self.QUALITY_PATTERNS.get(self.min_quality, [])

            # Check exact match
            for keyword in quality_keywords:
                if keyword in title_lower:
                    log(f"Quality filter: PASS (exact match: {keyword})", 'debug')
                    return True

            # === FIX: Allow HIGHER quality streams ===
            # If user wants 720p, 1080p and 4K should also pass
            quality_hierarchy = {
                '480p': 1,
                '720p': 2,
                '1080p': 3,
                '2160p': 4,
            }

            min_rank = quality_hierarchy.get(self.min_quality, 0)
            for quality_name, rank in quality_hierarchy.items():
                if rank >= min_rank and quality_name in title_lower:
                    log(f"Quality filter: PASS (higher quality: {quality_name} >= {self.min_quality})", 'debug')
                    return True

            log(f"Quality filter: REJECT (required {self.min_quality}, not found) - {title[:50]}", 'debug')
            return False

        return True

    def _is_trusted_source(self, title):
        """Check if stream is from a trusted source."""
        title_lower = title.lower()

        # Check for trusted release groups
        for group in self.TRUSTED_GROUPS:
            if group in title_lower:
                return True

        # Check for standard release patterns
        standard_patterns = [
            r'\b(bluray|web-dl|webrip|brrip|bdrip)\b',
            r'\b(x264|x265|h264|h265|hevc)\b'
        ]

        for pattern in standard_patterns:
            if re.search(pattern, title_lower):
                return True

        return False

    def _matches_language(self, stream):
        """Check if stream matches language filter."""
        if not self.language_filter:
            return True

        title = stream.get('title', '').lower()

        # Check if any required language is in title
        for lang in self.language_filter:
            if lang in title:
                return True

        # If no language specified in title, assume it passes
        # (to avoid filtering too aggressively)
        return True

    def _log_filter_stats(self, total, remaining):
        """Log filtering statistics."""
        filtered = total - remaining
        if filtered > 0 or self.filtered_count['bypassed'] > 0:
            log(f"Filtered {filtered}/{total} streams:", 'info')
            for reason, count in self.filtered_count.items():
                if count > 0:
                    if reason == 'bypassed':
                        log(f"  ✓ {reason}: {count} (filter bypassed)", 'info')
                    else:
                        log(f"  {reason}: {count}", 'info')

    def get_filter_summary(self):
        """Get a summary of filtered content."""
        total_filtered = sum(self.filtered_count.values())
        if total_filtered == 0:
            return None

        summary = []
        if self.filtered_count['adult'] > 0:
            summary.append(f"adult: {self.filtered_count['adult']}")
        if self.filtered_count['cam'] > 0:
            summary.append(f"low quality: {self.filtered_count['cam']}")
        if self.filtered_count['seeders'] > 0:
            summary.append(f"low seeders: {self.filtered_count['seeders']}")

        return ', '.join(summary) if summary else None


class SafetyPresets:
    """Predefined safety level configurations."""

    PRESETS = {
        'relaxed': {
            'exclude_adult': True,
            'exclude_cam': False,
            'min_seeders': 0,
            'whitelist_mode': False,
            'trusted_only': False
        },
        'standard': {
            'exclude_adult': True,
            'exclude_cam': True,
            'min_seeders': 10,
            'whitelist_mode': False,
            'trusted_only': False
        },
        'strict': {
            'exclude_adult': True,
            'exclude_cam': True,
            'min_seeders': 20,
            'whitelist_mode': False,
            'trusted_only': True
        },
        'paranoid': {
            'exclude_adult': True,
            'exclude_cam': True,
            'min_seeders': 50,
            'whitelist_mode': True,
            'trusted_only': True
        }
    }

    @staticmethod
    def apply_preset(level):
        """Apply a safety preset."""
        if level not in SafetyPresets.PRESETS:
            return

        preset = SafetyPresets.PRESETS[level]
        for key, value in preset.items():
            Settings.set(key, value)
