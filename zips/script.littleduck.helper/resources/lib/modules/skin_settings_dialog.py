# -*- coding: utf-8 -*-
"""
skin_settings_dialog.py  —  skin.littleduck
Data-driven settings + widget-config dialogs.
Route: RunScript(script.littleduck.helper,mode=open_skin_settings)
"""
import os
import threading
import xbmc
import xbmcgui
import xbmcaddon

SKIN_ADDON = xbmcaddon.Addon('skin.littleduck')
SKIN_PATH  = SKIN_ADDON.getAddonInfo('path')
MEDIA_PATH = os.path.join(SKIN_PATH, 'media')


def _icon(rel):
    # Use special:// so Kodi's texture engine always resolves the path correctly,
    # regardless of the actual filesystem layout or how the dialog was launched.
    return f'special://skin/media/{rel}' if rel else ''


def _bool_on(setting_id, invert=False):
    state = bool(xbmc.getCondVisibility(f'Skin.HasSetting({setting_id})'))
    return 'true' if (not state if invert else state) else 'false'


def _str_val(setting_id, default='Not set'):
    v = xbmc.getInfoLabel(f'Skin.String({setting_id})')
    return v if v else default


def _display_val(s):
    """Return the value string shown as Label2 (subtitle row)."""
    t   = s.get('type', 'action')
    sid = s.get('setting_id', '')
    if t == 'bool':
        on = _bool_on(sid, s.get('invert', False)) == 'true'
        return 'Enabled' if on else 'Disabled'
    if t in ('select', 'number'):
        return _str_val(sid, s.get('default_value', '—'))
    if t == 'text' and sid:
        # Show current value if set, otherwise show subtitle hint
        return _str_val(sid, s.get('subtitle', ''))
    # apikey subtitle is always the static description line, not the key value
    # (key value is carried by key_val property for the badge)
    return s.get('subtitle', s.get('description', s.get('value', '')))


def _key_display(setting_id):
    """Return (key_set: str, key_val: str) for an API key skin string."""
    raw = xbmc.getInfoLabel(f'Skin.String({setting_id})')
    if not raw:
        return 'false', ''
    # show first 4 chars then mask the rest
    masked = raw[:4] + '●' * min(8, max(4, len(raw) - 4))
    return 'true', masked


# ── Categories ────────────────────────────────────────────────────────────────
CATEGORIES = [
    {'id': 'main_menu',  'label': 'Main Menu Items',    'icon': 'icons/settings/squares-four.png'},
    {'id': 'options',    'label': 'Options',             'icon': 'icons/settings/sliders.png'},
    {'id': 'search',     'label': 'Search',              'icon': 'icons/settings/magnifying-glass.png'},
    {'id': 'ratings',    'label': 'Ratings & Trailers',  'icon': 'icons/settings/star.png'},
    {'id': 'general',    'label': 'General',             'icon': 'icons/settings/gear-six.png'},
    {'id': 'artwork',    'label': 'Artwork',             'icon': 'icons/settings/image.png'},
    {'id': 'osd',        'label': 'On Screen Display',   'icon': 'icons/settings/monitor.png'},
    {'id': 'apikeys',    'label': 'API Keys',            'icon': 'icons/settings/stack.png'},
    {'id': 'appearance', 'label': 'Appearance',          'icon': 'icons/settings/rows.png'},
    {'id': 'powermenu',  'label': 'Power Menu',          'icon': 'icons/settings/sliders.png'},
    {'id': 'extra',      'label': 'Extra Info',          'icon': 'icons/settings/info.png'},
]

# Helper: read API key set status for conditional items
def _has_mdb():  return bool(xbmc.getInfoLabel('Skin.String(mdblist_api_key)'))
def _has_omdb(): return bool(xbmc.getInfoLabel('Skin.String(omdb_api_key)'))
def _has_any_rating_key(): return _has_mdb() or _has_omdb()


