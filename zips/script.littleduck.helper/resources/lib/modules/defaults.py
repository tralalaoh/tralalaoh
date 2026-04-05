# -*- coding: utf-8 -*-
import xbmc
import xbmcgui

TMDB = "plugin://plugin.video.themoviedb.helper/?"
RABITEWATCH = "plugin://plugin.video.rabitewatch/"

# DEFAULT_WIDGETS: keyed by cpath_setting
# Values: (cpath_path, cpath_header, cpath_type, cpath_label)
DEFAULT_WIDGETS = {
    # Home (custom1) — fast-first ordering: local DB → cached TMDb → Trakt
    "custom1.widget.1": (
        RABITEWATCH + "?action=continue_watching",
        "Continue Watching",
        "WidgetListBigLandscape",
        "Continue Watching | BigLandscape",
    ),
    "custom1.widget.2": (
        TMDB + "info=trending_week&tmdb_type=movie",
        "Trending Movies",
        "WidgetListBigLandscape",
        "Trending Movies | BigLandscape",
    ),
    "custom1.widget.3": (
        TMDB + "info=trending_week&tmdb_type=tv",
        "Trending TV Shows",
        "WidgetListBigLandscape",
        "Trending TV Shows | BigLandscape",
    ),
    "custom1.widget.4": (
        TMDB + "info=trakt_trending&genres=anime&tmdb_type=movie",
        "Trending Anime Movies",
        "WidgetListBigLandscape",
        "Trending Anime Movies | BigLandscape",
    ),
    "custom1.widget.5": (
        TMDB + "info=trakt_trending&genres=anime&tmdb_type=tv",
        "Trending Anime Series",
        "WidgetListBigLandscape",
        "Trending Anime Series | BigLandscape",
    ),
    # Films (movie) — Trending first (BigLandscape), then the rest
    "movie.widget.1": (
        TMDB + "info=trending_week&tmdb_type=movie",
        "Trending This Week",
        "WidgetListBigLandscape",
        "Trending This Week | BigLandscape",
    ),
    "movie.widget.2": (
        TMDB + "info=popular&tmdb_type=movie",
        "Popular",
        "WidgetListBigLandscape",
        "Popular | BigLandscape",
    ),
    "movie.widget.3": (
        TMDB + "info=top_rated&tmdb_type=movie",
        "Top Rated",
        "WidgetListBigLandscape",
        "Top Rated | BigLandscape",
    ),
    "movie.widget.4": (
        TMDB + "info=now_playing&tmdb_type=movie",
        "Now Playing",
        "WidgetListBigLandscape",
        "Now Playing | BigLandscape",
    ),
    "movie.widget.5": (
        TMDB + "info=upcoming&tmdb_type=movie",
        "Upcoming",
        "WidgetListBigLandscape",
        "Upcoming | BigLandscape",
    ),
    # TV Shows (tvshow) — Trending first (BigLandscape), then the rest
    "tvshow.widget.1": (
        TMDB + "info=trending_week&tmdb_type=tv",
        "Trending This Week",
        "WidgetListBigLandscape",
        "Trending This Week | BigLandscape",
    ),
    "tvshow.widget.2": (
        TMDB + "info=popular&tmdb_type=tv",
        "Popular",
        "WidgetListBigLandscape",
        "Popular | BigLandscape",
    ),
    "tvshow.widget.3": (
        TMDB + "info=top_rated&tmdb_type=tv",
        "Top Rated",
        "WidgetListBigLandscape",
        "Top Rated | BigLandscape",
    ),
    "tvshow.widget.4": (
        TMDB + "info=on_the_air&tmdb_type=tv",
        "On the Air",
        "WidgetListBigLandscape",
        "On the Air | BigLandscape",
    ),
    "tvshow.widget.5": (
        TMDB + "info=airing_today&tmdb_type=tv",
        "Airing Today",
        "WidgetListBigLandscape",
        "Airing Today | BigLandscape",
    ),
    # Anime (custom2) — trending first (BigLandscape), then popular
    "custom2.widget.1": (
        TMDB + "info=trakt_trending&genres=anime&tmdb_type=tv",
        "Trending Anime",
        "WidgetListBigLandscape",
        "Trending Anime | BigLandscape",
    ),
    "custom2.widget.2": (
        TMDB + "info=trakt_popular&genres=anime&tmdb_type=tv",
        "Popular Anime Series",
        "WidgetListBigLandscape",
        "Popular Anime Series | BigLandscape",
    ),
    "custom2.widget.3": (
        TMDB + "info=trakt_trending&genres=anime&tmdb_type=movie",
        "Trending Anime Movies",
        "WidgetListBigLandscape",
        "Trending Anime Movies | BigLandscape",
    ),
    "custom2.widget.4": (
        TMDB + "info=trakt_anticipated&genres=anime&tmdb_type=tv",
        "Most Anticipated",
        "WidgetListBigLandscape",
        "Most Anticipated | BigLandscape",
    ),
    "custom2.widget.5": (
        TMDB + "info=trakt_popular&genres=anime&tmdb_type=movie",
        "Popular Anime Movies",
        "WidgetListBigLandscape",
        "Popular Anime Movies | BigLandscape",
    ),
    # Lists (custom3) — hidden by default, but configured so user can re-enable
    "custom3.widget.1": (
        TMDB + "info=trakt_watchlist&tmdb_type=movie",
        "Watchlist - Movies",
        "WidgetListBigLandscape",
        "Watchlist - Movies | BigLandscape",
    ),
    "custom3.widget.2": (
        TMDB + "info=trakt_watchlist&tmdb_type=tv",
        "Watchlist - TV Shows",
        "WidgetListBigLandscape",
        "Watchlist - TV Shows | BigLandscape",
    ),
    "custom3.widget.3": (
        TMDB + "info=top_rated&tmdb_type=movie",
        "Top Rated Movies",
        "WidgetListBigLandscape",
        "Top Rated Movies | BigLandscape",
    ),
    "custom3.widget.4": (
        TMDB + "info=top_rated&tmdb_type=tv",
        "Top Rated TV Shows",
        "WidgetListBigLandscape",
        "Top Rated TV Shows | BigLandscape",
    ),
}

