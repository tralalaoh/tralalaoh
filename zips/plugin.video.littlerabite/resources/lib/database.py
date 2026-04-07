# -*- coding: utf-8 -*-
"""
Little Rabite - Database Handler
UPDATED: Schema version 3 - Added list_status column for watchlist/watching/dropped tracking.

List status values (matches Trakt, Simkl, AniList):
  'watchlist'  - Plan to watch (Trakt watchlist, Simkl plantowatch, AniList PLANNING)
  'watching'   - Currently watching (Trakt progress, Simkl watching, AniList CURRENT)
  'watched'    - Completed (from watch history)
  'dropped'    - Dropped (Trakt hidden progress_watched, Simkl dropped, AniList DROPPED)
  'onhold'     - On hold / Paused (Simkl hold, AniList PAUSED)
  None         - Unknown / not set
"""

import sqlite3
import json
import time
import os
from contextlib import closing
from threading import Lock

try:
    import xbmc
    import xbmcvfs
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class Database:
    """
    SQLite database handler for Little Rabite.
    Implements smart merging and thread-safe operations.
    """

    # Schema version for migration tracking
    SCHEMA_VERSION = 3  # BUMPED from 2 to add list_status column

    def __init__(self, db_path=None):
        if db_path is None:
            if KODI_ENV:
                addon_data = xbmcvfs.translatePath('special://profile/addon_data/plugin.video.littlerabite/')
                if not xbmcvfs.exists(addon_data):
                    xbmcvfs.mkdirs(addon_data)
                self.db_path = os.path.join(addon_data, 'littlerabite.db')
            else:
                self.db_path = 'littlerabite.db'
        else:
            self.db_path = db_path

        self._lock = Lock()
        self._initialize_database()
        self._migrate_database()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        conn.execute('PRAGMA cache_size=10000')
        conn.execute('PRAGMA temp_store=MEMORY')
        return conn

    def _initialize_database(self):
        """Create tables if they don't exist."""
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS progress (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_ids TEXT NOT NULL,
                        type TEXT NOT NULL,
                        title TEXT,
                        year INTEGER,
                        season INTEGER,
                        episode INTEGER,
                        last_watched_at INTEGER NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        resume_time INTEGER NOT NULL DEFAULT 0,
                        duration INTEGER,
                        completed INTEGER DEFAULT 0,
                        poster TEXT,
                        fanart TEXT,
                        plot TEXT,
                        list_status TEXT
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS auth (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service TEXT UNIQUE NOT NULL,
                        token TEXT,
                        refresh_token TEXT,
                        expires_at INTEGER,
                        user_data TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sync_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        service TEXT NOT NULL,
                        action TEXT NOT NULL,
                        data TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        retry_count INTEGER DEFAULT 0,
                        last_error TEXT
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY
                    )
                ''')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_last_watched ON progress(last_watched_at DESC)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_type ON progress(type)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_completed ON progress(completed)')
                # NOTE: idx_progress_list_status is created in _migrate_database() (version 3)
                # because the list_status column may not exist yet on existing databases.
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_sync_queue_service ON sync_queue(service)')

                conn.commit()

    def _migrate_database(self):
        """Migrate database schema to latest version."""
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                try:
                    cursor.execute('SELECT version FROM schema_version')
                    row = cursor.fetchone()
                    current_version = row[0] if row else 0
                except sqlite3.OperationalError:
                    current_version = 0

                if current_version >= self.SCHEMA_VERSION:
                    # Even if version says up-to-date, verify critical columns exist.
                    # Guards against partial migrations where version was bumped but ALTER failed.
                    self._ensure_columns(conn)
                    return

                self._log(f'Migrating database from version {current_version} to {self.SCHEMA_VERSION}')

                if current_version < 1:
                    try:
                        cursor.execute('ALTER TABLE progress ADD COLUMN year INTEGER')
                        conn.commit()
                        self._log('Added year column')
                    except sqlite3.OperationalError:
                        pass

                if current_version < 2:
                    for col in ['poster TEXT', 'fanart TEXT', 'plot TEXT']:
                        try:
                            cursor.execute(f'ALTER TABLE progress ADD COLUMN {col}')
                            conn.commit()
                            self._log(f'Added {col.split()[0]} column')
                        except sqlite3.OperationalError:
                            pass

                # Migration version 3 - add list_status column
                if current_version < 3:
                    try:
                        cursor.execute('ALTER TABLE progress ADD COLUMN list_status TEXT')
                        conn.commit()
                        self._log('Added list_status column to progress table')
                    except sqlite3.OperationalError:
                        pass  # Column already exists

                    try:
                        cursor.execute('CREATE INDEX IF NOT EXISTS idx_progress_list_status ON progress(list_status)')
                        conn.commit()
                        self._log('Added list_status index')
                    except sqlite3.OperationalError:
                        pass

                cursor.execute('DELETE FROM schema_version')
                cursor.execute('INSERT INTO schema_version (version) VALUES (?)', (self.SCHEMA_VERSION,))
                conn.commit()
                self._log(f'Database migration complete: version {self.SCHEMA_VERSION}')

    def _ensure_columns(self, conn):
        """
        Verify all expected columns exist and add any that are missing.
        Safety net for partial migrations or version-bumped-but-not-altered databases.
        """
        cursor = conn.cursor()
        cursor.execute('PRAGMA table_info(progress)')
        existing_cols = {row['name'] for row in cursor.fetchall()}

        needed = {
            'year': 'INTEGER',
            'poster': 'TEXT',
            'fanart': 'TEXT',
            'plot': 'TEXT',
            'list_status': 'TEXT',
        }

        for col_name, col_type in needed.items():
            if col_name not in existing_cols:
                try:
                    conn.execute(f'ALTER TABLE progress ADD COLUMN {col_name} {col_type}')
                    conn.commit()
                    self._log(f'_ensure_columns: added missing column {col_name}')
                except sqlite3.OperationalError:
                    pass

        # Ensure the index exists too
        try:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_progress_list_status ON progress(list_status)')
            conn.commit()
        except sqlite3.OperationalError:
            pass

    def _log(self, message, level=None):
        if KODI_ENV:
            if level is None:
                level = xbmc.LOGINFO
            xbmc.log(f'[LittleRabite-DB] {message}', level)
        else:
            print(f'[LittleRabite-DB] {message}')

    # ============================================================================
    # PROGRESS METHODS (SMART MERGING)
    # ============================================================================

    def update_progress(self, service_ids, media_type, progress, resume_time,
                       duration=None, title=None, year=None, season=None, episode=None,
                       poster=None, fanart=None, plot=None, list_status=None):
        """
        Update or insert playback progress with SMART MERGING.

        Args:
            service_ids: Dict of service IDs
            media_type: 'movie' or 'episode'
            progress: Percentage watched (0-100)
            resume_time: Resume position in seconds
            duration: Total duration in seconds
            title: Media title
            year: Release year
            season: Season number (for episodes)
            episode: Episode number (for episodes)
            poster: Poster image URL
            fanart: Fanart image URL
            plot: Plot/description text
            list_status: List status ('watchlist', 'watching', 'watched', 'dropped', 'onhold')

        Returns:
            Row ID of the updated/inserted record
        """
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                timestamp = int(time.time())
                completed = 1 if progress >= 80 else 0

                new_ids = {k: v for k, v in service_ids.items() if v is not None}

                if not new_ids:
                    self._log('No valid service IDs provided, skipping update',
                             xbmc.LOGWARNING if KODI_ENV else None)
                    return None

                query = 'SELECT * FROM progress WHERE type = ?'
                params = [media_type]

                if media_type == 'episode' and season is not None and episode is not None:
                    query += ' AND season = ? AND episode = ?'
                    params.extend([season, episode])

                cursor.execute(query, params)
                existing_rows = cursor.fetchall()

                matched_row = None
                for row in existing_rows:
                    existing_ids = json.loads(row['service_ids'])
                    if self._ids_intersect(new_ids, existing_ids):
                        matched_row = row
                        break

                if matched_row:
                    existing_id = matched_row['id']
                    existing_ids = json.loads(matched_row['service_ids'])
                    existing_timestamp = matched_row['last_watched_at']

                    merged_ids = existing_ids.copy()
                    merged_ids.update(new_ids)
                    merged_ids_json = json.dumps(merged_ids, sort_keys=True)

                    if timestamp >= existing_timestamp:
                        cursor.execute('''
                            UPDATE progress SET
                                service_ids = ?,
                                progress = ?,
                                resume_time = ?,
                                duration = ?,
                                last_watched_at = ?,
                                completed = ?,
                                title = COALESCE(?, title),
                                year = COALESCE(?, year),
                                poster = COALESCE(?, poster),
                                fanart = COALESCE(?, fanart),
                                plot = COALESCE(?, plot),
                                list_status = COALESCE(?, list_status)
                            WHERE id = ?
                        ''', (merged_ids_json, progress, resume_time, duration,
                              timestamp, completed, title, year, poster, fanart, plot,
                              list_status, existing_id))

                        self._log(f'Updated existing row {existing_id} (merged IDs: {merged_ids})')
                        conn.commit()
                        return existing_id
                    else:
                        cursor.execute('''
                            UPDATE progress SET
                                service_ids = ?,
                                list_status = COALESCE(?, list_status)
                            WHERE id = ?
                        ''', (merged_ids_json, list_status, existing_id))

                        self._log(f'Merged IDs for row {existing_id} (kept existing data)')
                        conn.commit()
                        return existing_id
                else:
                    service_ids_json = json.dumps(new_ids, sort_keys=True)

                    cursor.execute('''
                        INSERT INTO progress
                        (service_ids, type, title, year, season, episode, last_watched_at,
                         progress, resume_time, duration, completed, poster, fanart, plot, list_status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (service_ids_json, media_type, title, year, season, episode,
                          timestamp, progress, resume_time, duration, completed,
                          poster, fanart, plot, list_status))

                    new_id = cursor.lastrowid
                    self._log(f'Inserted new row {new_id} (IDs: {new_ids})')
                    conn.commit()
                    return new_id

    def update_list_status(self, service_ids, list_status, media_type=None):
        """
        Update only the list_status of an existing item (or insert a skeleton row).
        Used for watchlist/watching/dropped sync where we don't have full progress data.

        Args:
            service_ids: Dict of service IDs
            list_status: New status ('watchlist', 'watching', 'watched', 'dropped', 'onhold')
            media_type: 'movie' or 'episode' (required for insert)
        """
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                new_ids = {k: v for k, v in service_ids.items() if v is not None}
                if not new_ids:
                    return None

                # Find any existing matching row
                cursor.execute('SELECT * FROM progress')
                rows = cursor.fetchall()

                matched_row = None
                for row in rows:
                    existing_ids = json.loads(row['service_ids'])
                    if self._ids_intersect(new_ids, existing_ids):
                        matched_row = row
                        break

                if matched_row:
                    # Merge IDs and update status
                    existing_ids = json.loads(matched_row['service_ids'])
                    merged_ids = existing_ids.copy()
                    merged_ids.update(new_ids)
                    merged_ids_json = json.dumps(merged_ids, sort_keys=True)

                    cursor.execute('''
                        UPDATE progress SET service_ids = ?, list_status = ? WHERE id = ?
                    ''', (merged_ids_json, list_status, matched_row['id']))

                    self._log(f'Updated list_status={list_status} for row {matched_row["id"]}')
                    conn.commit()
                    return matched_row['id']
                else:
                    # Insert new skeleton row with just the status
                    if not media_type:
                        return None

                    service_ids_json = json.dumps(new_ids, sort_keys=True)
                    timestamp = int(time.time())

                    cursor.execute('''
                        INSERT INTO progress
                        (service_ids, type, last_watched_at, progress, resume_time, list_status)
                        VALUES (?, ?, ?, 0, 0, ?)
                    ''', (service_ids_json, media_type, timestamp, list_status))

                    new_id = cursor.lastrowid
                    self._log(f'Inserted list-only row {new_id} (status={list_status}, IDs: {new_ids})')
                    conn.commit()
                    return new_id

    def get_items_by_list_status(self, list_status, media_type=None, limit=200):
        """
        Get all items with a specific list status.

        Args:
            list_status: Status to filter by ('watchlist', 'watching', 'watched', 'dropped', 'onhold')
            media_type: Optional filter by 'movie' or 'episode'
            limit: Maximum number of items to return

        Returns:
            List of progress dicts
        """
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM progress WHERE list_status = ?'
                params = [list_status]

                if media_type:
                    query += ' AND type = ?'
                    params.append(media_type)

                query += ' ORDER BY last_watched_at DESC LIMIT ?'
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

    def _ids_intersect(self, ids1, ids2):
        for key in ids1:
            if key in ids2:
                val1 = ids1[key]
                val2 = ids2[key]
                if val1 is None or val2 is None:
                    continue
                if str(val1) == str(val2):
                    return True
        return False

    def get_continue_watching(self, limit=20, media_type=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM progress WHERE completed = 0 AND progress > 0'
                params = []

                if media_type:
                    query += ' AND type = ?'
                    params.append(media_type)

                query += ' ORDER BY last_watched_at DESC LIMIT ?'
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [self._row_to_dict(row) for row in rows]

    def get_progress_by_ids(self, service_ids, season=None, episode=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM progress'
                params = []

                if season is not None and episode is not None:
                    query += ' WHERE season = ? AND episode = ?'
                    params.extend([season, episode])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    existing_ids = json.loads(row['service_ids'])
                    if self._ids_intersect(service_ids, existing_ids):
                        return self._row_to_dict(row)

                return None

    def mark_completed(self, service_ids, season=None, episode=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                query = 'SELECT * FROM progress'
                params = []

                if season is not None and episode is not None:
                    query += ' WHERE season = ? AND episode = ?'
                    params.extend([season, episode])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    existing_ids = json.loads(row['service_ids'])
                    if self._ids_intersect(service_ids, existing_ids):
                        cursor.execute('''
                            UPDATE progress
                            SET completed = 1, progress = 100, list_status = 'watched'
                            WHERE id = ?
                        ''', (row['id'],))

                conn.commit()

    def clear_progress(self, service_ids=None, older_than_days=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                if service_ids:
                    cursor.execute('SELECT * FROM progress')
                    rows = cursor.fetchall()
                    for row in rows:
                        existing_ids = json.loads(row['service_ids'])
                        if self._ids_intersect(service_ids, existing_ids):
                            cursor.execute('DELETE FROM progress WHERE id = ?', (row['id'],))
                elif older_than_days:
                    cutoff = int(time.time()) - (older_than_days * 86400)
                    cursor.execute('DELETE FROM progress WHERE last_watched_at < ? AND completed = 1', (cutoff,))
                else:
                    cursor.execute('DELETE FROM progress')

                conn.commit()

    def _row_to_dict(self, row):
        return dict(row)

    # ============================================================================
    # AUTH METHODS
    # ============================================================================

    def store_auth(self, service, token, refresh_token=None, expires_at=None, user_data=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()
                timestamp = int(time.time())
                user_data_json = json.dumps(user_data) if user_data else None

                cursor.execute('''
                    INSERT INTO auth
                    (service, token, refresh_token, expires_at, user_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(service) DO UPDATE SET
                        token = excluded.token,
                        refresh_token = excluded.refresh_token,
                        expires_at = excluded.expires_at,
                        user_data = excluded.user_data,
                        updated_at = excluded.updated_at
                ''', (service, token, refresh_token, expires_at, user_data_json, timestamp, timestamp))

                conn.commit()

    def get_auth(self, service):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM auth WHERE service = ?', (service,))
                row = cursor.fetchone()

                if not row:
                    return None

                result = self._row_to_dict(row)
                if result.get('user_data'):
                    result['user_data'] = json.loads(result['user_data'])
                return result

    def is_token_expired(self, service):
        auth = self.get_auth(service)
        if not auth or not auth.get('expires_at'):
            return True
        return int(time.time()) >= (auth['expires_at'] - 300)

    def delete_auth(self, service):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM auth WHERE service = ?', (service,))
                conn.commit()

    # ============================================================================
    # SYNC QUEUE METHODS
    # ============================================================================

    def queue_sync(self, service, action, data):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()
                timestamp = int(time.time())
                data_json = json.dumps(data)
                cursor.execute('''
                    INSERT INTO sync_queue (service, action, data, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (service, action, data_json, timestamp))
                conn.commit()
                return cursor.lastrowid

    def get_sync_queue(self, service=None, limit=100):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                if service:
                    cursor.execute('''
                        SELECT * FROM sync_queue
                        WHERE service = ? AND retry_count < 5
                        ORDER BY created_at ASC LIMIT ?
                    ''', (service, limit))
                else:
                    cursor.execute('''
                        SELECT * FROM sync_queue
                        WHERE retry_count < 5
                        ORDER BY created_at ASC LIMIT ?
                    ''', (limit,))

                rows = cursor.fetchall()
                results = []
                for row in rows:
                    item = self._row_to_dict(row)
                    item['data'] = json.loads(item['data'])
                    results.append(item)

                return results

    def update_sync_item(self, item_id, success=True, error=None):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                if success:
                    cursor.execute('DELETE FROM sync_queue WHERE id = ?', (item_id,))
                else:
                    cursor.execute('''
                        UPDATE sync_queue
                        SET retry_count = retry_count + 1, last_error = ?
                        WHERE id = ?
                    ''', (error, item_id))

                conn.commit()

    def vacuum(self):
        with self._lock:
            with closing(self._get_connection()) as conn:
                conn.execute('VACUUM')

    def get_stats(self):
        with self._lock:
            with closing(self._get_connection()) as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT COUNT(*) as total FROM progress')
                total_progress = cursor.fetchone()[0]

                cursor.execute('SELECT COUNT(*) as total FROM progress WHERE completed = 1')
                completed = cursor.fetchone()[0]

                cursor.execute('SELECT COUNT(*) as total FROM auth')
                auth_count = cursor.fetchone()[0]

                cursor.execute('SELECT COUNT(*) as total FROM sync_queue')
                queue_count = cursor.fetchone()[0]

                try:
                    cursor.execute('SELECT version FROM schema_version')
                    row = cursor.fetchone()
                    schema_version = row[0] if row else 0
                except Exception:
                    schema_version = 0

                # Count by list_status
                status_counts = {}
                try:
                    cursor.execute('''
                        SELECT list_status, COUNT(*) as cnt
                        FROM progress
                        WHERE list_status IS NOT NULL
                        GROUP BY list_status
                    ''')
                    for row in cursor.fetchall():
                        status_counts[row['list_status']] = row['cnt']
                except Exception:
                    pass

                return {
                    'total_progress': total_progress,
                    'completed': completed,
                    'in_progress': total_progress - completed,
                    'authenticated_services': auth_count,
                    'pending_syncs': queue_count,
                    'schema_version': schema_version,
                    'list_status_counts': status_counts
                }


# Singleton
_db_instance = None
_db_lock = Lock()

def get_database(db_path=None):
    global _db_instance
    with _db_lock:
        if _db_instance is None:
            _db_instance = Database(db_path)
        return _db_instance