def _build_settings():
    has_mdb  = _has_mdb()
    has_omdb = _has_omdb()
    has_any  = has_mdb or has_omdb

    # Rating sources — shown only when at least one ratings API key is set
    rating_sources = [
        {'label': '  Metacritic',         'subtitle': 'Metacritic score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.MetacriticRating', 'invert': True,
         'description': 'Show the Metacritic critic score.'},
        {'label': '  Rotten Tomatoes (Critic)',   'subtitle': 'RT critic score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.RTCRating', 'invert': True,
         'description': 'Show the Rotten Tomatoes Tomatometer critic score.'},
        {'label': '  Rotten Tomatoes (Audience)', 'subtitle': 'RT audience score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.RTARating', 'invert': True,
         'description': 'Show the Rotten Tomatoes audience score.'},
        {'label': '  IMDb (Main)',         'subtitle': 'IMDb weighted average',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.IMDbRating', 'invert': True,
         'description': 'Show the main IMDb weighted average score.'},
        {'label': '  IMDb (Popular)',      'subtitle': 'IMDb popularity rank',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.IMDbPopularRating', 'invert': True,
         'description': 'Show the IMDb popularity ranking.'},
        {'label': '  TMDb',               'subtitle': 'TMDb community score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.TMDbRating', 'invert': True,
         'description': 'Show the TMDb community score.'},
    ] + ([
        {'label': '  IMDb vote count (OMDb)', 'subtitle': 'Requires OMDb key',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.OmdbVotes', 'invert': True,
         'description': 'Show the IMDb vote count sourced from OMDb.'},
    ] if has_omdb else []) + ([
        {'label': '  Trakt',              'subtitle': 'Trakt community score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.TraktRating', 'invert': True,
         'description': 'Show the Trakt community score.'},
        {'label': '  Letterboxd',         'subtitle': 'Letterboxd score',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.LetterboxdRating', 'invert': True,
         'description': 'Show the Letterboxd community score.'},
        {'label': '  Awards (wins)',       'subtitle': 'Award wins count',
         'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
         'setting_id': 'Disable.AwardWins', 'invert': True,
         'description': 'Show the number of award wins for each title.'},
    ] if has_mdb else [])

    return {
        'options': [
            {'label': 'Default power button behavior',
             'subtitle': 'Toggle suspend vs. shutdown',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'OneClickClose',
             'description': 'Toggle between suspend and shutdown for the power button action.'},
            {'label': 'Enable alternate InfoPanel',
             'subtitle': 'Alt layout on media pages',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'Enable.AlternateInfo',
             'description': 'Use the alternate InfoPanel layout on movie and show detail pages.'},
            {'label': 'Show raindrop background',
             'subtitle': 'Animated bg effect',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'HideRainDrops', 'invert': True,
             'description': 'Show the animated raindrop effect in the background.'},
            {'label': 'Enable focus animations',
             'subtitle': 'Smooth list focus transitions',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'NoFocusAnimations', 'invert': True,
             'description': 'Animate items as they receive focus in lists and menus.'},
            {'label': 'Enable icon silhouettes',
             'subtitle': 'Category widget icons',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'NoIconSilhouettes', 'invert': True,
             'description': 'Show icon silhouettes behind category widget items.'},
            {'label': 'Enable color studio logos',
             'subtitle': 'Requires coloured studios pack',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'Disable.ColorStudio', 'invert': True,
             'description': 'Display studio logos in full color. Installs resource pack if needed.'},
            {'label': 'Stacked widget load delay',
             'subtitle': 'Milliseconds  (1000 = 1 second)',
             'type': 'number', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'category_widget_delay',
             'description': 'How long to wait before loading the next stacked widget.'},
            {'label': 'Show countdown timer',
             'subtitle': 'During stacked widget delay',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'category_widget_display_delay',
             'description': 'Show a visual countdown while the stacked widget delay runs.'},
        ],
        'search': [
            {'label': 'Enable search results window',
             'subtitle': 'Dedicated results screen',
             'type': 'bool', 'icon': 'icons/settings/magnifying-glass.png', 'right_icon': '',
             'setting_id': 'NoSearchResultsWindow', 'invert': True,
             'description': 'Show a dedicated search results window when searching.'},
            {'label': 'Default search icon behavior',
             'subtitle': 'Home screen search button action',
             'type': 'bool', 'icon': 'icons/settings/magnifying-glass.png', 'right_icon': '',
             'setting_id': 'DefaultSearchWindowBehavior',
             'description': 'Toggle which window the home screen search icon opens by default.'},
            {'label': 'Show Movies in results',
             'subtitle': 'Include movie matches',
             'type': 'bool', 'icon': 'icons/settings/film-strip.png', 'right_icon': '',
             'setting_id': 'HideMovieResults', 'invert': True,
             'description': 'Include Movies in the search results window.'},
            {'label': 'Show TV Shows in results',
             'subtitle': 'Include TV show matches',
             'type': 'bool', 'icon': 'icons/settings/television.png', 'right_icon': '',
             'setting_id': 'HideTVShowResults', 'invert': True,
             'description': 'Include TV Shows in the search results window.'},
            {'label': 'Show Collections in results',
             'subtitle': 'Include movie collections',
             'type': 'bool', 'icon': 'icons/settings/squares-four.png', 'right_icon': '',
             'setting_id': 'HideCollectionsResults', 'invert': True,
             'description': 'Include movie collections in the search results window.'},
            {'label': 'Show Actors/Actresses in results',
             'subtitle': 'Include cast members',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'HidePeopleResults', 'invert': True,
             'description': 'Include cast and crew members in search results.'},
            {'label': 'Show Keywords in results',
             'subtitle': 'Include keyword matches',
             'type': 'bool', 'icon': 'icons/settings/magnifying-glass.png', 'right_icon': '',
             'setting_id': 'HideMovieKeywordResults', 'invert': True,
             'description': 'Include keyword-tagged items in the search results window.'},
            {'label': 'AI Recommendations (Gemini)',
             'subtitle': 'Requires Gemini API key',
             'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
             'setting_id': 'ShowGeminiResults',
             'description': 'Show AI-powered recommendations powered by Google Gemini.'},
            {'label': 'Clear search history',
             'subtitle': 'Remove all stored searches',
             'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
             'action': 'RunScript(script.littleduck.helper,mode=remove_all_spaths)',
             'description': 'Permanently delete all stored search history entries.',
             'danger': True},
        ],
        'ratings': [
            {'label': 'Enable one-click trailers',
             'subtitle': 'Long-press play or press T',
             'type': 'bool', 'icon': 'icons/settings/film-strip.png', 'right_icon': '',
             'setting_id': 'Enable.OneClickTrailers',
             'description': 'Long-press play/pause or press T on keyboard to instantly play a trailer.'},
        ] + ([
            {'label': 'Ratings for InfoPanel',
             'subtitle': 'Home screen info overlay',
             'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
             'setting_id': 'Disable.RatingsINF', 'invert': True,
             'description': 'Show rating scores in the home screen InfoPanel overlay.'},
            {'label': 'Ratings for widget labels',
             'subtitle': 'Score badge on items',
             'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
             'setting_id': 'Disable.WidgetLabelRatings', 'invert': True,
             'description': 'Display rating scores overlaid on widget item thumbnails.'},
        ] + rating_sources + [
            {'label': 'Clear ratings cache',
             'subtitle': 'Wipe MDbList + OMDb cache',
             'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
             'action': 'RunScript(script.littleduck.helper,mode=delete_all_ratings)',
             'description': 'Delete all locally cached rating data from MDbList and OMDb.',
             'danger': True},
        ] if has_any else []) + ([
            {'label': 'Clear MDbList API Key',
             'subtitle': 'Remove stored MDbList key',
             'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
             'action': 'Skin.SetString(mdblist_api_key,)',
             'description': 'Clear your saved MDbList API key from skin settings.',
             'danger': True},
        ] if has_mdb else []) + ([
            {'label': 'Clear OMDb API Key',
             'subtitle': 'Remove stored OMDb key',
             'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
             'action': 'Skin.SetString(omdb_api_key,)',
             'description': 'Clear your saved OMDb API key from skin settings.',
             'danger': True},
        ] if has_omdb else []),
        'general': [
            {'label': 'Enable slide animations',
             'subtitle': 'Screen transition slides',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'no_slide_animations', 'invert': True,
             'description': 'Slide elements during screen-to-screen transitions.'},
            {'label': 'Auto-scroll descriptions',
             'subtitle': 'Long plot text scrolls',
             'type': 'bool', 'icon': 'icons/settings/rows.png', 'right_icon': '',
             'setting_id': 'autoscroll',
             'description': 'Automatically scroll long plot or description text on media pages.'},
            {'label': 'Touch mode',
             'subtitle': 'Optimise for touchscreen',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'touchmode',
             'description': 'Remove scroll delays and optimise the UI for touchscreen input.'},
            {'label': 'Show weather info',
             'subtitle': 'Header weather display',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'show_weatherinfo',
             'description': 'Display weather information in the header area of the home screen.'},
            {'label': 'Show media flags',
             'subtitle': 'Codec / resolution badges',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'hide_mediaflags', 'invert': True,
             'description': 'Show resolution and codec flags on media items in lists.'},
            {'label': 'Rating display style',
             'subtitle': 'How ratings appear on items',
             'type': 'action', 'icon': 'icons/settings/star.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'Skin.SelectBool(Rating display,User rating|circle_userrating,Rating|circle_rating,None|circle_none)',
             'description': 'Choose whether to show user rating, critic rating, or no rating badge on items.'},
            {'label': 'Profile identification',
             'subtitle': 'Display name or avatar in header',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'Skin.SelectBool(Profile identification,Name|show_profilename,Avatar|show_profileavatar,None|show_none)',
             'description': 'Choose how the active profile is identified in the UI.'},
            {'label': 'Configure default views',
             'subtitle': 'Per content-type view style',
             'type': 'action', 'icon': 'icons/settings/layout.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'RunScript(script.skinvariables,action=buildviews,configure)',
             'description': 'Set the default view style (Poster, Landscape, Wall…) per content type.'},
        ],
        'artwork': [
            {'label': 'Show fanart',
             'subtitle': 'Background fanart images',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'no_fanart', 'invert': True,
             'description': 'Display fanart artwork as the background on media detail pages.'},
            {'label': 'Show music video poster',
             'subtitle': 'Poster art for music videos',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'show_musicvideoposter',
             'description': 'Display poster artwork for music video items.'},
            {'label': 'Default background style',
             'subtitle': 'Home screen background',
             'type': 'select', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'CustomBackground',
             'options': ['blueblur', 'motionblur', 'black', 'redblur'],
             'description': 'Choose the default background style shown on the home screen.'},
            {'label': 'Background brightness',
             'subtitle': 'How bright the bg appears',
             'type': 'select', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'DefaultBackgroundBrightness',
             'options': ['Highest', 'High', 'Medium', 'Low'],
             'description': 'Control how bright the background image appears on the home screen.'},
            {'label': 'Fanart brightness',
             'subtitle': 'Fanart overlay intensity',
             'type': 'select', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'DefaultFanartBrightness',
             'options': ['Highest', 'High', 'Medium', 'Low'],
             'description': 'Control how bright the fanart artwork appears on media pages.'},
            {'label': 'Choose skin background pack',
             'subtitle': 'Browse resource packs',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'RunScript(script.image.resource.select,property=HomeFanart&type=resource.images.skinbackgrounds)',
             'description': 'Browse and install a skin background resource pack from the repo.'},
            {'label': 'Choose weather fanart pack',
             'subtitle': 'Weather background images',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'RunScript(script.image.resource.select,property=WeatherFanart&type=resource.images.weatherfanart)',
             'description': 'Browse and install a weather fanart resource pack.'},
            {'label': 'Choose movie genre fanart',
             'subtitle': 'Genre background images',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'RunScript(script.image.resource.select,property=MovieGenreFanart&type=resource.images.moviegenrefanart)',
             'description': 'Browse and install a movie genre fanart resource pack.'},
        ],
        'osd': [
            {'label': 'Auto-close OSD',
             'subtitle': 'Hide OSD after timeout',
             'type': 'bool', 'icon': 'icons/settings/monitor.png', 'right_icon': '',
             'setting_id': 'OSDAutoClose',
             'description': 'Automatically hide the On Screen Display after a period of inactivity.'},
            {'label': 'OSD auto-close timeout',
             'subtitle': 'Seconds of inactivity',
             'type': 'number', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'OSDAutoCloseTime',
             'description': 'Number of seconds of inactivity before the OSD hides itself.'},
        ],
        'apikeys': [
            {'label': 'TMDb API Key',
             'subtitle': 'ID conversion & metadata',
             'type': 'apikey', 'icon': 'icons/settings/stack.png', 'right_icon': 'icons/pencil.png',
             'setting_id': 'tmdb_api_key',
             'action': 'RunScript(script.littleduck.helper,mode=set_tmdb_key)',
             'description': 'Set your TMDb API key for automatic ID conversion and enhanced metadata.'},
            {'label': 'TVDb API Key',
             'subtitle': 'TV show metadata',
             'type': 'apikey', 'icon': 'icons/settings/stack.png', 'right_icon': 'icons/pencil.png',
             'setting_id': 'tvdb_api_key',
             'action': 'RunScript(script.littleduck.helper,mode=set_tvdb_key)',
             'description': 'Set your TVDb API key for TV show metadata lookups.'},
            {'label': 'RPDB API Key',
             'subtitle': 'Rated poster art (Top Poster)',
             'type': 'apikey', 'icon': 'icons/settings/stack.png', 'right_icon': 'icons/pencil.png',
             'setting_id': 'rpdb_api_key',
             'action': 'RunScript(script.littleduck.helper,mode=set_rpdb_key)',
             'description': 'Set your RPDB (Top Poster) API key to unlock rated poster artwork.'},
            {'label': 'MDbList API Key',
             'subtitle': 'Multi-source ratings',
             'type': 'apikey', 'icon': 'icons/settings/stack.png', 'right_icon': 'icons/pencil.png',
             'setting_id': 'mdblist_api_key',
             'action': 'RunScript(script.littleduck.helper,mode=set_mdblist_key)',
             'description': 'Set your MDbList key to enable ratings from multiple sources.'},
            {'label': 'OMDb API Key',
             'subtitle': 'Ratings fallback + vote counts',
             'type': 'apikey', 'icon': 'icons/settings/stack.png', 'right_icon': 'icons/pencil.png',
             'setting_id': 'omdb_api_key',
             'action': 'RunScript(script.littleduck.helper,mode=set_omdb_key)',
             'description': 'Set your OMDb key as a ratings fallback and for IMDb vote counts.'},
        ],
        'appearance': [
            {'label': 'Default theme',
             'subtitle': 'Standard littleduck look',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'action': 'Skin.SetTheme()',
             'description': 'Switch to the default littleduck theme (dark, yellow accent).'},
            {'label': 'Curial theme',
             'subtitle': 'Curial variant',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'action': 'Skin.SetTheme(curial)',
             'description': 'Apply the Curial theme variant.'},
            {'label': 'Flat theme',
             'subtitle': 'Flat / minimal variant',
             'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'action': 'Skin.SetTheme(flat)',
             'description': 'Apply the Flat theme variant with a minimal aesthetic.'},
            {'label': '[DEBUG] Show view overlay',
             'subtitle': 'ViewMode / Content info on screen',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'debug_views',
             'description': 'Overlay ViewMode, Content, Plugin and Control visibility info on MyVideoNav.'},
        ],
        'powermenu': [
            {'label': 'Show Favourites',
             'subtitle': 'Quick-access favourites',
             'type': 'bool', 'icon': 'icons/settings/star.png', 'right_icon': '',
             'setting_id': 'PowerMenuHideFavourites', 'invert': True,
             'description': 'Include a Favourites shortcut in the power / quick menu.'},
            {'label': 'Show Add-ons',
             'subtitle': 'Add-ons shortcut',
             'type': 'bool', 'icon': 'icons/settings/squares-four.png', 'right_icon': '',
             'setting_id': 'PowerMenuHideAddons', 'invert': True,
             'description': 'Include an Add-ons shortcut in the power / quick menu.'},
            {'label': 'Show Reload Skin',
             'subtitle': 'Reload skin shortcut',
             'type': 'bool', 'icon': 'icons/settings/rows.png', 'right_icon': '',
             'setting_id': 'PowerMenuHideReloadSkin', 'invert': True,
             'description': 'Include a Reload Skin option in the power / quick menu.'},
            {'label': 'Show Quit / Exit',
             'subtitle': 'Exit Kodi shortcut',
             'type': 'bool', 'icon': 'icons/x-circle.png', 'right_icon': '',
             'setting_id': 'PowerMenuHideQuit', 'invert': True,
             'description': 'Include a Quit / Exit Kodi option in the power menu.'},
            {'label': 'Show Search',
             'subtitle': 'Search shortcut',
             'type': 'bool', 'icon': 'icons/settings/magnifying-glass.png', 'right_icon': '',
             'setting_id': 'PowerMenuSearch',
             'description': 'Include a Search shortcut in the power / quick menu.'},
            {'label': 'Show File Manager',
             'subtitle': 'File manager shortcut',
             'type': 'bool', 'icon': 'icons/folder-open.png', 'right_icon': '',
             'setting_id': 'PowerMenuFileManager',
             'description': 'Include a File Manager shortcut in the power / quick menu.'},
            {'label': 'Show Switch User',
             'subtitle': 'Profile switch shortcut',
             'type': 'bool', 'icon': 'icons/settings/image.png', 'right_icon': '',
             'setting_id': 'PowerMenuSwitchUser',
             'description': 'Include a Switch User / profile option in the power menu.'},
            {'label': 'Show Power Down',
             'subtitle': 'Power off shortcut',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'PowerMenuPowerDown',
             'description': 'Include a Power Down option in the power menu.'},
            {'label': 'Show Suspend',
             'subtitle': 'Suspend / sleep shortcut',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'PowerMenuSuspend',
             'description': 'Include a Suspend option in the power menu.'},
            {'label': 'Show Hibernate',
             'subtitle': 'Hibernate shortcut',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'PowerMenuHibernate',
             'description': 'Include a Hibernate option in the power menu.'},
            {'label': 'Show Reboot',
             'subtitle': 'Reboot shortcut',
             'type': 'bool', 'icon': 'icons/swap.png', 'right_icon': '',
             'setting_id': 'PowerMenuReboot',
             'description': 'Include a Reboot option in the power menu.'},
            {'label': 'Show Shutdown Timer',
             'subtitle': 'Timed shutdown shortcut',
             'type': 'bool', 'icon': 'icons/settings/sliders.png', 'right_icon': '',
             'setting_id': 'PowerMenuShutdownTimer',
             'description': 'Include a Shutdown Timer option in the power menu.'},
            {'label': 'Show Master Lock Mode',
             'subtitle': 'Lock Kodi shortcut',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'PowerMenuMasterMode',
             'description': 'Include a Master Lock mode toggle in the power menu.'},
            {'label': 'Show Idle Shutdown Inhibit',
             'subtitle': 'Prevent auto-shutdown',
             'type': 'bool', 'icon': 'icons/settings/info.png', 'right_icon': '',
             'setting_id': 'PowerMenuIdleShutdown',
             'description': 'Include an option to prevent Kodi from auto-shutting down when idle.'},
        ],
        'extra': [
            {'label': 'View Changelog',
             'subtitle': 'Version history & release notes',
             'type': 'action', 'icon': 'icons/settings/info.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'SetProperty(Changelog,True)|SetProperty(TextViewerHeader,[B]CHANGELOG[/B],Home)|ActivateWindow(1119)',
             'description': 'Open the skin changelog to read version history and release notes.'},
            {'label': 'View Setup Guide',
             'subtitle': 'Step-by-step install guide',
             'type': 'action', 'icon': 'icons/settings/info.png', 'right_icon': 'icons/settings/caret-right.png',
             'action': 'SetProperty(SetupGuide,True)|SetProperty(TextViewerHeader,[B]Setup Guide[/B],Home)|ActivateWindow(1118)',
             'description': 'Open the step-by-step setup guide for first-time configuration.'},
        ],
    }


