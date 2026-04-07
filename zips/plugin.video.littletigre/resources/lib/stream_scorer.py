"""Stream confidence scoring and sorting - CLEAN encoding with proper metadata display."""

import re
from resources.lib.logger import log


class StreamScorer:
    """Calculate confidence scores for streams with speed indicators and color coding."""

    # Scoring weights
    SCORE_CACHED = 100
    SCORE_HIGH_SEEDERS_100 = 50
    SCORE_HIGH_SEEDERS_50 = 30
    SCORE_TRUSTED_GROUP = 40
    SCORE_STANDARD_NAMING = 20
    SCORE_BLURAY_WEBDL = 25
    SCORE_4K = 15
    SCORE_1080P = 10
    SCORE_720P = 5

    # Speed bonuses
    SCORE_INSTANT_PLAY = 150
    SCORE_FAST_PLAY = 50
    PENALTY_SLOW_PLAY = -20

    # Negative scores
    PENALTY_LOW_SEEDERS = -30
    PENALTY_NO_SEEDERS = -50
    PENALTY_UNKNOWN_SOURCE = -10

    # Quality order
    QUALITY_ORDER = {
        '2160p': 4,
        '1080p': 3,
        '720p': 2,
        '480p': 1,
        'unknown': 0
    }

    # Trusted release groups
    TRUSTED_GROUPS = [
        'yts', 'yify', 'rarbg', 'eztv', 'ettv', 'tgx', 'galaxyrg',
        'psarips', 'pahe', 'sparks', 'cmrg', 'ntg', 'ion10',
        'tigole', 'qxr', 'scene', 'vxt', 'momentum', 'flux',
        'nahom', 'joy', 'terminal', 'sujaidr'
    ]

    # Kodi color scheme (CLEAN - no emoji encoding issues)
    COLORS = {
        'cached': 'lime',
        'speed_instant': 'lime',
        'speed_fast': 'cyan',
        'speed_medium': 'yellow',
        'speed_slow': 'orange',
        'service': 'deepskyblue',
        'quality_4k': 'gold',
        'quality_1080': 'cyan',
        'quality_720': 'lightblue',
        'quality_low': 'silver',
        'source': 'white',
        'codec': 'lightgrey',
        'hdr': 'orange',
        'audio': 'violet',
        'size': 'yellow',
        'lang': 'khaki',
        'seeders': 'coral',
        'separator': 'dimgray'
    }

    def __init__(self):
        """Initialize scorer."""
        pass

    def score_stream(self, stream):
        """Calculate confidence score for a stream WITH SPEED SCORING."""
        score = 0
        title = stream.get('title', '').lower()
        cached = stream.get('cached', False)
        seeders = stream.get('seeders', 0)

        # Speed detection
        playback_speed = self._detect_playback_speed(stream)
        stream['playback_speed'] = playback_speed

        # Speed-based scoring
        if playback_speed == 'instant':
            score += self.SCORE_INSTANT_PLAY
        elif playback_speed == 'fast':
            score += self.SCORE_FAST_PLAY
        elif playback_speed == 'slow':
            score += self.PENALTY_SLOW_PLAY

        # Cached streams get highest priority
        if cached:
            score += self.SCORE_CACHED

        # Seeder-based scoring
        if seeders >= 100:
            score += self.SCORE_HIGH_SEEDERS_100
        elif seeders >= 50:
            score += self.SCORE_HIGH_SEEDERS_50
        elif seeders < 5 and not cached:
            score += self.PENALTY_LOW_SEEDERS
        elif seeders == 0 and not cached:
            score += self.PENALTY_NO_SEEDERS

        # Trusted release group
        if self._has_trusted_group(title):
            score += self.SCORE_TRUSTED_GROUP

        # Standard naming convention
        if self._has_standard_naming(title):
            score += self.SCORE_STANDARD_NAMING

        # Quality bonus
        if 'bluray' in title or 'web-dl' in title or 'webrip' in title:
            score += self.SCORE_BLURAY_WEBDL

        # Resolution bonus
        if '2160p' in title or '4k' in title:
            score += self.SCORE_4K
        elif '1080p' in title:
            score += self.SCORE_1080P
        elif '720p' in title:
            score += self.SCORE_720P

        stream['confidence_score'] = score
        stream['confidence_level'] = self._get_confidence_level(score, cached)

        return stream

    def _detect_playback_speed(self, stream):
        """
        Detect how fast this stream will start playing.

        Returns:
        - 'instant': Direct CDN links (0-2 seconds)
        - 'fast': Simple resolution (2-5 seconds)
        - 'medium': Standard resolution (5-10 seconds)
        - 'slow': Multi-step resolution (10-20 seconds)
        """
        url = stream.get('url', '')
        cached = stream.get('cached', False)

        # INSTANT PLAYBACK (Direct CDN URLs)
        instant_domains = [
            'tb-cdn.st',
            'download.real-debrid.com',
            'premiumize.me/dl/',
            'alldebrid.com/dl/',
            '.m3u8',
        ]

        for domain in instant_domains:
            if domain in url.lower():
                log(f"Speed: INSTANT - Direct CDN link detected: {domain}")
                return 'instant'

        # FAST PLAYBACK (Simple resolution)
        if 'stremthru.elfhosted.com/playback/' in url.lower():
            log(f"Speed: FAST - StremThru playback URL")
            return 'fast'

        if 'mediafusion.elfhosted.com/playback/' in url.lower():
            log(f"Speed: FAST - MediaFusion playback URL")
            return 'fast'

        # MEDIUM PLAYBACK (Standard resolution)
        if 'comet.elfhosted.com/playback/' in url.lower():
            log(f"Speed: MEDIUM - Comet playback URL")
            return 'medium'

        # SLOW PLAYBACK (Multi-step resolution)
        if 'torrentio.strem.fun/resolve/' in url.lower():
            log(f"Speed: SLOW - Torrentio resolve URL")
            return 'slow'

        if url.startswith('magnet:'):
            log(f"Speed: SLOW - Magnet link")
            return 'slow'

        # Default: medium speed
        log(f"Speed: MEDIUM - Unknown URL type")
        return 'medium'

    def _has_trusted_group(self, title):
        """Check if title contains a trusted release group."""
        for group in self.TRUSTED_GROUPS:
            if group in title:
                return True
        return False

    def _has_standard_naming(self, title):
        """Check if title follows standard naming conventions."""
        patterns = [
            r'\d{4}\.',
            r'\.(bluray|web-dl|webrip|brrip|bdrip)\.',
            r'\.(x264|x265|h264|h265|hevc)\b'
        ]
        matches = sum(1 for p in patterns if re.search(p, title))
        return matches >= 2

    def _get_confidence_level(self, score, cached):
        """Get confidence level based on score."""
        if cached:
            return 'instant'
        elif score >= 100:
            return 'high'
        elif score >= 50:
            return 'medium'
        elif score >= 20:
            return 'low'
        else:
            return 'minimal'

    def sort_streams(self, streams, sort_by='confidence'):
        """Sort streams based on criteria."""
        if sort_by == 'confidence':
            return sorted(streams, key=lambda s: s.get('confidence_score', 0), reverse=True)
        elif sort_by == 'speed':
            speed_order = {'instant': 4, 'fast': 3, 'medium': 2, 'slow': 1}
            return sorted(streams, key=lambda s: (
                speed_order.get(s.get('playback_speed', 'medium'), 2),
                s.get('confidence_score', 0)
            ), reverse=True)
        elif sort_by == 'quality':
            return sorted(streams, key=lambda s: self._get_quality_score(s), reverse=True)
        elif sort_by == 'resolution':
            # NEW: Multi-level hierarchical sorting
            return self._sort_by_resolution_hierarchical(streams)
        elif sort_by == 'seeders':
            return sorted(streams, key=lambda s: s.get('seeders', 0), reverse=True)
        elif sort_by == 'size':
            return sorted(streams, key=lambda s: s.get('size_gb', 0), reverse=True)
        else:
            return streams

    def _sort_by_resolution_hierarchical(self, streams):
        """
        HIERARCHICAL SORTING: Resolution first, then quality within each tier.

        Primary Sort: Resolution (4K > 1080p > 720p > 480p)
        Secondary Sort (within each resolution):
          1. Cached status (cached first)
          2. Source quality (REMUX > BluRay > WEB-DL > WEBRip > HDTV)
          3. Playback speed (instant > fast > medium > slow)
          4. Seeders (for uncached)

        Result: Beautiful tier-based presentation!
        """

        # Resolution ranks (higher = better)
        resolution_ranks = {
            '2160p': 4,
            '1080p': 3,
            '720p': 2,
            '480p': 1,
            'unknown': 0
        }

        # Source quality ranks (higher = better)
        source_ranks = {
            'remux': 6,
            'bluray': 5,
            'web-dl': 4,
            'webrip': 3,
            'hdtv': 2,
            'dvdrip': 1,
            'unknown': 0
        }

        # Playback speed ranks (higher = better)
        speed_ranks = {
            'instant': 4,
            'fast': 3,
            'medium': 2,
            'slow': 1
        }

        def get_sort_key(stream):
            """Generate multi-level sort key for a stream."""
            title = stream.get('title', '').lower()

            # Level 1: Resolution (PRIMARY)
            resolution_rank = 0
            for res, rank in resolution_ranks.items():
                if res in title:
                    resolution_rank = rank
                    break

            # Level 2: Cached status (cached > uncached)
            cached = stream.get('cached', False)
            cached_rank = 1 if cached else 0

            # Level 3: Source quality
            source_rank = 0
            if 'remux' in title or 'bdremux' in title:
                source_rank = source_ranks['remux']
            elif 'bluray' in title or 'blu-ray' in title or 'brrip' in title:
                source_rank = source_ranks['bluray']
            elif 'web-dl' in title or 'webdl' in title:
                source_rank = source_ranks['web-dl']
            elif 'webrip' in title or 'web-rip' in title:
                source_rank = source_ranks['webrip']
            elif 'hdtv' in title:
                source_rank = source_ranks['hdtv']
            elif 'dvdrip' in title:
                source_rank = source_ranks['dvdrip']

            # Level 4: Playback speed (for cached streams)
            speed = stream.get('playback_speed', 'medium')
            speed_rank = speed_ranks.get(speed, 2)

            # Level 5: Seeders (for uncached streams)
            seeders = stream.get('seeders', 0)

            # Return composite key: (resolution, cached, source, speed, seeders)
            # All reverse=True, so higher values = better
            return (
                resolution_rank,     # 4K first, then 1080p, etc.
                cached_rank,         # Cached before uncached
                source_rank,         # REMUX before BluRay, etc.
                speed_rank,          # Instant before slow
                seeders              # More seeders better (for uncached)
            )

        return sorted(streams, key=get_sort_key, reverse=True)

    def _get_quality_score(self, stream):
        """Get quality score for sorting."""
        title = stream.get('title', '').lower()
        for quality, rank in self.QUALITY_ORDER.items():
            if quality in title:
                return rank
        return 0

    def group_by_confidence(self, streams):
        """Group streams by confidence level."""
        groups = {
            'instant': [],
            'high': [],
            'medium': [],
            'low': [],
            'minimal': []
        }
        for stream in streams:
            level = stream.get('confidence_level', 'minimal')
            groups[level].append(stream)
        return groups

    def _color(self, text, color_key):
        """Apply Kodi color tag to text."""
        color = self.COLORS.get(color_key, 'white')
        return f"[COLOR {color}]{text}[/COLOR]"

    def _get_speed_indicator(self, playback_speed):
        """
        Get CLEAN speed indicator (NO EMOJI ENCODING ISSUES).

        Returns colored text like:
        [COLOR lime]INSTANT[/COLOR] | [COLOR cyan]FAST[/COLOR] | etc.
        """
        speed_map = {
            'instant': ('INSTANT', 'speed_instant'),
            'fast': ('FAST', 'speed_fast'),
            'medium': ('OK', 'speed_medium'),
            'slow': ('SLOW', 'speed_slow')
        }

        label, color_key = speed_map.get(playback_speed, ('OK', 'speed_medium'))

        return self._color(label, color_key)

    def format_stream_stremio_style(self, stream, show_size=True, show_seeders=True):
        """
        Format stream title with CLEAN COLOR CODING + SPEED INDICATOR.

        FIXED: NO MORE ENCODING ISSUES - Clean UTF-8 text only!

        Format:
        [SPEED] [SERVICE âš¡] Addon | Resolution | Source | Codec | HDR | Audio | Size | Lang | Seeders
        """
        parts = []

        # === SPEED INDICATOR (CLEAN TEXT) ===
        playback_speed = stream.get('playback_speed', 'medium')
        speed_indicator = self._get_speed_indicator(playback_speed)
        parts.append(speed_indicator)

        # Get metadata
        original_title = stream.get('title', '')
        description = stream.get('description', original_title)
        addon_name = stream.get('addon', 'Unknown')
        cached = stream.get('cached', False)
        debrid_service = stream.get('debrid_service')

        # === SERVICE INDICATOR (with DEBRID SERVICE) ===
        service_prefix = self._get_colored_service_indicator(addon_name, cached, debrid_service)
        parts.append(service_prefix)

        # === ADDON NAME ===
        addon_clean = self._clean_addon_name(addon_name)
        if addon_clean:
            parts.append(addon_clean)

        # Parse metadata
        metadata = self._parse_stream_metadata(description, stream, original_title)

        # === RESOLUTION (Color-coded) ===
        if metadata['quality'] and metadata['quality'] != 'unknown':
            quality_colored = self._get_colored_quality(metadata['quality'])
            parts.append(quality_colored)

        # === SOURCE TYPE ===
        if metadata['source_type']:
            parts.append(self._color(metadata['source_type'], 'source'))

        # === VIDEO CODEC ===
        if metadata['video_codec']:
            parts.append(self._color(metadata['video_codec'], 'codec'))

        # === HDR INFORMATION ===
        if metadata['hdr']:
            for hdr_type in metadata['hdr']:
                parts.append(self._color(hdr_type, 'hdr'))

        # === AUDIO CODEC ===
        if metadata['audio_codec']:
            parts.append(self._color(metadata['audio_codec'], 'audio'))

        # === AUDIO CHANNELS ===
        if metadata['audio_channels']:
            parts.append(self._color(metadata['audio_channels'], 'audio'))

        # === FILE SIZE ===
        if show_size:
            size = stream.get('size_gb', 0)
            if size > 0:
                size_text = f"{size:.2f}GB"
                parts.append(self._color(size_text, 'size'))

        # === LANGUAGES ===
        if metadata['languages']:
            lang_display = '/'.join(metadata['languages'][:3])
            parts.append(self._color(lang_display, 'lang'))

        # === SUBTITLES ===
        if metadata['subtitles']:
            sub_display = 'SUB:' + '/'.join(metadata['subtitles'][:3])
            parts.append(self._color(sub_display, 'lang'))

        # === SEEDERS (only for uncached) ===
        if show_seeders and not cached:
            seeders = stream.get('seeders', 0)
            if seeders > 0:
                if seeders >= 100:
                    seeder_text = self._color(f"S:{seeders}", 'cached')
                elif seeders >= 30:
                    seeder_text = self._color(f"S:{seeders}", 'size')
                else:
                    seeder_text = self._color(f"S:{seeders}", 'seeders')
                parts.append(seeder_text)

        # Join with clean separator
        separator = self._color(' | ', 'separator')
        return separator.join(parts)

    def _get_colored_service_indicator(self, addon_name, cached, debrid_service=None):
        """Get service indicator with color coding."""
        addon_lower = addon_name.lower()

        service = None

        # Try to get service from debrid_service field first
        if debrid_service:
            service_map = {
                'realdebrid': 'RD',
                'torbox': 'TB',
                'premiumize': 'PM',
                'alldebrid': 'AD'
            }
            service = service_map.get(debrid_service)

        # Fallback: detect from addon name
        if not service:
            if 'real-debrid' in addon_lower or 'realdebrid' in addon_lower:
                service = 'RD'
            elif 'torbox' in addon_lower:
                service = 'TB'
            elif 'premiumize' in addon_lower:
                service = 'PM'
            elif 'alldebrid' in addon_lower:
                service = 'AD'
            elif 'comet' in addon_lower:
                service = 'CM'
            elif 'stremthru' in addon_lower:
                service = 'ST'
            elif 'mediafusion' in addon_lower:
                service = 'MF'
            elif 'torrentio' in addon_lower:
                service = 'TR'
            else:
                service = '??'

        service_colored = self._color(service, 'service')

        if cached:
            # CLEAN cached indicator (no emoji encoding issues)
            cached_icon = self._color('[CACHED]', 'cached')
            return f"[{service_colored} {cached_icon}]"
        else:
            return f"[{service_colored}]"

    def _get_colored_quality(self, quality):
        """Get color-coded quality indicator."""
        if '2160p' in quality or '4K' in quality.upper():
            return self._color(quality, 'quality_4k')
        elif '1080p' in quality:
            return self._color(quality, 'quality_1080')
        elif '720p' in quality:
            return self._color(quality, 'quality_720')
        else:
            return self._color(quality, 'quality_low')

    def _clean_addon_name(self, addon_name):
        """Clean addon name by removing service indicators."""
        cleaned = addon_name

        # Remove service tags
        patterns_to_remove = [
            r'\[RD[^\]]*\]',
            r'\[TB[^\]]*\]',
            r'\[PM[^\]]*\]',
            r'\[AD[^\]]*\]',
            r'\[MF[^\]]*\]',
            r'\[ST[^\]]*\]',
            r'\[TR[^\]]*\]',
        ]

        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, '', cleaned)

        return cleaned.strip()

    def _parse_stream_metadata(self, description, stream, original_title=''):
        """Parse metadata from stream description and title."""
        metadata = {
            'quality': '',
            'source_type': '',
            'video_codec': '',
            'hdr': [],
            'audio_codec': '',
            'audio_channels': '',
            'languages': [],
            'subtitles': [],
        }

        full_text = f"{description} {original_title}".lower()

        if not full_text.strip():
            return metadata

        # Extract quality
        if '2160p' in full_text or '4k' in full_text or 'uhd' in full_text:
            metadata['quality'] = '2160p'
        elif '1080p' in full_text or 'fhd' in full_text:
            metadata['quality'] = '1080p'
        elif '720p' in full_text or 'hd' in full_text:
            metadata['quality'] = '720p'
        elif '480p' in full_text or 'sd' in full_text:
            metadata['quality'] = '480p'

        # Extract source type
        if 'remux' in full_text or 'bdremux' in full_text:
            metadata['source_type'] = 'REMUX'
        elif 'bluray' in full_text or 'blu-ray' in full_text or 'brrip' in full_text:
            metadata['source_type'] = 'BluRay'
        elif 'web-dl' in full_text or 'webdl' in full_text:
            metadata['source_type'] = 'WEB-DL'
        elif 'webrip' in full_text or 'web-rip' in full_text:
            metadata['source_type'] = 'WEBRip'
        elif 'hdtv' in full_text:
            metadata['source_type'] = 'HDTV'

        # Extract video codec
        if 'hevc' in full_text or 'h.265' in full_text or 'h265' in full_text or 'x265' in full_text:
            metadata['video_codec'] = 'HEVC'
        elif 'h.264' in full_text or 'h264' in full_text or 'x264' in full_text:
            metadata['video_codec'] = 'H.264'
        elif 'av1' in full_text:
            metadata['video_codec'] = 'AV1'

        # Extract HDR
        if 'dolby vision' in full_text or 'dv' in full_text.split():
            metadata['hdr'].append('DV')
        if 'hdr10+' in full_text:
            metadata['hdr'].append('HDR10+')
        elif 'hdr10' in full_text:
            metadata['hdr'].append('HDR10')
        elif 'hdr' in full_text:
            metadata['hdr'].append('HDR')

        # Extract audio codec
        if 'dts-hd ma' in full_text or 'dtshd ma' in full_text:
            metadata['audio_codec'] = 'DTS-HD MA'
        elif 'dts-hd' in full_text or 'dtshd' in full_text:
            metadata['audio_codec'] = 'DTS-HD'
        elif 'dts-x' in full_text or 'dtsx' in full_text:
            metadata['audio_codec'] = 'DTS:X'
        elif 'dts' in full_text:
            metadata['audio_codec'] = 'DTS'
        elif 'atmos' in full_text:
            metadata['audio_codec'] = 'Atmos'
        elif 'truehd' in full_text:
            metadata['audio_codec'] = 'TrueHD'
        elif 'dd+' in full_text or 'ddp' in full_text or 'eac3' in full_text:
            metadata['audio_codec'] = 'DD+'
        elif 'dd5.1' in full_text or 'dd 5.1' in full_text:
            metadata['audio_codec'] = 'DD5.1'
        elif 'ac3' in full_text or 'dd' in full_text:
            metadata['audio_codec'] = 'DD'
        elif 'aac' in full_text:
            metadata['audio_codec'] = 'AAC'

        # Extract audio channels
        channel_patterns = [
            (r'7\.1\.4', '7.1.4'),
            (r'7\.1\.2', '7.1.2'),
            (r'7\.1', '7.1'),
            (r'5\.1', '5.1'),
            (r'2\.0', '2.0'),
        ]

        for pattern, display in channel_patterns:
            if re.search(pattern, full_text):
                metadata['audio_channels'] = display
                break

        # Extract languages
        language_map = {
            'english': 'EN', 'eng': 'EN',
            'multi': 'Multi',
            'dual audio': 'Dual',
        }

        for lang_key, lang_code in language_map.items():
            if re.search(r'\b' + re.escape(lang_key) + r'\b', full_text):
                if lang_code not in metadata['languages']:
                    metadata['languages'].append(lang_code)

        # Extract subtitles
        if 'subtitle' in full_text or ' sub' in full_text or 'subs' in full_text:
            metadata['subtitles'].append('Yes')

        return metadata

    def get_confidence_label(self, level):
        """Get human-readable label for confidence level."""
        labels = {
            'instant': 'Instant Play - Cached',
            'high': 'High Quality - Verified',
            'medium': 'Good Quality',
            'low': 'Available',
            'minimal': 'Low Confidence'
        }
        return labels.get(level, 'Unknown')


