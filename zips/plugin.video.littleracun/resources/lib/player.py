#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Player module - Handles playback via external players.
UPDATED: Removed ID translation, players access metadata via Kodi properties
"""

import os
import json
import re
import xbmc
import xbmcgui

from urllib.parse import quote_plus, urlparse, parse_qs, urlencode

from .utils import log, log_error, ADDON_PATH
from .settings import settings


class PlayerManager:
    """
    ID-Agnostic Player Manager

    Dynamically matches placeholders in player templates with metadata.
    """

    # Class variable to store last selected player
    _session_player = None

    def __init__(self):
        """Initialize the PlayerManager and load all player configurations"""
        self.players = []
        self.load_players()

    def load_players(self):
        """Load all player JSON files from resources/players/ directory"""
        players_dir = os.path.join(ADDON_PATH, 'resources', 'players')

        log(f"Loading players from: {players_dir}")

        if not os.path.exists(players_dir):
            log(f"Players directory does not exist: {players_dir}")
            try:
                os.makedirs(players_dir, exist_ok=True)
                log(f"Created players directory: {players_dir}")
            except Exception as e:
                log(f"Could not create players directory: {str(e)}")
            return

        try:
            files = os.listdir(players_dir)
        except Exception as e:
            log(f"Error listing players directory: {str(e)}")
            return

        json_files = [f for f in files if f.endswith('.json')]

        log(f"Found {len(json_files)} player configuration files")

        for json_file in json_files:
            player_path = os.path.join(players_dir, json_file)
            try:
                with open(player_path, 'r', encoding='utf-8') as f:
                    player_config = json.load(f)
                    self.players.append(player_config)
                    log(f"Loaded player: {player_config.get('name', 'Unknown')}")
            except Exception as e:
                log(f"Error loading player config {json_file}: {str(e)}")

        log(f"Total players loaded: {len(self.players)}")

    def get_available_players(self, content_type='movie'):
        """
        Get list of available players for the content type

        Args:
            content_type: 'movie' or 'episode'

        Returns:
            List of player configurations, sorted by priority
        """
        available = []

        for player in self.players:
            if content_type == 'movie' and 'play_movie' in player:
                available.append(player)
            elif content_type == 'episode' and 'play_episode' in player:
                available.append(player)

        # Sort by priority (higher first)
        available.sort(key=lambda p: p.get('priority', 0), reverse=True)

        return available

    def extract_placeholders(self, template):
        """Extract all placeholders from a template string"""
        pattern = r'\{(\w+)\}'
        matches = re.findall(pattern, template)
        return matches

    def build_url(self, template, metadata):
        """
        Build final URL by replacing placeholders with metadata values

        Args:
            template: URL template with placeholders
            metadata: Dictionary containing 'ids' dict and other fields

        Returns:
            Final URL with placeholders replaced
        """
        log(f"Building URL from template")
        log(f"Available IDs: {list(metadata.get('ids', {}).keys())}")
        log(f"Root metadata keys: {list(metadata.keys())}")

        # Parse the template URL
        parsed = urlparse(template)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Extract query parameters
        query_params = parse_qs(parsed.query, keep_blank_values=True)

        # Convert to single values
        query_dict = {k: v[0] if isinstance(v, list) else v for k, v in query_params.items()}

        # Get IDs dictionary and root metadata
        ids = metadata.get('ids', {})

        # Process each query parameter
        final_params = {}

        for param_key, param_value in query_dict.items():
            placeholders = self.extract_placeholders(param_value)

            if not placeholders:
                final_params[param_key] = param_value
                continue

            resolved_value = param_value
            all_resolved = True

            for placeholder in placeholders:
                # Try to find value in IDs first
                if placeholder in ids:
                    value = ids[placeholder]
                    log(f"Resolved {{{placeholder}}} from IDs: {value}")
                # Then try root metadata
                elif placeholder in metadata:
                    value = metadata[placeholder]
                    log(f"Resolved {{{placeholder}}} from root metadata: {value}")

                    # URL encode if it's a string
                    if isinstance(value, str):
                        value = quote_plus(value)
                else:
                    log(f"WARNING: {{{placeholder}}} not found in metadata")
                    all_resolved = False
                    break

                resolved_value = resolved_value.replace(f"{{{placeholder}}}", str(value))

            if all_resolved:
                final_params[param_key] = resolved_value
            else:
                log(f"Skipping parameter '{param_key}' due to missing placeholder")

        # Rebuild the URL
        if final_params:
            final_url = f"{base_url}?{urlencode(final_params)}"
        else:
            final_url = base_url

        log(f"Final URL: {final_url}")
        return final_url

    def play(self, metadata, content_type='movie', player_name=None, player_id=None):
        """
        Play content using a player

        Args:
            metadata: Dictionary with 'ids' and other fields
            content_type: 'movie' or 'episode'
            player_name: Specific player name to use
            player_id: Specific player ID to use

        Returns:
            True if playback started, False otherwise
        """
        log(f"Play request - Type: {content_type}, Player: {player_name}, ID: {player_id}")

        # Get available players
        available_players = self.get_available_players(content_type)

        if not available_players:
            log(f"No players available for content type: {content_type}")
            xbmcgui.Dialog().notification(
                "PlayerManager",
                f"No players configured for {content_type}",
                xbmcgui.NOTIFICATION_WARNING,
                3000
            )
            return False

        # Select player
        player = None

        if player_id:
            player = next((p for p in available_players if p.get('id') == player_id), None)
            if not player:
                log(f"Player with ID '{player_id}' not found")
                return False
        elif player_name:
            player = next((p for p in available_players if p['name'] == player_name), None)
            if not player:
                log(f"Player '{player_name}' not found")
                return False
        else:
            # Check session memory
            if PlayerManager._session_player:
                player = next((p for p in available_players if p.get('id') == PlayerManager._session_player.get('id')), None)
                if player:
                    log(f"Using remembered player: {player['name']}")

            # If no session player, prompt user
            if not player:
                if len(available_players) == 1:
                    player = available_players[0]
                else:
                    player = self._select_player_dialog(available_players)
                    if not player:
                        log("User cancelled player selection")
                        return False

                    # Remember choice
                    PlayerManager._session_player = player
                    log(f"Remembered player: {player['name']}")

        log(f"Selected player: {player['name']}")

        # Get template
        template_key = 'play_movie' if content_type == 'movie' else 'play_episode'
        template = player.get(template_key)

        if not template:
            log(f"Player '{player['name']}' missing '{template_key}' template")
            return False

        # Build URL
        try:
            final_url = self.build_url(template, metadata)
        except Exception as e:
            log_error("Error building URL", e)
            xbmcgui.Dialog().notification(
                "PlayerManager",
                f"Error building playback URL: {str(e)}",
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
            return False

        # Execute playback
        log(f"Executing: RunPlugin({final_url})")

        try:
            xbmc.executebuiltin(f'RunPlugin({final_url})')
            log("Playback command executed successfully")
            return True
        except Exception as e:
            log_error("Error executing playback", e)
            xbmcgui.Dialog().notification(
                "PlayerManager",
                f"Playback error: {str(e)}",
                xbmcgui.NOTIFICATION_ERROR,
                3000
            )
            return False

    def _select_player_dialog(self, players):
        """Show dialog for user to select a player"""
        player_names = [p['name'] for p in players]

        selected = xbmcgui.Dialog().select("Select Player", player_names)

        if selected < 0:
            return None

        return players[selected]

    @classmethod
    def clear_session_player(cls):
        """Clear the remembered player for this session"""
        cls._session_player = None
        log("Cleared session player memory")


def play_item(title, ids, item_type, year=None, season=None, episode=None, plot=None, poster=None, fanart=None, thumbnail=None, logo=None, rating=None):
    """
    Play an item using PlayerManager.

    Args:
        title: Content title
        ids: JSON string of IDs
        item_type: Type (movie/episode/series)
        year: Release year
        season: Season number (for episodes)
        episode: Episode number (for episodes)
        plot: Plot/overview text
        poster: Poster image URL
        fanart: Fanart/background image URL
        thumbnail: Thumbnail image URL
        logo: Logo/clearlogo image URL
        rating: Content rating (e.g., "8.1")
    """
    log(f"Playing: {title} (S{season}E{episode})" if season else f"Playing: {title}")

    try:
        # Parse IDs
        try:
            ids_dict = json.loads(ids)
            log(f"Total IDs available: {len(ids_dict)}")
            for id_type, id_value in ids_dict.items():
                log(f"  → {id_type}: {id_value}")
        except Exception as e:
            log_error("Error parsing IDs", e)
            ids_dict = {}

        # Build metadata with all available info
        metadata = {
            'title': title,
            'ids': ids_dict
        }

        # Add metadata fields for player URL templates
        if plot:
            metadata['plot'] = plot
        if poster:
            metadata['poster'] = poster
        if fanart:
            metadata['fanart'] = fanart
        if thumbnail:
            metadata['thumbnail'] = thumbnail
        if logo:
            metadata['logo'] = logo
        if rating:
            metadata['rating'] = rating

        if year:
            try:
                metadata['year'] = int(year)
            except:
                pass

        if season:
            metadata['season'] = int(season)
        if episode:
            metadata['episode'] = int(episode)

        # Determine content type
        if item_type in ['movie', 'anime_movie']:
            content_type = 'movie'
        elif item_type in ['series', 'anime', 'anime_series', 'tvshow']:
            content_type = 'episode'
        else:
            content_type = 'movie'

        # Get default player setting
        default_player_setting = settings.default_player
        remember_choice = settings.remember_player_choice

        player_map = {
            'Always Ask': None,
            'Stremio Bridge': 'stremio_bridge_v2',
            'Fen Light': 'fenlight',
            'Otaku': 'otaku',
            'Universal Bridge': 'universalbridge'
        }

        player_id = player_map.get(default_player_setting)

        # Create player manager
        player_manager = PlayerManager()

        # Clear session if not remembering
        if not remember_choice:
            PlayerManager.clear_session_player()

        # Play
        success = player_manager.play(
            metadata,
            content_type=content_type,
            player_id=player_id
        )

        if not success:
            log("Playback failed", level=xbmc.LOGWARNING)
            xbmcgui.Dialog().notification(
                "Little Racun",
                "Playback failed",
                icon=xbmcgui.NOTIFICATION_WARNING,
                time=3000
            )

    except Exception as e:
        log_error("Error in play_item", e)
        xbmcgui.Dialog().notification(
            "Little Racun",
            f"Error: {str(e)}",
            icon=xbmcgui.NOTIFICATION_ERROR,
            time=3000
        )