# DEFAULT_MENUS: keyed by cpath_setting
# Values: (cpath_path, cpath_header)
DEFAULT_MENUS = {
    "custom1.main_menu": (RABITEWATCH, "Home"),
    "movie.main_menu": (TMDB + "info=popular&tmdb_type=movie", "Films"),
    "tvshow.main_menu": (TMDB + "info=popular&tmdb_type=tv", "TV Shows"),
    "custom2.main_menu": (
        TMDB + "info=trakt_trending&genres=anime&tmdb_type=tv",
        "Anime",
    ),
    "custom3.main_menu": (
        TMDB + "info=trakt_watchlist&tmdb_type=movie",
        "Lists",
    ),
}


_ALL_MENU_BOOLS = (
    "HomeMenuNoMoviesButton",
    "HomeMenuNoTVShowsButton",
    "HomeMenuNoCustom2Button",
    "HomeMenuNoCustom3Button",
    "HomeMenuNoFavButton",
    "HomeMenuNoMusicButton",
    "HomeMenuNoMusicVideoButton",
    "HomeMenuNoTVButton",
    "HomeMenuNoRadioButton",
    "HomeMenuNoPicturesButton",
    "HomeMenuNoVideosButton",
    "HomeMenuNoWeatherButton",
    "HomeMenuNoGamesButton",
    "HomeMenuNoProgramsButton",
)

# Settings that should be HIDDEN in the default layout
_DEFAULT_HIDDEN_MENUS = (
    "HomeMenuNoProgramsButton",  # Add-ons
    "HomeMenuNoMusicButton",
    "HomeMenuNoMusicVideoButton",
    "HomeMenuNoTVButton",
    "HomeMenuNoRadioButton",
    "HomeMenuNoPicturesButton",
    "HomeMenuNoVideosButton",
    "HomeMenuNoWeatherButton",
)


