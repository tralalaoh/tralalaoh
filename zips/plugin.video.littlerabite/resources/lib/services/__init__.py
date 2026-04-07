# -*- coding: utf-8 -*-
"""
Little Rabite Services Package
Exports all available sync services.
"""

from resources.lib.services.base import SyncService
from resources.lib.services.trakt import TraktService
from resources.lib.services.anilist import AniListService
from resources.lib.services.simkl import SimklService

__all__ = [
    'SyncService',
    'TraktService',
    'AniListService',
    'SimklService'
]
