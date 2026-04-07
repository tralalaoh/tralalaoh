"""Premium source selection dialog for Little Tigre."""

import re
import xbmcgui
from urllib.parse import unquote_plus
from resources.lib.logger import log, log_debug


class SourceSelectDialog(xbmcgui.WindowXMLDialog):
    """
    Premium stream selection dialog.

    Item properties set per stream:
      cached_status  — "instant" | "cached" | "uncached"  (drives accent bar color)
      resolution     — "2160p" | "1080p" | "720p" | "480p" | "SD"
      title_clean    — release name stripped of tags/emoji
      meta_line      — "Provider  ·  Source  ·  Codec  ·  Audio"
      detail_line    — "Lang  ·  HDR  ·  [Debrid]" or "S:N"
      size_text      — "15.24 GB" or ""
      speed_text     — "INSTANT" | "FAST" | "OK" | "SLOW"
      icon           — path to status icon
      url            — playback URL

    Window properties:
      item.title      — content title
      item.year_rating — "2024  |  8.5 / 10"
      item.plot       — synopsis
      item.poster     — poster URL
      item.fanart     — fanart URL
      stream_count    — "23 streams"
    """

    def __init__(self, xml_file, addon_path, item_information=None, sources=None):
        super(SourceSelectDialog, self).__init__()
        self.item_information = item_information or {}
        self.sources = sources or []
        self.selected_url = None
        self.display_list = None
        log(f"SourceSelectDialog: {len(self.sources)} streams")

    def onInit(self):
        try:
            self.display_list = self.getControl(1000)
            self._set_item_information()
            self._populate_sources()
            if self.display_list.size() > 0:
                self.setFocusId(1000)
        except Exception as e:
            import traceback
            log(f"onInit error: {e}\n{traceback.format_exc()}")

    def onAction(self, action):
        if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, 10):
            self.close()

    def onClick(self, control_id):
        if control_id == 1000:
            try:
                item = self.display_list.getSelectedItem()
                self.selected_url = item.getProperty("url")
                log(f"Selected: {self.selected_url[:80]}")
                self.close()
            except Exception as e:
                log(f"onClick error: {e}")
        elif control_id == 2999:
            self.close()

    def doModal(self):
        super(SourceSelectDialog, self).doModal()
        return self.selected_url

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT PANEL — item information
    # ─────────────────────────────────────────────────────────────────────────

    def _set_item_information(self):
        info = self.item_information

        # Title
        title = info.get('title', 'Unknown')
        if info.get('type') == 'episode':
            season = info.get('season', '')
            episode = info.get('episode', '')
            showtitle = info.get('showtitle', title)
            if season and episode:
                title = f"{showtitle}  S{str(season).zfill(2)}E{str(episode).zfill(2)}"
            else:
                title = showtitle
        self.setProperty("item.title", title)

        # Year + Rating combined
        year = str(info.get('year', '')).strip()
        rating_raw = info.get('rating', '')
        rating = ''
        if rating_raw:
            try:
                rating = f"{float(rating_raw):.1f}"
            except (ValueError, TypeError):
                rating = str(rating_raw).strip()

        if year and rating:
            self.setProperty("item.year_rating", f"{year}   |   {rating} / 10")
        elif year:
            self.setProperty("item.year_rating", year)
        elif rating:
            self.setProperty("item.year_rating", f"{rating} / 10")
        else:
            self.setProperty("item.year_rating", "")

        # Separate year and rating for IMDb badge layout in XML
        self.setProperty("item.year",   year)
        self.setProperty("item.rating", rating)

        # Plot
        plot = info.get('plot', '')
        if plot:
            self.setProperty("item.plot", unquote_plus(plot))

        # Artwork
        poster = unquote_plus(info.get('poster', ''))
        fanart = unquote_plus(info.get('fanart', ''))
        thumb  = unquote_plus(info.get('thumbnail', info.get('thumb', '')))

        self.setProperty("item.poster", poster or thumb or fanart)
        if fanart:
            self.setProperty("item.fanart", fanart)

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT PANEL — stream list
    # ─────────────────────────────────────────────────────────────────────────

    def _populate_sources(self):
        log(f"Populating {len(self.sources)} sources")
        self.display_list.reset()

        try:
            from resources.lib.stream_scorer import StreamScorer
            sorted_sources = StreamScorer().sort_streams(self.sources, sort_by='resolution')
        except Exception as e:
            log(f"Sort failed ({e}), using fallback")
            sorted_sources = sorted(
                self.sources,
                key=lambda s: (0 if s.get('cached', False) else 1, -s.get('confidence_score', 0))
            )

        self.setProperty("stream_count", f"{len(sorted_sources)} streams")

        added = 0
        for idx, source in enumerate(sorted_sources):
            try:
                url   = source.get('url', '')
                title = source.get('title', 'Unknown')

                cached_status = self._cached_status(source)
                resolution    = self._resolution(source, title)
                title_clean   = self._clean_title(title)
                meta_line     = self._meta_line(source, title)
                detail_line   = self._detail_line(source, title)
                size_text     = self._size_text(source)
                speed_text    = self._speed_text(source)
                icon          = self._icon_path(source)
                # New display properties for card layout
                provider      = source.get('addon', 'Unknown')
                badge_res     = self._badge_res(resolution)
                badge_svc     = self._badge_svc(source)
                tags_line     = self._tags_line(source)

                item = xbmcgui.ListItem(label=title_clean)
                item.setProperty("url",          url)
                item.setProperty("cached_status", cached_status)
                item.setProperty("resolution",    resolution)
                item.setProperty("title_clean",   title_clean)
                item.setProperty("meta_line",     meta_line)
                item.setProperty("detail_line",   detail_line)
                item.setProperty("size_text",     size_text)
                item.setProperty("speed_text",    speed_text)
                item.setProperty("icon",          icon)
                item.setProperty("provider",      provider)
                item.setProperty("badge_res",     badge_res)
                item.setProperty("badge_svc",     badge_svc)
                item.setProperty("tags_line",     tags_line)

                self.display_list.addItem(item)
                added += 1
                log_debug(f"[{cached_status:8s}] [{resolution:5s}] {title_clean[:60]}")

            except Exception as e:
                import traceback
                log(f"Error at source {idx}: {e}\n{traceback.format_exc()}")
                continue

        log(f"Added {added}/{len(self.sources)} items")

    # ─────────────────────────────────────────────────────────────────────────
    # Per-stream property builders
    # ─────────────────────────────────────────────────────────────────────────

    def _cached_status(self, source):
        """Return 'instant', 'cached', or 'uncached' — drives left accent bar color."""
        if not source.get('cached', False):
            return 'uncached'
        return 'instant' if source.get('playback_speed') == 'instant' else 'cached'

    def _resolution(self, source, title):
        # Use StreamParser result if available, else fall back to title scan
        parsed = source.get('parsed', {})
        res = parsed.get('resolution')
        if res:
            return res
        t = title.lower()
        if '2160p' in t or '4k' in t or 'uhd' in t:
            return '2160p'
        if '1080p' in t or 'fhd' in t:
            return '1080p'
        if '720p' in t:
            return '720p'
        if '480p' in t:
            return '480p'
        return 'SD'

    def _meta_line(self, source, title):
        """Provider  ·  Source  ·  Codec  ·  Audio  ·  Channels"""
        SEP = '  \u00b7  '
        parsed = source.get('parsed', {})
        parts = [source.get('addon', 'Unknown')]

        quality = parsed.get('quality')
        if quality:
            parts.append(quality)

        encode = parsed.get('encode')
        bit_depth = parsed.get('bit_depth')
        if encode:
            # Normalise AVC label to match common display convention
            label = 'H.264' if encode == 'AVC' else encode
            parts.append(f'{label} {bit_depth}' if bit_depth else label)
        elif bit_depth:
            parts.append(bit_depth)

        # All audio tags (e.g. Atmos + TrueHD, or DTS-HD MA alone)
        audio_tags = parsed.get('audio_tags', [])
        if audio_tags:
            parts.extend(audio_tags[:2])  # cap at 2 to avoid overflow

        # Audio channels
        audio_ch = parsed.get('audio_ch', [])
        if audio_ch:
            parts.append(audio_ch[0])

        return SEP.join(parts)

    def _detail_line(self, source, title):
        """
        Third row: Language  ·  Debrid/cache status.
        Visual tags and seeders live in _tags_line() now.
        """
        SEP = '  \u00b7  '
        parsed = source.get('parsed', {})
        parts = []

        # Languages (up to 3)
        langs = parsed.get('languages', [])
        if langs:
            parts.append('/'.join(langs[:3]))

        # Debrid / cached status — green for cached, gray for torrent
        cached = source.get('cached', False)
        debrid = self._debrid_tag(source)
        if cached and debrid:
            parts.append(f'[COLOR FF2ECC71][{debrid} CACHED][/COLOR]')
        elif cached:
            parts.append('[COLOR FF2ECC71][CACHED][/COLOR]')
        else:
            parts.append('[COLOR FF555555][TORRENT][/COLOR]')

        return SEP.join(parts)

    def _size_text(self, source):
        size = source.get('size_gb', 0)
        if size >= 1:
            return f'{size:.2f} GB'
        if size > 0:
            return f'{size * 1024:.0f} MB'
        return ''

    def _speed_text(self, source):
        return {'instant': 'INSTANT', 'fast': 'FAST', 'medium': 'OK', 'slow': 'SLOW'}.get(
            source.get('playback_speed', 'medium'), 'OK'
        )

    def _badge_res(self, resolution):
        """Human-readable resolution label for the left-column badge."""
        return {
            '2160p': '4K UHD',
            '1440p': '2K QHD',
            '1080p': '1080p',
            '720p':  '720p',
            '576p':  '576p',
            '480p':  '480p',
            '360p':  '360p',
        }.get(resolution, resolution or 'SD')

    def _badge_svc(self, source):
        """Service badge label: 'RD+' / 'TB+' etc. for cached, 'TORRENT' for P2P."""
        if source.get('cached', False):
            svc_map = {
                'realdebrid': 'RD+',
                'torbox':     'TB+',
                'premiumize': 'PM+',
                'alldebrid':  'AD+',
                'debridlink': 'DL+',
            }
            return svc_map.get(source.get('debrid_service', ''), 'CACHED')
        return 'TORRENT'

    def _tags_line(self, source):
        """
        Chip-style colored tags row — matches the HTML preview design.

        Order: [Source] [Codec] [Audio] [Ch] [HDR] [DV] [S:N]
        Colors (Kodi color markup):
          - HDR variants → orange  #E8921E
          - DV           → purple  #B45AFF
          - Seeders      → blue    #2A6AAD
          - Everything else → muted gray #555555
        """
        parsed = source.get('parsed', {})
        tags = []

        # Source quality (WEB-DL / BluRay REMUX / etc.)
        quality = parsed.get('quality')
        if quality:
            tags.append(self._chip(quality))

        # Video codec
        encode = parsed.get('encode')
        if encode:
            tags.append(self._chip('H.264' if encode == 'AVC' else encode))

        # Audio codec(s) — cap at 2 to avoid overflow
        for audio in parsed.get('audio_tags', [])[:2]:
            tags.append(self._chip(audio))

        # Audio channels
        audio_ch = parsed.get('audio_ch', [])
        if audio_ch:
            tags.append(self._chip(audio_ch[0]))

        # HDR / visual tags — color-coded
        for vt in parsed.get('visual_tags', [])[:3]:
            vl = vt.lower()
            if 'dv' in vl or 'dolby vision' in vl:
                tags.append(self._chip(vt, 'dv'))
            elif any(k in vl for k in ('hdr', 'hlg')):
                tags.append(self._chip(vt, 'hdr'))
            else:
                tags.append(self._chip(vt))

        # Release flags
        if parsed.get('is_proper'):
            tags.append(self._chip('PROPER', 'proper'))
        if parsed.get('is_repack'):
            tags.append(self._chip('REPACK', 'repack'))
        if parsed.get('is_dubbed'):
            tags.append(self._chip('DUBBED', 'dubbed'))

        # Seeders — only for uncached streams
        if not source.get('cached', False):
            seeders = source.get('seeders', 0)
            if seeders > 0:
                seed_label = f'{seeders:,}' if seeders >= 1000 else str(seeders)
                tags.append(self._chip(f'S:{seed_label}', 'seed'))

        return '  '.join(tags)

    def _chip(self, text, chip_type='default'):
        """
        Wrap text in [brackets] with a Kodi color tag to simulate an HTML chip badge.

        chip_type:
          'hdr'     → orange  (HDR10+, HDR10, HDR, HLG)
          'dv'      → purple  (Dolby Vision)
          'seed'    → blue    (seeder count)
          'default' → dark gray (everything else)
        """
        COLORS = {
            'hdr':     'FFE8921E',
            'dv':      'FFB45AFF',
            'seed':    'FF4A9EFF',
            'proper':  'FF2ECC71',
            'repack':  'FFFFB347',
            'dubbed':  'FF5BC0DE',
            'default': 'FF999999',
        }
        color = COLORS.get(chip_type, COLORS['default'])
        return f'[COLOR {color}][{text}][/COLOR]'

    def _icon_path(self, source):
        base = 'special://home/addons/plugin.video.littletigre/resources/media/icons/'
        if not source.get('cached', False):
            return base + 'uncached.png'
        if source.get('playback_speed') == 'instant':
            return base + 'instant.png'
        return base + 'cached.png'

    def _debrid_tag(self, source):
        """Return short debrid tag like 'RD', 'TB', etc., or None."""
        svc = source.get('debrid_service', '')
        tag_map = {'realdebrid': 'RD', 'torbox': 'TB', 'premiumize': 'PM', 'alldebrid': 'AD'}
        if svc in tag_map:
            return tag_map[svc]

        url   = source.get('url', '').lower()
        title = source.get('title', '').lower()
        for check, tag in [
            ('real-debrid.com', 'RD'), ('download.real-debrid.com', 'RD'),
            ('torbox.app', 'TB'), ('tb-cdn.st', 'TB'),
            ('premiumize.me', 'PM'), ('alldebrid.com', 'AD'),
        ]:
            if check in url:
                return tag
        for check, tag in [
            ('[rd', 'RD'), ('real-debrid', 'RD'),
            ('[tb', 'TB'), ('torbox', 'TB'),
            ('[pm', 'PM'), ('premiumize', 'PM'),
            ('[ad', 'AD'), ('alldebrid', 'AD'),
        ]:
            if check in title:
                return tag
        return None

    def _clean_title(self, title):
        """Strip emoji, debrid tags, size, seeders from release name."""
        # Remove unicode emoji
        emoji_re = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002600-\U000027BF"
            "\U0001F900-\U0001F9FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0000231A-\U0000231B"
            "\U000025AA-\U000025FE"
            "\U00002B50\U00002B55"
            "]+",
            flags=re.UNICODE
        )
        s = emoji_re.sub('', title)
        s = s.replace('\u25a1', '')  # strip stray box char □
        s = re.sub(r'\[(RD|TB|PM|AD|MF|ST|TR)[^\]]*\]', '', s, flags=re.IGNORECASE)
        s = re.sub(r'\[S:\s*\d+\]', '', s)
        s = re.sub(r'\d+\.?\d*\s*(GB|MB)', '', s, flags=re.IGNORECASE)
        return ' '.join(s.split()).strip()
