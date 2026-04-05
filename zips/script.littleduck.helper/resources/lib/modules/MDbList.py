import xbmc, xbmcgui, xbmcvfs
import datetime as dt
import sqlite3 as database
import time
import requests
import json

settings_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/"
)
ratings_database_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/ratings_cache.db"
)
IMAGE_PATH = "special://home/addons/skin.littleduck/resources/rating_images/"


def make_session(url="https://"):
    session = requests.Session()
    session.mount(url, requests.adapters.HTTPAdapter(pool_maxsize=100))
    return session


# Base URL - query parameter will be added dynamically based on ID type
base_api_url = "https://mdblist.com/api/?apikey=%s"
session = make_session("https://www.mdblist.com/")

# Rating keys that indicate valid rating data
VALID_RATING_KEYS = ['imdbRating', 'tomatoMeter', 'metascore', 'tmdbRating', 'tomatoUserMeter', 'traktRating', 'letterboxdRating', 'awardWins']


class MDbListAPI:
    last_checked_imdb_id = None

    def __init__(self):
        self.connect_database()

    def connect_database(self):
        """
        Connect to database and ensure schema is correct.
        Handles migration from old schema automatically.
        """
        if not xbmcvfs.exists(settings_path):
            xbmcvfs.mkdir(settings_path)

        self.dbcon = database.connect(
            ratings_database_path, timeout=20.0, isolation_level=None
        )
        self.dbcon.execute("PRAGMA journal_mode=WAL")
        self.dbcur = self.dbcon.cursor()

        # Check if table exists and get its schema
        self.dbcur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='ratings'"
        )
        result = self.dbcur.fetchone()

        if result:
            table_schema = result[0]
            # Check if id_type column exists in the schema
            if "id_type" not in table_schema:
                xbmc.log(
                    "###littleduck: Migrating ratings database to include id_type column",
                    1
                )
                # Create new table with correct schema
                self.dbcur.execute(
                    """CREATE TABLE IF NOT EXISTS ratings_new (
                        item_id TEXT NOT NULL,
                        id_type TEXT NOT NULL,
                        ratings TEXT,
                        last_updated TIMESTAMP,
                        PRIMARY KEY (item_id, id_type)
                    )"""
                )
                # Copy data from old table (all entries will be assumed as 'imdb' type)
                self.dbcur.execute(
                    """INSERT INTO ratings_new (item_id, id_type, ratings, last_updated)
                       SELECT item_id, 'imdb', ratings, last_updated FROM ratings"""
                )
                # Drop old table and rename new one
                self.dbcur.execute("DROP TABLE ratings")
                self.dbcur.execute("ALTER TABLE ratings_new RENAME TO ratings")
                xbmc.log("###littleduck: Database migration completed", 1)
        else:
            # Create table with new schema
            self.dbcur.execute(
                """CREATE TABLE IF NOT EXISTS ratings (
                    item_id TEXT NOT NULL,
                    id_type TEXT NOT NULL,
                    ratings TEXT,
                    last_updated TIMESTAMP,
                    PRIMARY KEY (item_id, id_type)
                )"""
            )
            xbmc.log("###littleduck: Created new ratings database", 1)

    def _is_valid_ratings_data(self, data):
        """
        Check if the ratings data contains at least one valid rating.
        Returns True if data has any of the key rating fields with actual values.
        """
        if not data or not isinstance(data, dict):
            return False

        # Check if any of the important rating keys have non-empty values
        for key in VALID_RATING_KEYS:
            if data.get(key):
                return True

        return False

    def clear_all_ratings(self):
        """Delete all cached ratings from database."""
        xbmc.log("###littleduck DEBUG: ========================================", 1)
        xbmc.log("###littleduck DEBUG: clear_all_ratings() function CALLED", 1)
        xbmc.log("###littleduck DEBUG: ========================================", 1)

        try:
            # Check database connection
            xbmc.log(f"###littleduck DEBUG: Database connection status: {self.dbcon is not None}", 1)
            xbmc.log(f"###littleduck DEBUG: Database cursor status: {self.dbcur is not None}", 1)

            # Count rows before deletion
            xbmc.log("###littleduck DEBUG: Counting rows before deletion...", 1)
            row_count_before = self.dbcur.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
            xbmc.log(f"###littleduck DEBUG: Rows BEFORE deletion: {row_count_before}", 1)

            # Perform deletion
            xbmc.log("###littleduck DEBUG: Executing DELETE FROM ratings...", 1)
            self.dbcur.execute("DELETE FROM ratings")
            xbmc.log("###littleduck DEBUG: DELETE command executed", 1)

            # Commit changes
            xbmc.log("###littleduck DEBUG: Committing changes...", 1)
            self.dbcon.commit()
            xbmc.log("###littleduck DEBUG: Changes committed", 1)

            # Verify deletion
            xbmc.log("###littleduck DEBUG: Verifying deletion...", 1)
            row_count_after = self.dbcur.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
            xbmc.log(f"###littleduck DEBUG: ✓ Cache cleared. Rows AFTER deletion: {row_count_after}", 1)

            # Show success dialog
            xbmc.log("###littleduck DEBUG: Creating success dialog...", 1)
            dialog = xbmcgui.Dialog()
            xbmc.log("###littleduck DEBUG: Showing success dialog to user...", 1)
            dialog.ok(
                "littleduck",
                "Ratings cache cleared successfully![CR][CR]"
                "Please restart Kodi for changes to take effect."
            )
            xbmc.log("###littleduck DEBUG: Success dialog closed by user", 1)
            xbmc.log("###littleduck DEBUG: clear_all_ratings() completed SUCCESSFULLY", 1)

        except Exception as e:
            xbmc.log("###littleduck DEBUG: ========================================", 2)
            xbmc.log(f"###littleduck ERROR: Exception caught in clear_all_ratings()", 2)
            xbmc.log(f"###littleduck ERROR: Exception type: {type(e).__name__}", 2)
            xbmc.log(f"###littleduck ERROR: Exception message: {str(e)}", 2)
            xbmc.log("###littleduck DEBUG: ========================================", 2)

            # Show error dialog
            xbmc.log("###littleduck DEBUG: Creating error dialog...", 2)
            dialog = xbmcgui.Dialog()
            dialog.ok("littleduck", f"Error clearing database: {str(e)}")
            xbmc.log("###littleduck DEBUG: Error dialog closed by user", 2)

        xbmc.log("###littleduck DEBUG: ========================================", 1)
        xbmc.log("###littleduck DEBUG: clear_all_ratings() function EXITING", 1)
        xbmc.log("###littleduck DEBUG: ========================================", 1)

    def get_cached_info(self, item_id, id_type):
        """
        Retrieve cached ratings from database.
        Returns None if not cached, cache is expired, or cache contains invalid data.
        """
        try:
            self.dbcur.execute(
                "SELECT item_id, id_type, ratings, last_updated FROM ratings WHERE item_id=? AND id_type=?",
                (item_id, id_type),
            )
            entry = self.dbcur.fetchone()

            if entry:
                _, _, ratings_data, last_updated = entry
                ratings = json.loads(ratings_data)
                last_updated_date = self.datetime_workaround(
                    last_updated, "%Y-%m-%d %H:%M:%S.%f"
                )

                # Check if cache is expired (7 days)
                if dt.datetime.now() - last_updated_date >= dt.timedelta(days=7):
                    xbmc.log(
                        f"###littleduck DEBUG: Cache EXPIRED for {id_type}:{item_id}",
                        1
                    )
                    return None

                # Validate that cached data contains actual ratings
                if not self._is_valid_ratings_data(ratings):
                    xbmc.log(
                        f"###littleduck DEBUG: Cache INVALID (empty ratings) for {id_type}:{item_id} - will retry API",
                        2
                    )
                    return None

                xbmc.log(
                    f"###littleduck DEBUG: Cache HIT (valid) for {id_type}:{item_id}",
                    1
                )
                return ratings

            return None

        except Exception as e:
            xbmc.log(f"###littleduck: Cache lookup error for {id_type}:{item_id}: {str(e)}", 2)
            return None

    def build_api_url(self, api_key, item_id, id_type):
        """
        Build the appropriate API URL based on ID type.
        MDbList API supports: i (IMDb), tmdb (TMDb), tvdb (TVDb)
        """
        if id_type == "imdb":
            param = f"&i={item_id}"
        elif id_type == "tmdb":
            param = f"&tmdb={item_id}"
        elif id_type == "tvdb":
            param = f"&tvdb={item_id}"
        else:
            xbmc.log(f"###littleduck: Unknown ID type: {id_type}", 2)
            return None

        url = base_api_url % api_key + param

        # Log URL with hidden API key for debugging
        safe_url = url.replace(api_key, "HIDDEN_KEY")
        xbmc.log(f"###littleduck DEBUG: Requesting URL: {safe_url}", 1)

        return url

    def fetch_info(self, meta, api_key):
        """
        Fetch ratings info from MDbList API.

        Args:
            meta: Dictionary containing 'id' and 'id_type'
                  id_type should be one of: 'imdb', 'tmdb', 'tvdb'
            api_key: MDbList API key

        Returns:
            Dictionary of ratings data or empty dict if none found
        """
        item_id = meta.get("id")
        id_type = meta.get("id_type", "imdb")

        if not item_id or not api_key:
            xbmc.log(
                f"###littleduck DEBUG: Missing ID or API key (ID: {item_id}, Key present: {bool(api_key)})",
                2
            )
            return {}

        xbmc.log(
            f"###littleduck DEBUG: fetch_info called for {id_type}:{item_id}",
            1
        )

        # Check cache first
        cached_info = self.get_cached_info(item_id, id_type)
        if cached_info:
            # Cache hit with valid data
            return cached_info

        # Cache miss or invalid - fetch from API
        xbmc.log(
            f"###littleduck DEBUG: Cache MISS - fetching from API for {id_type}:{item_id}",
            1
        )
        data = self.get_result(item_id, id_type, api_key)

        # Only cache if we got valid rating data
        if data and self._is_valid_ratings_data(data):
            self.insert_or_update_ratings(item_id, id_type, data)
        elif data:
            xbmc.log(
                f"###littleduck DEBUG: API returned data but no valid ratings for {id_type}:{item_id}",
                2
            )

        return data

    def get_result(self, item_id, id_type, api_key):
        """
        Fetch ratings from MDbList API using the appropriate ID type.

        Args:
            item_id: The ID (IMDb, TMDb, or TVDb)
            id_type: Type of ID ('imdb', 'tmdb', or 'tvdb')
            api_key: MDbList API key

        Returns:
            Dictionary of ratings or empty dict
        """
        url = self.build_api_url(api_key, item_id, id_type)
        if not url:
            return {}

        try:
            xbmc.log(
                f"###littleduck DEBUG: Sending HTTP request for {id_type}:{item_id}...",
                1
            )

            response = requests.get(url, timeout=10)

            xbmc.log(
                f"###littleduck DEBUG: HTTP Status Code: {response.status_code} for {id_type}:{item_id}",
                1
            )

            if response.status_code != 200:
                xbmc.log(
                    f"###littleduck: MDbList API returned status {response.status_code} for {id_type}:{item_id}",
                    2
                )
                # Log response body for debugging (first 200 chars)
                try:
                    error_body = response.text[:200]
                    xbmc.log(
                        f"###littleduck DEBUG: Error response: {error_body}",
                        2
                    )
                except Exception as e:
                    xbmc.log(f"###littleduck: Failed to read error response body: {e}", 2)
                return {}

            json_data = response.json()

            # Log what we received
            xbmc.log(
                f"###littleduck DEBUG: API response received for {id_type}:{item_id}",
                1
            )

            # Check if we got ratings data
            ratings_list = json_data.get("ratings", [])
            if not ratings_list:
                xbmc.log(
                    f"###littleduck DEBUG: ⚠ API returned empty ratings array for {id_type}:{item_id}",
                    2
                )
                # Log the full response for debugging (first 500 chars)
                try:
                    response_preview = str(json_data)[:500]
                    xbmc.log(
                        f"###littleduck DEBUG: Response data: {response_preview}",
                        2
                    )
                except Exception as e:
                    xbmc.log(f"###littleduck: Failed to preview response data: {e}", 2)
            else:
                xbmc.log(
                    f"###littleduck DEBUG: Found {len(ratings_list)} rating sources",
                    1
                )

        except requests.exceptions.Timeout:
            xbmc.log(f"###littleduck: MDbList API timeout for {id_type}:{item_id}", 2)
            return {}
        except requests.exceptions.RequestException as e:
            xbmc.log(f"###littleduck: MDbList API request error: {str(e)}", 2)
            return {}
        except json.JSONDecodeError:
            xbmc.log(f"###littleduck: MDbList API returned invalid JSON", 2)
            return {}
        except Exception as e:
            xbmc.log(f"###littleduck: MDbList API error: {str(e)}", 2)
            return {}

        # Parse ratings from response
        ratings = json_data.get("ratings", [])
        data = {}

        for rating in ratings:
            source = rating.get("source")
            value = rating.get("value")
            popular = rating.get("popular")

            if source == "imdb":
                if value is not None:
                    data["imdbRating"] = str(value)
                    data["imdbImage"] = IMAGE_PATH + "imdb.png"
                    xbmc.log(
                        f"###littleduck DEBUG: Found IMDb rating: {value}",
                        1
                    )
                    if popular is not None:
                        try:
                            popular_int = int(str(popular).replace(",", "").strip())
                        except (ValueError, TypeError):
                            popular_int = 9999
                        data["popularRating"] = "#" + str(popular_int)
                        if popular_int <= 10:
                            data["popularImage"] = IMAGE_PATH + "purpleflame.png"
                        elif popular_int <= 33:
                            data["popularImage"] = IMAGE_PATH + "pinkflame.png"
                        elif popular_int <= 66:
                            data["popularImage"] = IMAGE_PATH + "redflame.png"
                        elif popular_int <= 100:
                            data["popularImage"] = IMAGE_PATH + "orangeflame.png"
                        else:
                            data["popularImage"] = IMAGE_PATH + "blueflame.png"

            elif source == "metacritic":
                if value is not None:
                    data["metascore"] = str(value)
                    data["metascoreImage"] = IMAGE_PATH + "metacritic.png"

            elif source == "tmdb":
                if value is not None:
                    # TMDb ratings are 0-10, convert to percentage-like format
                    data["tmdbRating"] = str(value)
                    data["tmdbImage"] = IMAGE_PATH + "tmdb.png"

            elif source == "tomatoes":
                if value is not None:
                    data["tomatoMeter"] = str(value)
                    if value > 74:
                        data["tomatoImage"] = IMAGE_PATH + "rtcertified.png"
                    elif value > 59:
                        data["tomatoImage"] = IMAGE_PATH + "rtfresh.png"
                    else:
                        data["tomatoImage"] = IMAGE_PATH + "rtrotten.png"

            elif source == "tomatoesaudience":
                if value is not None:
                    data["tomatoUserMeter"] = str(value)
                    if value > 59:
                        data["tomatoUserImage"] = IMAGE_PATH + "popcorn.png"
                    else:
                        data["tomatoUserImage"] = IMAGE_PATH + "popcorn_spilt.png"

            elif source == "trakt":
                if value is not None:
                    data["traktRating"] = str(value) + "%"
                    data["traktImage"] = IMAGE_PATH + "trakt.png"
                    xbmc.log(
                        f"###littleduck DEBUG: Found Trakt rating: {value}",
                        1
                    )

            elif source == "letterboxd":
                if value is not None:
                    data["letterboxdRating"] = str(value)
                    data["letterboxdImage"] = IMAGE_PATH + "letterboxd.png"
                    xbmc.log(
                        f"###littleduck DEBUG: Found Letterboxd rating: {value}",
                        1
                    )

        # Parse total award wins from top-level awards field
        awards = json_data.get("awards", {})
        if awards:
            wins = awards.get("wins")
            if wins is not None and wins > 0:
                data["awardWins"] = str(wins)
                data["awardImage"] = IMAGE_PATH + "emmys.png"
                xbmc.log(
                    f"###littleduck DEBUG: Found award wins: {wins}",
                    1
                )

        return data

    def insert_or_update_ratings(self, item_id, id_type, ratings):
        """
        Insert or update ratings in the database.

        Args:
            item_id: The ID (IMDb, TMDb, or TVDb)
            id_type: Type of ID ('imdb', 'tmdb', or 'tvdb')
            ratings: Dictionary of ratings data
        """
        try:
            now = dt.datetime.now()
            self.dbcur.execute(
                """INSERT OR REPLACE INTO ratings (item_id, id_type, ratings, last_updated)
                   VALUES (?, ?, ?, ?)""",
                (item_id, id_type, json.dumps(ratings), now),
            )
            self.dbcon.commit()
            xbmc.log(
                f"###littleduck DEBUG: Cached ratings for {id_type}:{item_id}",
                1
            )
        except Exception as e:
            xbmc.log(
                f"###littleduck: Failed to cache ratings for {id_type}:{item_id}: {str(e)}",
                2
            )

    def datetime_workaround(self, datetime_string, str_format):
        """
        Workaround for Python datetime parsing issues.
        """
        try:
            datetime_object = dt.datetime.strptime(datetime_string, str_format)
        except TypeError:
            datetime_object = dt.datetime(
                *(time.strptime(datetime_string, str_format)[0:6])
            )
        return datetime_object