def setup_default_home(force=False):
    from modules.cpath_maker import CPaths, remake_all_cpaths

    cp = CPaths("movie.widget")

    if not force:
        count = cp.dbcur.execute(
            "SELECT COUNT(*) FROM custom_paths"
        ).fetchone()[0]
        if count > 0:
            xbmc.log(
                "###littleduck defaults: DB already populated, skipping"
                " (use force=true to override)",
                1,
            )
            xbmcgui.Dialog().notification(
                "littleduck",
                "Already configured — use Reset to overwrite",
                xbmcgui.NOTIFICATION_WARNING,
                4000,
            )
            return

    # Wipe all existing widget/menu data before applying defaults
    cp.dbcur.execute("DELETE FROM custom_paths")

    for cpath_setting, (cpath_path, cpath_header, cpath_type, cpath_label) in DEFAULT_WIDGETS.items():
        cp.dbcur.execute(
            "INSERT INTO custom_paths VALUES (?, ?, ?, ?, ?)",
            (cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label),
        )

    for cpath_setting, (cpath_path, cpath_header) in DEFAULT_MENUS.items():
        cp.dbcur.execute(
            "INSERT INTO custom_paths VALUES (?, ?, ?, ?, ?)",
            (cpath_setting, cpath_path, cpath_header, "", ""),
        )

    cp.dbcon.commit()

    # Reset every menu visibility bool to clear any user customisation
    for setting in _ALL_MENU_BOOLS:
        xbmc.executebuiltin("Skin.ResetSetting(%s)" % setting)

    # Apply default menu labels
    xbmc.executebuiltin("Skin.SetString(MenuCustom1Label,Home)")
    xbmc.executebuiltin("Skin.SetString(MenuMovieLabel,Films)")
    xbmc.executebuiltin("Skin.SetString(MenuTVShowLabel,TV Shows)")
    xbmc.executebuiltin("Skin.SetString(MenuCustom2Label,Anime)")
    xbmc.executebuiltin("Skin.SetString(MenuCustom3Label,Lists)")

    # Apply default widget display types (spotlight layout)
    for section in ("custom1", "movie", "tvshow", "custom2", "custom3"):
        xbmc.executebuiltin("Skin.SetString(spotlight.%s.type,landscape)" % section)

    # Hide items not in the default layout
    for setting in _DEFAULT_HIDDEN_MENUS:
        xbmc.executebuiltin("Skin.SetBool(%s)" % setting)

    remake_all_cpaths(silent=True)
    xbmc.log("###littleduck defaults: Quick setup complete", 1)
    xbmcgui.Dialog().notification(
        "littleduck",
        "Quick setup applied",
        xbmcgui.NOTIFICATION_INFO,
        4000,
    )


def reset_home():
    """Clear all widget paths, menu paths, and labels — leaves a blank slate."""
    from modules.cpath_maker import CPaths, remake_all_cpaths

    cp = CPaths("movie.widget")
    cp.dbcur.execute("DELETE FROM custom_paths")
    cp.dbcon.commit()

    # Reset all menu visibility bools
    for setting in _ALL_MENU_BOOLS:
        xbmc.executebuiltin("Skin.ResetSetting(%s)" % setting)

    # Clear menu labels
    for key in ("MenuCustom1Label", "MenuMovieLabel", "MenuTVShowLabel",
                "MenuCustom2Label", "MenuCustom3Label"):
        xbmc.executebuiltin("Skin.ResetSetting(%s)" % key)

    # Clear spotlight display type strings
    for section in ("custom1", "movie", "tvshow", "custom2", "custom3"):
        xbmc.executebuiltin("Skin.ResetSetting(spotlight.%s.type)" % section)

    remake_all_cpaths(silent=True)
    xbmc.log("###littleduck defaults: Home reset (full clear)", 1)
    xbmcgui.Dialog().notification(
        "littleduck",
        "Home cleared",
        xbmcgui.NOTIFICATION_INFO,
        4000,
    )
