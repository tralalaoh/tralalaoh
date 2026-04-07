"""Custom Stremio addon registry - stores user-added scrapers."""

import json
import os
import uuid
from datetime import datetime

import requests
import xbmcaddon
import xbmcvfs

from resources.lib.logger import log, log_debug, log_error

REGISTRY_FILENAME = 'custom_addons.json'


def _get_registry_path():
    """Get path to registry JSON file in Kodi addon data directory."""
    addon = xbmcaddon.Addon()
    data_path = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
    if not xbmcvfs.exists(data_path):
        xbmcvfs.mkdirs(data_path)
    return os.path.join(data_path, REGISTRY_FILENAME)


class AddonRegistry:
    """Manages user-added custom Stremio scrapers."""

    @staticmethod
    def load():
        """Load registry from disk. Returns list of addon dicts."""
        path = _get_registry_path()
        try:
            if xbmcvfs.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('addons', [])
        except Exception as e:
            log_error('AddonRegistry: Failed to load registry', e)
        return []

    @staticmethod
    def save(addons):
        """Save registry to disk."""
        path = _get_registry_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({'version': 1, 'addons': addons}, f, indent=2, ensure_ascii=False)
            log_debug(f'AddonRegistry: Saved {len(addons)} addons to {path}')
        except Exception as e:
            log_error('AddonRegistry: Failed to save registry', e)

    @staticmethod
    def get_all():
        """Get all registered addons."""
        return AddonRegistry.load()

    @staticmethod
    def get_enabled():
        """Get only enabled addons."""
        return [a for a in AddonRegistry.load() if a.get('enabled', True)]

    @staticmethod
    def fetch_manifest(url):
        """
        Fetch and parse a Stremio addon manifest.

        Accepts either a manifest URL (.../manifest.json) or a base URL.

        Returns dict with: name, version, base_url, manifest_url, types, id_prefixes
        Returns None on failure.
        """
        url = url.strip().rstrip('/')

        if url.endswith('/manifest.json'):
            manifest_url = url
            base_url = url[:-len('/manifest.json')]
        else:
            manifest_url = f"{url}/manifest.json"
            base_url = url

        log(f'AddonRegistry: Fetching manifest from {manifest_url}')

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Origin': 'https://web.stremio.com',
                'Referer': 'https://web.stremio.com/',
            }
            resp = requests.get(manifest_url, headers=headers, timeout=15)
            resp.raise_for_status()
            manifest = resp.json()
        except requests.exceptions.Timeout:
            log_error(f'AddonRegistry: Timeout fetching {manifest_url}')
            return None
        except requests.exceptions.RequestException as e:
            log_error('AddonRegistry: HTTP error fetching manifest', e)
            return None
        except ValueError as e:
            log_error('AddonRegistry: Invalid JSON in manifest response', e)
            return None

        name = manifest.get('name') or manifest.get('id') or 'Custom Addon'
        version = manifest.get('version', '')
        types = manifest.get('types', ['movie', 'series'])

        # Extract id_prefixes — check per-resource first, then top-level
        id_prefixes = []
        for res in manifest.get('resources', []):
            if isinstance(res, dict) and res.get('name') == 'stream':
                id_prefixes = res.get('idPrefixes', [])
                break
        if not id_prefixes:
            id_prefixes = manifest.get('idPrefixes', [])
        if not id_prefixes:
            id_prefixes = ['tt']  # Default to IMDB

        log(f"AddonRegistry: Manifest OK — name='{name}' types={types} id_prefixes={id_prefixes}")

        return {
            'name': name,
            'version': version,
            'base_url': base_url,
            'manifest_url': manifest_url,
            'types': types,
            'id_prefixes': id_prefixes,
        }

    @staticmethod
    def add(manifest_info):
        """
        Add a new addon to the registry from a manifest_info dict.

        Returns (entry, None) on success.
        Returns (None, 'already_exists') if URL already registered.
        Returns (None, 'save_error') on failure.
        """
        addons = AddonRegistry.load()

        # Duplicate check by base_url
        new_base = manifest_info['base_url'].rstrip('/')
        for existing in addons:
            if existing.get('base_url', '').rstrip('/') == new_base:
                log(f"AddonRegistry: Duplicate addon URL: {new_base}")
                return None, 'already_exists'

        entry = {
            'id': str(uuid.uuid4())[:8],
            'name': manifest_info['name'],
            'version': manifest_info.get('version', ''),
            'base_url': manifest_info['base_url'],
            'manifest_url': manifest_info['manifest_url'],
            'enabled': True,
            'types': manifest_info.get('types', ['movie', 'series']),
            'id_prefixes': manifest_info.get('id_prefixes', ['tt']),
            'added_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

        addons.append(entry)
        AddonRegistry.save(addons)
        log(f"AddonRegistry: Added '{entry['name']}' (id={entry['id']})")
        return entry, None

    @staticmethod
    def remove(addon_id):
        """Remove addon by id. Returns True if removed."""
        addons = AddonRegistry.load()
        filtered = [a for a in addons if a.get('id') != addon_id]
        if len(filtered) < len(addons):
            AddonRegistry.save(filtered)
            log(f"AddonRegistry: Removed addon {addon_id}")
            return True
        return False

    @staticmethod
    def toggle(addon_id):
        """Toggle enabled state. Returns new enabled state or None if not found."""
        addons = AddonRegistry.load()
        for addon in addons:
            if addon.get('id') == addon_id:
                addon['enabled'] = not addon.get('enabled', True)
                AddonRegistry.save(addons)
                return addon['enabled']
        return None

    @staticmethod
    def update_name(addon_id, new_name):
        """Rename an addon. Returns True on success."""
        addons = AddonRegistry.load()
        for addon in addons:
            if addon.get('id') == addon_id:
                addon['name'] = new_name.strip()
                AddonRegistry.save(addons)
                return True
        return False
