"""Menu Management - Test menu and settings UI."""

import os
import xbmcgui
import xbmcaddon
import xbmcvfs

from resources.lib.playback_engine import PlaybackEngine
from resources.lib.debrid import test_debrid_connection
from resources.lib.logger import log, log_error


class MainMenu:
    """
    Main menu and UI controller.
    
    Responsibilities:
    - Test menu display
    - Debrid service testing
    - Settings access
    - About dialog
    """
    
    def __init__(self):
        """Initialize menu controller."""
        self.addon = xbmcaddon.Addon()
    
    def show(self):
        """Show main test menu."""
        try:
            dialog = xbmcgui.Dialog()
            
            options = [
                'Test: The Dark Knight (Movie)',
                'Test: Inception (Movie)',
                'Test: Attack on Titan S01E01 (Anime - MAL)',
                'Custom Search',
                'Manage Custom Scrapers',
                'Settings',
                'About'
            ]

            selected = dialog.select('Stremio Bridge - Test Menu', options)

            if selected == 0:
                self._test_dark_knight()
            elif selected == 1:
                self._test_inception()
            elif selected == 2:
                self._test_attack_on_titan()
            elif selected == 3:
                self._custom_search()
            elif selected == 4:
                self._manage_scrapers()
            elif selected == 5:
                self.addon.openSettings()
            elif selected == 6:
                self._show_about()
                
        except Exception as e:
            log_error("show_info failed", e)
            import traceback
            import xbmc
            xbmc.log(f'[Stremio Bridge] show_info exception:\n{traceback.format_exc()}', xbmc.LOGERROR)
            raise
    
    def _test_dark_knight(self):
        """Test with The Dark Knight movie."""
        # Use a fake handle for standalone test
        engine = PlaybackEngine(-1, 'plugin://plugin.video.stremio.bridge')
        engine.play_with_dialog({
            'imdb_id': 'tt0468569',
            'tmdb_id': '155',
            'type': 'movie',
            'title': 'The Dark Knight',
            '_force_standalone': True
        })
    
    def _test_inception(self):
        """Test with Inception movie."""
        engine = PlaybackEngine(-1, 'plugin://plugin.video.stremio.bridge')
        engine.play_with_dialog({
            'imdb_id': 'tt1375666',
            'tmdb_id': '27205',
            'type': 'movie',
            'title': 'Inception',
            '_force_standalone': True
        })
    
    def _test_attack_on_titan(self):
        """Test with Attack on Titan anime."""
        engine = PlaybackEngine(-1, 'plugin://plugin.video.stremio.bridge')
        engine.play_with_dialog({
            'mal_id': '16498',
            'tmdb_id': '1429',
            'type': 'episode',
            'season': '1',
            'episode': '1',
            'title': 'Attack on Titan',
            '_force_standalone': True
        })
    
    def _custom_search(self):
        """Custom search dialog."""
        dialog = xbmcgui.Dialog()
        
        id_types = ['IMDB', 'TMDB', 'MAL', 'AniList', 'Kitsu']
        id_type_selected = dialog.select('Select ID Type', id_types)
        
        if id_type_selected < 0:
            return
        
        id_type = id_types[id_type_selected].lower()
        id_value = dialog.input(f'Enter {id_types[id_type_selected]} ID')
        
        if not id_value:
            return
        
        title = dialog.input('Enter Title (optional)', 'Content')
        
        params = {
            'type': 'movie',
            'title': title or 'Content',
            '_force_standalone': True
        }
        
        if id_type == 'imdb':
            params['imdb_id'] = id_value
        elif id_type == 'tmdb':
            params['tmdb_id'] = id_value
        elif id_type == 'mal':
            params['mal_id'] = id_value
        elif id_type == 'anilist':
            params['anilist_id'] = id_value
        elif id_type == 'kitsu':
            params['kitsu_id'] = id_value
        
        engine = PlaybackEngine(-1, 'plugin://plugin.video.stremio.bridge')
        engine.play_with_dialog(params)
    
    def _manage_scrapers(self):
        """Open the custom scraper manager dialog."""
        from resources.lib.gui.addon_manager import AddonManagerDialog
        AddonManagerDialog().show()

    def _show_about(self):
        """Show about dialog."""
        dialog = xbmcgui.Dialog()
        dialog.textviewer(
            'Stremio Bridge',
            'Stremio Bridge for Kodi v2.6.3 - REFACTORED EDITION\n\n'
            'Professional TMDb Helper integration with ANIME SUPPORT.\n\n'
            'Architecture:\n'
            '• Router-Controller-Service pattern\n'
            '• Modular, maintainable codebase\n'
            '• Clean separation of concerns\n\n'
            'Features:\n'
            '• Custom stream selection dialog\n'
            '• Beautiful color-coded streams\n'
            '• Browse 100+ quality streams\n'
            '• Professional user experience\n'
            '• Smart content filtering\n'
            '• Multiple debrid services\n'
            '• ANIME ID SUPPORT (MAL, AniList, Kitsu)\n'
            '• Automatic ID resolution and conversion\n'
            '• Torrentio URL fixing\n'
            '• Speed indicators for playback\n\n'
            'Supported IDs:\n'
            '• IMDB (tt1234567)\n'
            '• TMDB (12345)\n'
            '• MyAnimeList / MAL (98765)\n'
            '• AniList (54321)\n'
            '• Kitsu (11223)\n\n'
            'Test directly from Video Addons menu!'
        )
    
    def setup_player(self):
        """Copy LittleTigre.json player file to the chosen addon's players folder."""
        home = xbmcvfs.translatePath('special://home')
        addon_path = self.addon.getAddonInfo('path')
        src = os.path.join(addon_path, 'LittleTigre.json')

        # Supported metadata addons and where their players folder lives
        target_defs = [
            {
                'label': 'TMDb Helper',
                'addon_id': 'plugin.video.themoviedb.helper',
                'players_dir': os.path.join(
                    home, 'userdata', 'addon_data',
                    'plugin.video.themoviedb.helper', 'players'
                ),
            },
            {
                'label': 'Little Racun',
                'addon_id': 'plugin.video.littleracun',
                'players_dir': os.path.join(
                    home, 'addons', 'plugin.video.littleracun',
                    'resources', 'players'
                ),
            },
        ]

        # Keep only installed addons
        installed = []
        for t in target_defs:
            try:
                xbmcaddon.Addon(t['addon_id'])
                installed.append(t)
            except Exception:
                pass

        if not installed:
            xbmcgui.Dialog().ok(
                'Setup Player',
                'No supported addons found.\nInstall TMDb Helper first.'
            )
            return

        labels = [t['label'] for t in installed]
        selected = xbmcgui.Dialog().select('Install Little Tigre Player For...', labels)
        if selected < 0:
            return

        target = installed[selected]
        players_dir = target['players_dir']
        dst = os.path.join(players_dir, 'LittleTigre.json')

        xbmcvfs.mkdir(players_dir)
        success = xbmcvfs.copy(src, dst)

        if success:
            xbmcgui.Dialog().notification(
                'Little Tigre',
                f'Player installed for {target["label"]}',
                xbmcgui.NOTIFICATION_INFO
            )
            log(f"setup_player: {src} -> {dst}")
        else:
            xbmcgui.Dialog().ok('Setup Player - Error', f'Failed to copy player file.\nSrc: {src}\nDst: {dst}')
            log_error('setup_player: xbmcvfs.copy returned False', Exception('copy failed'))

    def test_debrid(self):
        """Test debrid service connections."""
        success, message = test_debrid_connection()
        if success:
            xbmcgui.Dialog().ok('Stremio Bridge', f'✓ {message}')
        else:
            xbmcgui.Dialog().ok('Stremio Bridge', f'✗ Connection failed\n{message}')
