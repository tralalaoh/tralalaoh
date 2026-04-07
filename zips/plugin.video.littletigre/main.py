"""Stremio Bridge - Main Entry Point (Router Only)"""

import sys
import xbmc
import xbmcaddon
from urllib.parse import parse_qsl

try:
    from resources.lib.playback_engine import PlaybackEngine
    from resources.lib.menus import MainMenu
    from resources.lib.logger import log, log_error
except Exception as e:
    xbmc.log(f'[Stremio Bridge] CRITICAL: Import failed - {str(e)}', xbmc.LOGERROR)
    raise


def route(paramstring, addon_handle, addon_url):
    """
    Route addon calls to appropriate controllers.
    
    Args:
        paramstring: URL query parameters
        addon_handle: Kodi plugin handle
        addon_url: Base addon URL
    """
    try:
        params = dict(parse_qsl(paramstring))
        action = params.get('action')
        
        log(f"Router called - action: {action}, handle: {addon_handle}")
        
        # Playback action - delegate to PlaybackEngine
        if action in ('play', 'play_with_dialog'):
            engine = PlaybackEngine(addon_handle, addon_url)
            engine.play_with_dialog(params)
        
        # Debrid test action
        elif action == 'test_debrid':
            menu = MainMenu()
            menu.test_debrid()

        # Setup player installer
        elif action == 'setup_player':
            menu = MainMenu()
            menu.setup_player()

        # Custom scraper manager
        elif action == 'manage_scrapers':
            from resources.lib.gui.addon_manager import AddonManagerDialog
            AddonManagerDialog().show()
            xbmc.executebuiltin('Container.Refresh')
        
        # Default: Show main menu
        else:
            # Check if already playing (avoid menu spam)
            player = xbmc.Player()
            if player.isPlayingVideo():
                log("Video already playing, ignoring menu request")
                return
            
            menu = MainMenu()
            menu.show()
            
    except Exception as e:
        log_error("Router failed", e)
        import traceback
        xbmc.log(f'[Stremio Bridge] Router exception:\n{traceback.format_exc()}', xbmc.LOGERROR)
        raise


def run():
    """Main entry point - parse sys.argv and route."""
    try:
        addon_handle = int(sys.argv[1])
        addon_url = sys.argv[0]
        paramstring = sys.argv[2][1:]  # Remove leading '?'
        
        addon = xbmcaddon.Addon()
        log(f'Stremio Bridge v{addon.getAddonInfo("version")} started')
        log(f'Handle: {addon_handle}, URL: {addon_url}, Params: {paramstring}')
        
        route(paramstring, addon_handle, addon_url)
        
    except Exception as e:
        xbmc.log(f'[Stremio Bridge] FATAL ERROR in run(): {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(f'[Stremio Bridge] Traceback:\n{traceback.format_exc()}', xbmc.LOGERROR)
        raise


if __name__ == '__main__':
    run()
