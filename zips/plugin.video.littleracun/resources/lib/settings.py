#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Centralized settings management.
"""

import uuid as uuid_module
import xbmcaddon
import xbmcgui
from .utils import log

ADDON = xbmcaddon.Addon()


class Settings:
    """Centralized settings manager"""
    
    @staticmethod
    def get(key, default=None):
        """Get a setting value"""
        try:
            value = ADDON.getSetting(key)
            return value if value else default
        except:
            return default
    
    @staticmethod
    def set(key, value):
        """Set a setting value"""
        try:
            ADDON.setSetting(key, str(value))
            return True
        except Exception as e:
            log(f"Failed to set setting {key}: {str(e)}")
            return False
    
    @staticmethod
    def get_bool(key, default=False):
        """Get a boolean setting"""
        value = Settings.get(key)
        if value is None:
            return default
        return value.lower() == 'true'
    
    @staticmethod
    def get_int(key, default=0):
        """Get an integer setting"""
        try:
            value = Settings.get(key)
            return int(value) if value else default
        except:
            return default
    
    @staticmethod
    def open_settings():
        """Open addon settings dialog"""
        try:
            ADDON.openSettings()
        except Exception as e:
            log(f"Error opening settings: {str(e)}")
    
    # Convenience properties for commonly used settings
    
    @property
    def user_uuid(self):
        """Get or create user UUID"""
        uuid = self.get('user_uuid')
        if not uuid:
            uuid = self.generate_uuid()
        return uuid
    
    @property
    def server_url(self):
        """Get server URL"""
        url = self.get('server_url')
        if not url:
            url = "https://aiometadata.elfhosted.com"
        return url.rstrip('/')
    
    @property
    def use_local_config(self):
        """Check if using local config"""
        return self.get_bool('use_local_config', default=False)
    
    @property
    def api_timeout(self):
        """Get API timeout"""
        return self.get_int('api_timeout', default=30)
    
    @property
    def show_fanart(self):
        """Check if fanart should be shown"""
        return self.get_bool('show_fanart', default=True)
    
    @property
    def show_year(self):
        """Check if year should be shown in titles"""
        return self.get_bool('show_year', default=True)
    
    @property
    def show_rating(self):
        """Check if ratings should be shown"""
        return self.get_bool('show_rating', default=True)
    
    @property
    def default_player(self):
        """Get default player setting"""
        return self.get('default_player', default='Always Ask')
    
    @property
    def remember_player_choice(self):
        """Check if player choice should be remembered"""
        return self.get_bool('remember_player_choice', default=False)
    
    @staticmethod
    def generate_uuid():
        """Generate a new UUID"""
        new_uuid = str(uuid_module.uuid4())
        Settings.set('user_uuid', new_uuid)
        log(f"Generated new UUID: {new_uuid}")
        
        manifest_url = f"https://aiometadata.elfhosted.com/stremio/{new_uuid}/manifest.json"
        xbmcgui.Dialog().ok(
            "Little Racun",
            f"New UUID generated![CR][CR]"
            f"UUID: {new_uuid[:8]}...{new_uuid[-8:]}[CR][CR]"
            f"Configure at:[CR]{manifest_url}"
        )
        
        return new_uuid
    
    @staticmethod
    def check_configured():
        """Check if addon is properly configured"""
        settings = Settings()
        uuid = settings.user_uuid
        
        if not uuid:
            dialog = xbmcgui.Dialog().yesno(
                "Little Racun",
                "Welcome to AIO Metadata![CR][CR]"
                "To use AIO Metadata catalogs, you need a UUID.[CR][CR]"
                "Would you like to generate one now?"
            )
            
            if dialog:
                uuid = Settings.generate_uuid()
            else:
                Settings.open_settings()
                uuid = Settings().user_uuid
        
        return bool(uuid)


# Create singleton instance
settings = Settings()
