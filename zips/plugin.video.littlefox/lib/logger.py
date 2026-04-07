"""Logging utilities for Little Fox."""

import xbmc
import xbmcaddon

_debug_enabled = None


def _is_debug():
    global _debug_enabled
    if _debug_enabled is None:
        try:
            _debug_enabled = xbmcaddon.Addon().getSetting('enable_debug') == 'true'
        except Exception:
            _debug_enabled = False
    return _debug_enabled


def log(message, level='info'):
    """Log a message to Kodi log."""
    if level == 'debug' and not _is_debug():
        return
    level_map = {
        'debug':   xbmc.LOGDEBUG,
        'info':    xbmc.LOGINFO,
        'warning': xbmc.LOGWARNING,
        'error':   xbmc.LOGERROR,
    }
    xbmc.log(f'[Little Fox] {message}', level_map.get(level, xbmc.LOGINFO))


def log_debug(message):
    log(message, 'debug')


def log_error(message, exception=None):
    if exception:
        log(f'{message}: {exception}', 'error')
    else:
        log(message, 'error')
