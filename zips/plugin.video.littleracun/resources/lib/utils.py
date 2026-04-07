#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility functions for logging, URL handling, and common helpers.
"""

import xbmc
import xbmcaddon
from urllib.parse import urlencode, parse_qsl

# Get addon info
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = ADDON.getAddonInfo('path')
ADDON_ICON = ADDON.getAddonInfo('icon')


def log(msg, level=xbmc.LOGINFO):
    """Helper function to log messages"""
    try:
        debug_enabled = ADDON.getSetting('enable_debug') == 'true'
        if debug_enabled or level >= xbmc.LOGWARNING:
            xbmc.log(f"[🦝 {ADDON_NAME}] {msg}", level=level)
    except:
        xbmc.log(f"[🦝 Little Racun] {msg}", level=level)


def log_error(msg, error=None):
    """Log error with traceback"""
    if error:
        import traceback
        log(f"ERROR: {msg} - {str(error)}", level=xbmc.LOGERROR)
        log(f"Traceback:\n{traceback.format_exc()}", level=xbmc.LOGERROR)
    else:
        log(f"ERROR: {msg}", level=xbmc.LOGERROR)


def build_url(query, base=None):
    """Build a URL for the plugin with the given query parameters"""
    import sys
    if base is None:
        base = sys.argv[0]
    return f"{base}?{urlencode(query)}"


def parse_params(argv):
    """Parse URL parameters from argv"""
    if len(argv) > 2:
        return dict(parse_qsl(argv[2][1:]))
    return {}


def get_plugin_handle(argv):
    """Get plugin handle from argv"""
    if len(argv) > 1:
        return int(argv[1])
    return -1
