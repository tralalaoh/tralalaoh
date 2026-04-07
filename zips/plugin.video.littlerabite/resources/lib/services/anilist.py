# -*- coding: utf-8 -*-
"""
Little Rabite - AniList Service Implementation (WITH QR CODE AUTH)
Handles authentication (QR Code + Token Input), syncing, and scrobbling with AniList.co

ARCHITECTURE:
- Inherits from SyncService (resources/lib/services/base.py)
- Uses GraphQL API at https://graphql.anilist.co
- Episode-based progress tracking (not time-based)
- CRITICAL: Requests idMal (MAL ID) to bridge with Trakt in database
- NEW: QR Code authentication for easy TV-based login
"""

import requests
import time
import json
import os
from resources.lib.services.base import SyncService, is_authorized

try:
    import xbmc
    import xbmcgui
    import xbmcvfs
    KODI_ENV = True
except ImportError:
    KODI_ENV = False

# Try to import qrcode - fallback gracefully if not available
try:
    import qrcode
    from io import BytesIO
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False


class AniListService(SyncService):
    """
    AniList.co service implementation with QR Code authentication.
    
    Authentication: OAuth Implicit Grant with QR Code display
    Sync: Episode-based progress (not time-based)
    Bridge: Uses MAL ID (idMal) to link with Trakt items in database
    """
    
    BASE_URL = "https://graphql.anilist.co"
    AUTH_URL = "https://anilist.co/api/v2/oauth/authorize"
    CLIENT_ID = "35064"  # Little Rabite Client ID
    
    def __init__(self, database):
        """
        Initialize AniList service.
        
        Args:
            database: Database instance
        """
        super().__init__(database)
        self.service_name = 'anilist'
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _get_headers(self):
        """
        Get request headers with authorization.
        
        Returns:
            dict: Request headers
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        auth_data = self.db.get_auth(self.service_name)
        if auth_data and auth_data.get('token'):
            headers['Authorization'] = f"Bearer {auth_data['token']}"
        
        return headers
    
    def _make_graphql_request(self, query, variables=None):
        """
        Make GraphQL API request.
        
        Args:
            query: GraphQL query string
            variables: Optional query variables
            
        Returns:
            dict: Response data or None on failure
        """
        headers = self._get_headers()
        
        payload = {
            'query': query,
            'variables': variables or {}
        }
        
        try:
            response = requests.post(
                self.BASE_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self._log(f'Rate limited, waiting {retry_after} seconds', 
                         xbmc.LOGWARNING if KODI_ENV else None)
                time.sleep(retry_after)
                return None
            
            response.raise_for_status()
            result = response.json()
            
            # Check for GraphQL errors
            if 'errors' in result:
                error_msg = result['errors'][0].get('message', 'Unknown error')
                self._log(f'GraphQL error: {error_msg}', 
                         xbmc.LOGERROR if KODI_ENV else None)
                return None
            
            return result.get('data')
            
        except requests.exceptions.RequestException as e:
            self._log(f'Request failed: {str(e)}', 
                     xbmc.LOGERROR if KODI_ENV else None)
            return None
    
    # ============================================================================
    # AUTHENTICATION WITH QR CODE
    # ============================================================================
    
    def authenticate(self):
        """
        Initiate OAuth authentication flow with QR Code display.
        
        Flow:
        1. Generate Auth URL with client_id and response_type=token
        2. Create QR Code image from URL
        3. Display QR Code in Kodi window
        4. User scans QR with phone, authorizes, and copies token
        5. User enters token into Kodi input dialog
        6. Verify token and store credentials
        
        Returns:
            bool: True if authentication successful
        """
        if not KODI_ENV:
            self._log('Authentication requires Kodi environment', None)
            return False
        
        dialog = xbmcgui.Dialog()
        
        # Build auth URL
        auth_url = f"{self.AUTH_URL}?client_id={self.CLIENT_ID}&response_type=token"
        
        # Try QR code method first
        if QR_AVAILABLE:
            try:
                return self._authenticate_with_qr(auth_url, dialog)
            except Exception as e:
                self._log(f'QR code auth failed: {str(e)}, falling back to text', xbmc.LOGWARNING)
                # Fall through to text-based method
        
        # Fallback: Text-based authentication
        return self._authenticate_with_text(auth_url, dialog)
    
    def _authenticate_with_qr(self, auth_url, dialog):
        """
        Authenticate using QR code display.
        
        Args:
            auth_url: Authorization URL to encode
            dialog: xbmcgui.Dialog instance
            
        Returns:
            bool: True if successful
        """
        self._log('Starting QR code authentication...')
        
        # Generate QR code
        qr_image_path = self._generate_qr_code(auth_url)
        
        if not qr_image_path:
            self._log('Failed to generate QR code', xbmc.LOGWARNING)
            return False
        
        # STEP 1: Show initial instructions (before showing QR)
        pre_instructions = (
            "[B]AniList Authentication with QR Code[/B]\n\n"
            "In the next screen, you will see a QR code.\n\n"
            "[B]What to do:[/B]\n"
            "1. Get your phone ready with camera app open\n"
            "2. Click OK to display the QR code\n"
            "3. Scan the QR code with your phone\n"
            "4. Authorize on your phone's browser\n"
            "5. Press BACK on your remote when done scanning\n\n"
            "[COLOR yellow]Make sure your phone camera is ready before clicking OK[/COLOR]"
        )
        
        if not dialog.yesno('AniList Authentication', pre_instructions, nolabel='Cancel', yeslabel='Show QR Code'):
            # User cancelled
            try:
                if xbmcvfs.exists(qr_image_path):
                    xbmcvfs.delete(qr_image_path)
            except:
                pass
            return False
        
        # STEP 2: Show QR code FULLSCREEN (no dialog on top)
        try:
            # Show QR code in fullscreen
            xbmc.executebuiltin(f'ShowPicture({qr_image_path})')
            
            # Show notification with brief instruction
            dialog.notification(
                'Scan QR Code Now',
                'Press BACK when finished scanning',
                xbmcgui.NOTIFICATION_INFO,
                8000
            )
            
            # Wait for user to scan (they press BACK when done)
            # We'll wait up to 60 seconds, checking every second if user pressed back
            max_wait = 60
            for i in range(max_wait):
                xbmc.sleep(1000)
                
                # Check if slideshow is still active
                # If user pressed BACK, the slideshow will close
                if not xbmc.getCondVisibility('Window.IsActive(slideshow)'):
                    self._log('User closed QR code viewer')
                    break
            
        except Exception as e:
            self._log(f'Error displaying QR code: {str(e)}', xbmc.LOGWARNING)
        
        # Make sure QR viewer is closed
        try:
            xbmc.executebuiltin('Action(Back)')
        except:
            pass
        
        # STEP 3: Ask if user successfully scanned
        scan_success = dialog.yesno(
            'QR Code Scanned?',
            'Did you successfully scan the QR code and authorize on your phone?',
            nolabel='No, Cancel',
            yeslabel='Yes, I Have Token'
        )
        
        if not scan_success:
            # User didn't scan successfully - offer fallback
            if dialog.yesno(
                'Try Manual URL?',
                f'Would you like to see the manual URL instead?\n\n{auth_url}',
                nolabel='No, Cancel',
                yeslabel='Yes, Show URL'
            ):
                # Fall back to text method
                try:
                    if xbmcvfs.exists(qr_image_path):
                        xbmcvfs.delete(qr_image_path)
                except:
                    pass
                return self._authenticate_with_text(auth_url, dialog)
            else:
                # User cancelled completely
                try:
                    if xbmcvfs.exists(qr_image_path):
                        xbmcvfs.delete(qr_image_path)
                except:
                    pass
                return False
        
        # STEP 4: Get token from user
        token = dialog.input(
            'Enter Token from Phone Browser',
            type=xbmcgui.INPUT_ALPHANUM
        )
        
        # Clean up QR image
        try:
            if xbmcvfs.exists(qr_image_path):
                xbmcvfs.delete(qr_image_path)
        except:
            pass
        
        if not token or len(token.strip()) == 0:
            dialog.ok('Authentication Cancelled', 'No token provided.')
            return False
        
        # Verify and save token
        return self._verify_and_save_token(token.strip(), dialog)
    
    def _authenticate_with_text(self, auth_url, dialog):
        """
        Fallback text-based authentication (original method).
        
        Args:
            auth_url: Authorization URL
            dialog: xbmcgui.Dialog instance
            
        Returns:
            bool: True if successful
        """
        self._log('Using text-based authentication (QR unavailable)')
        
        # Show URL to user
        dialog.ok(
            'AniList Authentication',
            f'Please visit the following URL to authorize Little Rabite:\n\n{auth_url}\n\nClick OK when you have copied the token.'
        )
        
        # Get token from user
        token = dialog.input('Enter AniList Token', type=xbmcgui.INPUT_ALPHANUM)
        
        if not token:
            dialog.ok('Authentication Cancelled', 'No token provided.')
            return False
        
        # Verify and save token
        return self._verify_and_save_token(token, dialog)
    
    def _generate_qr_code(self, url):
        """
        Generate QR code image from URL.
        
        Args:
            url: URL to encode in QR code
            
        Returns:
            str: Path to saved QR code image, or None on failure
        """
        try:
            # Generate QR code with larger box size for TV viewing
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=15,  # Increased from 10 to 15 for larger QR code
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create image with explicit size for better TV display
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Save to temp directory
            temp_path = xbmcvfs.translatePath('special://temp/anilist_qr.png')
            
            # Ensure directory exists
            temp_dir = os.path.dirname(temp_path)
            if not xbmcvfs.exists(temp_dir):
                xbmcvfs.mkdirs(temp_dir)
            
            # Save image
            img.save(temp_path)
            
            self._log(f'QR code saved to: {temp_path}')
            return temp_path
            
        except Exception as e:
            self._log(f'Failed to generate QR code: {str(e)}', xbmc.LOGERROR)
            return None
    
    def _verify_and_save_token(self, token, dialog):
        """
        Verify token with AniList API and save to database.
        
        Args:
            token: Access token from user
            dialog: xbmcgui.Dialog instance
            
        Returns:
            bool: True if successful
        """
        # Verify token by getting user info
        query = '''
        query {
            Viewer {
                id
                name
            }
        }
        '''
        
        # Temporarily store token for verification
        old_auth = self.db.get_auth(self.service_name)
        self.db.store_auth(self.service_name, token=token)
        
        # Make verification request
        data = self._make_graphql_request(query)
        
        if data and data.get('Viewer'):
            viewer = data['Viewer']
            user_id = viewer['id']
            username = viewer['name']
            
            # Store complete auth data with user info
            user_data = {
                'user_id': user_id,
                'username': username
            }
            self.db.store_auth(
                self.service_name, 
                token=token, 
                user_data=user_data
            )
            
            self._log(f'Successfully authenticated as {username} (ID: {user_id})')
            
            dialog.ok(
                'Authentication Successful',
                f'Logged in as: {username}'
            )
            return True
        else:
            # Verification failed - restore old auth if it existed
            if old_auth:
                self.db.store_auth(
                    self.service_name,
                    token=old_auth.get('token'),
                    refresh_token=old_auth.get('refresh_token'),
                    expires_at=old_auth.get('expires_at'),
                    user_data=old_auth.get('user_data')
                )
            else:
                self.db.delete_auth(self.service_name)
            
            dialog.ok(
                'Authentication Failed',
                'Invalid token or API error. Please try again.'
            )
            return False
    
    def refresh_token(self):
        """
        AniList tokens don't expire - no refresh needed.
        
        Returns:
            bool: Always True (no refresh required)
        """
        return True
    
    # ============================================================================
    # SYNC METHODS
    # ============================================================================
    
    @is_authorized
    def sync_pull(self, media_type=None, limit=None):
        """
        Pull watch history from AniList and update local database.
        
        CRITICAL: Requests idMal (MAL ID) to bridge with Trakt items.
        
        Fetches:
        - CURRENT (Watching)
        - PAUSED (On Hold)
        - COMPLETED
        
        Args:
            media_type: Ignored (AniList is anime-only)
            limit: Optional limit on items to sync
            
        Returns:
            dict: {'success': bool, 'synced': int, 'errors': list}
        """
        self._log('Starting AniList sync pull...')
        
        user_data = self.get_user_data()
        if not user_data:
            return {'success': False, 'synced': 0, 'errors': ['No user data found']}
        
        user_id = user_data.get('user_id')
        if not user_id:
            return {'success': False, 'synced': 0, 'errors': ['No user ID found']}
        
        statuses_to_sync = ['CURRENT', 'PAUSED', 'COMPLETED']
        synced_count = 0
        errors = []
        
        for status in statuses_to_sync:
            try:
                entries = self.fetch_list_by_status(user_id, status)
                
                for entry in entries:
                    try:
                        self._process_sync_entry(entry, status)
                        synced_count += 1
                    except Exception as e:
                        error_msg = f'Failed to process entry: {str(e)}'
                        self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                        errors.append(error_msg)
                
                self._log(f'Synced {len(entries)} items from {status} list')
                
            except Exception as e:
                error_msg = f'Failed to fetch {status} list: {str(e)}'
                self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                errors.append(error_msg)
        
        self._log(f'AniList sync complete: {synced_count} items synced, {len(errors)} errors')
        
        return {
            'success': len(errors) == 0,
            'synced': synced_count,
            'errors': errors
        }
    
    def fetch_list_by_status(self, user_id, status):
        """
        Fetch anime list for a specific status (PUBLIC METHOD for catalog browsing).
        
        CRITICAL: Requests idMal for database bridging.
        
        Args:
            user_id: AniList user ID
            status: List status (CURRENT, PAUSED, COMPLETED, PLANNING, DROPPED, REPEATING)
            
        Returns:
            list: List entries
        """
        query = '''
        query ($userId: Int, $status: MediaListStatus, $type: MediaType) {
            MediaListCollection(userId: $userId, status: $status, type: $type) {
                lists {
                    entries {
                        id
                        mediaId
                        status
                        progress
                        score
                        media {
                            id
                            idMal
                            title {
                                userPreferred
                                romaji
                                english
                            }
                            coverImage {
                                extraLarge
                                large
                            }
                            bannerImage
                            description
                            episodes
                            duration
                            status
                            startDate {
                                year
                                month
                                day
                            }
                            averageScore
                            genres
                            format
                        }
                    }
                }
            }
        }
        '''
        
        variables = {
            'userId': int(user_id),
            'status': status,
            'type': 'ANIME'
        }
        
        data = self._make_graphql_request(query, variables)
        
        if not data or not data.get('MediaListCollection'):
            return []
        
        # Flatten entries from all lists
        entries = []
        for media_list in data['MediaListCollection'].get('lists', []):
            entries.extend(media_list.get('entries', []))
        
        return entries
    
    def _process_sync_entry(self, entry, status):
        """
        Process a single anime entry and update database.
        
        Args:
            entry: AniList entry data
            status: List status
        """
        media = entry.get('media', {})
        
        # Extract IDs
        anilist_id = media.get('id')
        mal_id = media.get('idMal')  # CRITICAL: MAL ID for bridging
        
        if not anilist_id:
            self._log('Entry missing AniList ID, skipping', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return
        
        # Build service IDs dict (MAL ID is the bridge to Trakt)
        service_ids = {'anilist': anilist_id}
        if mal_id:
            service_ids['mal'] = mal_id
        
        # Extract metadata
        title_data = media.get('title', {})
        title = (title_data.get('userPreferred') or 
                title_data.get('romaji') or 
                title_data.get('english') or 
                'Unknown Title')
        
        # Poster
        cover_image = media.get('coverImage', {})
        poster = cover_image.get('extraLarge') or cover_image.get('large')
        
        # Fanart (use banner if available, otherwise poster)
        fanart = media.get('bannerImage') or poster
        
        # Plot
        plot = media.get('description', '')
        if plot:
            # Clean HTML tags from description
            plot = plot.replace('<br>', '\n')
            plot = plot.replace('<i>', '').replace('</i>', '')
            plot = plot.replace('<b>', '').replace('</b>', '')
        
        # Year
        start_date = media.get('startDate', {})
        year = start_date.get('year')
        
        # Progress tracking
        progress_count = entry.get('progress', 0)
        total_episodes = media.get('episodes') or 0
        
        # Calculate progress percentage
        if total_episodes > 0:
            progress_percent = int((progress_count / total_episodes) * 100)
        else:
            # Unknown total - if we've watched some, consider it in progress
            progress_percent = 50 if progress_count > 0 else 0
        
        # Duration (convert minutes to seconds)
        duration_minutes = media.get('duration')
        duration = duration_minutes * 60 if duration_minutes else None
        
        # Calculate resume time (for next episode)
        # AniList doesn't store timestamps, so we set to 0
        resume_time = 0
        
        # Check if show format is MOVIE
        is_movie = media.get('format') == 'MOVIE'
        
        if is_movie and total_episodes == 1:
            # Handle as movie
            media_type = 'movie'
            
            self.db.update_progress(
                service_ids=service_ids,
                media_type=media_type,
                progress=progress_percent,
                resume_time=resume_time,
                duration=duration,
                title=title,
                year=year,
                poster=poster,
                fanart=fanart,
                plot=plot
            )
        else:
            # Handle as TV show episodes
            # For AniList, we store the NEXT unwatched episode
            if status == 'COMPLETED' or (total_episodes > 0 and progress_count >= total_episodes):
                # Show is completed - store last episode as watched
                if total_episodes > 0:
                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='episode',
                        progress=100,
                        resume_time=0,
                        duration=duration,
                        title=title,
                        year=year,
                        season=1,  # AniList doesn't have seasons
                        episode=total_episodes,
                        poster=poster,
                        fanart=fanart,
                        plot=plot
                    )
            elif progress_count > 0:
                # In progress - store next episode to watch
                next_episode = progress_count + 1
                
                # Only store if next episode exists or total is unknown
                if total_episodes == 0 or next_episode <= total_episodes:
                    self.db.update_progress(
                        service_ids=service_ids,
                        media_type='episode',
                        progress=0,  # Next episode not started yet
                        resume_time=0,
                        duration=duration,
                        title=title,
                        year=year,
                        season=1,
                        episode=next_episode,
                        poster=poster,
                        fanart=fanart,
                        plot=plot
                    )
    
    @is_authorized
    def sync_push(self):
        """
        Push local watch history to AniList (process sync queue).
        
        Returns:
            dict: {'success': bool, 'pushed': int, 'errors': list}
        """
        self._log('Starting AniList sync push...')
        
        # Get queued items for AniList
        queue = self.db.get_sync_queue(self.service_name)
        
        if not queue:
            self._log('No items in sync queue')
            return {'success': True, 'pushed': 0, 'errors': []}
        
        pushed_count = 0
        errors = []
        
        for item in queue:
            try:
                action = item.get('action')
                data = item.get('data')
                
                if action == 'scrobble_stop':
                    # Update episode count on AniList
                    success = self._update_episode_progress(data)
                    
                    if success:
                        self.db.update_sync_item(item['id'], success=True)
                        pushed_count += 1
                    else:
                        errors.append(f'Failed to push item {item["id"]}')
                else:
                    # Unknown action - remove from queue
                    self.db.update_sync_item(item['id'], success=True)
                    
            except Exception as e:
                error_msg = f'Error processing queue item {item["id"]}: {str(e)}'
                self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
                errors.append(error_msg)
        
        self._log(f'AniList sync push complete: {pushed_count} items pushed, {len(errors)} errors')
        
        return {
            'success': len(errors) == 0,
            'pushed': pushed_count,
            'errors': errors
        }
    
    def _update_episode_progress(self, data):
        """
        Update episode progress on AniList.
        
        Args:
            data: Dict with media_info and progress
            
        Returns:
            bool: True if successful
        """
        media_info = data.get('media_info', {})
        progress = data.get('progress', 0)
        
        # Get AniList ID
        ids = media_info.get('ids', {})
        anilist_id = ids.get('anilist')
        
        if not anilist_id:
            self._log('No AniList ID found, cannot update progress', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return False
        
        # Get episode number
        episode = media_info.get('episode')
        
        if episode is None:
            self._log('No episode number found, cannot update progress', 
                     xbmc.LOGWARNING if KODI_ENV else None)
            return False
        
        # Only update if progress > 80% (considered watched)
        if progress < 80:
            self._log(f'Progress {progress}% < 80%, not updating AniList', 
                     xbmc.LOGINFO if KODI_ENV else None)
            return True  # Not an error, just skip
        
        # Update progress on AniList
        mutation = '''
        mutation ($mediaId: Int, $progress: Int, $status: MediaListStatus) {
            SaveMediaListEntry (mediaId: $mediaId, progress: $progress, status: $status) {
                id
                progress
                status
            }
        }
        '''
        
        variables = {
            'mediaId': int(anilist_id),
            'progress': int(episode),
            'status': 'CURRENT'  # Keep as CURRENT unless manually changed
        }
        
        data = self._make_graphql_request(mutation, variables)
        
        if data and data.get('SaveMediaListEntry'):
            self._log(f'Updated AniList progress: Episode {episode}')
            return True
        else:
            self._log('Failed to update AniList progress', 
                     xbmc.LOGERROR if KODI_ENV else None)
            return False
    
    # ============================================================================
    # SCROBBLING METHODS
    # ============================================================================
    
    @is_authorized
    def scrobble_start(self, media_info, progress=0):
        """
        Send 'start watching' scrobble (NO-OP for AniList).
        
        AniList is episode-based, not time-based.
        We log the event but don't make API calls.
        
        Args:
            media_info: Media information dict
            progress: Playback progress (0-100)
            
        Returns:
            dict: Status response
        """
        title = media_info.get('title', 'Unknown')
        episode = media_info.get('episode')
        
        if episode:
            self._log(f'Scrobble start: {title} S{media_info.get("season", 1)}E{episode} ({progress}%)')
        else:
            self._log(f'Scrobble start: {title} ({progress}%)')
        
        return {'status': 'logged', 'message': 'AniList does not support real-time scrobbling'}
    
    @is_authorized
    def scrobble_pause(self, media_info, progress):
        """
        Send 'pause' scrobble (NO-OP for AniList).
        
        Args:
            media_info: Media information dict
            progress: Playback progress (0-100)
            
        Returns:
            dict: Status response
        """
        title = media_info.get('title', 'Unknown')
        self._log(f'Scrobble pause: {title} ({progress}%)')
        
        return {'status': 'logged', 'message': 'AniList does not support real-time scrobbling'}
    
    @is_authorized
    def scrobble_stop(self, media_info, progress):
        """
        Send 'stop watching' scrobble.
        
        If progress > 80%, update episode count on AniList.
        
        Args:
            media_info: Media information dict
            progress: Final playback progress (0-100)
            
        Returns:
            dict: Response from service or None
        """
        title = media_info.get('title', 'Unknown')
        episode = media_info.get('episode')
        
        if episode:
            self._log(f'Scrobble stop: {title} S{media_info.get("season", 1)}E{episode} ({progress}%)')
        else:
            self._log(f'Scrobble stop: {title} ({progress}%)')
        
        # Only update if progress > 80%
        if progress < 80:
            self._log(f'Progress {progress}% < 80%, not updating AniList')
            return {'status': 'skipped', 'message': 'Progress below 80%'}
        
        # Queue for sync push (will be processed in background)
        self._queue_for_sync('scrobble_stop', {
            'media_info': media_info,
            'progress': progress
        })
        
        return {'status': 'queued', 'message': 'Queued for sync'}


