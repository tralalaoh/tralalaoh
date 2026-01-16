PROJECT STRUCTURE: my-kodi-repo
.
├── .nojekyll
├── _generator.py
├── addon.xml
├── addons.xml
├── addons.xml.md5
├── diagnose_index.sh
├── index.html
├── README_FOR_REPO.md
├── repo-logo.png
└── zips
    ├── index.html
    ├── plugin.video.3sk
    │   ├── 3sk.jpg
    │   ├── addon.xml
    │   ├── index.html
    │   └── plugin.video.3sk-1.0.1.zip
    ├── plugin.video.tmdb.turkish
    │   ├── addon.xml
    │   ├── icon.svg
    │   ├── index.html
    │   └── plugin.video.tmdb.turkish-2.0.0.zip
    ├── plugin.video.turkish123
    │   ├── addon.xml
    │   ├── index.html
    │   ├── plugin.video.turkish123-1.0.0.zip
    │   └── turkish123.jpg
    └── plugin.video.upt
        ├── addon.xml
        ├── icon.png
        ├── index.html
        └── plugin.video.upt.zip

======================================================================
FILE CONTENTS START HERE
======================================================================

START OF FILE: _generator.py
----------------------------
import os
import hashlib
import re

# Configuration
ADDONS_DIR = "zips"

def generate_addons_xml():
    """ Generates addons.xml and addons.xml.md5 """
    xbmc_addons = []

    if os.path.exists(ADDONS_DIR):
        for root, dirs, files in os.walk(ADDONS_DIR):
            for file_name in files:
                if file_name == "addon.xml":
                    addon_path = os.path.join(root, file_name)
                    try:
                        with open(addon_path, "r", encoding="utf-8") as f:
                            xml_content = f.read().strip()
                            if xml_content.startswith("<?xml"):
                                xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, count=1).strip()
                            xbmc_addons.append(xml_content)
                    except Exception as e:
                        print(f"Error reading {addon_path}: {e}")

    if os.path.exists("addon.xml"):
        with open("addon.xml", "r", encoding="utf-8") as f:
            xml_content = f.read().strip()
            if xml_content.startswith("<?xml"):
                xml_content = re.sub(r'<\?xml[^>]*\?>', '', xml_content, count=1).strip()
            xbmc_addons.append(xml_content)

    final_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    final_xml += "\n".join(xbmc_addons)
    final_xml += '\n</addons>'

    with open("addons.xml", "w", encoding="utf-8") as f:
        f.write(final_xml)

    m = hashlib.md5(final_xml.encode("utf-8")).hexdigest()
    with open("addons.xml.md5", "w") as f:
        f.write(m)

    print("✅ addons.xml & md5 generated.")

