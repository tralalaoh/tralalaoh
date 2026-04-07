import requests
import json
import sys
import time

class AnimeIDTester:
    """
    Standalone tester for Anime ID translation using arm.haglund.dev
    """

    # API Endpoint
    ARM_API_URL = "https://arm.haglund.dev/api/v2/ids"

    # Mapping short codes to API expected source names
    SOURCE_MAP = {
        'mal': 'myanimelist',
        'myanimelist': 'myanimelist',
        'anilist': 'anilist',
        'kitsu': 'kitsu',
        'imdb': 'imdb',
        'tmdb': 'themoviedb',
        'thetvdb': 'thetvdb',
        'tvdb': 'thetvdb'
    }

    def __init__(self):
        self.session = requests.Session()
        # Fake a user agent just in case
        self.session.headers.update({
            'User-Agent': 'AnimeIDTester/1.0'
        })

    def get_all_ids(self, source, id_value):
        """
        Translate a single ID into ALL other IDs.
        """
        # clean inputs
        source = str(source).lower()
        id_value = str(id_value).strip()

        # map short code (e.g. 'mal') to full api name ('myanimelist')
        api_source = self.SOURCE_MAP.get(source)

        if not api_source:
            print(f"❌ Error: Unknown source '{source}'. Valid sources: {list(self.SOURCE_MAP.keys())}")
            return None

        print(f"\n🔎 Searching for {source.upper()}: {id_value}...")

        params = {
            'source': api_source,
            'id': id_value
        }

        try:
            start_time = time.time()
            response = self.session.get(self.ARM_API_URL, params=params, timeout=10)
            elapsed = (time.time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                print(f"✅ Success ({elapsed:.2f}ms)")
                return data
            elif response.status_code == 404:
                print(f"⚠️ ID not found in database.")
            else:
                print(f"❌ API Error: {response.status_code}")

        except Exception as e:
            print(f"❌ Connection Error: {e}")

        return None

def main():
    tester = AnimeIDTester()

    # --- TEST CASE 1: Attack on Titan (From Kitsu) ---
    # Kitsu ID 7442 should return MAL 16498, IMDb tt2560140, etc.
    print("-" * 50)
    print("TEST 1: Kitsu -> Others (Attack on Titan)")
    results = tester.get_all_ids('kitsu', '47679')
    if results:
        print(json.dumps(results, indent=2))

    # --- TEST CASE 2: One Piece (From IMDb) ---
    # IMDb tt0388629 should return MAL 21, AniList 21, etc.
    print("-" * 50)
    print("TEST 2: IMDb -> Others (One Piece)")
    results = tester.get_all_ids('imdb', ' tt9307686')
    if results:
        print(json.dumps(results, indent=2))

    # --- TEST CASE 3: Your Name (From MAL) ---
    # MAL 32281
    print("-" * 50)
    print("TEST 3: MAL -> Others (Your Name)")
    results = tester.get_all_ids('mal', '32281')
    if results:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting...")
