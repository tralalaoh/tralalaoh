# -*- coding: utf-8 -*-
import sys
import xbmc
from urllib.parse import parse_qsl


def routing():
    params = dict(parse_qsl(sys.argv[1], keep_blank_values=True))
    _get = params.get
    mode = _get("mode", "check_for_update")

    # Log all routing calls
    xbmc.log(f"###littleduck ROUTER: ========================================", 1)
    xbmc.log(f"###littleduck ROUTER: routing() function called", 1)
    xbmc.log(f"###littleduck ROUTER: Mode: {mode}", 1)
    xbmc.log(f"###littleduck ROUTER: Params: {params}", 1)
    xbmc.log(f"###littleduck ROUTER: ========================================", 1)

    if mode == "manage_widgets":
        from modules.cpath_maker import CPaths
        return CPaths(params.get("cpath_setting")).manage_widgets()

    if mode == "manage_main_menu_path":
        from modules.cpath_maker import CPaths
        return CPaths(params.get("cpath_setting")).manage_main_menu_path()

    if mode == "widget_monitor":
        from modules.widget_utils import widget_monitor
        return widget_monitor(params.get("list_id"))

    # --- ADD THESE NEW HANDLERS ---
    if mode == "fix_black_screen":
        from modules.custom_actions import fix_black_screen
        return fix_black_screen()

    if mode == "modify_keymap":
        from modules.custom_actions import manage_trailer_playback
        return manage_trailer_playback(params)
    # ----------------------------------

    if "actions" in mode:
        from modules import actions
        return getattr(actions, mode.split(".")[1])(params)

    if "custom_actions" in mode:
        from modules import custom_actions
        return getattr(custom_actions, mode.split(".")[1])(params)

    if mode == "check_for_update":
        from modules.version_monitor import check_for_update
        return check_for_update("skin.littleduck")

    if mode == "check_for_profile_change":
        from modules.version_monitor import check_for_profile_change
        return check_for_profile_change("skin.littleduck")

    if mode == "starting_widgets":
        from modules.cpath_maker import starting_widgets
        return starting_widgets()

    if mode == "setup_default_home":
        from modules.defaults import setup_default_home
        return setup_default_home(force=params.get("force") == "true")

    if mode == "reset_home":
        from modules.defaults import reset_home
        return reset_home()

    if mode == "clear_ratings_cache" or mode == "delete_all_ratings":
        xbmc.log(f"###littleduck ROUTER: {mode} mode detected!", 1)
        from modules.MDbList import MDbListAPI
        from modules.OmDb import OmDbAPI
        mdb_api = MDbListAPI()
        mdb_api.clear_all_ratings()
        omdb_api = OmDbAPI()
        omdb_api.clear_all_ratings()
        xbmc.log(f"###littleduck ROUTER: {mode} completed (MDbList + OMDb caches cleared)", 1)
        return


    # ── Widget management ──────────────────────────────────────────────────────

    if mode == "remake_widgets":
        cpath_setting = params.get("cpath_setting")
        if not cpath_setting:
            return
        from modules.cpath_maker import CPaths
        return CPaths(cpath_setting).remake_widgets()

    # ── Main menu management ───────────────────────────────────────────────────
    if mode == "remake_main_menus":
        cpath_setting = params.get("cpath_setting")
        if not cpath_setting:
            return
        from modules.cpath_maker import CPaths
        return CPaths(cpath_setting).remake_main_menus()

    # ── Search provider management ─────────────────────────────────────────────
    if mode == "manage_search_providers":
        from modules.cpath_maker import CPaths
        return CPaths("search_providers").manage_search_providers()

    if mode == "remake_search_providers":
        from modules.cpath_maker import CPaths
        return CPaths("search_providers").remake_search_providers()

    if mode == "remake_all_cpaths":
        from modules.cpath_maker import remake_all_cpaths
        return remake_all_cpaths()

    # ── Search ─────────────────────────────────────────────────────────────────
    if mode == "search_input":
        from modules.search_utils import SPaths
        return SPaths().search_input(params.get("search_term"))

    if mode == "re_search":
        from modules.search_utils import SPaths
        return SPaths().re_search()

    if mode == "open_search_window":
        from modules.search_utils import SPaths
        return SPaths().open_search_window()

    if mode == "remove_all_spaths":
        from modules.search_utils import SPaths
        return SPaths().remove_all_spaths()

    # ── API key management ─────────────────────────────────────────────────────
    if mode == "pick_menu_icon":
        from modules.custom_actions import pick_menu_icon
        return pick_menu_icon(params)

    if mode == "set_tmdb_key":
        from modules.custom_actions import set_tmdb_key
        return set_tmdb_key()

    if mode == "set_tvdb_key":
        from modules.custom_actions import set_tvdb_key
        return set_tvdb_key()

    if mode == "set_rpdb_key":
        from modules.custom_actions import set_rpdb_key
        return set_rpdb_key()

    if mode == "set_mdblist_key":
        from modules.custom_actions import set_mdblist_key
        return set_mdblist_key()

    if mode == "set_omdb_key":
        from modules.custom_actions import set_omdb_key
        return set_omdb_key()

    xbmc.log(f"###littleduck ROUTER: Unknown mode '{mode}' - no handler found", 2)
