# -*- coding: utf-8 -*-
"""
Little Rabite Service Interface (ABC)
Defines the contract that all sync services (Trakt, AniList, Simkl) must implement.
"""

from abc import ABC, abstractmethod
from functools import wraps
import time

try:
    import xbmc
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


def is_authorized(func):
    """
    Decorator that checks if service is authorized before API calls.
    Automatically refreshes token if expired.
    
    Usage:
        @is_authorized
        def my_api_call(self):
            # Will only execute if authenticated
            pass
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.is_authenticated():
            if KODI_ENV:
                xbmc.log(f'[LittleRabite] {self.service_name}: Not authenticated', xbmc.LOGWARNING)
            return None
        
        # Check if token needs refresh
        if self.token_needs_refresh():
            if KODI_ENV:
                xbmc.log(f'[LittleRabite] {self.service_name}: Token expired, refreshing...', xbmc.LOGINFO)
            
            if not self.refresh_token():
                if KODI_ENV:
                    xbmc.log(f'[LittleRabite] {self.service_name}: Token refresh failed', xbmc.LOGERROR)
                return None
        
        return func(self, *args, **kwargs)
    
    return wrapper


def retry_on_failure(max_retries=3, delay=1):
    """
    Decorator that retries a function on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Delay in seconds between retries
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        if KODI_ENV:
                            xbmc.log(f'[LittleRabite] Attempt {attempt + 1} failed: {str(e)}, retrying...', xbmc.LOGWARNING)
                        time.sleep(delay * (attempt + 1))  # Exponential backoff
            
            # All retries failed
            if KODI_ENV:
                xbmc.log(f'[LittleRabite] All {max_retries} attempts failed: {str(last_exception)}', xbmc.LOGERROR)
            raise last_exception
        
        return wrapper
    return decorator


