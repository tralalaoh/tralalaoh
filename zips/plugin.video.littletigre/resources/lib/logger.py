"""Logging utilities for Little Tigre 🐯"""

import xbmc
from resources.lib.settings import Settings, ADDON_NAME


def log(message, level='info'):
    """Log a message to Kodi log."""
    if level == 'debug' and not Settings.is_debug_enabled():
        return
    
    log_levels = {
        'debug': xbmc.LOGDEBUG,
        'info': xbmc.LOGINFO,
        'warning': xbmc.LOGWARNING,
        'error': xbmc.LOGERROR
    }
    
    xbmc_level = log_levels.get(level, xbmc.LOGINFO)
    xbmc.log(f'[Little Tigre 🐯] {message}', xbmc_level)


def log_error(message, exception=None):
    """Log an error message."""
    if exception:
        log(f'{message}: {str(exception)}', 'error')
    else:
        log(message, 'error')


def log_debug(message):
    """Log a debug message."""
    log(message, 'debug')
