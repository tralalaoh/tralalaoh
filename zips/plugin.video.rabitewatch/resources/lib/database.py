
# -*- coding: utf-8 -*-
"""
Rabite Watch - Local Database
Stores watch progress pulled from Trakt, AniList, and Simkl.
Each item tracks resume percentages from every connected service
and computes a smart merged resume point.
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
    import xbmcaddon
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

SCHEMA_VERSION = 4


def get_database():
    return WatchDatabase()


class WatchDatabase:

    SCHEMA_VERSION = SCHEMA_VERSION

    def __init__(self, db_path=None):
        if db_path is None:
            if KODI_ENV:
                addon = xbmcaddon.Addon()
                profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
                if not xbmcvfs.exists(profile):
                    xbmcvfs.mkdirs(profile)
                self.db_path = os.path.join(profile, 'rabitewatch.db')
            else:
                self.db_path = 'rabitewatch.db'
        else:
            self.db_path = db_path

        self._lock = Lock()
        self._init_db()
        self._migrate_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def _init_db(self):
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS progress (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        service_ids      TEXT    NOT NULL,
                        media_type       TEXT    NOT NULL,
                        title            TEXT,
                        show_title       TEXT,
                        year             INTEGER,
                        season           INTEGER,
                        episode          INTEGER,
                        poster           TEXT,
                        fanart           TEXT,
                        landscape        TEXT,
                        clearlogo        TEXT,
                        plot             TEXT,
                        duration         INTEGER DEFAULT 0,
                        resume_pct       INTEGER DEFAULT 0,
                        resume_time      INTEGER DEFAULT 0,
                        completed        INTEGER DEFAULT 0,
                        resume_data      TEXT    DEFAULT '{}',
                        list_status      TEXT,
                        sources          TEXT    DEFAULT '[]',
                        last_pulled_at   INTEGER DEFAULT 0,
                        last_watched_at  INTEGER DEFAULT 0
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS auth (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        service       TEXT UNIQUE NOT NULL,
                        token         TEXT,
                        refresh_token TEXT,
                        expires_at    INTEGER,
                        user_data     TEXT,
                        created_at    INTEGER NOT NULL,
                        updated_at    INTEGER NOT NULL
                    )
                ''')
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version INTEGER PRIMARY KEY
                    )
                ''')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_prog_last_watched ON progress(last_watched_at DESC)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_prog_type ON progress(media_type)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_prog_completed ON progress(completed)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_prog_show ON progress(show_title, media_type)')
                conn.commit()

    def _migrate_db(self):
        with self._lock:
            with closing(self._connect()) as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute('SELECT version FROM schema_version')
                    row = cursor.fetchone()
                    version = row[0] if row else 0
                except sqlite3.OperationalError:
                    version = 0

                if version >= self.SCHEMA_VERSION:
                    return

                if version < 1:
                    for col in ['show_title TEXT', 'resume_data TEXT', 'list_status TEXT', 'last_pulled_at INTEGER DEFAULT 0']:
                        try:
                            conn.execute(f'ALTER TABLE progress ADD COLUMN {col}')
                        except sqlite3.OperationalError:
                            pass
                    conn.commit()

                if version < 2:
                    for col in ['season INTEGER', 'episode INTEGER']:
                        try:
                            conn.execute(f'ALTER TABLE progress ADD COLUMN {col}')
                        except sqlite3.OperationalError:
                            pass
                    conn.commit()

                if version < 3:
                    try:
                        conn.execute("ALTER TABLE progress ADD COLUMN sources TEXT DEFAULT '[]'")
                    except sqlite3.OperationalError:
                        pass
                    conn.commit()

                if version < 4:
                    for col in ['landscape TEXT', 'clearlogo TEXT']:
                        try:
                            conn.execute(f'ALTER TABLE progress ADD COLUMN {col}')
                        except sqlite3.OperationalError:
                            pass
                    conn.commit()

                conn.execute('DELETE FROM schema_version')
                conn.execute('INSERT INTO schema_version (version) VALUES (?)', (self.SCHEMA_VERSION,))
                conn.commit()

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    def store_auth(self, service, token, refresh_token=None, expires_at=None, user_data=None):
        """
        Store auth credentials. Called store_auth to match littlerabite pattern.
        Also aliased as save_auth for backward compatibility.
        """
        now = int(time.time())
        if user_data and not isinstance(user_data, str):
            user_data_str = json.dumps(user_data)
        else:
            user_data_str = user_data

        with self._lock:
            with closing(self._connect()) as conn:
                existing = conn.execute(
                    'SELECT created_at FROM auth WHERE service=?', (service,)
                ).fetchone()
                created_at = existing['created_at'] if existing else now

                conn.execute('''
                    INSERT OR REPLACE INTO auth
                        (service, token, refresh_token, expires_at, user_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (service, token, refresh_token, expires_at, user_data_str, created_at, now))
                conn.commit()

    # Alias
    def save_auth(self, service, token, refresh_token=None, expires_at=None, user_data=None):
        return self.store_auth(service, token, refresh_token, expires_at, user_data)

    def get_auth(self, service):
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute('SELECT * FROM auth WHERE service=?', (service,)).fetchone()
                if not row:
                    return None
                result = dict(row)
                if result.get('user_data'):
                    try:
                        result['user_data'] = json.loads(result['user_data'])
                    except Exception as e:
                        self._log(
                            f'get_auth({service}): user_data JSON decode failed: {e}',
                            xbmc.LOGWARNING if KODI_ENV else None
                        )
                return result

    def delete_auth(self, service):
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute('DELETE FROM auth WHERE service=?', (service,))
                conn.commit()

    def is_token_expired(self, service):
        auth = self.get_auth(service)
        if not auth:
            return True
        expires_at = auth.get('expires_at')
        if not expires_at:
            return False
        return int(time.time()) >= expires_at - 300

    # ------------------------------------------------------------------
    # PROGRESS UPSERT
    # ------------------------------------------------------------------

    def upsert_progress(self, service_ids, media_type, title=None, show_title=None,
                        year=None, season=None, episode=None,
                        poster=None, fanart=None, landscape=None, clearlogo=None,
                        plot=None, duration=None, resume_pct=0, resume_time=0,
                        completed=0, list_status=None, service_name=None,
                        last_watched_at=None):
        """
        Upsert a progress row.

        For EPISODES: matches on shared service_id key, then keeps the
        highest season/episode. If the incoming item is for a newer episode
        than what's stored, the row is updated to the newer episode.
        This means each show has exactly ONE row showing the latest ep.

        Sources list tracks which services contributed (e.g. ['trakt', 'simkl']).
        """
        # Read the completion threshold once, outside the DB lock, so the
        # setting change takes effect on the very next upsert call.
        threshold = 95
        if KODI_ENV:
            try:
                threshold = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingInt('resume_threshold')
            except Exception:
                pass

        now = int(time.time())
        if last_watched_at is None:
            last_watched_at = now

        with self._lock:
            with closing(self._connect()) as conn:
                # ----------------------------------------------------------
                # Find any existing row for this content (by shared ID key)
                # ----------------------------------------------------------
                existing_id = None
                ex_row      = None

                rows = conn.execute(
                    'SELECT id, service_ids, resume_data, resume_pct, resume_time, '
                    'completed, season, episode, sources, last_watched_at '
                    'FROM progress WHERE media_type=?',
                    (media_type,)
                ).fetchall()

                for row in rows:
                    try:
                        ex_ids = json.loads(row['service_ids'] or '{}')
                    except Exception:
                        ex_ids = {}

                    # Match if any service ID key/value overlaps
                    matched = any(
                        v and ex_ids.get(k) == v
                        for k, v in service_ids.items()
                    )
                    if matched:
                        existing_id = row['id']
                        ex_row      = dict(row)
                        break

                # ----------------------------------------------------------
                # UPDATE existing row
                # ----------------------------------------------------------
                if existing_id and ex_row:
                    # Merge service IDs
                    try:
                        merged_ids = json.loads(ex_row['service_ids'] or '{}')
                    except Exception:
                        merged_ids = {}
                    merged_ids.update({k: v for k, v in service_ids.items() if v})

                    # Merge resume_data per service
                    try:
                        resume_data = json.loads(ex_row['resume_data'] or '{}')
                    except Exception:
                        resume_data = {}

                    if service_name:
                        resume_data[service_name] = {
                            'pct':        resume_pct,
                            'time':       resume_time,
                            'updated_at': now
                        }

                    # Merge sources list
                    try:
                        sources = json.loads(ex_row['sources'] or '[]')
                    except Exception:
                        sources = []
                    if service_name and service_name not in sources:
                        sources.append(service_name)

                    # For episodes: the service with the most recent last_watched_at
                    # timestamp determines the current episode position.
                    #
                    # Episode-number comparison ("highest wins") was intentionally
                    # removed: it caused stale Trakt history (e.g. ep 4 from months
                    # ago) to permanently override a more recent AniList CURRENT
                    # entry (e.g. ep 3 from today during a rewatch).
                    ex_season  = ex_row['season']  or 0
                    ex_episode = ex_row['episode'] or 0
                    in_season  = season  or 0
                    in_episode = episode or 0

                    ex_ts = ex_row['last_watched_at'] or 0
                    in_ts = last_watched_at or 0

                    if media_type == 'episode' and in_ts >= ex_ts:
                        # Incoming data is at least as recent — use its episode
                        use_season  = in_season  if in_season  else ex_season
                        use_episode = in_episode if in_episode else ex_episode
                        use_title   = title or ex_row.get('title') or ex_row.get('show_title')
                    else:
                        # Existing data is more recent — keep its episode
                        use_season  = ex_season  or in_season
                        use_episode = ex_episode or in_episode
                        use_title   = ex_row.get('title') or title

                    use_last_watched = max(in_ts, ex_ts)

                    best_pct, best_time = self._best_resume(resume_data)

                    # Rewatch guard: if the incoming data explicitly puts this
                    # item back into an active-watching state (e.g. Trakt
                    # /sync/playback reports 21% on a previously-completed
                    # movie), clear the stale completed flag so the item
                    # reappears in Continue Watching.  Without this, once a
                    # row is completed=1 it can never surface again.
                    if list_status == 'watching' and not completed:
                        if ex_row['completed']:
                            self._log(
                                f'Rewatch guard: clearing completed flag for id={existing_id} '
                                f'title={title or show_title!r} (was completed=1, now watching)'
                            )
                        is_completed = False
                    else:
                        is_completed = bool(completed or ex_row['completed'])

                    if is_completed:
                        best_pct  = 100
                        best_time = 0
                    elif best_pct >= threshold:
                        # Crossed the user-configured threshold — treat as done.
                        is_completed = True
                        best_pct     = 100
                        best_time    = 0

                    conn.execute('''
                        UPDATE progress SET
                            service_ids=?, title=COALESCE(?,title),
                            show_title=COALESCE(?,show_title), year=COALESCE(?,year),
                            season=?, episode=?,
                            poster=COALESCE(?,poster), fanart=COALESCE(?,fanart),
                            landscape=COALESCE(?,landscape), clearlogo=COALESCE(?,clearlogo),
                            plot=COALESCE(?,plot), duration=COALESCE(?,duration),
                            resume_pct=?, resume_time=?, completed=?,
                            resume_data=?, list_status=COALESCE(?,list_status),
                            sources=?,
                            last_pulled_at=?, last_watched_at=?
                        WHERE id=?
                    ''', (json.dumps(merged_ids), use_title, show_title, year,
                          use_season, use_episode,
                          poster, fanart, landscape, clearlogo, plot, duration,
                          best_pct, best_time, 1 if is_completed else 0,
                          json.dumps(resume_data), list_status,
                          json.dumps(sources),
                          now, use_last_watched, existing_id))
                    conn.commit()
                    self._log(
                        f'UPDATE id={existing_id} [{service_name}] '
                        f'{title or show_title!r} pct={best_pct}% '
                        f'completed={is_completed} ep=S{use_season:02d}E{use_episode:02d}'
                        if media_type == 'episode' else
                        f'UPDATE id={existing_id} [{service_name}] '
                        f'{title or show_title!r} pct={best_pct}% completed={is_completed}'
                    )
                    return existing_id

                # ----------------------------------------------------------
                # INSERT new row
                # ----------------------------------------------------------
                else:
                    resume_data = {}
                    if service_name:
                        resume_data[service_name] = {
                            'pct':        resume_pct,
                            'time':       resume_time,
                            'updated_at': now
                        }
                    sources = [service_name] if service_name else []

                    best_pct, best_time = self._best_resume(resume_data)
                    if completed:
                        best_pct  = 100
                        best_time = 0
                    elif best_pct >= threshold:
                        # Crossed the user-configured threshold — treat as done.
                        completed = True
                        best_pct  = 100
                        best_time = 0

                    clean_ids = {k: v for k, v in service_ids.items() if v}
                    cursor = conn.execute('''
                        INSERT INTO progress
                            (service_ids, media_type, title, show_title, year, season, episode,
                             poster, fanart, landscape, clearlogo, plot, duration,
                             resume_pct, resume_time, completed,
                             resume_data, list_status, sources, last_pulled_at, last_watched_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ''', (json.dumps(clean_ids), media_type, title, show_title, year,
                          season, episode, poster, fanart, landscape, clearlogo, plot, duration,
                          best_pct, best_time, 1 if completed else 0,
                          json.dumps(resume_data), list_status,
                          json.dumps(sources), now, last_watched_at))
                    conn.commit()
                    new_id = cursor.lastrowid
                    self._log(
                        f'INSERT id={new_id} [{service_name}] '
                        f'{title or show_title!r} pct={best_pct}% '
                        f'completed={bool(completed)} ep=S{(season or 0):02d}E{(episode or 0):02d}'
                        if media_type == 'episode' else
                        f'INSERT id={new_id} [{service_name}] '
                        f'{title or show_title!r} pct={best_pct}% completed={bool(completed)}'
                    )
                    return new_id

    def _best_resume(self, resume_data):
        best_pct, best_time = 0, 0
        for info in resume_data.values():
            pct = info.get('pct', 0)
            t = info.get('time', 0)
            if pct > best_pct:
                best_pct = pct
                best_time = t
        return best_pct, best_time

    # ------------------------------------------------------------------
    # QUERIES
    # ------------------------------------------------------------------

    def get_by_id(self, row_id):
        """Fetch a single progress row by its primary key. Returns dict or None."""
        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    'SELECT * FROM progress WHERE id=?', (row_id,)
                ).fetchone()
                return self._row_to_dict(row) if row else None

    def find_by_service_id(self, id_type, id_value):
        """Return the first progress row whose service_ids[id_type_id] == id_value, or None."""
        id_key = id_type + '_id'   # 'imdb' -> 'imdb_id', 'tmdb' -> 'tmdb_id'
        if not id_value:
            return None
        with self._lock:
            with closing(self._connect()) as conn:
                rows = conn.execute('SELECT * FROM progress').fetchall()
                for row in rows:
                    try:
                        ids = json.loads(row['service_ids'] or '{}')
                    except Exception:
                        ids = {}
                    stored = ids.get(id_key)
                    if stored is not None and str(stored) == str(id_value):
                        return self._row_to_dict(row)
        return None

    def get_continue_watching(self, limit=50):
        """
        Return currently-watching items across ALL connected services.

        Sorted strictly by last_watched_at DESC so the most recently watched
        content is always first.
        Each row already represents ONE show (deduplication at upsert time).
        """
        hide_completed = True
        if KODI_ENV:
            try:
                hide_completed = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingBool('hide_completed')
            except Exception:
                pass

        with self._lock:
            with closing(self._connect()) as conn:
                if hide_completed:
                    cursor = conn.execute(
                        "SELECT * FROM progress"
                        " WHERE completed = 0 AND list_status = 'watching'"
                        " ORDER BY last_watched_at DESC LIMIT ?",
                        (limit,)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM progress"
                        " WHERE list_status = 'watching'"
                        " ORDER BY last_watched_at DESC LIMIT ?",
                        (limit,)
                    )
                return [self._row_to_dict(r) for r in cursor.fetchall()]

    def get_unenriched(self, limit=500):
        """
        Return ALL progress rows that have not yet been TMDB-enriched.

        `landscape` is the canonical enrichment sentinel — it is ONLY ever
        written by tmdb_enricher, never by any pull service.  A NULL/empty
        landscape therefore means the row has never been through the enricher.

        No list_status or completed filter is applied so that items in all
        states (watching, completed, planning …) get enriched proactively
        and are ready to display with full art the first time the user sees them.
        """
        with self._lock:
            with closing(self._connect()) as conn:
                cursor = conn.execute(
                    "SELECT * FROM progress WHERE landscape IS NULL OR landscape = '' LIMIT ?",
                    (limit,)
                )
                return [self._row_to_dict(r) for r in cursor.fetchall()]

    def get_by_list_status(self, status, limit=200):
        with self._lock:
            with closing(self._connect()) as conn:
                cursor = conn.execute('''
                    SELECT * FROM progress WHERE list_status=?
                    ORDER BY last_watched_at DESC LIMIT ?
                ''', (status, limit))
                return [self._row_to_dict(r) for r in cursor.fetchall()]

    def get_stats(self):
        with self._lock:
            with closing(self._connect()) as conn:
                total = conn.execute('SELECT COUNT(*) FROM progress').fetchone()[0]
                in_prog = conn.execute(
                    'SELECT COUNT(*) FROM progress WHERE completed=0 AND resume_pct>0'
                ).fetchone()[0]
                done = conn.execute(
                    'SELECT COUNT(*) FROM progress WHERE completed=1'
                ).fetchone()[0]
                auth_c = conn.execute(
                    'SELECT COUNT(*) FROM auth WHERE token IS NOT NULL'
                ).fetchone()[0]
                return {'total': total, 'in_progress': in_prog, 'completed': done, 'authenticated_services': auth_c}

    def clear_progress(self):
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute('DELETE FROM progress')
                conn.commit()

    def update_local_progress(self, row_id, resume_time, resume_pct, completed=False):
        """
        Fast-path UPDATE called by service.py's player listener after playback stops.

        Bypasses the full upsert overhead (no service-ID matching, no source merging).
        Applies the same resume_threshold logic as upsert_progress() so that
        finishing a video marks it completed regardless of which path wrote the row.

        A 'local' entry is merged into resume_data so the per-service plot
        breakdown reflects the most recent Kodi position immediately, even
        before the next cloud sync arrives with the authoritative data.
        """
        threshold = 95
        if KODI_ENV:
            try:
                threshold = xbmcaddon.Addon(
                    'plugin.video.rabitewatch'
                ).getSettingInt('resume_threshold')
            except Exception:
                pass

        if not completed and resume_pct >= threshold:
            completed   = True
            resume_pct  = 100
            resume_time = 0
        if completed:
            resume_pct  = 100
            resume_time = 0

        now = int(time.time())

        with self._lock:
            with closing(self._connect()) as conn:
                row = conn.execute(
                    'SELECT resume_data FROM progress WHERE id=?', (row_id,)
                ).fetchone()
                if not row:
                    return

                try:
                    resume_data = json.loads(row['resume_data'] or '{}')
                except Exception:
                    resume_data = {}

                resume_data['local'] = {
                    'pct':        resume_pct,
                    'time':       int(resume_time),
                    'updated_at': now,
                }

                conn.execute('''
                    UPDATE progress SET
                        resume_time=?, resume_pct=?, completed=?,
                        resume_data=?, last_watched_at=?
                    WHERE id=?
                ''', (int(resume_time), resume_pct, 1 if completed else 0,
                      json.dumps(resume_data), now, row_id))
                conn.commit()

        self._log(
            f'Local progress update: id={row_id} t={int(resume_time)}s '
            f'pct={resume_pct}% completed={completed}'
        )

    def update_enriched_metadata(self, row_id, poster=None, fanart=None,
                                landscape=None, clearlogo=None,
                                plot=None, duration=None):
        """
        Persist TMDB-enriched fields back to the DB after the first live fetch.
        Only fills NULL / zero columns so it never overwrites user-visible data.
        Called by tmdb_enricher.enrich_item() so subsequent widget renders skip
        the TMDB API entirely.
        """
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute('''
                    UPDATE progress SET
                        poster    = COALESCE(?, poster),
                        fanart    = COALESCE(?, fanart),
                        landscape = COALESCE(?, landscape),
                        clearlogo = COALESCE(?, clearlogo),
                        plot      = COALESCE(?, plot),
                        duration  = CASE WHEN ? > 0 AND (duration IS NULL OR duration = 0)
                                         THEN ? ELSE duration END
                    WHERE id = ?
                ''', (poster, fanart, landscape, clearlogo, plot,
                      duration or 0, duration or 0, row_id))
                conn.commit()

    def update_service_ids(self, row_id, service_ids):
        """Persist resolved IDs (e.g. from AniZip) back to the DB."""
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute(
                    'UPDATE progress SET service_ids=? WHERE id=?',
                    (json.dumps(service_ids), row_id)
                )
                conn.commit()

    def vacuum(self):
        with self._lock:
            with closing(self._connect()) as conn:
                conn.execute('VACUUM')

    def _row_to_dict(self, row):
        d = dict(row)
        for field in ('service_ids', 'resume_data'):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    d[field] = {}
            else:
                d[field] = {}
        # Deserialize sources list
        if d.get('sources'):
            try:
                d['sources'] = json.loads(d['sources'])
            except Exception:
                d['sources'] = []
        else:
            d['sources'] = []
        return d

    def _log(self, msg, level=None):
        if KODI_ENV:
            if level is None:
                try:
                    debug = xbmcaddon.Addon(
                        'plugin.video.rabitewatch'
                    ).getSettingBool('debug_logging')
                except Exception:
                    debug = False
                level = xbmc.LOGINFO if debug else xbmc.LOGDEBUG
            xbmc.log(f'[RabiteWatch-DB] {msg}', level)
