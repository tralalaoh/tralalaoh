# -*- coding: utf-8 -*-
"""
Library Linking Service
Scans Kodi library and links items to sync services (Trakt, AniList, etc.)
Enables progress sync between local library and external services.
"""

import xbmc
import xbmcgui
import json

try:
    KODI_ENV = True
except ImportError:
    KODI_ENV = False


class LibraryLinker:
    """
    Links Kodi library items to sync service database.
    
    Features:
    - Scans movies and TV shows from Kodi library
    - Extracts IDs (IMDb, TMDB, TVDB) from library metadata
    - Matches library items with database items by ID
    - Updates database with library paths for direct playback
    - Syncs progress from library to database
    """
    
    def __init__(self, database):
        """
        Initialize library linker.
        
        Args:
            database: Database instance
        """
        self.db = database
        self._log('LibraryLinker initialized')
    
    def _log(self, message, level=xbmc.LOGINFO if KODI_ENV else None):
        """Log message."""
        if KODI_ENV:
            xbmc.log(f'[LittleRabite-Library] {message}', level)
        else:
            print(f'[LibraryLinker] {message}')
    
    # ============================================================================
    # LIBRARY SCANNING
    # ============================================================================
    
    def scan_library(self, progress_callback=None):
        """
        Scan Kodi library and link items to database.
        
        Args:
            progress_callback: Optional callback(percent, message)
            
        Returns:
            dict: {
                'movies_scanned': int,
                'movies_linked': int,
                'episodes_scanned': int,
                'episodes_linked': int,
                'errors': list
            }
        """
        self._log('Starting library scan...')
        
        results = {
            'movies_scanned': 0,
            'movies_linked': 0,
            'episodes_scanned': 0,
            'episodes_linked': 0,
            'errors': []
        }
        
        try:
            # Scan movies
            if progress_callback:
                progress_callback(10, 'Scanning movies...')
            
            movie_results = self._scan_movies()
            results['movies_scanned'] = movie_results['scanned']
            results['movies_linked'] = movie_results['linked']
            results['errors'].extend(movie_results['errors'])
            
            # Scan TV shows
            if progress_callback:
                progress_callback(60, 'Scanning TV shows...')
            
            tv_results = self._scan_tv_shows()
            results['episodes_scanned'] = tv_results['scanned']
            results['episodes_linked'] = tv_results['linked']
            results['errors'].extend(tv_results['errors'])
            
            if progress_callback:
                progress_callback(100, 'Scan complete!')
            
            self._log(
                f'Library scan complete: '
                f'{results["movies_linked"]}/{results["movies_scanned"]} movies, '
                f'{results["episodes_linked"]}/{results["episodes_scanned"]} episodes linked'
            )
            
        except Exception as e:
            error_msg = f'Library scan error: {str(e)}'
            self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
            results['errors'].append(error_msg)
        
        return results
    
    def _scan_movies(self):
        """
        Scan movie library.
        
        Returns:
            dict: {'scanned': int, 'linked': int, 'errors': list}
        """
        results = {'scanned': 0, 'linked': 0, 'errors': []}
        
        try:
            # Query Kodi JSON-RPC for movies
            query = {
                'jsonrpc': '2.0',
                'method': 'VideoLibrary.GetMovies',
                'params': {
                    'properties': [
                        'title',
                        'year',
                        'imdbnumber',  # IMDb ID
                        'uniqueid',     # All IDs (TMDB, TVDB, etc.)
                        'file',         # File path
                        'playcount',    # Times watched
                        'resume',       # Resume point
                        'runtime'       # Duration
                    ]
                },
                'id': 1
            }
            
            response = xbmc.executeJSONRPC(json.dumps(query))
            data = json.loads(response)
            
            if 'result' not in data or 'movies' not in data['result']:
                return results
            
            movies = data['result']['movies']
            results['scanned'] = len(movies)
            
            # Process each movie
            for movie in movies:
                try:
                    linked = self._link_movie(movie)
                    if linked:
                        results['linked'] += 1
                except Exception as e:
                    error_msg = f'Error linking movie {movie.get("title")}: {str(e)}'
                    self._log(error_msg, xbmc.LOGWARNING if KODI_ENV else None)
                    results['errors'].append(error_msg)
            
        except Exception as e:
            error_msg = f'Movie scan error: {str(e)}'
            self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
            results['errors'].append(error_msg)
        
        return results
    
    def _scan_tv_shows(self):
        """
        Scan TV show library.
        
        Returns:
            dict: {'scanned': int, 'linked': int, 'errors': list}
        """
        results = {'scanned': 0, 'linked': 0, 'errors': []}
        
        try:
            # First, get all TV shows
            query = {
                'jsonrpc': '2.0',
                'method': 'VideoLibrary.GetTVShows',
                'params': {
                    'properties': [
                        'title',
                        'year',
                        'imdbnumber',
                        'uniqueid'
                    ]
                },
                'id': 1
            }
            
            response = xbmc.executeJSONRPC(json.dumps(query))
            data = json.loads(response)
            
            if 'result' not in data or 'tvshows' not in data['result']:
                return results
            
            shows = data['result']['tvshows']
            
            # For each show, get all episodes
            for show in shows:
                try:
                    show_results = self._link_show_episodes(show)
                    results['scanned'] += show_results['scanned']
                    results['linked'] += show_results['linked']
                    results['errors'].extend(show_results['errors'])
                except Exception as e:
                    error_msg = f'Error linking show {show.get("title")}: {str(e)}'
                    self._log(error_msg, xbmc.LOGWARNING if KODI_ENV else None)
                    results['errors'].append(error_msg)
            
        except Exception as e:
            error_msg = f'TV show scan error: {str(e)}'
            self._log(error_msg, xbmc.LOGERROR if KODI_ENV else None)
            results['errors'].append(error_msg)
        
        return results
    
    def _link_show_episodes(self, show):
        """
        Link all episodes of a TV show.
        
        Args:
            show: Show dict from Kodi
            
        Returns:
            dict: {'scanned': int, 'linked': int, 'errors': list}
        """
        results = {'scanned': 0, 'linked': 0, 'errors': []}
        
        try:
            # Get all episodes for this show
            query = {
                'jsonrpc': '2.0',
                'method': 'VideoLibrary.GetEpisodes',
                'params': {
                    'tvshowid': show['tvshowid'],
                    'properties': [
                        'title',
                        'season',
                        'episode',
                        'file',
                        'playcount',
                        'resume',
                        'runtime',
                        'uniqueid'
                    ]
                },
                'id': 1
            }
            
            response = xbmc.executeJSONRPC(json.dumps(query))
            data = json.loads(response)
            
            if 'result' not in data or 'episodes' not in data['result']:
                return results
            
            episodes = data['result']['episodes']
            results['scanned'] = len(episodes)
            
            # Extract show IDs
            show_ids = self._extract_ids(show)
            
            # Process each episode
            for episode in episodes:
                try:
                    linked = self._link_episode(episode, show, show_ids)
                    if linked:
                        results['linked'] += 1
                except Exception as e:
                    error_msg = f'Error linking episode {episode.get("title")}: {str(e)}'
                    results['errors'].append(error_msg)
            
        except Exception as e:
            error_msg = f'Episode scan error: {str(e)}'
            results['errors'].append(error_msg)
        
        return results
    
    # ============================================================================
    # LINKING LOGIC
    # ============================================================================
    
    def _link_movie(self, movie):
        """
        Link a movie from library to database.
        
        Args:
            movie: Movie dict from Kodi
            
        Returns:
            bool: True if linked
        """
        # Extract IDs
        ids = self._extract_ids(movie)
        
        if not ids:
            self._log(f'No IDs found for movie: {movie.get("title")}', xbmc.LOGDEBUG if KODI_ENV else None)
            return False
        
        # Check if movie exists in database
        db_item = self._find_in_database(ids, 'movie')
        
        if db_item:
            # Update existing item with library info
            self._update_with_library_info(db_item, movie, 'movie')
            return True
        else:
            # Create new item in database from library
            self._create_from_library(movie, ids, 'movie')
            return True
    
    def _link_episode(self, episode, show, show_ids):
        """
        Link a TV episode from library to database.
        
        Args:
            episode: Episode dict from Kodi
            show: Show dict from Kodi
            show_ids: Extracted show IDs
            
        Returns:
            bool: True if linked
        """
        if not show_ids:
            return False
        
        season = episode.get('season', 0)
        episode_num = episode.get('episode', 0)
        
        # Check if episode exists in database
        db_item = self._find_in_database(show_ids, 'episode', season, episode_num)
        
        if db_item:
            # Update existing item with library info
            self._update_with_library_info(db_item, episode, 'episode')
            return True
        else:
            # Create new item in database from library
            self._create_from_library(episode, show_ids, 'episode', show.get('title'), season, episode_num)
            return True
    
    # ============================================================================
    # DATABASE OPERATIONS
    # ============================================================================
    
    def _find_in_database(self, ids, media_type, season=None, episode=None):
        """
        Find item in database by IDs.
        
        Args:
            ids: Dict of service IDs
            media_type: 'movie' or 'episode'
            season: Season number (episodes only)
            episode: Episode number (episodes only)
            
        Returns:
            dict: Database item or None
        """
        try:
            # Query database for items with matching IDs
            if media_type == 'movie':
                items = self.db.get_continue_watching(limit=1000)  # Get all items
            else:
                items = self.db.get_continue_watching(limit=1000)
            
            # Check each item for ID intersection
            for item in items:
                if item.get('type') != media_type:
                    continue
                
                item_ids = item.get('service_ids', {})
                
                # Check if any ID matches
                for key, value in ids.items():
                    if key in item_ids and str(item_ids[key]) == str(value):
                        # For episodes, also check season/episode
                        if media_type == 'episode':
                            if item.get('season') == season and item.get('episode') == episode:
                                return item
                        else:
                            return item
            
            return None
            
        except Exception as e:
            self._log(f'Database search error: {str(e)}', xbmc.LOGWARNING if KODI_ENV else None)
            return None
    
    def _update_with_library_info(self, db_item, library_item, media_type):
        """
        Update database item with library information.
        
        Args:
            db_item: Item from database
            library_item: Item from Kodi library
            media_type: 'movie' or 'episode'
        """
        try:
            # Extract library info
            file_path = library_item.get('file')
            playcount = library_item.get('playcount', 0)
            resume = library_item.get('resume', {})
            runtime = library_item.get('runtime', 0)
            
            # Calculate progress
            resume_position = resume.get('position', 0)
            total_time = resume.get('total', runtime * 60 if runtime else 0)
            
            progress = 0
            if total_time > 0:
                progress = int((resume_position / total_time) * 100)
            
            # Determine completion status
            completed = 1 if playcount > 0 and progress >= 90 else 0
            
            # Update database
            service_ids = db_item.get('service_ids', {})
            
            self.db.update_progress(
                service_ids=service_ids,
                media_type=media_type,
                progress=progress if not completed else 100,
                resume_time=int(resume_position) if not completed else 0,
                duration=int(total_time),
                title=db_item.get('title'),
                season=db_item.get('season') if media_type == 'episode' else None,
                episode=db_item.get('episode') if media_type == 'episode' else None,
                # Store library path as metadata
                plot=db_item.get('plot'),  # Keep existing plot
                year=db_item.get('year'),  # Keep existing year
                poster=db_item.get('poster'),  # Keep existing poster
                fanart=db_item.get('fanart')  # Keep existing fanart
            )
            
            if completed:
                self.db.mark_completed(
                    service_ids=service_ids,
                    season=db_item.get('season') if media_type == 'episode' else None,
                    episode=db_item.get('episode') if media_type == 'episode' else None
                )
            
            self._log(
                f'Updated {media_type} in database: {db_item.get("title")} '
                f'(progress: {progress}%, completed: {completed})'
            )
            
        except Exception as e:
            self._log(f'Update error: {str(e)}', xbmc.LOGWARNING if KODI_ENV else None)
    
    def _create_from_library(self, library_item, ids, media_type, title=None, season=None, episode=None):
        """
        Create new database item from library item.
        
        Args:
            library_item: Item from Kodi library
            ids: Service IDs
            media_type: 'movie' or 'episode'
            title: Title (for episodes, this is show title)
            season: Season number (episodes only)
            episode: Episode number (episodes only)
        """
        try:
            # Extract library info
            playcount = library_item.get('playcount', 0)
            resume = library_item.get('resume', {})
            runtime = library_item.get('runtime', 0)
            
            # Calculate progress
            resume_position = resume.get('position', 0)
            total_time = resume.get('total', runtime * 60 if runtime else 0)
            
            progress = 0
            if total_time > 0:
                progress = int((resume_position / total_time) * 100)
            
            # Determine completion status
            completed = 1 if playcount > 0 and progress >= 90 else 0
            
            # Get title
            if not title:
                title = library_item.get('title', 'Unknown')
            
            # Create in database
            self.db.update_progress(
                service_ids=ids,
                media_type=media_type,
                progress=progress if not completed else 100,
                resume_time=int(resume_position) if not completed else 0,
                duration=int(total_time),
                title=title,
                season=season,
                episode=episode,
                year=library_item.get('year')
            )
            
            if completed:
                self.db.mark_completed(
                    service_ids=ids,
                    season=season,
                    episode=episode
                )
            
            self._log(f'Created new {media_type} from library: {title}')
            
        except Exception as e:
            self._log(f'Create error: {str(e)}', xbmc.LOGWARNING if KODI_ENV else None)
    
    # ============================================================================
    # UTILITY METHODS
    # ============================================================================
    
    def _extract_ids(self, item):
        """
        Extract service IDs from Kodi library item.
        
        Args:
            item: Item dict from Kodi
            
        Returns:
            dict: Service IDs (imdb, tmdb, tvdb, etc.)
        """
        ids = {}
        
        try:
            # Extract from uniqueid dict
            unique_ids = item.get('uniqueid', {})
            
            if isinstance(unique_ids, dict):
                for key, value in unique_ids.items():
                    if value:
                        ids[key] = value
            
            # Also check imdbnumber (legacy)
            imdb_number = item.get('imdbnumber')
            if imdb_number and imdb_number.startswith('tt'):
                ids['imdb'] = imdb_number
            
        except Exception as e:
            self._log(f'ID extraction error: {str(e)}', xbmc.LOGDEBUG if KODI_ENV else None)
        
        return ids


def get_library_linker(database):
    """
    Get library linker instance.
    
    Args:
        database: Database instance
        
    Returns:
        LibraryLinker instance
    """
    return LibraryLinker(database)
