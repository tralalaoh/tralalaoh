import re
import sys
import json

# --- Mock Kodi Libraries ---
try:
    import requests
    import xbmc
    import xbmcgui
    import xbmcplugin
except ImportError:
    import requests
    class MockXBMC:
        LOGINFO = 1
        def log(self, msg, level):
            print(f"  [LOG] {msg}")
    xbmc = MockXBMC()

class AnimeResolver:
    def __init__(self):
        self.anilist_url = "https://graphql.anilist.co"
        self.default_cour_length = 12
        self.request_timeout = 5

    def log(self, msg):
        xbmc.log(f"[AnimeResolver] {msg}", xbmc.LOGINFO)

    # ---------------------------------------------------------
    # STRATEGY 1: ANILIST RECURSIVE OFFSET
    # ---------------------------------------------------------
    def _calculate_api_offset(self, anilist_id):
        """
        Recursively queries AniList for 'PREQUEL' relations and sums their episode counts.
        """
        if not anilist_id: return None

        current_id = anilist_id
        total_offset = 0
        chain_log = []

        # GraphQL Query: Fetch Episodes + Prequel Relation
        # We fetch the 'format' to ensure we don't count Movies/OVAs as main season offsets
        query = '''
        query ($id: Int) {
          Media (id: $id, type: ANIME) {
            id
            title { romaji }
            episodes
            format
            relations {
              edges {
                relationType
                node {
                  id
                  title { romaji }
                  episodes
                  format
                  type
                }
              }
            }
          }
        }
        '''

        # Recursive Loop (Max 10 seasons back)
        for _ in range(10):
            try:
                # Make the request
                r = requests.post(self.anilist_url, json={'query': query, 'variables': {'id': current_id}}, timeout=self.request_timeout)
                if r.status_code != 200:
                    self.log(f"AniList HTTP Error: {r.status_code}")
                    break

                data = r.json().get('data', {}).get('Media')
                if not data: break

                # Search for the PREQUEL relation
                prequel_node = None
                relations = data.get('relations', {}).get('edges', [])

                for edge in relations:
                    if edge['relationType'] == 'PREQUEL':
                        node = edge['node']
                        # IMPORTANT: Only count TV Series or ONAs (Web Anime).
                        # We usually skip Movies/OVAs so they don't break the season numbering.
                        if node.get('format') in ['TV', 'TV_SHORT', 'ONA'] and node.get('type') == 'ANIME':
                            prequel_node = node
                            break

                if prequel_node:
                    # We found a previous season!
                    eps = prequel_node.get('episodes')

                    if eps:
                        total_offset += eps
                        chain_log.append(f"{eps} (ID:{prequel_node['id']} - {prequel_node['title']['romaji']})")

                        # Set current ID to the prequel to check if IT has a prequel
                        current_id = prequel_node['id']
                    else:
                        # Prequel exists but episode count is null/unknown (e.g. actively airing or broken data)
                        self.log(f"Prequel found ({prequel_node['id']}) but has no episode count.")
                        break
                else:
                    # No prequel found, we have reached Season 1.
                    break

            except Exception as e:
                self.log(f"AniList API Error: {e}")
                return None

        if chain_log:
            self.log(f"Offset Chain: {' + '.join(reversed(chain_log))} = {total_offset}")

        return total_offset

    # ---------------------------------------------------------
    # STRATEGY 2: REGEX FALLBACK
    # ---------------------------------------------------------
    def _calculate_regex_offset(self, title):
        if not title: return 0
        match = re.search(r'(?:Part|Cour)\s?(\d+)', title, re.IGNORECASE)
        if match:
            part = int(match.group(1))
            if part > 1:
                return (part - 1) * self.default_cour_length
        return 0

    # ---------------------------------------------------------
    # MAIN PUBLIC FUNCTION
    # ---------------------------------------------------------
    def get_absolute_number(self, anilist_id, relative_episode, title=""):
        """
        Calculates the absolute episode number.
        """
        offset = 0
        method = "None"

        # 1. Try Automated API Logic
        if anilist_id:
            api_offset = self._calculate_api_offset(anilist_id)
            if api_offset is not None:
                offset = api_offset
                method = "AniList API"

        # 2. Try Regex Fallback (If API failed or no ID)
        if offset == 0 and title:
            regex_offset = self._calculate_regex_offset(title)
            if regex_offset > 0:
                offset = regex_offset
                method = "Regex Guess"

        final_episode = int(relative_episode) + offset

        # Safety: If input is already absolute (e.g. Ep 100), don't add offset
        if int(relative_episode) > 50 and offset > 0:
            return int(relative_episode)

        self.log(f"Resolved '{title}' (AniList:{anilist_id}): Rel {relative_episode} + Offset {offset} [{method}] = Abs {final_episode}")

        return final_episode

# =========================================================================
# TEST RUNNER
# =========================================================================

def run_tests():
    resolver = AnimeResolver()

    print("\n" + "="*70)
    print("  ANIME RECURSIVE TEST (DIRECT ANILIST IDS)")
    print("="*70)

    # --- TEST 1: Attack on Titan Final Season Part 2 ---
    # AniList ID: 127237
    # Logic: S4P1 (16) + S3P2 (10) + S3P1 (12) + S2 (12) + S1 (25) = 75
    print("\nTest 1: Attack on Titan Final Season Part 2 (ID: 127237)")
    res = resolver.get_absolute_number(127237, 1, "Attack on Titan Final Season Part 2")

    if res == 76:
        print(f"✅ SUCCESS: {res}")
    else:
        print(f"❌ FAIL: Expected 76, got {res}")


    # --- TEST 2: Dr. STONE: Stone Wars (Season 2) ---
    # AniList ID: 112151
    # Logic: S1 (24 eps).
    # Expected: Ep 1 -> 25
    print("\nTest 2: Dr. STONE Season 2 (ID: 112151)")
    res = resolver.get_absolute_number(112151, 1, "Dr. STONE: Stone Wars")

    if res == 25:
        print(f"✅ SUCCESS: {res}")
    else:
        print(f"❌ FAIL: Expected 25, got {res}")


    # --- TEST 3: Bleach TYBW Part 2 ---
    # AniList ID: 155749
    # Logic: TYBW Part 1 (13 eps) + Original Bleach (366 eps) = 379.
    # Result: Ep 1 -> 380.
    # Note: This technically "Correct" for AniList, though file names might be '14'.
    # Most scrapers handle Absolute numbering correctly.
    print("\nTest 3: Bleach TYBW Part 2 (ID: 155749)")
    res = resolver.get_absolute_number(155749, 1, "Bleach: Thousand-Year Blood War - The Separation")

    if res == 380:
        print(f"✅ SUCCESS: {res} (Calculated full absolute chain including original series)")
    elif res == 14:
        print(f"⚠️ RESULT: 14 (Only counted current arc)")
    else:
        print(f"❌ FAIL: Got {res}")

if __name__ == "__main__":
    run_tests()
