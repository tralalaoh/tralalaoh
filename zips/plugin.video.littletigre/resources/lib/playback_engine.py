"""Playback Engine - WITH DUAL ANIME QUERY STRATEGY + InfoTag fixes."""

import re
import json
import xbmc
import xbmcgui
import xbmcplugin
from urllib.parse import unquote_plus

from resources.lib.logger import log, log_error, log_debug
from resources.lib.anime_resolver import AnimeResolver
from resources.lib.stremio_api import StremioAPI
from resources.lib.filters import StreamFilter
from resources.lib.deduplicator import StreamDeduplicator
from resources.lib.stream_scorer import StreamScorer
from resources.lib.debrid import get_debrid_service
from resources.lib.settings import Settings


class PlaybackEngine:
    """
    Controller for stream playback orchestration.

    FEATURES:
    - Dual anime query strategy (absolute + season)
    - Real season resolution from AniList
    - InfoTag Kodi 19/20 compatibility
    - Netflix-style metadata
    """

    def __init__(self, addon_handle, addon_url):
        """Initialize playback engine."""
        self.handle = addon_handle
        self.url = addon_url
        self.anime_resolver = AnimeResolver()

    def play_with_dialog(self, params):
        """Main playback flow with stream selection dialog."""
        is_playback_context = self._detect_playback_context(params)

        log(f"Playback context: {is_playback_context}, handle: {self.handle}")
        log(f"📋 Received parameters: {params}")

        try:
            # Extract metadata from incoming ListItem
            incoming_metadata = self._extract_incoming_metadata()
            if incoming_metadata:
                log(f"✓ Extracted metadata from incoming ListItem: {list(incoming_metadata.keys())}")
                for key, value in incoming_metadata.items():
                    if key not in params or not params.get(key):
                        params[key] = value

            # Decode title
            raw_title = params.get('title', 'Unknown')
            clean_title = unquote_plus(raw_title)
            params['title'] = clean_title
            log(f"📺 Title decoded: {raw_title} → {clean_title}")

            # Step 1: Resolve IDs
            episode_resolution_id, episode_id_type = self._resolve_ids(params)

            if not episode_resolution_id:
                self._show_error('No valid ID provided (IMDB/TMDB/AniList required)')
                self._fail_playback(is_playback_context)
                return

            # Extract metadata
            content_type = params.get('type', 'movie')
            season = params.get('season', '')
            episode = params.get('episode', '')
            title = params.get('title', 'Unknown')
            is_anime = self.anime_resolver.detect_content_type(params)

            # === ANIME EPISODE + SEASON RESOLUTION ===
            absolute_episode = None
            real_season = None
            season_episode = None  # Episode to use for season-based query

            if is_anime and content_type == 'episode' and episode:
                anilist_id = params.get('anilist_id', '').strip()
                if anilist_id:
                    log(f"🎌 Anime detected! Resolving via AniList API...")
                    try:
                        relative_episode = int(episode)

                        # Get absolute episode, real season, AND check if split-cour
                        anime_data = self.anime_resolver.get_absolute_episode_and_season(
                            anilist_id,
                            relative_episode,
                            title
                        )

                        absolute_episode = anime_data['absolute_episode']
                        real_season = anime_data['real_season']
                        is_split_cour = anime_data.get('is_split_cour', False)

                        # === CRITICAL: For split-cour Part 2, use corrected episode ===
                        if is_split_cour:
                            # Part 2 Episode 1 → should query as S3E13 (if Part 1 had 12 eps)
                            # Use ONLY the Part 1 offset (not total offset which includes all previous seasons)
                            part_1_offset = anime_data.get('split_cour_offset', 0)
                            season_episode = str(part_1_offset + relative_episode)
                            log(f"🎌 SPLIT-COUR: Real Season {real_season}, Part 1 Offset {part_1_offset}, Corrected Episode {season_episode}")
                        else:
                            # Normal anime: use relative episode as-is
                            season_episode = str(relative_episode)

                        log(f"✓ Resolved: Relative E{relative_episode} → Absolute E{absolute_episode}, Real Season {real_season}")

                    except Exception as e:
                        log_error("Anime episode resolution failed", e)
                        absolute_episode = int(episode)
                        real_season = int(season) if season else 1
                        season_episode = episode

            # === GET SEARCH ID FOR ADDON QUERIES ===
            if is_anime:
                preferred_id_type = Settings.get_anime_search_id_type()
                log(f"🔍 User prefers {preferred_id_type.upper()} for addon queries")

                search_id, id_type = self.anime_resolver.get_search_id_for_addon(
                    params,
                    preferred_id_type
                )

                if not search_id:
                    log("⚠️ Could not get preferred ID, using episode resolution ID")
                    search_id = episode_resolution_id
                    id_type = episode_id_type
            else:
                search_id = episode_resolution_id
                id_type = episode_id_type

            log(f"🎯 Final search ID for addons: {search_id} (type: {id_type})")

            # === DUAL QUERY STRATEGY FOR ANIME ===
            all_streams = []

            if is_anime and content_type == 'episode' and absolute_episode:
                search_strategy = Settings.get_anime_search_strategy()
                log(f"🔍 Anime search strategy: {search_strategy.upper()}")

                queries = []

                # BOTH or ABSOLUTE_ONLY
                if search_strategy in ['both', 'absolute_only']:
                    queries.append({
                        'season': None,
                        'episode': str(absolute_episode),
                        'label': 'absolute'
                    })

                # BOTH or SEASON_ONLY
                if search_strategy in ['both', 'season_only']:
                    # Use corrected season_episode for split-cour anime
                    episode_for_query = season_episode if season_episode else episode

                    queries.append({
                        'season': str(real_season) if real_season else season,
                        'episode': episode_for_query,
                        'label': 'season'
                    })

                log(f"📊 Will perform {len(queries)} queries in parallel: {[q['label'] for q in queries]}")

                # Execute all queries in one parallel batch
                all_streams = self._fetch_multi_query_with_progress(
                    search_id, id_type, content_type, queries, title, is_anime, params
                )

                log(f"📊 Total streams from all queries: {len(all_streams)}")

            else:
                # Non-anime or movie: standard single query
                if content_type == 'episode':
                    log(f"📺 Episode info: Season {season}, Episode {episode}")

                all_streams = self._fetch_streams_with_progress(
                    search_id, id_type, content_type, season, episode, title, is_anime, params
                )

            log(f"📊 Received {len(all_streams)} total streams from addons")

            if not all_streams:
                self._show_notification('No streams found')
                self._fail_playback(is_playback_context)
                return

            # Step 3: Filter streams
            stream_filter = StreamFilter()
            filtered_streams = stream_filter.filter_streams(all_streams)

            if not filtered_streams:
                self._show_filter_warning(stream_filter)
                self._fail_playback(is_playback_context)
                return

            # Step 4: Deduplicate streams
            unique_streams = self._deduplicate_streams(filtered_streams)

            if not unique_streams:
                self._show_notification('No unique streams found after deduplication', duration=5000)
                self._fail_playback(is_playback_context)
                return

            # Step 5: Score and sort streams
            sorted_streams = self._score_and_sort_streams(unique_streams)

            # Step 6: Show selection dialog
            selected_stream = self._show_selection_dialog(sorted_streams, clean_title, is_anime, params)

            if not selected_stream:
                log("User cancelled stream selection")
                self._fail_playback(is_playback_context)
                return

            # Step 7: Resolve and play
            self._resolve_and_play(selected_stream, is_playback_context, params)

        except Exception as e:
            log_error("Playback engine failed", e)
            import traceback
            xbmc.log(f'[Little Tigre] Playback exception:\n{traceback.format_exc()}', xbmc.LOGERROR)
            self._show_error('Playback failed - check logs')
            self._fail_playback(is_playback_context)

    def _extract_incoming_metadata(self):
        """Extract metadata from incoming ListItem."""
        try:
            import sys
            if hasattr(sys, 'listitem') and sys.listitem:
                return self._extract_from_listitem(sys.listitem)
        except:
            pass
        return None

    def _extract_from_listitem(self, listitem):
        """Extract metadata from a ListItem object."""
        metadata = {}
        try:
            info_tag = listitem.getVideoInfoTag()

            plot = info_tag.getPlot()
            if plot: metadata['plot'] = plot

            original_title = info_tag.getOriginalTitle()
            if original_title: metadata['originaltitle'] = original_title

            show_title = info_tag.getTVShowTitle()
            if show_title:
                metadata['showtitle'] = show_title
                metadata['tvshowtitle'] = show_title

            rating = info_tag.getRating()
            if rating and rating > 0: metadata['rating'] = rating

            art = listitem.getArt()
            if art:
                for k, v in art.items():
                    if v: metadata[k] = v

            return metadata if metadata else None
        except Exception as e:
            log_debug(f"Error extracting from ListItem: {e}")
            return None

    def _detect_playback_context(self, params):
        """Detect if we're in playback context."""
        if params.get('_force_standalone', False):
            return False
        return self.handle > 1 or params.get('_from_player', False)

    def _resolve_ids(self, params):
        """Resolve content IDs to search ID."""
        try:
            return self.anime_resolver.resolve_to_search_id(params)
        except Exception as e:
            log_error("ID resolution failed", e)
            return None, None

    def _fetch_streams_with_progress(self, search_id, id_type, content_type,
                                     season, episode, title, is_anime, params):
        """Fetch streams from addons with progress dialog."""
        progress = xbmcgui.DialogProgress()
        progress_title = f'Searching streams for {title}...'
        if is_anime:
            progress_title += ' [ANIME]'

        progress.create('Little Tigre', progress_title)

        try:
            progress.update(30, 'Querying Stremio addons...')

            api = StremioAPI()
            stremio_type = 'series' if content_type == 'episode' else 'movie'

            streams = api.get_streams_with_anime_support(
                search_id, id_type, stremio_type, season, episode, params
            )

            progress.close()
            return streams

        except Exception as e:
            progress.close()
            log_error("Stream fetching failed", e)
            return []

    def _fetch_multi_query_with_progress(self, search_id, id_type, content_type,
                                          queries, title, is_anime, params):
        """Fetch streams for multiple episode queries in a single parallel batch."""
        progress = xbmcgui.DialogProgress()
        progress_title = f'Searching streams for {title}...'
        if is_anime:
            progress_title += ' [ANIME]'

        progress.create('Little Tigre', progress_title)
        try:
            label_str = ' + '.join(q['label'] for q in queries)
            progress.update(30, f'Querying addons ({label_str} in parallel)...')

            api = StremioAPI()
            stremio_type = 'series' if content_type == 'episode' else 'movie'

            streams = api.get_streams_multi_query(
                search_id, id_type, stremio_type, queries, params
            )

            progress.close()
            return streams

        except Exception as e:
            progress.close()
            log_error("Multi-query stream fetching failed", e)
            return []

    def _deduplicate_streams(self, streams):
        """Remove duplicate streams."""
        deduplicator = StreamDeduplicator()
        unique = deduplicator.deduplicate(streams)
        log(f"Deduplication: {deduplicator.get_stats_message()}")
        return unique

    def _score_and_sort_streams(self, streams):
        """Score and sort streams."""
        scorer = StreamScorer()
        for stream in streams:
            scorer.score_stream(stream)
        return scorer.sort_streams(streams, Settings.get_sort_by())

    def _show_selection_dialog(self, streams, title, is_anime, params):
        """Show beautiful Little Tigre source selection dialog."""
        try:
            # Try to use the beautiful dialog
            from resources.lib.gui.source_select import SourceSelectDialog

            # Get addon path for XML
            import xbmcaddon
            addon = xbmcaddon.Addon()
            addon_path = addon.getAddonInfo('path')

            # Prepare metadata for side panel
            metadata = {
                'title': title,
                'year': params.get('year', ''),
                'plot': params.get('plot', ''),
                'rating': params.get('rating', ''),
                'poster': params.get('poster', ''),
                'fanart': params.get('fanart', ''),
                'type': params.get('type', 'movie')
            }

            # Episode-specific
            if metadata['type'] == 'episode':
                metadata['season'] = params.get('season', '')
                metadata['episode'] = params.get('episode', '')
                metadata['showtitle'] = params.get('showtitle', params.get('tvshowtitle', title))

            # Show dialog - Pass FULL streams (not formatted) to preserve all metadata!
            dialog = SourceSelectDialog(
                'source_select.xml',
                addon_path,
                item_information=metadata,
                sources=streams  # Pass full streams with cached field!
            )

            selected_url = dialog.doModal()
            del dialog

            # Find original stream by URL
            if selected_url:
                for stream in streams:
                    if stream.get('url') == selected_url:
                        log(f"✓ User selected: {stream.get('title', 'Unknown')}")
                        return stream

            return None

        except ImportError as e:
            # Fallback to simple dialog if custom dialog not available
            log(f"⚠️ Custom dialog not available, using fallback: {e}")
            return self._show_selection_dialog_fallback(streams, title, is_anime)

        except Exception as e:
            log_error("Beautiful dialog failed, using fallback", e)
            return self._show_selection_dialog_fallback(streams, title, is_anime)

    def _show_selection_dialog_fallback(self, streams, title, is_anime):
        """Fallback to simple list dialog if beautiful dialog unavailable."""
        scorer = StreamScorer()

        dialog_items = []
        for stream in streams:
            stream_title = scorer.format_stream_stremio_style(
                stream, show_size=True, show_seeders=True
            )
            dialog_items.append(stream_title)

        dialog_title = f'Little Tigre - Select Stream for {title}'
        if is_anime:
            dialog_title += ' [ANIME]'

        selected = xbmcgui.Dialog().select(dialog_title, dialog_items)

        if selected < 0:
            return None

        selected_stream = streams[selected]
        log(f"User selected stream #{selected}: {selected_stream.get('title', 'Unknown')}")

        return selected_stream

    def _resolve_and_play(self, stream, is_playback_context, metadata):
        """Resolve stream URL and initiate playback."""
        # Overlay spinner — visible immediately, animates while we work
        xbmc.executebuiltin('ActivateWindow(busydialognocancel)')
        # Corner widget for step-by-step status text
        progress = xbmcgui.DialogProgressBG()
        progress.create('Little Tigre', 'Resolving stream...')
        try:
            url = stream.get('url', '')
            if not url:
                log_error("Stream has no URL")
                self._fail_playback(is_playback_context)
                return

            log(f"Resolving URL: {url[:100]}...")
            self._log_debrid_info(stream)

            progress.update(20, 'Little Tigre', 'Contacting service...')
            url = self._resolve_torrentio_url(url, stream)

            progress.update(60, 'Little Tigre', 'Getting direct link...')
            url = self._resolve_addon_urls(url, stream)

            progress.update(80, 'Little Tigre', 'Unrestricting...')
            url = self._unrestrict_magnet(url, is_playback_context)
            if not url:
                return

            if not self._validate_url(url, is_playback_context):
                return

            progress.update(100, 'Little Tigre', 'Starting playback...')
            play_item = self._create_play_item(url, stream, metadata)
            self._set_scrobbling_window_properties(metadata)
            self._start_playback(url, play_item, is_playback_context)

        except Exception as e:
            log_error("Failed to resolve and play stream", e)
            import traceback
            xbmc.log(f'[Little Tigre] Playback exception:\n{traceback.format_exc()}', xbmc.LOGERROR)
            self._show_error(f'Playback failed: {str(e)[:50]}')
            self._fail_playback(is_playback_context)
        finally:
            xbmc.executebuiltin('Dialog.Close(busydialognocancel)')
            progress.close()

    def _log_debrid_info(self, stream):
        """Log debrid service information."""
        cached = stream.get('cached', False)
        debrid_service = stream.get('debrid_service')

        if cached and debrid_service:
            service_names = {
                'realdebrid': 'Real-Debrid',
                'torbox': 'Torbox',
                'premiumize': 'Premiumize',
                'alldebrid': 'AllDebrid'
            }
            service_label = service_names.get(debrid_service, debrid_service)
            log(f"🎯 DEBRID SERVICE: {service_label} (cached)")
        elif cached:
            log(f"⚡ CACHED STREAM")
        else:
            log(f"📦 UNCACHED STREAM")

    def _resolve_torrentio_url(self, url, stream):
        """
        Handle Torrentio /resolve/ URLs.

        Strategy: one GET with allow_redirects=False to grab the Location header
        (Torrentio's CDN link) without downloading any body, then pass the CDN URL
        to Kodi with pipe-format headers so the CDN accepts the request.

        Why not pass the /resolve/ URL directly to Kodi:
          Kodi's HTTP VFS cannot follow Torrentio's redirect chain (timeouts / auth
          headers not forwarded), resulting in 'could not open file' errors.

        Why not use HEAD:
          Torrentio returns 302 only for GET; HEAD may return 200 without redirect.
        """
        if 'torrentio.strem.fun/resolve/' not in url:
            return url

        log("Torrentio resolve URL — pre-resolving to CDN link...")

        try:
            import requests
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://web.stremio.com/'
            }
            response = requests.get(
                url,
                allow_redirects=False,
                headers=headers,
                timeout=15
            )

            location = response.headers.get('Location', '')
            if location and location.startswith('http'):
                log(f"✓ Torrentio pre-resolve: got CDN URL")
                # Append headers so Kodi's HTTP VFS is accepted by the CDN
                cdn_url = location + '|User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36&Referer=https://torrentio.strem.fun/'
                return cdn_url

            # Non-redirect response — Torrentio may have returned the file directly
            log(f"Torrentio returned status {response.status_code} (no redirect); using original URL")

        except Exception as e:
            log_error("Torrentio pre-resolve failed", e)

        # Fallback: pass original URL with headers and hope Kodi can handle it
        if '|' not in url:
            url = url + '|User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36&Referer=https://web.stremio.com/'
        return url

    def _resolve_addon_urls(self, url, stream):
        """Resolve addon URLs."""
        if not any(service in url.lower() for service in ['comet', 'mediafusion', 'stremthru']):
            return url

        if any(domain in url.lower() for domain in ['torbox.app', 'tb-cdn.st', 'real-debrid.com',
                                                      'premiumize.me', '/files/', '/download/']):
            return url

        log(f"Attempting to resolve URL...")

        try:
            import requests
            headers = {'User-Agent': 'Mozilla/5.0'}

            response = requests.head(url, allow_redirects=True, timeout=10, headers=headers)
            resolved_url = response.url

            debrid_domains = ['torbox.app', 'tb-cdn.st', 'real-debrid.com', 'premiumize.me', 'alldebrid.com']
            if resolved_url != url and any(domain in resolved_url.lower() for domain in debrid_domains):
                log(f"✓ Resolved to direct download")
                return resolved_url

            response = requests.get(url, allow_redirects=True, timeout=10, stream=True, headers=headers)
            resolved_url = response.url

            if resolved_url != url and any(domain in resolved_url.lower() for domain in debrid_domains):
                log(f"✓ Resolved to direct download")
                return resolved_url

            return self._extract_magnet_from_stream(stream, url)

        except Exception as e:
            log_error(f"Failed to resolve URL", e)
            return self._extract_magnet_from_stream(stream, url)

    def _extract_magnet_from_stream(self, stream, original_url):
        """Extract magnet link from stream."""
        behavior_hints = stream.get('behaviorHints', {})
        binge_group = behavior_hints.get('bingeGroup', '')

        if '|' in binge_group:
            parts = binge_group.split('|')
            if len(parts) >= 2:
                info_hash = parts[1].strip()
                if info_hash:
                    magnet = f"magnet:?xt=urn:btih:{info_hash}"
                    log(f"Converted to magnet link")
                    return magnet

        return original_url

    def _unrestrict_magnet(self, url, is_playback_context):
        """Unrestrict magnet links."""
        if not url.startswith('magnet:'):
            return url

        debrid = get_debrid_service()
        if not debrid:
            log_error("No debrid service configured")
            self._show_error('Magnet links require debrid service')
            self._fail_playback(is_playback_context)
            return None

        log("Unrestricting magnet link...")
        unrestricted = debrid.unrestrict_link(url)

        if unrestricted:
            log(f"✓ Got unrestricted URL")
            return unrestricted
        else:
            log_error("Failed to unrestrict magnet link")
            self._show_error('Failed to unrestrict link', duration=5000)
            self._fail_playback(is_playback_context)
            return None

    def _validate_url(self, url, is_playback_context):
        """Validate final URL. Accepts Kodi pipe-header format (url|headers)."""
        base = url.split('|')[0] if url else ''
        if not base or not base.startswith(('http://', 'https://')):
            log_error(f"Invalid final URL")
            self._show_error('Invalid stream URL')
            self._fail_playback(is_playback_context)
            return False
        return True

    def _create_play_item(self, url, stream, metadata):
        """Create ListItem with Netflix-style metadata (FIXED InfoTag)."""
        play_item = xbmcgui.ListItem()
        play_item.setPath(url)

        url_base = url.split('|')[0]
        if '.mkv' in url_base or 'mkv' in stream.get('title', '').lower():
            play_item.setMimeType('video/x-matroska')
        elif '.mp4' in url_base or '.m4v' in url_base:
            play_item.setMimeType('video/mp4')
        else:
            play_item.setMimeType('video/x-matroska')

        play_item.setProperty('IsPlayable', 'true')
        play_item.setContentLookup(False)

        if metadata:
            self._apply_netflix_metadata(play_item, metadata, stream)
        else:
            self._apply_basic_metadata(play_item, stream)

        return play_item

    def _apply_netflix_metadata(self, play_item, metadata, stream):
        """Apply Netflix-style metadata with FIXED InfoTag (Kodi 19/20/21 compatible)."""
        content_type = metadata.get('type', 'movie')

        raw_title = metadata.get('title', 'Unknown')
        title = unquote_plus(raw_title)

        raw_plot = metadata.get('plot', metadata.get('description', ''))
        plot = unquote_plus(raw_plot) if raw_plot else ""

        year = metadata.get('year', '')
        rating = metadata.get('rating', metadata.get('vote_average', 0))
        genre = metadata.get('genre', '')

        ids = self._extract_all_ids(metadata)

        # === CRITICAL: SET ALL IDs VIA setProperty (always works) ===
        for id_type, id_value in ids.items():
            if id_value:
                play_item.setProperty(f'{id_type}_id', str(id_value))
                log_debug(f"Set property: {id_type}_id = {id_value}")

        try:
            info_tag = play_item.getVideoInfoTag()

            if content_type == 'episode':
                info_tag.setMediaType('episode')
                season = metadata.get('season', '')
                episode = metadata.get('episode', '')

                raw_show_title = metadata.get('showtitle', metadata.get('tvshowtitle', title))
                show_title = unquote_plus(raw_show_title)

                # === LEGACY + SCROBBLING COMPAT (Kodi 19/20, Trakt, Simkl, etc.) ===
                # setInfo() reliably populates VideoPlayer.Season / VideoPlayer.Episode /
                # VideoPlayer.TVShowTitle InfoLabels that scrobbling addons read in
                # onAVStarted() via getInfoLabelDetails(). Trakt requires:
                #   VideoPlayer.Season >= 0, VideoPlayer.Episode > 0,
                #   and VideoPlayer.TVShowTitle OR script.trakt.ids window property.
                _legacy = {
                    'mediatype': 'episode',
                    'tvshowtitle': show_title,
                }
                if ids.get('imdb'):
                    _legacy['imdbnumber'] = str(ids['imdb'])
                if season:
                    try: _legacy['season'] = int(season)
                    except: pass
                if episode:
                    try: _legacy['episode'] = int(episode)
                    except: pass
                if year:
                    try: _legacy['year'] = int(year)
                    except: pass
                play_item.setInfo('video', _legacy)

                # Also set via InfoTag for skin compatibility (Kodi 20/21)
                try:
                    info_tag.setTVShowTitle(show_title)  # Kodi 20+
                except AttributeError:
                    try:
                        info_tag.setShowTitle(show_title)  # Kodi 19
                    except AttributeError:
                        pass

                if season and episode:
                    season_str = str(season).zfill(2)
                    episode_str = str(episode).zfill(2)
                    formatted_title = f"{show_title} S{season_str}E{episode_str}"

                    # Set the Episode Title (Bottom line of OSD)
                    info_tag.setTitle(formatted_title)
                    play_item.setLabel(formatted_title)
                else:
                    info_tag.setTitle(show_title)
                    play_item.setLabel(show_title)

                if season:
                    try: info_tag.setSeason(int(season))
                    except: pass
                if episode:
                    try: info_tag.setEpisode(int(episode))
                    except: pass

            else:
                info_tag.setMediaType('movie')
                info_tag.setTitle(title)
                play_item.setLabel(title)
                # === LEGACY + SCROBBLING COMPAT ===
                # Trakt movie scrobble needs VideoPlayer.Year OR script.trakt.ids,
                # with VideoPlayer.Season unset (returns -1).
                _legacy = {'mediatype': 'movie', 'title': title}
                if ids.get('imdb'):
                    _legacy['imdbnumber'] = str(ids['imdb'])
                if year:
                    try: _legacy['year'] = int(year)
                    except: pass
                play_item.setInfo('video', _legacy)

            if year:
                try: info_tag.setYear(int(year))
                except: pass

            # === SET ONLY STANDARD IDs IN INFOTAG ===
            if ids.get('imdb'):
                info_tag.setIMDBNumber(str(ids['imdb']))
                info_tag.setUniqueID(str(ids['imdb']), 'imdb')

            # TMDB and TVDB are OK in InfoTag
            if ids.get('tmdb'):
                info_tag.setUniqueID(str(ids['tmdb']), 'tmdb')

            if ids.get('tvdb'):
                info_tag.setUniqueID(str(ids['tvdb']), 'tvdb')

            if plot:
                info_tag.setPlot(plot)

            if rating:
                try: info_tag.setRating(float(rating))
                except: pass

            if genre:
                info_tag.setGenres([genre])

            # Artwork
            raw_poster = metadata.get('poster', '')
            poster = unquote_plus(raw_poster) if raw_poster else ""

            raw_fanart = metadata.get('fanart', '')
            fanart = unquote_plus(raw_fanart) if raw_fanart else ""

            art = {}
            if poster:
                art['poster'] = poster
                art['thumb'] = poster
                art['icon'] = poster

            if fanart:
                art['fanart'] = fanart

            if art:
                play_item.setArt(art)

            log("✓ Netflix-style metadata applied successfully")

        except AttributeError as e:
            log_error(f"InfoTag not available, using fallback", e)
            self._apply_netflix_metadata_fallback(play_item, metadata, ids, title)

    def _extract_all_ids(self, metadata):
        """Extract ALL available IDs."""
        ids = {}

        ids['imdb'] = metadata.get('imdb_id', metadata.get('imdb', '')).strip()
        ids['tmdb'] = metadata.get('tmdb_id', metadata.get('tmdb', '')).strip()
        ids['tvdb'] = metadata.get('tvdb_id', metadata.get('tvdb', '')).strip()
        ids['mal'] = metadata.get('mal_id', metadata.get('mal', '')).strip()
        ids['anilist'] = metadata.get('anilist_id', metadata.get('anilist', '')).strip()
        ids['kitsu'] = metadata.get('kitsu_id', metadata.get('kitsu', '')).strip()

        return {k: v for k, v in ids.items() if v}

    def _apply_netflix_metadata_fallback(self, play_item, metadata, ids, clean_title):
        """Fallback for older Kodi (FIXED - no anime IDs in video_info)."""
        content_type = metadata.get('type', 'movie')
        year = metadata.get('year', '')
        rating = metadata.get('rating', 0)
        genre = metadata.get('genre', '')

        video_info = {
            'mediatype': 'episode' if content_type == 'episode' else 'movie'
        }

        if content_type == 'episode':
            season = metadata.get('season', '')
            episode = metadata.get('episode', '')

            raw_show_title = metadata.get('showtitle', metadata.get('tvshowtitle', clean_title))
            show_title = unquote_plus(raw_show_title)
            video_info['tvshowtitle'] = show_title

            if season and episode:
                video_info['title'] = f"{show_title} S{season.zfill(2)}E{episode.zfill(2)}"
            else:
                video_info['title'] = clean_title

            if season:
                try: video_info['season'] = int(season)
                except: pass
            if episode:
                try: video_info['episode'] = int(episode)
                except: pass
        else:
            video_info['title'] = clean_title

        if year:
            try: video_info['year'] = int(year)
            except: pass

        if rating:
            try: video_info['rating'] = float(rating)
            except: pass

        if genre:
            video_info['genre'] = genre

        # === CRITICAL: ONLY STANDARD IDs in video_info ===
        if ids.get('imdb'):
            video_info['imdbnumber'] = str(ids['imdb'])

        if ids.get('tmdb'):
            video_info['tmdb_id'] = str(ids['tmdb'])

        if ids.get('tvdb'):
            video_info['tvdb_id'] = str(ids['tvdb'])

        # DON'T add anime IDs here - causes NEWADDON errors!
        # They're already set via setProperty

        raw_plot = metadata.get('plot', '')
        plot = unquote_plus(raw_plot) if raw_plot else ""
        if plot: video_info['plot'] = plot

        play_item.setInfo('video', video_info)

        # Artwork
        poster = metadata.get('poster', '')
        fanart = metadata.get('fanart', '')

        art = {}
        if poster:
            art['poster'] = unquote_plus(poster)
            art['thumb'] = unquote_plus(poster)
            art['icon'] = unquote_plus(poster)
        if fanart:
            art['fanart'] = unquote_plus(fanart)

        if art: play_item.setArt(art)

        log(f"✓ Netflix-style metadata applied (fallback)")

    def _apply_basic_metadata(self, play_item, stream):
        """Apply basic metadata."""
        try:
            info_tag = play_item.getVideoInfoTag()
            info_tag.setTitle(stream.get('title', 'Stream'))
            info_tag.setMediaType('video')
        except AttributeError:
            play_item.setInfo('video', {
                'title': stream.get('title', 'Stream'),
                'mediatype': 'video'
            })

    def _start_playback(self, url, play_item, is_playback_context):
        """Initiate playback."""
        if is_playback_context:
            log(f"✓ Resolving with setResolvedUrl()")
            xbmcplugin.setResolvedUrl(self.handle, succeeded=True, listitem=play_item)
        else:
            log(f"✓ Starting with xbmc.Player().play()")
            player = xbmc.Player()
            player.play(url, play_item)

    def _show_error(self, message, duration=5000):
        """Show error notification."""
        xbmcgui.Dialog().notification('Little Tigre', message, xbmcgui.NOTIFICATION_ERROR, duration)

    def _show_notification(self, message, duration=3000):
        """Show info notification."""
        xbmcgui.Dialog().notification('Little Tigre', message, xbmcgui.NOTIFICATION_INFO, duration)

    def _show_filter_warning(self, stream_filter):
        """Show warning about filtered streams."""
        filter_summary = stream_filter.get_filter_summary()
        message = f"All streams filtered ({filter_summary})" if filter_summary else "All streams filtered"
        xbmcgui.Dialog().notification('Little Tigre', message, xbmcgui.NOTIFICATION_WARNING, 5000)

    def _set_scrobbling_window_properties(self, metadata):
        """
        Set Window(10000) properties for Trakt and other scrobbling addons.

        script.trakt.ids is read by Trakt's getInfoLabelDetails() when a
        non-library (plugin-played) item starts. It is the PRIMARY way for
        plugin addons to pass IDs to the scrobbler. Without it, Trakt falls
        back to fuzzy title matching which fails for non-English content.

        Format: JSON string, e.g. '{"imdb": "tt1234567", "tmdb": "12345"}'
        """
        try:
            ids = {}
            imdb = metadata.get('imdb_id', metadata.get('imdb', '')).strip()
            tmdb = metadata.get('tmdb_id', metadata.get('tmdb', '')).strip()
            tvdb = metadata.get('tvdb_id', metadata.get('tvdb', '')).strip()
            if imdb:
                ids['imdb'] = imdb
            if tmdb:
                ids['tmdb'] = tmdb
            if tvdb:
                ids['tvdb'] = tvdb
            if ids:
                xbmcgui.Window(10000).setProperty('script.trakt.ids', json.dumps(ids))
                log(f"Scrobbling: set script.trakt.ids = {ids}")
            else:
                log_debug("Scrobbling: no IDs available for script.trakt.ids")
        except Exception as e:
            log_error("Failed to set scrobbling window properties", e)

    def _fail_playback(self, is_playback_context):
        """Handle playback failure."""
        # Clear scrobbling window property so stale IDs don't bleed into next item.
        try:
            xbmcgui.Window(10000).clearProperty('script.trakt.ids')
        except Exception:
            pass
        if is_playback_context:
            xbmcplugin.setResolvedUrl(self.handle, succeeded=False, listitem=xbmcgui.ListItem())