# ── Main menu parent items ────────────────────────────────────────────────────
def _menu_children(entry_id, label, widget_cpath, main_menu_cpath=None):
    """Return editor options for one main-menu entry."""
    mm_cpath = main_menu_cpath or f'{entry_id}.main_menu'
    return [
        {'label': 'Set path',
         'subtitle': 'Choose content source',
         'type': 'path', 'id': f'{entry_id}.path',
         'icon': 'icons/folder-open.png', 'right_icon': 'icons/folder-open.png',
         'action': f'RunScript(script.littleduck.helper,mode=manage_main_menu_path&cpath_setting={mm_cpath})',
         'description': f'Choose the content source path for the {label} menu entry.'},
        {'label': 'Set label',
         'subtitle': 'Custom display name',
         'type': 'text', 'id': f'{entry_id}.setlabel',
         'icon': 'icons/tag.png', 'right_icon': 'icons/pencil.png',
         'setting_id': f'menu.{entry_id}.label',
         'description': f'Set a custom display name for the {label} menu entry.'},
        {'label': 'Set widgets',
         'subtitle': 'Configure home screen widgets',
         'type': 'action', 'id': f'{entry_id}.widget',
         'icon': 'icons/list-plus.png', 'right_icon': 'icons/settings/caret-right.png',
         'action': f'__open_widget_config__{widget_cpath}__{label}',
         'description': f'Configure the widgets displayed on the {label} home page.'},
        {'label': 'Set icon',
         'subtitle': 'Custom menu icon',
         'type': 'action', 'id': f'{entry_id}.icon',
         'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
         'action': f'RunScript(script.littleduck.helper,mode=pick_menu_icon&setting=menu.{entry_id}.icon)',
         'description': f'Pick a custom icon for the {label} menu entry.'},
        {'label': 'Reset main menu',
         'subtitle': f'Restore {label} default path, label & icon',
         'type': 'action', 'id': f'{entry_id}.reset_menu',
         'icon': 'icons/arrow-counter-clockwise.png', 'right_icon': 'icons/settings/trash.png',
         # Pipe-separated: remake the cpath, then wipe the custom icon and
         # custom label skin strings so nothing is left behind.
         'action': (
             f'RunScript(script.littleduck.helper,mode=remake_main_menus&cpath_setting={mm_cpath})'
             f'|Skin.ResetSetting(menu.{entry_id}.icon)'
             f'|Skin.ResetSetting(menu.{entry_id}.label)'
         ),
         'description': f'Restore the {label} menu to its default path, label and icon. Cannot be undone.',
         'danger': True},
        {'label': 'Reset widgets',
         'subtitle': f'Restore {label} default widgets',
         'type': 'action', 'id': f'{entry_id}.reset_widgets',
         'icon': 'icons/arrow-counter-clockwise.png', 'right_icon': 'icons/settings/trash.png',
         'action': f'RunScript(script.littleduck.helper,mode=remake_widgets&cpath_setting={widget_cpath})',
         'description': f'Restore all {label} widgets to their defaults. This clears all custom widget paths.',
         'danger': True},
    ]


