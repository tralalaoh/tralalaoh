#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API module - Handles all HTTP/Network requests to AIO Metadata server.
"""

import json
import xbmcgui
import xbmcvfs

try:
    import requests
except ImportError:
    requests = None

from .utils import log, log_error
from .settings import settings


class AIOMetadataAPI:
    """API client for AIO Metadata server"""
    
    def __init__(self):
        self.server_url = settings.server_url
        self.user_uuid = settings.user_uuid
        self.timeout = settings.api_timeout
    
    def build_manifest_url(self):
        """Build Stremio manifest URL"""
        return f"{self.server_url}/stremio/{self.user_uuid}/manifest.json"
    
    def build_catalog_url(self, catalog_id, catalog_type, extra=None):
        """Build catalog URL with optional extra parameters"""
        if extra:
            return f"{self.server_url}/stremio/{self.user_uuid}/catalog/{catalog_type}/{catalog_id}/{extra}.json"
        else:
            return f"{self.server_url}/stremio/{self.user_uuid}/catalog/{catalog_type}/{catalog_id}.json"
    
    def build_meta_url(self, content_type, content_id):
        """Build meta URL for detailed content info"""
        return f"{self.server_url}/stremio/{self.user_uuid}/meta/{content_type}/{content_id}.json"
    
    def get_manifest(self):
        """Fetch Stremio manifest from AIO Metadata"""
        if not requests:
            log("requests module not available", level=xbmcgui.LOGERROR)
            return None
        
        try:
            manifest_url = self.build_manifest_url()
            log(f"Fetching manifest from: {manifest_url}")
            
            response = requests.get(manifest_url, timeout=self.timeout)
            response.raise_for_status()
            manifest = response.json()
            
            log("Manifest fetched successfully")
            log(f"Catalogs: {len(manifest.get('catalogs', []))}")
            
            return manifest
        
        except Exception as e:
            log_error("Error fetching manifest", e)
            xbmcgui.Dialog().notification(
                "Little Racun",
                f"Failed to fetch manifest from server",
                xbmcgui.NOTIFICATION_ERROR,
                5000
            )
            return None
    
    def get_catalog(self, catalog_id, catalog_type, extra=None):
        """Fetch catalog data"""
        if not requests:
            return None
        
        try:
            catalog_url = self.build_catalog_url(catalog_id, catalog_type, extra)
            log(f"Fetching catalog from: {catalog_url}")
            
            response = requests.get(catalog_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            log("Catalog data fetched successfully")
            return data
        
        except Exception as e:
            log_error("Error fetching catalog", e)
            return None
    
    def get_meta(self, content_type, content_id):
        """Fetch meta information for content"""
        if not requests:
            return None
        
        try:
            meta_url = self.build_meta_url(content_type, content_id)
            log(f"Fetching meta from: {meta_url}")
            
            response = requests.get(meta_url, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            
            log("Meta data fetched successfully")
            return data
        
        except Exception as e:
            log_error("Error fetching meta", e)
            return None
    
    def get_config(self):
        """Load configuration from manifest or local file"""
        try:
            if settings.use_local_config:
                return self._load_local_config()
            else:
                return self._load_server_config()
        
        except Exception as e:
            log_error("Error loading config", e)
            return {'config': {'catalogs': []}}
    
    def _load_local_config(self):
        """Load configuration from local config.json file"""
        try:
            import xbmcaddon
            addon_id = xbmcaddon.Addon().getAddonInfo('id')
            config_file = xbmcvfs.translatePath(f'special://home/addons/{addon_id}/config.json')
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            log("Config loaded from local file")
            return config_data
        
        except FileNotFoundError:
            log("Local config not found, using server manifest", level=xbmcgui.LOGWARNING)
            return self._load_server_config()
        except Exception as e:
            log_error("Error loading local config", e)
            return {'config': {'catalogs': []}}
    
    def _load_server_config(self):
        """Load configuration from server manifest"""
        manifest = self.get_manifest()
        
        if not manifest:
            return {'config': {'catalogs': []}}
        
        # Convert Stremio manifest catalogs to internal format
        catalogs = []
        
        for stremio_catalog in manifest.get('catalogs', []):
            catalog = {
                'id': stremio_catalog.get('id', ''),
                'name': stremio_catalog.get('name', 'Unknown'),
                'type': stremio_catalog.get('type', 'movie'),
                'source': 'aiometadata',
                'enabled': True,
                'showInHome': True,
                'extra': stremio_catalog.get('extra', [])
            }
            
            catalogs.append(catalog)
        
        log(f"Converted {len(catalogs)} catalogs from manifest")
        
        return {'config': {'catalogs': catalogs}}


# Create singleton instance
api = AIOMetadataAPI()