def generate_directory_indexes():
    """
    Recursively creates index.html files
    so Kodi can browse folders on GitHub Pages
    """
    # Start from current directory
    start_dir = "."

    for root, dirs, files in os.walk(start_dir):
        # Skip .git folder
        if ".git" in root: continue

        # Build HTML content
        html = "<!DOCTYPE html><html><head><title>Index of /</title></head><body>"
        html += "<h1>Index of /</h1><hr><pre>"

        # Link to Parent Directory
        html += '<a href="../">../</a>\n'

        # List Directories
        for d in dirs:
            if d.startswith(".") or d == "venv": continue
            html += f'<a href="{d}/">{d}/</a>\n'

        # List Files
        for f in files:
            if f in ["index.html", "_generator.py", ".gitignore", ".DS_Store"]: continue
            html += f'<a href="{f}">{f}</a>\n'

        html += "</pre><hr></body></html>"

        # Write index.html in the current folder
        index_path = os.path.join(root, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(html)

    print("✅ Directory Indexes generated (Recursive).")

if __name__ == "__main__":
    generate_addons_xml()
    generate_directory_indexes()


END OF FILE: _generator.py
======================================================================

START OF FILE: addon.xml
------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="repository.tralalaoh" name="Tralalaoh Repository" version="1.0.0" provider-name="tralalaoh">
    <extension point="xbmc.addon.repository" name="Tralalaoh Add-ons">
        <dir>
            <info compressed="false">https://tralalaoh.github.io/tralalaoh/addons.xml</info>
            <checksum>https://tralalaoh.github.io/tralalaoh/addons.xml.md5</checksum>
            <datadir zip="true">https://tralalaoh.github.io/tralalaoh/zips/</datadir>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary>Tralalaoh's Kodi Addons</summary>
        <description>Repository for 3SK Video and other addons.</description>
        <platform>all</platform>
        <assets>
            <icon>icon.png</icon>
        </assets>
    </extension>
</addon>


END OF FILE: addon.xml
======================================================================

START OF FILE: addons.xml
-------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addons>
<addon id="plugin.video.3sk" name="3SK Video" version="1.1.0" provider-name="Tralalaoh">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">3SK Video Streaming Addon</summary>
        <description lang="en_GB">Watch series and episodes from 3SK streaming service. This addon provides access to a wide variety of TV shows and series.</description>
        <disclaimer lang="en_GB">The authors do not host or distribute any of the content displayed by this addon. The authors have no affiliation with the content provider.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://github.com/yourusername/plugin.video.3sk</website>
        <source>https://github.com/yourusername/plugin.video.3sk</source>
        <news>
v1.1.0 (2025-12-25)
- Added real-time search functionality
- Search results show episodes with automatic parent series detection
- Selecting an episode from search navigates to full series page
v1.0.0 (2025-12-24)
- Initial release
- Browse series catalog
- View episode lists
- Play episodes with stream resolution
        </news>
        <assets>
            <icon>3sk.jpg</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>
<addon id="plugin.video.turkish123" name="Turkish123" version="1.0.0" provider-name="Tralalaoh">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">Turkish123 Video Streaming</summary>
        <description lang="en_GB">Watch Turkish series and shows from Turkish123. Features smart caching for fast playback, favorites, watch history, and resume positions.</description>
        <disclaimer lang="en_GB">The authors do not host or distribute any of the content displayed by this addon. The authors have no affiliation with the content provider.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://www2.turkish123.org</website>
        <source>https://github.com/yourusername/plugin.video.turkish123</source>
        <news>
v1.0.0 (2025-12-25)
- Initial release
- Browse series catalog
- Smart 2-level caching (fast playback)
- Search functionality
- Favorites system
- Watch history and continue watching
- Resume playback positions
- Auto-play next episode
        </news>
        <assets>
            <icon>turkish123.jpg</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>
<addon id="plugin.video.tmdb.turkish" name="Turkish Series (TMDB)" version="2.0.0" provider-name="Hamza">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
        <import addon="inputstream.adaptive" version="20.3.0" optional="true"/>
    </requires>
    
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">Turkish Series with TMDB Metadata</summary>
        <description lang="en_GB">Browse and watch Turkish series with beautiful TMDB metadata. Supports both Arabic (3SK) and English (Turkish123) audio.

🎬 Features:
- Popular Turkish Series
- Currently Airing Shows  
- Discover New Series
- Rich metadata (posters, descriptions, cast)
- Dual audio support (Arabic/English)
- Smart caching for instant playback

📺 Officially Supported:
- Android TV
- Linux (Ubuntu, Fedora, LibreELEC, OSMC)
- Windows 7/10/11

Also works on: macOS, Fire TV, Raspberry Pi 3+
        </description>
        <disclaimer lang="en_GB">This addon uses The Movie Database (TMDB) API but is not endorsed by TMDB. Content is streamed from third-party sources. The addon author is not responsible for the content.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://www.themoviedb.org</website>
        <source>https://github.com/hamza/plugin.video.tmdb.turkish</source>
        <news>
v2.0.0 (2025-12-27)
- 🎬 PHASE 2 COMPLETE: Actual video playback!
- ✅ 3SK Engine integrated (Arabic audio)
- ✅ Smart server index caching (24h)
- ✅ Episode search and mapping
- ✅ Multi-language name translation
- ✅ HLS streaming with anti-403 headers
- ✅ YOUR proven stream extraction logic
- Ready for Turkish123 engine (Phase 2C)

v1.0.0 (2025-12-27)
- Initial release (Phase 1)
- Browse Turkish series from TMDB
- Popular / Airing Now / Discover categories
- Rich metadata integration
        </news>
        <assets>
            <icon>resources/media/icon.png</icon>
            <fanart>resources/media/fanart.png</fanart>
        </assets>
    </extension>
</addon>
<addon id="repository.tralalaoh" name="Tralalaoh Repository" version="1.0.0" provider-name="tralalaoh">
    <extension point="xbmc.addon.repository" name="Tralalaoh Add-ons">
        <dir>
            <info compressed="false">https://tralalaoh.github.io/tralalaoh/addons.xml</info>
            <checksum>https://tralalaoh.github.io/tralalaoh/addons.xml.md5</checksum>
            <datadir zip="true">https://tralalaoh.github.io/tralalaoh/zips/</datadir>
        </dir>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary>Tralalaoh's Kodi Addons</summary>
        <description>Repository for 3SK Video and other addons.</description>
        <platform>all</platform>
        <assets>
            <icon>icon.png</icon>
        </assets>
    </extension>
</addon>
</addons>

END OF FILE: addons.xml
======================================================================

START OF FILE: zips/plugin.video.3sk/addon.xml
----------------------------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.3sk" name="3SK Video" version="1.1.0" provider-name="Tralalaoh">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">3SK Video Streaming Addon</summary>
        <description lang="en_GB">Watch series and episodes from 3SK streaming service. This addon provides access to a wide variety of TV shows and series.</description>
        <disclaimer lang="en_GB">The authors do not host or distribute any of the content displayed by this addon. The authors have no affiliation with the content provider.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://github.com/yourusername/plugin.video.3sk</website>
        <source>https://github.com/yourusername/plugin.video.3sk</source>
        <news>
v1.1.0 (2025-12-25)
- Added real-time search functionality
- Search results show episodes with automatic parent series detection
- Selecting an episode from search navigates to full series page
v1.0.0 (2025-12-24)
- Initial release
- Browse series catalog
- View episode lists
- Play episodes with stream resolution
        </news>
        <assets>
            <icon>3sk.jpg</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>


END OF FILE: zips/plugin.video.3sk/addon.xml
======================================================================

START OF FILE: zips/plugin.video.turkish123/addon.xml
-----------------------------------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.turkish123" name="Turkish123" version="1.0.0" provider-name="Tralalaoh">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
    </requires>
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">Turkish123 Video Streaming</summary>
        <description lang="en_GB">Watch Turkish series and shows from Turkish123. Features smart caching for fast playback, favorites, watch history, and resume positions.</description>
        <disclaimer lang="en_GB">The authors do not host or distribute any of the content displayed by this addon. The authors have no affiliation with the content provider.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://www2.turkish123.org</website>
        <source>https://github.com/yourusername/plugin.video.turkish123</source>
        <news>
v1.0.0 (2025-12-25)
- Initial release
- Browse series catalog
- Smart 2-level caching (fast playback)
- Search functionality
- Favorites system
- Watch history and continue watching
- Resume playback positions
- Auto-play next episode
        </news>
        <assets>
            <icon>turkish123.jpg</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>


END OF FILE: zips/plugin.video.turkish123/addon.xml
======================================================================

START OF FILE: zips/plugin.video.tmdb.turkish/addon.xml
-------------------------------------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.tmdb.turkish" name="Turkish Series (TMDB)" version="2.0.0" provider-name="Hamza">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
        <import addon="script.module.requests" version="2.31.0"/>
        <import addon="script.module.beautifulsoup4" version="4.11.0"/>
        <import addon="inputstream.adaptive" version="20.3.0" optional="true"/>
    </requires>
    
    <extension point="xbmc.python.pluginsource" library="main.py">
        <provides>video</provides>
    </extension>
    
    <extension point="xbmc.addon.metadata">
        <summary lang="en_GB">Turkish Series with TMDB Metadata</summary>
        <description lang="en_GB">Browse and watch Turkish series with beautiful TMDB metadata. Supports both Arabic (3SK) and English (Turkish123) audio.

🎬 Features:
- Popular Turkish Series
- Currently Airing Shows  
- Discover New Series
- Rich metadata (posters, descriptions, cast)
- Dual audio support (Arabic/English)
- Smart caching for instant playback

📺 Officially Supported:
- Android TV
- Linux (Ubuntu, Fedora, LibreELEC, OSMC)
- Windows 7/10/11

Also works on: macOS, Fire TV, Raspberry Pi 3+
        </description>
        <disclaimer lang="en_GB">This addon uses The Movie Database (TMDB) API but is not endorsed by TMDB. Content is streamed from third-party sources. The addon author is not responsible for the content.</disclaimer>
        <platform>all</platform>
        <license>MIT</license>
        <website>https://www.themoviedb.org</website>
        <source>https://github.com/hamza/plugin.video.tmdb.turkish</source>
        <news>
v2.0.0 (2025-12-27)
- 🎬 PHASE 2 COMPLETE: Actual video playback!
- ✅ 3SK Engine integrated (Arabic audio)
- ✅ Smart server index caching (24h)
- ✅ Episode search and mapping
- ✅ Multi-language name translation
- ✅ HLS streaming with anti-403 headers
- ✅ YOUR proven stream extraction logic
- Ready for Turkish123 engine (Phase 2C)

v1.0.0 (2025-12-27)
- Initial release (Phase 1)
- Browse Turkish series from TMDB
- Popular / Airing Now / Discover categories
- Rich metadata integration
        </news>
        <assets>
            <icon>resources/media/icon.png</icon>
            <fanart>resources/media/fanart.png</fanart>
        </assets>
    </extension>
</addon>


END OF FILE: zips/plugin.video.tmdb.turkish/addon.xml
======================================================================

START OF FILE: zips/plugin.video.upt/addon.xml
----------------------------------------------
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="plugin.video.upt" name="Universal Progress Tracker" version="2.1.2" provider-name="TRALALAOH">
    <requires>
        <import addon="xbmc.python" version="3.0.0"/>
    </requires>
    
    <extension point="xbmc.python.pluginsource" library="default.py">
        <provides>video</provides>
    </extension>
    
    <extension point="xbmc.service" library="service.py" start="startup" />
    
    <extension point="xbmc.addon.metadata">
        <platform>all</platform>
        <summary lang="en_GB">Universal Progress Tracker - Track your progress across all addons</summary>
        <description lang="en_GB">Automatically tracks playback progress for all videos in Kodi. Creates shortcuts for easy resume from Continue Watching menu. Works with any addon - no modifications needed!</description>
        <license>GPL-3.0-only</license>
        <forum></forum>
        <website></website>
        <source></source>
        <news>
v1.0.0 (2026-01-03)
- Initial release
- Automatic playback tracking
- Continue Watching menu with resume
- Clean poster-based interface
- Configurable settings with instant apply
        </news>
        <assets>
            <icon>icon.png</icon>
            <fanart>fanart.jpg</fanart>
        </assets>
    </extension>
</addon>


END OF FILE: zips/plugin.video.upt/addon.xml
======================================================================