def _toggle_child(setting_id, label, description):
    return {
        'label': 'Show in menu',
        'subtitle': label,
        'type': 'bool', 'icon': 'icons/settings/rows.png', 'right_icon': '',
        'setting_id': setting_id, 'invert': True,
        'description': description,
    }


def _get_main_menu_parents():
    """Build main menu parent list with dynamic labels from current skin strings."""
    def _cur_label(entry_id, fallback):
        v = xbmc.getInfoLabel(f'Skin.String(menu.{entry_id}.label)')
        return v if v else fallback

    def _icon_child(entry_id, label):
        return {
            'label': 'Set icon', 'subtitle': f'Custom {label} icon',
            'type': 'action', 'icon': 'icons/settings/image.png', 'right_icon': 'icons/settings/caret-right.png',
            'action': f'RunScript(script.littleduck.helper,mode=pick_menu_icon&setting=menu.{entry_id}.icon)',
            'description': f'Pick a custom icon for the {label} menu entry.',
        }

    home_lbl    = _cur_label('custom1',     'Home')
    movies_lbl  = _cur_label('movies',      'Movies')
    tvshows_lbl = _cur_label('tvshows',     'TV Shows')
    custom2_lbl = _cur_label('custom2',     'Custom 2')
    custom3_lbl = _cur_label('custom3',     'Custom 3')
    music_lbl   = _cur_label('music',       'Music')
    mvids_lbl   = _cur_label('musicvideos', 'Music Videos')
    livetv_lbl  = _cur_label('livetv',      'Live TV')
    radio_lbl   = _cur_label('radio',       'Radio')
    addons_lbl  = _cur_label('addons',      'Add-ons')
    pics_lbl    = _cur_label('pictures',    'Pictures')
    videos_lbl  = _cur_label('videos',      'Videos')
    games_lbl   = _cur_label('games',       'Games')
    fav_lbl     = _cur_label('fav',         'Favourites')
    weather_lbl = _cur_label('weather',     'Weather')

    games_enabled = xbmc.getCondVisibility('System.GetBool(gamesgeneral.enable)')

    entries = [
        {'id': 'home',    'label': home_lbl,    'type': 'parent',
         'icon': 'icons/house.png',      'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Path · widgets · icon',
         'description': 'Configure the Home main menu entry and its widgets.',
         'children': _menu_children('custom1', home_lbl, 'custom1.widget', 'custom1.main_menu')},

        {'id': 'movies',  'label': movies_lbl,  'type': 'parent',
         'icon': 'icons/settings/film-strip.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Path · widgets · icon · visibility',
         'description': 'Configure the Movies main menu entry.',
         'children': [
             _toggle_child('HomeMenuNoMoviesButton', 'Show Movies in menu',
                           'Toggle the Movies entry in the home menu.'),
         ] + _menu_children('movie', movies_lbl, 'movie.widget', 'movie.main_menu')},

        {'id': 'tvshows', 'label': tvshows_lbl, 'type': 'parent',
         'icon': 'icons/settings/television.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Path · widgets · icon · visibility',
         'description': 'Configure the TV Shows main menu entry.',
         'children': [
             _toggle_child('HomeMenuNoTVShowsButton', 'Show TV Shows in menu',
                           'Toggle the TV Shows entry in the home menu.'),
         ] + _menu_children('tvshow', tvshows_lbl, 'tvshow.widget', 'tvshow.main_menu')},

        {'id': 'custom2', 'label': custom2_lbl, 'type': 'parent',
         'icon': 'icons/settings/stack.png',      'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Path · label · widgets · icon · visibility',
         'description': f'Configure {custom2_lbl} — your custom menu entry.',
         'children': [
             _toggle_child('HomeMenuNoCustom2Button', f'Show {custom2_lbl} in menu',
                           f'Toggle the {custom2_lbl} entry in the home menu.'),
         ] + _menu_children('custom2', custom2_lbl, 'custom2.widget', 'custom2.main_menu')},

        {'id': 'custom3', 'label': custom3_lbl, 'type': 'parent',
         'icon': 'icons/settings/stack.png',      'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Path · label · widgets · icon · visibility',
         'description': f'Configure {custom3_lbl} — your custom menu entry.',
         'children': [
             _toggle_child('HomeMenuNoCustom3Button', f'Show {custom3_lbl} in menu',
                           f'Toggle the {custom3_lbl} entry in the home menu.'),
         ] + _menu_children('custom3', custom3_lbl, 'custom3.widget', 'custom3.main_menu')},

        {'id': 'music',   'label': music_lbl,   'type': 'parent',
         'icon': 'icons/settings/rows.png',       'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · label · icon',
         'description': 'Toggle Music visibility and set its display name and icon.',
         'children': [
             {'label': 'Show music categories widget',
              'subtitle': 'Home categories widget',
              'type': 'bool', 'icon': 'icons/settings/rows.png', 'right_icon': '',
              'setting_id': 'home_no_categories_widget', 'invert': True,
              'description': 'Show the music categories widget on the home screen.'},
             _toggle_child('HomeMenuNoMusicButton', 'Show Music in menu',
                           'Toggle the Music entry in the home menu.'),
             {'label': 'Set label', 'subtitle': 'Custom display name',
              'type': 'text', 'icon': 'icons/tag.png', 'right_icon': 'icons/pencil.png',
              'setting_id': 'menu.music.label',
              'description': 'Set a custom display name for the Music menu entry.'},
             _icon_child('music', music_lbl),
         ]},

        {'id': 'musicvideos', 'label': mvids_lbl, 'type': 'parent',
         'icon': 'icons/settings/film-strip.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Music Videos visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoMusicVideoButton', 'Show Music Videos in menu',
                           'Toggle the Music Videos entry in the home menu.'),
             _icon_child('musicvideos', mvids_lbl),
         ]},

        {'id': 'livetv',  'label': livetv_lbl,  'type': 'parent',
         'icon': 'icons/settings/television.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Live TV / PVR visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoTVButton', 'Show Live TV in menu',
                           'Toggle the Live TV / PVR entry in the home menu.'),
             _icon_child('livetv', livetv_lbl),
         ]},

        {'id': 'radio',   'label': radio_lbl,   'type': 'parent',
         'icon': 'icons/settings/rows.png',       'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Radio visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoRadioButton', 'Show Radio in menu',
                           'Toggle the Radio entry in the home menu.'),
             _icon_child('radio', radio_lbl),
         ]},

        {'id': 'addons',  'label': addons_lbl,  'type': 'parent',
         'icon': 'icons/settings/squares-four.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Add-ons visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoProgramsButton', 'Show Add-ons in menu',
                           'Toggle the Add-ons entry in the home menu.'),
             _icon_child('addons', addons_lbl),
         ]},

        {'id': 'pictures', 'label': pics_lbl,   'type': 'parent',
         'icon': 'icons/settings/image.png',      'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Pictures visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoPicturesButton', 'Show Pictures in menu',
                           'Toggle the Pictures entry in the home menu.'),
             _icon_child('pictures', pics_lbl),
         ]},

        {'id': 'videos',  'label': videos_lbl,  'type': 'parent',
         'icon': 'icons/settings/film-strip.png', 'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Videos visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoVideosButton', 'Show Videos in menu',
                           'Toggle the Videos entry in the home menu.'),
             _icon_child('videos', videos_lbl),
         ]},

        {'id': 'fav',     'label': fav_lbl,     'type': 'parent',
         'icon': 'icons/settings/star.png',       'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility',
         'description': 'Toggle Favourites visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoFavButton', 'Show Favourites in menu',
                           'Toggle the Favourites entry in the home menu.'),
         ]},

        {'id': 'weather', 'label': weather_lbl, 'type': 'parent',
         'icon': 'icons/settings/image.png',      'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Visibility · icon',
         'description': 'Toggle Weather visibility in the home menu.',
         'children': [
             _toggle_child('HomeMenuNoWeatherButton', 'Show Weather in menu',
                           'Toggle the Weather entry in the home menu.'),
             _icon_child('weather', weather_lbl),
         ]},

        {'id': 'setup',   'label': 'Quick Setup', 'type': 'parent',
         'icon': 'icons/settings/gear-six.png',   'right_icon': 'icons/settings/caret-right.png',
         'subtitle': 'Apply defaults · reset · rebuild',
         'description': 'Batch setup and reset options for the entire home screen.',
         'children': [
             {'label': 'Quick set up',
              'subtitle': 'Apply defaults, skip if configured',
              'type': 'action', 'icon': 'icons/settings/gear-six.png', 'right_icon': 'icons/settings/caret-right.png',
              'action': 'RunScript(script.littleduck.helper,mode=setup_default_home)',
              'description': 'Apply default menus and widgets. Skips entries that are already configured.'},
             {'label': 'Remake menus & widgets',
              'subtitle': 'Rebuild all content paths',
              'type': 'action', 'icon': 'icons/swap.png', 'right_icon': 'icons/settings/caret-right.png',
              'action': 'RunScript(script.littleduck.helper,mode=remake_all_cpaths)',
              'description': 'Rebuild all content paths for menus and widgets from the database.'},
             {'label': 'Reset home',
              'subtitle': 'Clear all paths, labels & icons',
              'type': 'action', 'icon': 'icons/arrow-counter-clockwise.png', 'right_icon': 'icons/settings/trash.png',
              # RunScript handles paths/labels/bools; the Skin.ResetSetting chain
              # clears every custom icon string that the icon-picker might have set.
              'action': (
                  'RunScript(script.littleduck.helper,mode=reset_home)'
                  '|Skin.ResetSetting(menu.custom1.icon)'
                  '|Skin.ResetSetting(menu.movie.icon)'
                  '|Skin.ResetSetting(menu.tvshow.icon)'
                  '|Skin.ResetSetting(menu.custom2.icon)'
                  '|Skin.ResetSetting(menu.custom3.icon)'
                  '|Skin.ResetSetting(menu.music.icon)'
                  '|Skin.ResetSetting(menu.musicvideos.icon)'
                  '|Skin.ResetSetting(menu.livetv.icon)'
                  '|Skin.ResetSetting(menu.radio.icon)'
                  '|Skin.ResetSetting(menu.addons.icon)'
                  '|Skin.ResetSetting(menu.pictures.icon)'
                  '|Skin.ResetSetting(menu.videos.icon)'
                  '|Skin.ResetSetting(menu.games.icon)'
                  '|Skin.ResetSetting(menu.weather.icon)'
              ),
              'description': 'Clears all widget paths, menu paths, custom labels and icons. Cannot be undone.',
              'danger': True},
         ]},
    ]

    # Games — only include when the Games system feature is enabled
    if games_enabled:
        games_entry = {
            'id': 'games', 'label': games_lbl, 'type': 'parent',
            'icon': 'icons/settings/squares-four.png', 'right_icon': 'icons/settings/caret-right.png',
            'subtitle': 'Visibility · icon',
            'description': 'Toggle Games visibility in the home menu (requires Games feature enabled).',
            'children': [
                _toggle_child('HomeMenuNoGamesButton', 'Show Games in menu',
                              'Toggle the Games entry in the home menu.'),
                _icon_child('games', games_lbl),
            ],
        }
        # Insert before Quick Setup (last entry)
        entries.insert(-1, games_entry)

    return entries


