# -*- coding: utf-8 -*-
"""
Provider Registry - Auto-Discovery System
Automatically discovers and registers providers
"""

import os
import importlib
import inspect

try:
    import xbmc
    KODI_ENV = True
except ImportError:
    KODI_ENV = False
    class xbmc:
        LOGDEBUG = 0
        LOGINFO = 1
        LOGWARNING = 2
        LOGERROR = 3
        @staticmethod
        def log(msg, level=1):
            print(f"[Registry] {msg}")

from .base_provider import BaseProvider


class ProviderRegistry:
    """
    Auto-discovers and registers streaming providers
    
    Usage:
        registry = ProviderRegistry()
        providers = registry.get_all_providers()
    """
    
    def __init__(self):
        """Initialize registry"""
        self._providers = {}
        self._discover_providers()
    
    def _discover_providers(self):
        """
        Auto-discover provider_*.py files and register classes
        """
        
        # Get directory of this file
        providers_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Log discovery
        if KODI_ENV:
            xbmc.log(f"ProviderRegistry: Discovering providers in {providers_dir}", xbmc.LOGINFO)
        
        # Find all provider_*.py files
        for filename in os.listdir(providers_dir):
            if not filename.startswith('provider_') or not filename.endswith('.py'):
                continue
            
            module_name = filename[:-3]  # Remove .py
            
            try:
                # Import module
                module = importlib.import_module(f'.{module_name}', package='lib.providers')
                
                # Find classes inheriting from BaseProvider
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseProvider) and obj is not BaseProvider:
                        # Register provider
                        provider_key = obj.__name__.replace('Provider', '').lower()
                        self._providers[provider_key] = obj
                        
                        if KODI_ENV:
                            xbmc.log(f"ProviderRegistry: Registered {name} as '{provider_key}'", xbmc.LOGINFO)
                
            except Exception as e:
                if KODI_ENV:
                    xbmc.log(f"ProviderRegistry: Failed to load {module_name}: {e}", xbmc.LOGERROR)
                else:
                    print(f"🦊 [Registry] Failed to load {module_name}: {e}")
    
    def get_all_providers(self):
        """
        Get all discovered provider classes
        
        Returns:
            dict: {provider_key: ProviderClass}
        """
        return self._providers.copy()
    
    def get_provider(self, provider_key):
        """
        Get specific provider class by key
        
        Args:
            provider_key (str): Provider key (e.g., '3sk', 'qrmzi')
        
        Returns:
            class: Provider class or None
        """
        return self._providers.get(provider_key.lower())


def get_enabled_providers(addon):
    """
    Get list of enabled provider instances based on settings
    
    Args:
        addon: Kodi addon instance
    
    Returns:
        list: Enabled provider instances
    """
    
    registry = ProviderRegistry()
    all_providers = registry.get_all_providers()
    
    enabled = []
    
    # Check settings for each provider
    provider_settings = {
        '3sk': 'use_3sk',
        '3skmedia': 'use_3skmedia',
        'qrmzi': 'use_qrmzi',
        'turkish123': 'use_turkish123',
        'egydead': 'use_egydead',
        'youtube': 'use_youtube'
    }
    
    tmdb_api_key = addon.getSetting('tmdb_api_key')

    for provider_key, setting_id in provider_settings.items():
        # Check if enabled in settings
        is_enabled = addon.getSetting(setting_id) != 'false'

        if is_enabled and provider_key in all_providers:
            # Instantiate provider and inject TMDB API key from settings
            provider_class = all_providers[provider_key]
            provider_instance = provider_class()
            provider_instance.tmdb_api_key = tmdb_api_key
            enabled.append(provider_instance)
            
            if KODI_ENV:
                xbmc.log(f"Enabled provider: {provider_instance.get_name()}", xbmc.LOGINFO)
    
    if not enabled:
        if KODI_ENV:
            xbmc.log("WARNING: No providers enabled!", xbmc.LOGWARNING)
    
    return enabled


__all__ = ['ProviderRegistry', 'get_enabled_providers', 'BaseProvider']