class StreamAnalyzer:
    """Analyze stream metadata."""

    @staticmethod
    def extract_quality(title):
        """Extract quality from title."""
        title_lower = title.lower()

        if '2160p' in title_lower or '4k' in title_lower:
            return '2160p'
        elif '1080p' in title_lower:
            return '1080p'
        elif '720p' in title_lower:
            return '720p'
        elif '480p' in title_lower:
            return '480p'
        else:
            return 'unknown'

    @staticmethod
    def extract_source(title):
        """Extract source type from title."""
        title_lower = title.lower()

        if 'bluray' in title_lower or 'brrip' in title_lower:
            return 'BluRay'
        elif 'web-dl' in title_lower:
            return 'WEB-DL'
        elif 'webrip' in title_lower:
            return 'WEBRip'
        elif 'hdtv' in title_lower:
            return 'HDTV'
        else:
            return 'Unknown'

    @staticmethod
    def extract_codec(title):
        """Extract codec from title."""
        title_lower = title.lower()

        if 'x265' in title_lower or 'hevc' in title_lower:
            return 'HEVC'
        elif 'x264' in title_lower or 'h264' in title_lower:
            return 'H.264'
        else:
            return 'Unknown'

    @staticmethod
    def parse_size(size_str):
        """Parse file size string to GB."""
        if not size_str:
            return 0

        size_str = size_str.lower()

        try:
            if 'gb' in size_str:
                return float(size_str.replace('gb', '').strip())
            elif 'mb' in size_str:
                return float(size_str.replace('mb', '').strip()) / 1024
            elif 'tb' in size_str:
                return float(size_str.replace('tb', '').strip()) * 1024
        except ValueError:
            pass

        return 0
