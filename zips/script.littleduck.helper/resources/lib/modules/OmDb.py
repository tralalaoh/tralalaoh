# -*- coding: utf-8 -*-
import xbmc, xbmcgui, xbmcvfs
import datetime as dt
import sqlite3 as database
import time
import requests
import json

settings_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/"
)
# Shares the same DB file as MDbList — separate table
omdb_database_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/ratings_cache.db"
)
IMAGE_PATH = "special://home/addons/skin.littleduck/resources/rating_images/"

OMDB_API_URL = "http://www.omdbapi.com/?apikey=%s&i=%s&r=json"


class OmDbAPI:

    def __init__(self):
        self.connect_database()

    def connect_database(self):
        if not xbmcvfs.exists(settings_path):
            xbmcvfs.mkdir(settings_path)

        self.dbcon = database.connect(
            omdb_database_path, timeout=20.0, isolation_level=None
        )
        self.dbcon.execute("PRAGMA journal_mode=WAL")
        self.dbcur = self.dbcon.cursor()
        self.dbcur.execute(
            """CREATE TABLE IF NOT EXISTS omdb_ratings (
                item_id TEXT NOT NULL PRIMARY KEY,
                ratings TEXT,
                last_updated TIMESTAMP
            )"""
        )
        xbmc.log("###littleduck: OmDbAPI database ready", 1)

    def clear_all_ratings(self):
        """Delete all cached OMDb ratings from database."""
        try:
            count_before = self.dbcur.execute(
                "SELECT COUNT(*) FROM omdb_ratings"
            ).fetchone()[0]
            self.dbcur.execute("DELETE FROM omdb_ratings")
            self.dbcon.commit()
            xbmc.log(
                f"###littleduck: OMDb cache cleared ({count_before} rows removed)", 1
            )
        except Exception as e:
            xbmc.log(f"###littleduck: Error clearing OMDb cache: {e}", 2)

    def get_cached_info(self, imdb_id):
        """Return cached OMDb ratings or None if missing/expired."""
        try:
            self.dbcur.execute(
                "SELECT ratings, last_updated FROM omdb_ratings WHERE item_id=?",
                (imdb_id,),
            )
            entry = self.dbcur.fetchone()
            if entry:
                ratings_data, last_updated = entry
                ratings = json.loads(ratings_data)
                last_updated_date = self.datetime_workaround(
                    last_updated, "%Y-%m-%d %H:%M:%S.%f"
                )
                if dt.datetime.now() - last_updated_date >= dt.timedelta(days=7):
                    xbmc.log(
                        f"###littleduck DEBUG: OMDb cache EXPIRED for {imdb_id}", 1
                    )
                    return None
                xbmc.log(
                    f"###littleduck DEBUG: OMDb cache HIT for {imdb_id}", 1
                )
                return ratings
            return None
        except Exception as e:
            xbmc.log(f"###littleduck: OMDb cache lookup error for {imdb_id}: {e}", 2)
            return None

    def fetch_info(self, imdb_id, api_key):
        """
        Fetch OMDb ratings for the given IMDb ID.

        Args:
            imdb_id: IMDb ID string (e.g. 'tt0111161')
            api_key: OMDb API key

        Returns:
            Dictionary of ratings data — same property names as MDbList
            plus the unique key 'omdbVotes'.
            Returns empty dict on failure.
        """
        if not imdb_id or not api_key:
            return {}

        cached = self.get_cached_info(imdb_id)
        if cached:
            return cached

        xbmc.log(
            f"###littleduck DEBUG: OMDb cache MISS — fetching from API for {imdb_id}", 1
        )
        data = self.get_result(imdb_id, api_key)

        if data:
            self.insert_or_update(imdb_id, data)

        return data

    def get_result(self, imdb_id, api_key):
        """Call the OMDb API and parse the response into property-ready dict."""
        url = OMDB_API_URL % (api_key, imdb_id)
        safe_url = url.replace(api_key, "HIDDEN_KEY")
        xbmc.log(f"###littleduck DEBUG: OMDb requesting: {safe_url}", 1)

        try:
            response = requests.get(url, timeout=10)
            xbmc.log(
                f"###littleduck DEBUG: OMDb HTTP status {response.status_code} for {imdb_id}", 1
            )

            if response.status_code != 200:
                xbmc.log(
                    f"###littleduck: OMDb API returned status {response.status_code}", 2
                )
                return {}

            json_data = response.json()

            if json_data.get("Response") != "True":
                xbmc.log(
                    f"###littleduck: OMDb no result for {imdb_id}: {json_data.get('Error', 'unknown error')}",
                    2,
                )
                return {}

            data = {}

            # IMDb rating (same key as MDbList so it can fill the gap)
            imdb_rating = json_data.get("imdbRating", "N/A")
            if imdb_rating and imdb_rating != "N/A":
                data["imdbRating"] = imdb_rating
                data["imdbImage"] = IMAGE_PATH + "imdb.png"

            # IMDb vote count — unique to OMDb (formatted as short number)
            imdb_votes = json_data.get("imdbVotes", "N/A")
            if imdb_votes and imdb_votes != "N/A":
                try:
                    votes_int = int(imdb_votes.replace(",", ""))
                    if votes_int >= 1_000_000:
                        data["omdbVotes"] = f"{votes_int / 1_000_000:.1f}M"
                    elif votes_int >= 1_000:
                        data["omdbVotes"] = f"{votes_int / 1_000:.0f}K"
                    else:
                        data["omdbVotes"] = str(votes_int)
                except ValueError:
                    data["omdbVotes"] = imdb_votes

            # Metacritic score (same key as MDbList)
            metascore = json_data.get("Metascore", "N/A")
            if metascore and metascore != "N/A":
                try:
                    int(metascore)  # validate it's numeric
                    data["metascore"] = metascore
                    data["metascoreImage"] = IMAGE_PATH + "metacritic.png"
                except ValueError:
                    pass

            # Rotten Tomatoes critic score from the Ratings array (same key as MDbList)
            for rating in json_data.get("Ratings", []):
                source = rating.get("Source", "")
                value_str = rating.get("Value", "")
                if source == "Rotten Tomatoes" and value_str.endswith("%"):
                    try:
                        value = int(value_str.rstrip("%"))
                        data["tomatoMeter"] = str(value)
                        if value > 74:
                            data["tomatoImage"] = IMAGE_PATH + "rtcertified.png"
                        elif value > 59:
                            data["tomatoImage"] = IMAGE_PATH + "rtfresh.png"
                        else:
                            data["tomatoImage"] = IMAGE_PATH + "rtrotten.png"
                    except ValueError:
                        pass

            xbmc.log(
                f"###littleduck DEBUG: OMDb result for {imdb_id}: {list(data.keys())}", 1
            )
            return data

        except requests.exceptions.Timeout:
            xbmc.log(f"###littleduck: OMDb timeout for {imdb_id}", 2)
            return {}
        except requests.exceptions.RequestException as e:
            xbmc.log(f"###littleduck: OMDb request error: {e}", 2)
            return {}
        except json.JSONDecodeError:
            xbmc.log("###littleduck: OMDb returned invalid JSON", 2)
            return {}
        except Exception as e:
            xbmc.log(f"###littleduck: OMDb unexpected error: {e}", 2)
            return {}

    def insert_or_update(self, imdb_id, ratings):
        """Cache OMDb ratings in the database."""
        try:
            now = dt.datetime.now()
            self.dbcur.execute(
                """INSERT OR REPLACE INTO omdb_ratings (item_id, ratings, last_updated)
                   VALUES (?, ?, ?)""",
                (imdb_id, json.dumps(ratings), now),
            )
            self.dbcon.commit()
            xbmc.log(
                f"###littleduck DEBUG: OMDb ratings cached for {imdb_id}", 1
            )
        except Exception as e:
            xbmc.log(
                f"###littleduck: Failed to cache OMDb ratings for {imdb_id}: {e}", 2
            )

    def datetime_workaround(self, datetime_string, str_format):
        try:
            return dt.datetime.strptime(datetime_string, str_format)
        except TypeError:
            return dt.datetime(
                *(time.strptime(datetime_string, str_format)[0:6])
            )
