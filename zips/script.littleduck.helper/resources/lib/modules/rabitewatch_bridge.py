# -*- coding: utf-8 -*-
"""
Read-only bridge to the Rabitewatch local SQLite DB.
Opens rabitewatch.db directly — no cross-addon import, no write operations.
Exposes watch status as a dict with keys matching the littleduck.rw.* namespace.
"""
import sqlite3
import json
import os

import xbmc
import xbmcvfs
import xbmcaddon


class RabitewatchBridge:
    def __init__(self):
        try:
            addon = xbmcaddon.Addon('plugin.video.rabitewatch')
            profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
            self._db_path = os.path.join(profile, 'rabitewatch.db')
        except Exception:
            self._db_path = None

    def find_by_id(self, id_type, id_value):
        """
        Look up watch status for an item by service ID.
        id_type: 'imdb', 'tmdb', or 'tvdb'
        id_value: the ID string
        Returns dict with rw.* keys (resumePct, resumeTime, completed, listStatus, sources),
        or None if not found or DB unavailable.
        """
        if not self._db_path or not os.path.exists(self._db_path):
            return None
        id_key = id_type + '_id'   # 'imdb' -> 'imdb_id', 'tmdb' -> 'tmdb_id'
        try:
            conn = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA journal_mode=WAL')
            rows = conn.execute('SELECT * FROM progress').fetchall()
            conn.close()
            for row in rows:
                try:
                    ids = json.loads(row['service_ids'] or '{}')
                except Exception:
                    ids = {}
                stored = ids.get(id_key)
                if stored is not None and str(stored) == str(id_value):
                    sources_raw = row['sources'] or '[]'
                    try:
                        sources = ','.join(json.loads(sources_raw))
                    except Exception:
                        sources = ''
                    return {
                        'resumePct':  str(row['resume_pct'] or ''),
                        'resumeTime': str(row['resume_time'] or ''),
                        'completed':  'true' if row['completed'] else '',
                        'listStatus': row['list_status'] or '',
                        'sources':    sources,
                    }
        except Exception as e:
            xbmc.log(f"###littleduck: RabitewatchBridge DB lookup failed: {e}", 3)
        return None