class SyncService(ABC):
    """
    Abstract Base Class for all sync services.
    All services (Trakt, AniList, Simkl) must implement these methods.
    """
    
    def __init__(self, database):
        """
        Initialize the sync service.
        
        Args:
            database: Database instance for storing auth and progress
        """
        self.db = database
        self.service_name = self.__class__.__name__.lower()
        self._user_data = None
    
    # ============================================================================
    # AUTHENTICATION METHODS (Required)
    # ============================================================================
    
    @abstractmethod
    def authenticate(self):
        """
        Initiate OAuth authentication flow.
        Must display device code to user and wait for authorization.
        
        Returns:
            bool: True if authentication successful, False otherwise
        """
        pass
    
    @abstractmethod
    def refresh_token(self):
        """
        Refresh the access token using the refresh token.
        
        Returns:
            bool: True if refresh successful, False otherwise
        """
        pass
    
    def is_authenticated(self):
        """
        Check if service is currently authenticated.
        
        Returns:
            bool: True if valid credentials exist
        """
        auth = self.db.get_auth(self.service_name)
        return auth is not None and auth.get('token') is not None
    
    def token_needs_refresh(self):
        """
        Check if the access token needs to be refreshed.
        
        Returns:
            bool: True if token is expired or expiring soon
        """
        return self.db.is_token_expired(self.service_name)
    
    def logout(self):
        """
        Revoke authentication and delete stored credentials.
        
        Returns:
            bool: True if logout successful
        """
        self.db.delete_auth(self.service_name)
        self._user_data = None
        
        if KODI_ENV:
            xbmc.log(f'[LittleRabite] {self.service_name}: Logged out successfully', xbmc.LOGINFO)
        
        return True
    
    def get_user_data(self):
        """
        Get cached user data from database.
        
        Returns:
            dict: User data or None
        """
        if self._user_data is None:
            auth = self.db.get_auth(self.service_name)
            if auth:
                self._user_data = auth.get('user_data')
        
        return self._user_data
    
    # ============================================================================
    # SYNC METHODS (Required)
    # ============================================================================
    
    @abstractmethod
    @is_authorized
    def sync_pull(self, media_type=None, limit=None):
        """
        Pull watch history from service and update local database.
        
        Args:
            media_type: Optional filter ('movie' or 'episode')
            limit: Optional limit on number of items to sync
            
        Returns:
            dict: {'success': bool, 'synced': int, 'errors': list}
        """
        pass
    
    @abstractmethod
    @is_authorized
    def sync_push(self):
        """
        Push local watch history to service (process sync queue).
        
        Returns:
            dict: {'success': bool, 'pushed': int, 'errors': list}
        """
        pass
    
    # ============================================================================
    # SCROBBLING METHODS (Required)
    # ============================================================================
    
    @abstractmethod
    @is_authorized
    def scrobble_start(self, media_info, progress=0):
        """
        Send 'start watching' scrobble to service.
        
        Args:
            media_info: Dict with media information:
                {
                    'type': 'movie' or 'episode',
                    'ids': {'trakt': 123, 'tmdb': 456, ...},
                    'title': 'Movie Title',
                    'year': 2024,
                    'season': 1,  # for episodes
                    'episode': 1,  # for episodes
                    'duration': 7200  # in seconds
                }
            progress: Playback progress percentage (0-100)
            
        Returns:
            dict: Response from service or None on failure
        """
        pass
    
    @abstractmethod
    @is_authorized
    def scrobble_pause(self, media_info, progress):
        """
        Send 'pause' scrobble to service.
        
        Args:
            media_info: Dict with media information (same as scrobble_start)
            progress: Current playback progress percentage (0-100)
            
        Returns:
            dict: Response from service or None on failure
        """
        pass
    
    @abstractmethod
    @is_authorized
    def scrobble_stop(self, media_info, progress):
        """
        Send 'stop watching' scrobble to service.
        
        Args:
            media_info: Dict with media information (same as scrobble_start)
            progress: Final playback progress percentage (0-100)
            
        Returns:
            dict: Response from service or None on failure
        """
        pass
    
    # ============================================================================
    # SEARCH & METADATA METHODS (Optional)
    # ============================================================================
    
    def search(self, query, media_type=None):
        """
        Search for media on the service.
        
        Args:
            query: Search query string
            media_type: Optional filter ('movie' or 'episode')
            
        Returns:
            list: Search results or empty list
        """
        return []
    
    def get_media_info(self, ids):
        """
        Get detailed media information from service.
        
        Args:
            ids: Dict of IDs ({'trakt': 123, 'tmdb': 456})
            
        Returns:
            dict: Media information or None
        """
        return None
    
    # ============================================================================
    # COLLECTION & WATCHLIST METHODS (Optional)
    # ============================================================================
    
    @is_authorized
    def add_to_collection(self, media_info):
        """
        Add media to user's collection on service.
        
        Args:
            media_info: Dict with media information
            
        Returns:
            bool: True if successful
        """
        return False
    
    @is_authorized
    def remove_from_collection(self, media_info):
        """
        Remove media from user's collection on service.
        
        Args:
            media_info: Dict with media information
            
        Returns:
            bool: True if successful
        """
        return False
    
    @is_authorized
    def add_to_watchlist(self, media_info):
        """
        Add media to user's watchlist on service.
        
        Args:
            media_info: Dict with media information
            
        Returns:
            bool: True if successful
        """
        return False
    
    @is_authorized
    def remove_from_watchlist(self, media_info):
        """
        Remove media from user's watchlist on service.
        
        Args:
            media_info: Dict with media information
            
        Returns:
            bool: True if successful
        """
        return False
    
    # ============================================================================
    # RATING METHODS (Optional)
    # ============================================================================
    
    @is_authorized
    def rate_media(self, media_info, rating):
        """
        Rate media on the service.
        
        Args:
            media_info: Dict with media information
            rating: Rating value (scale depends on service)
            
        Returns:
            bool: True if successful
        """
        return False
    
    @is_authorized
    def remove_rating(self, media_info):
        """
        Remove rating from media on the service.
        
        Args:
            media_info: Dict with media information
            
        Returns:
            bool: True if successful
        """
        return False
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def _queue_for_sync(self, action, data):
        """
        Add an action to the sync queue for later processing.
        Useful when service is temporarily unavailable.
        
        Args:
            action: Action name (e.g., 'scrobble_stop')
            data: Data for the action
        """
        self.db.queue_sync(self.service_name, action, data)
        
        if KODI_ENV:
            xbmc.log(f'[LittleRabite] {self.service_name}: Queued {action} for later sync', xbmc.LOGINFO)
    
    def _log(self, message, level=None):
        """
        Log a message (Kodi-aware).
        
        Args:
            message: Message to log
            level: Log level (uses xbmc log levels if in Kodi)
        """
        if KODI_ENV:
            if level is None:
                level = xbmc.LOGINFO
            xbmc.log(f'[LittleRabite] {self.service_name}: {message}', level)
        else:
            print(f'[{self.service_name}] {message}')
    
    def __repr__(self):
        """String representation of the service."""
        auth_status = "authenticated" if self.is_authenticated() else "not authenticated"
        return f"<{self.__class__.__name__} ({auth_status})>"