def _execute_setting(s):
    t      = s.get('type', 'action')
    sid    = s.get('setting_id', '')
    action = s.get('action', '')

    if t == 'bool':
        xbmc.executebuiltin(f'Skin.ToggleSetting({sid})')
        # executebuiltin is async — wait for the skin-setting engine to commit
        # before _render_items() reads it back, otherwise the toggle looks stale.
        xbmc.sleep(120)

    elif t == 'number':
        xbmc.executebuiltin(f'Skin.SetNumeric({sid})')
        xbmc.sleep(120)

    elif t == 'text':
        cur = xbmc.getInfoLabel(f'Skin.String({sid})')
        res = xbmcgui.Dialog().input(s['label'], defaultt=cur)
        if res is not None:
            xbmc.executebuiltin(f'Skin.SetString({sid},{res})')
            xbmc.sleep(120)

    elif t == 'select':
        options = s.get('options', [])
        cur = xbmc.getInfoLabel(f'Skin.String({sid})')
        try:
            pre = options.index(cur)
        except ValueError:
            pre = 0
        idx = xbmcgui.Dialog().select(s['label'], options, preselect=pre)
        if idx >= 0:
            xbmc.executebuiltin(f'Skin.SetString({sid},{options[idx]})')
            xbmc.sleep(120)

    elif t == 'apikey':
        # apikey acts like action — runs the helper script to set the key
        for cmd in action.split('|'):
            cmd = cmd.strip()
            if cmd:
                xbmc.executebuiltin(cmd)

    elif t in ('path', 'action'):
        if action.startswith('__open_widget_config__'):
            # format: __open_widget_config__<cpath>__<label>
            parts = action.split('__')
            cpath = parts[2] if len(parts) > 2 else 'custom1.widget'
            label = parts[3] if len(parts) > 3 else ''
            _open_widget_config(cpath, label)
        else:
            for cmd in action.split('|'):
                cmd = cmd.strip()
                if cmd:
                    xbmc.executebuiltin(cmd)


