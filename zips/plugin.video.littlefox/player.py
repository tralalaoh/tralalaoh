# -*- coding: utf-8 -*-
"""
Little Fox - Turkish Series Player
Main entry point for stream resolution

Your clever companion for Turkish series streaming!

Architecture Layer: DISPLAY (Playback)
Version 2.5.3 - Critical Fixes
"""

import sys
import os
import json
import urllib.parse
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

# Import PlayerCore and logger
from lib.player_core import PlayerCore
from lib.logger import log

# Constants
_handle = int(sys.argv[1]) if len(sys.argv) > 1 else -1
_url = sys.argv[0] if len(sys.argv) > 0 else ""
addon = xbmcaddon.Addon()

def get_params():
    """Parse URL parameters"""
    if len(sys.argv) < 3:
        return {}
    return dict(urllib.parse.parse_qsl(sys.argv[2][1:]))

def play_episode(params):
    """
    Resolve and play episode
    Called by AIO Metadata, Seren, or other addons

    Supports both TMDB and IMDb IDs:
    - tmdb_id=12345 â†' Direct playback
    - imdb_id=tt1234567 â†' Translate to TMDB first â†' Playback

    Uses Sub-Resolver Pattern:
    - PlayerCore orchestrates providers and resolvers
    - Returns standardized result with url, is_hls, subtitles, headers
    - This function handles Kodi 21 playback setup

    CRITICAL: Uses xbmcplugin.setResolvedUrl() to hand stream back to caller
    """

    try:
        # =====================================================================
        # EXTRACT ALL PARAMETERS (IDs + Metadata)
        # =====================================================================

        # IDs
        tmdb_id = params.get('tmdb_id', '')
        imdb_id = params.get('imdb_id', '')
        tvdb_id = params.get('tvdb_id', '')
        mal_id = params.get('mal_id', '')
        anilist_id = params.get('anilist_id', '')
        kitsu_id = params.get('kitsu_id', '')

        # Episode info
        season = int(params.get('season', 1))
        episode = int(params.get('episode', 1))
        title = params.get('title', 'Unknown')
        year = params.get('year', '')

        # Metadata (for display)
        poster = params.get('poster', '')
        fanart = params.get('fanart', '')
        clearlogo = params.get('clearlogo', '') or params.get('logo', '')
        plot = params.get('plot', '')
        rating = params.get('rating', '')
        thumbnail = params.get('thumbnail', '')

        log(f"Received metadata - Poster: {bool(poster)}, Fanart: {bool(fanart)}, Logo: {bool(clearlogo)}", 'debug')

        # Initialize PlayerCore first (we need it for translation)
        player_core = PlayerCore(addon)

        # SCENARIO 1: TMDB ID provided (direct usage)
        if tmdb_id and str(tmdb_id).isdigit():
            tmdb_id = int(tmdb_id)
            log(f"TMDB ID provided: {tmdb_id}")

        # SCENARIO 2: IMDb ID provided (needs translation)
        elif imdb_id:
            log(f"IMDb ID provided: {imdb_id}, translating to TMDB...")

            # Show progress dialog during translation
            progress = xbmcgui.DialogProgress()
            progress.create('Little Fox', 'Translating IMDb ID to TMDB...')
            progress.update(30)

            # Translate IMDb â†' TMDB
            tmdb_id = player_core.id_translator.translate(imdb_id)

            progress.close()

            if not tmdb_id:
                log(f"Failed to translate IMDb ID: {imdb_id}", 'error')
                xbmcgui.Dialog().ok(
                    'Little Fox',
                    f'Failed to translate IMDb ID:\n{imdb_id}\n\n'
                    f'Possible reasons:\n'
                    f'- Invalid IMDb ID format\n'
                    f'- Not a TV series (movies not supported)\n'
                    f'- Episode without parent series info\n\n'
                    f'Try using TMDB ID instead.'
                )
                xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
                return

            log(f"Translation successful: {imdb_id} -> TMDB {tmdb_id}")

        # SCENARIO 3: Neither ID provided
        else:
            log("Missing ID: Neither TMDB ID nor IMDb ID provided", 'error')
            xbmcgui.Dialog().ok(
                'Little Fox',
                'Missing ID parameter.\n\n'
                'Please provide either:\n'
                '- tmdb_id=12345, or\n'
                '- imdb_id=tt1234567'
            )
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return

        # At this point, we have a valid TMDB ID
        log(f"=== RESOLVING STREAM (Sub-Resolver Pattern) ===")
        log(f"Title: {title}")
        log(f"TMDB ID: {tmdb_id}")
        log(f"Episode: S{season:02d}E{episode:02d}")

        # Show progress dialog
        progress = xbmcgui.DialogProgress()
        progress.create('Little Fox', f'{title}\nS{season:02d}E{episode:02d}')
        progress.update(10, 'Initializing PlayerCore...')

        progress.update(30, 'Searching providers...')

        # Build metadata dict for the source select dialog right panel
        item_information = {
            'title':     title,
            'season':    season,
            'episode':   episode,
            'year':      year,
            'rating':    rating,
            'plot':      plot,
            'poster':    poster,
            'fanart':    fanart,
            'thumbnail': thumbnail,
            'type':      'episode',
        }

        # Resolve episode (interactive loop handles retries)
        result = player_core.resolve_episode(
            tmdb_id, season, episode, title,
            item_information=item_information,
        )

        progress.close()

        if not result:
            log("No stream found", 'error')
            xbmcgui.Dialog().ok(
                'Little Fox',
                'No stream found for this episode.\n\nTry different episode or enable more providers.'
            )
            xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())
            return

        # =====================================================================
        # KODI 21 OMEGA COMPATIBLE PLAYBACK SETUP
        # =====================================================================

        # Extract result from resolver
        stream_url = result['url']
        is_hls = result.get('is_hls', False)
        subtitles = result.get('subtitles', [])
        headers = result.get('headers', {})

        log(f"Final stream URL: {stream_url[:80]}...")
        log(f"Is HLS: {is_hls}")

        # =====================================================================
        # HANDSHAKE: Build URL with proper header syntax
        # =====================================================================

        # RULE: Only append headers for direct web URLs (NOT plugin:// URLs)
        if headers and not stream_url.startswith('plugin://'):
            # Ensure User-Agent
            if 'User-Agent' not in headers:
                headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

            # Build header string with URL-encoded values (Kodi 21 safe)
            # Format: url|Header1=EncodedValue1&Header2=EncodedValue2
            header_parts = []
            for key, value in headers.items():
                # URL-encode the value to handle special characters
                encoded_value = urllib.parse.quote(str(value))
                header_parts.append(f"{key}={encoded_value}")

            header_string = "&".join(header_parts)

            # Build final URL with pipe delimiter
            final_url = f"{stream_url}|{header_string}"

            log(f"Headers attached: {list(headers.keys())}")
        else:
            # No headers (plugin:// URL or no headers needed)
            final_url = stream_url
            log("No headers attached (plugin:// or no headers needed)")

        # =====================================================================
        # KODI 21 MEMORY SAFETY: Use getVideoInfoTag() instead of setInfo()
        # =====================================================================

        # Create ListItem — label is read by skins as Player.Title / ListItem.Label
        play_item = xbmcgui.ListItem(label=title, label2=f'S{season:02d}E{episode:02d}', path=final_url)

        # Set IsPlayable property
        play_item.setProperty('IsPlayable', 'true')

        # Prevent Kodi from probing the file first (helps with CDN streams)
        play_item.setContentLookup(False)

        # KODI 21 COMPATIBLE: Use getVideoInfoTag() to set metadata
        video_info_tag = play_item.getVideoInfoTag()

        # =====================================================================
        # LEGACY setInfo() — scrobbling addons (Trakt, Simkl, etc.) read from
        # the old InfoLabel pipeline (VideoPlayer.IMDBNumber, .TVShowTitle,
        # .Season, .Episode) which is only populated by setInfo(), not by the
        # InfoTagVideo API. Both must be set for full compatibility.
        # =====================================================================
        video_info = {
            'mediatype':   'episode',
            'tvshowtitle': title,
            'season':      season,
            'episode':     episode,
            'title':       f'{title} - S{season:02d}E{episode:02d}',
        }
        if imdb_id:
            video_info['imdbnumber'] = imdb_id
        if year:
            try:
                video_info['year'] = int(year)
            except (ValueError, TypeError):
                pass
        play_item.setInfo('video', video_info)
        log('Legacy setInfo() applied for scrobbling compatibility', 'debug')

        # Set video metadata using InfoTagVideo methods
        video_info_tag.setTitle(f'{title} - S{season:02d}E{episode:02d}')
        video_info_tag.setEpisode(episode)
        video_info_tag.setSeason(season)
        video_info_tag.setTvShowTitle(title)
        video_info_tag.setMediaType('episode')

        # Set plot/description
        if plot:
            plot_decoded = urllib.parse.unquote_plus(plot)
            video_info_tag.setPlot(plot_decoded)
            video_info_tag.setPlotOutline(plot_decoded)

        # Set year
        if year:
            try:
                video_info_tag.setYear(int(year))
            except:
                pass

        # Set rating
        if rating:
            try:
                rating_float = float(rating)
                video_info_tag.setRating(rating_float)
            except:
                pass

        # =====================================================================
        # UNIQUE IDs: Allow scrobbling addons (Trakt, Simkl, etc.) to detect
        # the episode via VideoPlayer.UniqueID(tmdb/imdb/tvdb) InfoLabels
        # and via ListItem.Property(tmdb_id/imdb_id/tvdb_id) for older addons
        # =====================================================================

        # TMDB is always available at this point (translated if needed)
        video_info_tag.setUniqueID(str(tmdb_id), 'tmdb', True)
        play_item.setProperty('tmdb_id', str(tmdb_id))

        if imdb_id:
            video_info_tag.setUniqueID(imdb_id, 'imdb')
            play_item.setProperty('imdb_id', imdb_id)

        if tvdb_id:
            video_info_tag.setUniqueID(tvdb_id, 'tvdb')
            play_item.setProperty('tvdb_id', tvdb_id)

        if mal_id:
            play_item.setProperty('mal_id', mal_id)

        if anilist_id:
            play_item.setProperty('anilist_id', anilist_id)

        if kitsu_id:
            play_item.setProperty('kitsu_id', kitsu_id)

        # ---------------------------------------------------------------------
        # script.trakt.ids — Home window property read by Trakt (and other
        # scrobbling addons) in their onAVStarted handler via:
        #   xbmcgui.Window(10000).getProperty("script.trakt.ids")
        # For non-library (plugin) items this is the ONLY reliable ID path.
        # Without it Trakt falls back to fuzzy title matching which fails on
        # non-English titles. With it, Trakt does a direct API ID lookup.
        # Priority: imdb > tmdb > tvdb  (imdb is most universal on Trakt)
        # ---------------------------------------------------------------------
        trakt_ids = {}
        if imdb_id:
            trakt_ids['imdb'] = imdb_id
        if tmdb_id:
            trakt_ids['tmdb'] = str(tmdb_id)
        if tvdb_id:
            trakt_ids['tvdb'] = tvdb_id
        xbmcgui.Window(10000).setProperty('script.trakt.ids', json.dumps(trakt_ids))

        log(f"Unique IDs set - TMDB: {tmdb_id}, IMDb: {imdb_id or 'N/A'}, TVDB: {tvdb_id or 'N/A'}")
        log(f"script.trakt.ids window property set: {trakt_ids}", 'debug')

        # =====================================================================
        # SET ALL ARTWORK (Poster, Fanart, Logo, Thumbnail)
        # =====================================================================

        art_dict = {}

        if poster:
            poster_decoded = urllib.parse.unquote_plus(poster)
            art_dict['poster'] = poster_decoded
            art_dict['tvshow.poster'] = poster_decoded

        if fanart:
            fanart_decoded = urllib.parse.unquote_plus(fanart)
            art_dict['fanart'] = fanart_decoded
            art_dict['tvshow.fanart'] = fanart_decoded
            # landscape = wide backdrop used by player OSD — prefer fanart
            art_dict['landscape'] = fanart_decoded
            art_dict['tvshow.landscape'] = fanart_decoded

        if clearlogo:
            logo_decoded = urllib.parse.unquote_plus(clearlogo)
            art_dict['clearlogo'] = logo_decoded
            art_dict['tvshow.clearlogo'] = logo_decoded
            # clearart is the key Estuary and Netflix-style skins use
            # to render the transparent logo overlay in the player
            art_dict['clearart'] = logo_decoded
            art_dict['tvshow.clearart'] = logo_decoded

        if thumbnail:
            thumb_decoded = urllib.parse.unquote_plus(thumbnail)
            art_dict['thumb'] = thumb_decoded
            # only use thumbnail as landscape when there is no fanart
            if 'landscape' not in art_dict:
                art_dict['landscape'] = thumb_decoded

        # Apply all artwork
        if art_dict:
            play_item.setArt(art_dict)
            log(f"Applied artwork: {list(art_dict.keys())}")

        log("Metadata set using getVideoInfoTag() (Kodi 21 compatible)")

        # =====================================================================
        # ADAPTIVE PLAYBACK: Configure inputstream.adaptive for HLS
        # =====================================================================

        if is_hls:
            log("Configuring inputstream.adaptive for HLS stream")

            play_item.setProperty('inputstream', 'inputstream.adaptive')
            play_item.setProperty('inputstream.adaptive.manifest_type', 'hls')
            play_item.setMimeType('application/vnd.apple.mpegurl')
            play_item.setContentLookup(False)

        # =====================================================================
        # SUBTITLES: Attach AI-translated tracks
        # =====================================================================

        if subtitles:
            log(f"Attaching {len(subtitles)} subtitle track(s)")

            try:
                play_item.setSubtitles(subtitles)
                log("Subtitles attached successfully")
            except Exception as e:
                log(f"Failed to attach subtitles: {e}", 'warning')

        # =====================================================================
        # HAND STREAM BACK TO TMDB HELPER / KODI VIA setResolvedUrl
        # =====================================================================

        # setResolvedUrl() is the correct way to return a resolved stream to
        # the caller (TMDb Helper or any other addon that opened us with a
        # handle).  It works for both direct URLs and plugin:// URLs — Kodi
        # will recursively resolve plugin:// paths (e.g. plugin.video.youtube).
        log("Resolving URL via xbmcplugin.setResolvedUrl()...")
        xbmcplugin.setResolvedUrl(_handle, True, play_item)
        log("SUCCESS: URL resolved via setResolvedUrl()")

    except Exception as e:
        log(f"Playback error: {e}", 'error')
        import traceback
        log(traceback.format_exc(), 'error')

        xbmcgui.Dialog().ok(
            'Little Fox',
            f'Playback error:\n{str(e)}\n\nCheck logs for details.'
        )
        xbmcplugin.setResolvedUrl(_handle, False, xbmcgui.ListItem())

