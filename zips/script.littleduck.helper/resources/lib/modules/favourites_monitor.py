# -*- coding: utf-8 -*-
"""
favourites_monitor.py
Polls favourites.xml every 5 seconds and sets Window(10000) properties
so the skin can detect favourites from any addon (not just exact URL match).

Property pattern: Window(home).Property(LittleDuck.Fav.<tmdb_id>) = "1"

Skin usage:
  !String.IsEmpty(Window(home).Property(LittleDuck.Fav.$INFO[ListItem.Property(tmdb_id)]))
"""
import os
import re
import xml.etree.ElementTree as ET

import xbmc
import xbmcgui
import xbmcvfs


def favourites_monitor():
    monitor = xbmc.Monitor()
    window = xbmcgui.Window(10000)
    fav_path = xbmcvfs.translatePath("special://userdata/favourites.xml")

    last_mtime = 0.0
    active_ids = set()

    xbmc.log("###littleduck FavMonitor: Started — watching %s" % fav_path, 1)

    while not monitor.abortRequested():
        if monitor.waitForAbort(5):
            break

        if xbmc.getSkinDir() != "skin.littleduck":
            continue

        try:
            mtime = os.path.getmtime(fav_path)
        except OSError:
            # File doesn't exist — clear any properties we set
            if active_ids:
                for tmdb_id in active_ids:
                    window.clearProperty("LittleDuck.Fav.%s" % tmdb_id)
                active_ids = set()
            continue

        if mtime == last_mtime:
            continue

        last_mtime = mtime
        new_ids = set()

        try:
            tree = ET.parse(fav_path)
            root = tree.getroot()
            for fav in root.findall("favourite"):
                action = fav.text or ""
                match = re.search(r'tmdb_id=(\d+)', action)
                if match:
                    new_ids.add(match.group(1))
        except Exception as exc:
            xbmc.log("###littleduck FavMonitor: Parse error — %s" % exc, 3)
            continue

        # Clear properties for ids that are no longer favourited
        for removed in active_ids - new_ids:
            window.clearProperty("LittleDuck.Fav.%s" % removed)

        # Set properties for newly added ids
        for added in new_ids - active_ids:
            window.setProperty("LittleDuck.Fav.%s" % added, "1")

        active_ids = new_ids
        xbmc.log("###littleduck FavMonitor: Refreshed — active ids: %s" % sorted(active_ids), 1)

    xbmc.log("###littleduck FavMonitor: Stopped", 1)
