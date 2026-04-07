"""Premium server selection dialog for Little Fox."""

import xbmcgui
from urllib.parse import unquote_plus
from lib.logger import log


class ServerSelectDialog(xbmcgui.WindowXMLDialog):
    """
    Premium server selection dialog.

    Item properties set per server:
      url           — embed_url (selection key)
      resolution    — '1080p' | '720p' | '480p' | 'SD'  (drives XML badge colors)
      badge_res     — quality label text shown in left badge
      badge_svc     — provider name (bottom badge)
      cached_status — 'instant' | 'cached' | 'uncached'  (drives accent bar color)
      title_clean   — server name
      tags_line     — colored chip badges: [host_type]  [LANG]
      detail_line   — full audio language name
      provider      — provider name (small label below badge_svc)
      size_text     — '' (not applicable for Fox)
      speed_text    — '' (not applicable for Fox)

    Window properties:
      item.title       — show title + episode (e.g. "Show  S01E05")
      item.year        — year string
      item.year_rating — "2024   |   8.5 / 10"
      item.plot        — synopsis
      item.poster      — poster URL
      item.fanart      — fanart URL
      stream_count     — "N servers"
    """

    def __init__(self, xml_file, addon_path, item_information=None, servers=None):
        super().__init__()
        self.item_information = item_information or {}
        self.servers = servers or []
        self.selected_url = None
        self.display_list = None
        log(f"ServerSelectDialog: {len(self.servers)} servers")

    def onInit(self):
        try:
            self.display_list = self.getControl(1000)
            self._set_item_information()
            self._populate_servers()
            if self.display_list.size() > 0:
                self.setFocusId(1000)
        except Exception as e:
            import traceback
            log(f"onInit error: {e}\n{traceback.format_exc()}", 'error')

    def onAction(self, action):
        if action in (xbmcgui.ACTION_NAV_BACK, xbmcgui.ACTION_PREVIOUS_MENU, 10):
            self.close()

    def onClick(self, control_id):
        if control_id == 1000:
            try:
                item = self.display_list.getSelectedItem()
                self.selected_url = item.getProperty('url')
                log(f"Selected: {self.selected_url[:80]}")
                self.close()
            except Exception as e:
                log(f"onClick error: {e}", 'error')
        elif control_id == 2999:
            self.close()

    def doModal(self):
        super().doModal()
        return self.selected_url

    # ─────────────────────────────────────────────────────────────────────────
    # RIGHT PANEL — item information
    # ─────────────────────────────────────────────────────────────────────────

    def _set_item_information(self):
        info = self.item_information

        # Title with episode label
        title = info.get('title', 'Unknown')
        season = info.get('season', '')
        episode = info.get('episode', '')
        if season and episode:
            self.setProperty('item.title', f"{title}  S{str(season).zfill(2)}E{str(episode).zfill(2)}")
        else:
            self.setProperty('item.title', title)

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
            self.setProperty('item.year_rating', f"{year}   |   {rating} / 10")
        elif year:
            self.setProperty('item.year_rating', year)
        elif rating:
            self.setProperty('item.year_rating', f"{rating} / 10")

        self.setProperty('item.year',   year)
        self.setProperty('item.rating', rating)

        # Plot
        plot = info.get('plot', '')
        if plot:
            self.setProperty('item.plot', unquote_plus(plot))

        # Artwork
        poster = unquote_plus(info.get('poster', ''))
        fanart = unquote_plus(info.get('fanart', ''))
        thumb  = unquote_plus(info.get('thumbnail', info.get('thumb', '')))

        self.setProperty('item.poster', poster or thumb or fanart)
        if fanart:
            self.setProperty('item.fanart', fanart)

    # ─────────────────────────────────────────────────────────────────────────
    # LEFT PANEL — server list
    # ─────────────────────────────────────────────────────────────────────────

    def _populate_servers(self):
        log(f"Populating {len(self.servers)} servers")
        self.display_list.reset()
        self.setProperty('stream_count', f"{len(self.servers)} servers")

        added = 0
        for idx, server in enumerate(self.servers):
            try:
                url           = server.get('embed_url', '')
                quality       = server.get('quality', 'Auto')
                resolution    = self._normalise_resolution(quality)
                badge_res     = self._badge_res(quality)
                cached_status = self._quality_to_status(quality)
                badge_svc     = server.get('provider', 'Unknown')
                server_name   = server.get('server_name') or f'Server {idx + 1}'
                tags_line     = self._tags_line(server)
                detail_line   = self._audio_display(server.get('audio_lang', ''))
                provider      = server.get('provider', 'Unknown')

                item = xbmcgui.ListItem(label=server_name)
                item.setProperty('url',           url)
                item.setProperty('resolution',    resolution)
                item.setProperty('badge_res',     badge_res)
                item.setProperty('cached_status', cached_status)
                item.setProperty('badge_svc',     badge_svc)
                item.setProperty('title_clean',   server_name)
                item.setProperty('tags_line',     tags_line)
                item.setProperty('detail_line',   detail_line)
                item.setProperty('provider',      provider)
                item.setProperty('size_text',     '')
                item.setProperty('speed_text',    '')

                self.display_list.addItem(item)
                added += 1

            except Exception as e:
                import traceback
                log(f"Error at server {idx}: {e}\n{traceback.format_exc()}", 'error')

        log(f"Added {added}/{len(self.servers)} items")

    # ─────────────────────────────────────────────────────────────────────────
    # Per-server property builders
    # ─────────────────────────────────────────────────────────────────────────

    def _normalise_resolution(self, quality):
        """Map quality string to the resolution key the XML badge system expects."""
        q = (quality or '').upper()
        if '1080' in q or q == 'FHD':
            return '1080p'
        if '720' in q or q == 'HD':
            return '720p'
        if '480' in q:
            return '480p'
        return 'SD'

    def _badge_res(self, quality):
        """Human-readable label for the left resolution badge."""
        q = (quality or '').upper()
        if '1080' in q:
            return '1080p'
        if '720' in q:
            return '720p'
        if q == 'HD':
            return 'HD'
        if '480' in q:
            return '480p'
        if q == 'SD':
            return 'SD'
        return quality or 'Auto'

    def _quality_to_status(self, quality):
        """
        Map quality to accent bar color key.
          instant  → green  (1080p — best quality)
          cached   → amber  (720p / HD — good quality)
          uncached → slate  (480p / SD / Auto — lower quality)
        """
        q = (quality or '').upper()
        if '1080' in q or q == 'FHD':
            return 'instant'
        if '720' in q or q == 'HD':
            return 'cached'
        return 'uncached'

    def _audio_display(self, lang_code):
        """Full language name from ISO code."""
        return {
            'ar': 'Arabic',
            'en': 'English Subs',
            'tr': 'Turkish',
        }.get(lang_code, lang_code or 'Unknown')

    def _chip(self, text, chip_type='default'):
        """Wrap text in a colored [bracket] chip badge."""
        COLORS = {
            'host':    'FF4A9EFF',   # blue  — host type
            'lang_ar': 'FF2ECC71',   # green — Arabic
            'lang_en': 'FF5BC0DE',   # cyan  — English
            'lang_tr': 'FFFFB347',   # amber — Turkish
            'default': 'FF999999',   # gray
        }
        color = COLORS.get(chip_type, COLORS['default'])
        return f'[COLOR {color}][{text}][/COLOR]'

    def _tags_line(self, server):
        """Build chip badges line: [host_type]  [LANG]"""
        tags = []

        host = server.get('host_type', '')
        if host and host != 'other':
            tags.append(self._chip(host, 'host'))

        lang = server.get('audio_lang', '')
        lang_chips = {
            'ar': ('AR', 'lang_ar'),
            'en': ('EN', 'lang_en'),
            'tr': ('TR', 'lang_tr'),
        }
        if lang in lang_chips:
            label, chip_type = lang_chips[lang]
            tags.append(self._chip(label, chip_type))

        return '  '.join(tags)