def setup_player():
    """Copy Littlefox.json player file to the chosen addon's players folder."""
    home = xbmcvfs.translatePath('special://home')
    addon_path = addon.getAddonInfo('path')
    src = os.path.join(addon_path, 'Littlefox.json')

    target_defs = [
        {
            'label': 'TMDb Helper',
            'addon_id': 'plugin.video.themoviedb.helper',
            'players_dir': os.path.join(
                home, 'userdata', 'addon_data',
                'plugin.video.themoviedb.helper', 'players'
            ),
        },
        {
            'label': 'Little Racun',
            'addon_id': 'plugin.video.littleracun',
            'players_dir': os.path.join(
                home, 'addons', 'plugin.video.littleracun',
                'resources', 'players'
            ),
        },
    ]

    installed = []
    for t in target_defs:
        try:
            xbmcaddon.Addon(t['addon_id'])
            installed.append(t)
        except Exception:
            pass

    if not installed:
        xbmcgui.Dialog().ok(
            'Setup Player',
            'No supported addons found.\nInstall TMDb Helper first.'
        )
        return

    labels = [t['label'] for t in installed]
    selected = xbmcgui.Dialog().select('Install Little Fox Player For...', labels)
    if selected < 0:
        return

    target = installed[selected]
    players_dir = target['players_dir']
    dst = os.path.join(players_dir, 'Littlefox.json')

    xbmcvfs.mkdir(players_dir)
    success = xbmcvfs.copy(src, dst)

    if success:
        xbmcgui.Dialog().notification(
            'Little Fox',
            f'Player installed for {target["label"]}',
            xbmcgui.NOTIFICATION_INFO
        )
        log(f"setup_player: {src} -> {dst}")
    else:
        xbmcgui.Dialog().ok(
            'Setup Player - Error',
            f'Failed to copy player file.\nSrc: {src}\nDst: {dst}'
        )
        log(f"setup_player: copy failed {src} -> {dst}", 'error')


def router():
    """Route to appropriate function"""
    params = get_params()

    action = params.get('action', '')

    if action == 'play':
        play_episode(params)
    elif action == 'setup_player':
        setup_player()
    else:
        log(f"Unknown action: {action}", 'warning')

if __name__ == '__main__':
    log("=== LITTLE FOX STARTED (v1.0.1) ===")

    try:
        router()
    except Exception as e:
        log(f"Router error: {e}", 'error')
        import traceback
        log(traceback.format_exc(), 'error')

    log("=== LITTLE FOX FINISHED ===")