def _open_widget_config(cpath_setting, entry_label):
    dialog = WidgetConfigDialog('DialogWidgetConfig.xml', SKIN_PATH, 'Default', '1080i')
    dialog.cpath_setting = cpath_setting
    dialog.entry_label   = entry_label
    dialog.doModal()
    del dialog


# ════════════════════════════════════════════════════════════════════════════
#  Widget Config Dialog
# ════════════════════════════════════════════════════════════════════════════
class WidgetConfigDialog(xbmcgui.WindowXMLDialog):

    def onInit(self):
        self._cpath       = getattr(self, 'cpath_setting', 'custom1.widget')
        self._label       = getattr(self, 'entry_label',   'Home')
        self._active      = 0
        self._pending_new = False   # True when user clicked "Add new widget"
        self._slots       = self._load_slots()

        try:
            self.getControl(9120).setLabel(
                f'Skin Settings  ›  {self._label}  ›  Configure Widgets'
            )
            used  = len(self._slots)
            total = 10
            self.getControl(9121).setLabel(f'{used} / {total} Widgets Used')
        except Exception:
            pass

        self._populate_slots()
        self._populate_editor(self._active)
        self.setFocusId(9101)

    def _load_slots(self):
        """Read widget slots from CPaths database."""
        try:
            from modules.cpath_maker import CPaths
            cp = CPaths(self._cpath)
            data = cp.fetch_current_cpaths()
            slots = []
            for idx in sorted(data.keys()):
                w = data[idx]
                slots.append({
                    'label':  w.get('cpath_header', f'Widget {idx}'),
                    'source': w.get('cpath_label',  ''),
                    'path':   w.get('cpath_path',   ''),
                    'type':   w.get('cpath_type',   ''),
                    'setting': w.get('cpath_setting', ''),
                })
            return slots
        except Exception as e:
            xbmc.log(f'###littleduck WidgetConfigDialog._load_slots: {e}', xbmc.LOGERROR)
            return []

    def _widget_settings(self, slot_idx):
        # Pending new slot: show full 4-item template (all options always visible)
        if self._pending_new and slot_idx >= len(self._slots):
            next_setting = f'{self._cpath}.{len(self._slots) + 1}'
            return [
                {'label': 'Choose widget path',
                 'subtitle': 'Not configured yet — select a source',
                 'type': 'path', 'icon': 'icons/folder-open.png', 'right_icon': 'icons/pencil.png',
                 'new_slot': next_setting,
                 'description': 'Select the content source. Browse your library or an add-on path.'},
                {'label': 'Widget label',
                 'subtitle': '(set a path first)',
                 'type': 'text', 'icon': 'icons/pencil.png', 'right_icon': 'icons/pencil.png',
                 'new_slot': next_setting,
                 'description': 'The display name shown above this widget on the home screen.'},
                {'label': 'Layout style',
                 'subtitle': 'BigLandscape',
                 'type': 'select', 'icon': 'icons/settings/layout.png', 'right_icon': '',
                 'new_slot': next_setting,
                 'description': "Choose how this widget's items are displayed visually."},
                {'label': 'Clear widget',
                 'subtitle': 'Discard this new widget slot',
                 'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
                 'new_slot': next_setting,
                 'description': 'Discard this new widget slot without saving.',
                 'danger': True},
            ]
        if slot_idx >= len(self._slots):
            return []
        w = self._slots[slot_idx]
        return [
            {'label': 'Choose widget path',
             'subtitle': w.get('path', 'Not set'),
             'type': 'path', 'icon': 'icons/folder-open.png', 'right_icon': 'icons/pencil.png',
             'description': 'Select the content source. Browse your library or an add-on path.'},
            {'label': 'Widget label',
             'subtitle': w.get('label', ''),
             'type': 'text', 'icon': 'icons/pencil.png', 'right_icon': 'icons/pencil.png',
             'description': 'The display name shown above this widget on the home screen.'},
            {'label': 'Layout style',
             'subtitle': w.get('type', 'BigLandscape'),
             'type': 'select', 'icon': 'icons/settings/layout.png', 'right_icon': '',
             'description': 'Choose how this widget\'s items are displayed visually.'},
            {'label': 'Clear widget',
             'subtitle': f'Remove this widget from {self._label}',
             'type': 'action', 'icon': 'icons/settings/trash.png', 'right_icon': 'icons/settings/trash.png',
             'description': 'Removes this widget slot and its configuration permanently.',
             'danger': True},
        ]

    def _populate_slots(self):
        ctrl = self.getControl(9100)
        ctrl.reset()
        for idx, slot in enumerate(self._slots):
            item = xbmcgui.ListItem(slot['label'])
            item.setLabel2(slot['source'])
            item.setArt({'icon': _icon('icons/settings/layout.png')})
            item.setProperty('is_active', 'true' if idx == self._active else 'false')
            ctrl.addItem(item)
        # If user clicked "Add new widget", show a pending placeholder slot
        if self._pending_new:
            pending_idx = len(self._slots)
            pend = xbmcgui.ListItem('New widget')
            pend.setLabel2('Choose a path to configure')
            pend.setArt({'icon': _icon('icons/plus-circle.png')})
            pend.setProperty('is_active', 'true' if pending_idx == self._active else 'false')
            pend.setProperty('type', 'pending')
            ctrl.addItem(pend)
        # Always show "Add new widget" at bottom (unless pending)
        if not self._pending_new:
            add = xbmcgui.ListItem('Add new widget')
            add.setLabel2('Tap to add')
            add.setArt({'icon': _icon('icons/plus-circle.png')})
            add.setProperty('is_active', 'false')
            add.setProperty('type', 'add')
            ctrl.addItem(add)

    def _populate_editor(self, slot_idx):
        ctrl = self.getControl(9101)
        ctrl.reset()
        settings = self._widget_settings(slot_idx)
        for s in settings:
            item = xbmcgui.ListItem(s['label'])
            item.setLabel2(s.get('subtitle', ''))
            item.setArt({
                'icon':       _icon(s.get('icon', '')),
                'right_icon': _icon(s.get('right_icon', '')),
            })
            item.setProperty('type',        s.get('type', 'action'))
            item.setProperty('description', s.get('description', ''))
            item.setProperty('danger',      'true' if s.get('danger') else 'false')
            ctrl.addItem(item)
        if settings:
            self._update_info(settings[0]['label'], settings[0]['description'])

    def _update_info(self, title, desc):
        try:
            self.getControl(9110).setLabel(title)
            self.getControl(9111).setLabel(desc)
        except Exception:
            pass

    def _handle_editor_select(self, pos):
        settings = self._widget_settings(self._active)
        if pos >= len(settings):
            return
        s = settings[pos]
        t      = s.get('type', 'action')
        is_new = self._pending_new and self._active >= len(self._slots)
        cpath_setting = '' if is_new else (
            self._slots[self._active]['setting'] if self._active < len(self._slots) else ''
        )

        if t == 'path':
            # ── Bug 1 fix: never let make_widget_xml() fire ReloadSkin() while
            # this dialog is open.  Pass a threading.Event so it writes the XML
            # but skips the reload thread.  A deferred reload fires when the
            # outermost SkinSettingsDialog closes.
            new_slot = s.get('new_slot', '')
            target   = new_slot if new_slot else cpath_setting
            if not target:
                return
            try:
                from modules.cpath_maker import CPaths
                cp = CPaths(self._cpath)
                result = cp.path_browser()  # only browse — no chaining
                if not result:
                    return
                cpath_path = result.get('file', '')
                if not cpath_path:
                    return
                if is_new:
                    default_header = cp.clean_header(result.get('label', '') or 'New Widget')
                    cp.add_cpath_to_database(
                        target, cpath_path, default_header,
                        'WidgetListBigLandscape',
                        f'{default_header} | BigLandscape'
                    )
                    cp._sync_spotlight_type(target, 'WidgetListBigLandscape')
                else:
                    existing      = self._slots[self._active]
                    exist_header  = existing.get('label', cp.clean_header(result.get('label', '') or 'Widget'))
                    exist_type    = existing.get('type', 'WidgetListBigLandscape')
                    exist_display = cp.get_widget_type(exist_type) or 'BigLandscape'
                    cp.update_cpath_in_database(
                        target, cpath_path, exist_header,
                        exist_type, f'{exist_header} | {exist_display}'
                    )
                    cp._sync_spotlight_type(target, exist_type)
                # Write XML without triggering a skin reload
                _no_reload = threading.Event()
                cp.make_widget_xml(cp.fetch_current_cpaths(), event=_no_reload)
                # Signal that a reload is needed once all settings dialogs close
                xbmcgui.Window(10000).setProperty('littleduck.needs_skin_reload', 'true')
                self._pending_new = False
                self._slots  = self._load_slots()
                self._active = len(self._slots) - 1
                self._populate_slots()
                self._populate_editor(self._active)
                self.getControl(9100).selectItem(self._active)
            except Exception as e:
                xbmc.log(f'###littleduck path browser error: {e}', xbmc.LOGERROR)
            return

        elif t == 'text':
            # ── Bug 2 fix: the widget label is stored in the CPaths SQLite
            # database, not as a Skin.String.  Write it there and refresh the UI.
            if is_new:
                return  # set path first
            cur = self._slots[self._active].get('label', '')
            res = xbmcgui.Dialog().input(s['label'], defaultt=cur)
            if res:
                try:
                    from modules.cpath_maker import CPaths
                    cp = CPaths(self._cpath)
                    existing     = self._slots[self._active]
                    exist_type   = existing.get('type', 'WidgetListBigLandscape')
                    display_type = cp.get_widget_type(exist_type) or 'BigLandscape'
                    cp.update_cpath_in_database(
                        cpath_setting,
                        existing.get('path', ''),
                        res,
                        exist_type,
                        f'{res} | {display_type}'
                    )
                    _no_reload = threading.Event()
                    cp.make_widget_xml(cp.fetch_current_cpaths(), event=_no_reload)
                    xbmcgui.Window(10000).setProperty('littleduck.needs_skin_reload', 'true')
                    self._slots = self._load_slots()
                    self._populate_slots()
                    self._populate_editor(self._active)
                except Exception as e:
                    xbmc.log(f'###littleduck label save error: {e}', xbmc.LOGERROR)

        elif t == 'select':
            # ── Bug 5 fix: use the CPaths DB (not Skin.SetString), fix the
            # display-name ↔ internal-name mapping, and refresh the UI.
            if is_new:
                return  # set path first
            try:
                from modules.cpath_maker import CPaths, widget_types
                cp = CPaths(self._cpath)
                existing = self._slots[self._active]
                exist_internal = existing.get('type', 'WidgetListBigLandscape')
                display_names  = [wt[0] for wt in widget_types]
                internal_names = [wt[1] for wt in widget_types]
                try:
                    pre = internal_names.index(exist_internal)
                except ValueError:
                    pre = 1
                idx = xbmcgui.Dialog().select('Layout style', display_names, preselect=pre)
                if idx >= 0:
                    new_internal = internal_names[idx]
                    new_display  = display_names[idx]
                    exist_header = existing.get('label', 'Widget')
                    cp.update_cpath_in_database(
                        cpath_setting,
                        existing.get('path', ''),
                        exist_header,
                        new_internal,
                        f'{exist_header} | {new_display}'
                    )
                    cp._sync_spotlight_type(cpath_setting, new_internal)
                    _no_reload = threading.Event()
                    cp.make_widget_xml(cp.fetch_current_cpaths(), event=_no_reload)
                    xbmcgui.Window(10000).setProperty('littleduck.needs_skin_reload', 'true')
                    self._slots = self._load_slots()
                    self._populate_slots()
                    self._populate_editor(self._active)
            except Exception as e:
                xbmc.log(f'###littleduck layout select error: {e}', xbmc.LOGERROR)

        elif t == 'action' and s.get('danger'):
            if is_new:
                # discard pending new slot — no confirmation needed
                self._pending_new = False
                self._active = max(0, len(self._slots) - 1)
                self._populate_slots()
                self._populate_editor(self._active)
                return
            if xbmcgui.Dialog().yesno('Clear widget', s.get('description', '')):
                try:
                    from modules.cpath_maker import CPaths
                    cp = CPaths(self._cpath)
                    # ── Bug 4 fix: correct method name is remove_cpath_from_database
                    cp.remove_cpath_from_database(cpath_setting)
                    _no_reload = threading.Event()
                    cp.make_widget_xml(cp.fetch_current_cpaths(), event=_no_reload)
                    xbmcgui.Window(10000).setProperty('littleduck.needs_skin_reload', 'true')
                except Exception as e:
                    xbmc.log(f'###littleduck clear widget error: {e}', xbmc.LOGERROR)
                self._slots  = self._load_slots()
                self._active = 0
                self._populate_slots()
                self._populate_editor(self._active)

    def onAction(self, action):
        aid     = action.getId()
        focused = self.getFocusId()

        if aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.close()
            return

        if focused == 9100 and aid in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
            try:
                pos = self.getControl(9100).getSelectedPosition()
                if pos != self._active and pos < len(self._slots):
                    self._active = pos
                    self._populate_slots()
                    self._populate_editor(pos)
                    self.getControl(9100).selectItem(pos)
            except Exception:
                pass

        if focused == 9101 and aid in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
            try:
                item = self.getControl(9101).getSelectedItem()
                if item:
                    self._update_info(item.getLabel(), item.getProperty('description'))
            except Exception:
                pass

        if focused == 9101 and aid == xbmcgui.ACTION_SELECT_ITEM:
            try:
                pos = self.getControl(9101).getSelectedPosition()
                self._handle_editor_select(pos)
            except Exception as e:
                xbmc.log(f'###littleduck WidgetConfigDialog select error: {e}', xbmc.LOGERROR)

        if focused == 9100 and aid == xbmcgui.ACTION_SELECT_ITEM:
            try:
                self._handle_slot_click(self.getControl(9100).getSelectedPosition())
            except Exception as e:
                xbmc.log(f'###littleduck slot select error: {e}', xbmc.LOGERROR)

    def _handle_slot_click(self, pos):
        if not self._pending_new and pos >= len(self._slots):
            # "Add new widget" — prepare pending slot, move focus to editor
            self._pending_new = True
            self._active      = len(self._slots)
            self._populate_slots()
            self._populate_editor(self._active)
            self.getControl(9100).selectItem(self._active)
            self.setFocusId(9101)
        elif self._pending_new and pos == len(self._slots):
            # clicked pending slot again — keep editor focus
            self.setFocusId(9101)
        elif pos < len(self._slots):
            # existing slot — switch active
            if pos != self._active:
                self._active = pos
                self._populate_slots()
                self._populate_editor(pos)
                self.getControl(9100).selectItem(pos)

    def onClick(self, control_id):
        """Handles mouse clicks (and Enter) on list controls."""
        if control_id == 9130:
            # Touch/tablet back button — close without triggering deferred reload here;
            # SkinSettingsDialog will handle the reload when it eventually closes.
            self.close()
            return
        if control_id == 9101:
            try:
                pos = self.getControl(9101).getSelectedPosition()
                self._handle_editor_select(pos)
            except Exception as e:
                xbmc.log(f'###littleduck WidgetConfigDialog onClick 9101: {e}', xbmc.LOGERROR)
        elif control_id == 9100:
            try:
                self._handle_slot_click(self.getControl(9100).getSelectedPosition())
            except Exception as e:
                xbmc.log(f'###littleduck WidgetConfigDialog onClick 9100: {e}', xbmc.LOGERROR)

    def onFocus(self, control_id):
        if control_id == 9101:
            try:
                item = self.getControl(9101).getSelectedItem()
                if item:
                    self._update_info(item.getLabel(), item.getProperty('description'))
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════════════════
#  Main Settings Dialog
# ════════════════════════════════════════════════════════════════════════════
class SkinSettingsDialog(xbmcgui.WindowXMLDialog):

    def onInit(self):
        self._settings       = _build_settings()
        self._current_cat_id = CATEGORIES[0]['id']
        self._nav_stack      = []
        self._current_items  = []
        self._populate_sidebar()
        self._load_category(self._current_cat_id)
        self.setFocusId(9001)

    def _populate_sidebar(self):
        ctrl = self.getControl(9000)
        ctrl.reset()
        for cat in CATEGORIES:
            item = xbmcgui.ListItem(cat['label'])
            item.setArt({'icon': _icon(cat['icon'])})
            ctrl.addItem(item)

    def _load_category(self, cat_id):
        self._nav_stack      = []
        self._current_cat_id = cat_id
        if cat_id == 'main_menu':
            items, crumb = _get_main_menu_parents(), 'Main Menu Items'
        else:
            label = next((c['label'] for c in CATEGORIES if c['id'] == cat_id), '')
            items = self._settings.get(cat_id, [
                {'label': 'No settings yet', 'subtitle': '',
                 'type': 'action', 'icon': '', 'right_icon': '',
                 'description': 'No configurable settings in this category yet.'}
            ])
            crumb = label
        self._render_items(items, crumb)

    def _drill_into(self, parent_item):
        self._nav_stack.append({
            'items':      self._current_items,
            'breadcrumb': self._get_breadcrumb(),
        })
        crumb = self._get_breadcrumb() + '  ›  ' + parent_item['label']
        self._render_items(parent_item.get('children', []), crumb)

    def _go_back(self):
        if not self._nav_stack:
            return False
        frame = self._nav_stack.pop()
        self._render_items(frame['items'], frame['breadcrumb'])
        return True

    def _render_items(self, items, breadcrumb):
        self._current_items = items
        self._set_breadcrumb(breadcrumb)
        ctrl = self.getControl(9001)
        ctrl.reset()
        for s in items:
            item = xbmcgui.ListItem(s['label'])
            item.setLabel2(_display_val(s))
            item.setArt({
                'icon':       _icon(s.get('icon', '')),
                'right_icon': _icon(s.get('right_icon', '')),
            })
            item.setProperty('type',        s.get('type', 'action'))
            item.setProperty('id',          s.get('id', s.get('setting_id', '')))
            item.setProperty('description', s.get('description', ''))
            item.setProperty('danger',      'true' if s.get('danger') else 'false')
            if s.get('type') == 'bool':
                item.setProperty('bool_on', _bool_on(s.get('setting_id', ''), s.get('invert', False)))
            if s.get('type') == 'apikey':
                key_set, key_val = _key_display(s.get('setting_id', ''))
                item.setProperty('key_set', key_set)
                item.setProperty('key_val', key_val)
            ctrl.addItem(item)
        if items:
            self._update_info(items[0]['label'], items[0].get('description', ''))
        self.getControl(9021).setVisible(len(self._nav_stack) > 0)

    def _set_breadcrumb(self, text):
        try:
            self.getControl(9020).setLabel(text)
        except Exception:
            pass

    def _get_breadcrumb(self):
        try:
            return self.getControl(9020).getLabel()
        except Exception:
            return ''

    def _update_info(self, title, desc):
        try:
            self.getControl(9010).setLabel(title)
            self.getControl(9011).setLabel(desc)
        except Exception:
            pass

    def onAction(self, action):
        aid     = action.getId()
        focused = self.getFocusId()

        if aid in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            if not self._go_back():
                # If widget changes were made, trigger a deferred skin reload
                # AFTER the dialog fully closes (ReloadSkin while a dialog is
                # open kills all dialogs instantly).
                _hw = xbmcgui.Window(10000)
                needs_reload = _hw.getProperty('littleduck.needs_skin_reload') == 'true'
                if needs_reload:
                    _hw.clearProperty('littleduck.needs_skin_reload')
                self.close()
                if needs_reload:
                    def _deferred_reload():
                        xbmc.sleep(400)
                        xbmc.executebuiltin('ReloadSkin()')
                    threading.Thread(target=_deferred_reload, daemon=True).start()
            return

        if focused == 9001 and aid == xbmcgui.ACTION_SELECT_ITEM:
            try:
                pos  = self.getControl(9001).getSelectedPosition()
                data = self._current_items[pos]
                if data.get('type') == 'parent':
                    self._drill_into(data)
                else:
                    _execute_setting(data)
                    self._render_items(self._current_items, self._get_breadcrumb())
                    self.getControl(9001).selectItem(pos)
            except Exception as e:
                xbmc.log(f'###littleduck SkinSettingsDialog select error: {e}', xbmc.LOGERROR)
            return

        if focused == 9001 and aid in (
            xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN,
            xbmcgui.ACTION_PAGE_UP, xbmcgui.ACTION_PAGE_DOWN,
        ):
            try:
                item = self.getControl(9001).getSelectedItem()
                if item:
                    self._update_info(item.getLabel(), item.getProperty('description'))
            except Exception:
                pass

        if focused == 9000 and aid in (xbmcgui.ACTION_MOVE_UP, xbmcgui.ACTION_MOVE_DOWN):
            try:
                pos = self.getControl(9000).getSelectedPosition()
                if 0 <= pos < len(CATEGORIES):
                    cat = CATEGORIES[pos]
                    if cat['id'] != self._current_cat_id:
                        self._load_category(cat['id'])
            except Exception:
                pass

    def onClick(self, control_id):
        """Handles mouse clicks (and Enter) on list controls."""
        if control_id == 9030:
            # Touch/tablet back button — same logic as Back key
            if not self._go_back():
                _hw = xbmcgui.Window(10000)
                needs_reload = _hw.getProperty('littleduck.needs_skin_reload') == 'true'
                if needs_reload:
                    _hw.clearProperty('littleduck.needs_skin_reload')
                self.close()
                if needs_reload:
                    def _deferred_reload():
                        xbmc.sleep(400)
                        xbmc.executebuiltin('ReloadSkin()')
                    threading.Thread(target=_deferred_reload, daemon=True).start()
            return
        if control_id == 9001:
            try:
                pos  = self.getControl(9001).getSelectedPosition()
                data = self._current_items[pos]
                if data.get('type') == 'parent':
                    self._drill_into(data)
                else:
                    _execute_setting(data)
                    self._render_items(self._current_items, self._get_breadcrumb())
                    self.getControl(9001).selectItem(pos)
            except Exception as e:
                xbmc.log(f'###littleduck SkinSettingsDialog onClick: {e}', xbmc.LOGERROR)
        elif control_id == 9000:
            try:
                pos = self.getControl(9000).getSelectedPosition()
                if 0 <= pos < len(CATEGORIES):
                    cat = CATEGORIES[pos]
                    if cat['id'] != self._current_cat_id:
                        self._load_category(cat['id'])
            except Exception as e:
                xbmc.log(f'###littleduck SkinSettingsDialog onClick sidebar: {e}', xbmc.LOGERROR)

    def onFocus(self, control_id):
        if control_id == 9001:
            try:
                item = self.getControl(9001).getSelectedItem()
                if item:
                    self._update_info(item.getLabel(), item.getProperty('description'))
            except Exception:
                pass


def open_settings():
    dialog = SkinSettingsDialog('DialogSkinSettings.xml', SKIN_PATH, 'Default', '1080i')
    dialog.doModal()
    del dialog
