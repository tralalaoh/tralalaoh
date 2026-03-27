"""
Syncs external Kodi addons into this repo's zips/ folder.
Reads external_addons.json for the list of addons and their source repos.
Runs _generator.py automatically if any addon was updated.
"""

import io
import json
import os
import glob as glob_mod
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

# Always run relative to the repo root regardless of where this script is called from
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_REPO_ROOT)

CONFIG_FILE = ".tools/external_addons.json"
ZIPS_DIR = "zips"

# Assets to extract from the zip alongside addon.xml
ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}


def fetch(url):
    print(f"    Fetching {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "KodiRepoSync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def parse_version(v):
    """'5.1.194' → (5, 1, 194)  for simple tuple comparison."""
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def remote_version(xml_bytes, addon_id):
    root = ET.fromstring(xml_bytes)
    for addon in root.findall("addon"):
        if addon.get("id") == addon_id:
            return addon.get("version")
    return None


def local_version(addon_id):
    path = os.path.join(ZIPS_DIR, addon_id, "addon.xml")
    if not os.path.exists(path):
        return None
    try:
        return ET.parse(path).getroot().get("version")
    except ET.ParseError:
        return None


def download_addon(addon_id, version, datadir):
    zip_name = f"{addon_id}-{version}.zip"
    zip_url = f"{datadir.rstrip('/')}/{addon_id}/{zip_name}"
    addon_dir = os.path.join(ZIPS_DIR, addon_id)
    os.makedirs(addon_dir, exist_ok=True)

    zip_data = fetch(zip_url)

    # Remove old zips
    for old in glob_mod.glob(os.path.join(addon_dir, "*.zip")):
        os.remove(old)

    # Save new zip
    with open(os.path.join(addon_dir, zip_name), "wb") as f:
        f.write(zip_data)

    # Extract addon.xml + icon/fanart assets from zip
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        for entry in zf.namelist():
            # Strip the leading addon_id/ prefix used inside the zip
            parts = entry.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            rel = parts[1]  # e.g. "addon.xml", "icon.png"
            ext = os.path.splitext(rel)[1].lower()
            if rel == "addon.xml" or (ext in ASSET_EXTENSIONS and "/" not in rel):
                dest = os.path.join(addon_dir, rel)
                with zf.open(entry) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                print(f"    Extracted {rel}")


def sync():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)

    # Group entries by source addons.xml to avoid duplicate fetches
    sources: dict[str, dict] = {}
    for entry in config:
        src = entry["source_addons_xml"]
        if src not in sources:
            sources[src] = {"datadir": entry["source_datadir"], "addons": []}
        sources[src]["addons"].append(entry["id"])

    updated = False

    for src_url, info in sources.items():
        print(f"\nSource: {src_url}")
        try:
            xml_bytes = fetch(src_url)
        except Exception as e:
            print(f"  ERROR fetching source: {e}")
            continue

        for addon_id in info["addons"]:
            rv = remote_version(xml_bytes, addon_id)
            if rv is None:
                print(f"  {addon_id}: not found in remote addons.xml — skipping")
                continue

            lv = local_version(addon_id)
            if lv and parse_version(rv) <= parse_version(lv):
                print(f"  {addon_id}: up to date ({lv})")
                continue

            action = f"installing {rv}" if lv is None else f"updating {lv} → {rv}"
            print(f"  {addon_id}: {action}")
            try:
                download_addon(addon_id, rv, info["datadir"])
                updated = True
                print(f"  {addon_id}: done")
            except Exception as e:
                print(f"  {addon_id}: ERROR — {e}")

    if updated:
        print("\nRunning _generator.py to rebuild addons.xml...")
        import subprocess
        subprocess.run(["python3", ".tools/_generator.py"], check=True)
    else:
        print("\nAll external addons are up to date.")

    return updated


if __name__ == "__main__":
    sync()
