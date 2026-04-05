# -*- coding: utf-8 -*-
import xbmc, xbmcgui, xbmcvfs
import json
import sqlite3 as database
from threading import Thread
from modules import xmls

dialog = xbmcgui.Dialog()
window = xbmcgui.Window(10000)
Listitem = xbmcgui.ListItem
max_widgets = 10
max_search_providers = 10

settings_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/"
)
database_path = xbmcvfs.translatePath(
    "special://profile/addon_data/script.littleduck.helper/cpath_cache.db"
)
(
    movies_widgets_xml,
    tvshows_widgets_xml,
    custom1_widgets_xml,
    custom2_widgets_xml,
    custom3_widgets_xml,
) = (
    "script-littleduck-widget_movies",
    "script-littleduck-widget_tvshows",
    "script-littleduck-widget_custom1",
    "script-littleduck-widget_custom2",
    "script-littleduck-widget_custom3",
)
(
    movies_main_menu_xml,
    tvshows_main_menu_xml,
    custom1_main_menu_xml,
    custom2_main_menu_xml,
    custom3_main_menu_xml,
) = (
    "script-littleduck-main_menu_movies",
    "script-littleduck-main_menu_tvshows",
    "script-littleduck-main_menu_custom1",
    "script-littleduck-main_menu_custom2",
    "script-littleduck-main_menu_custom3",
)
search_providers_xml = "script-littleduck-search_providers"

default_xmls = {
    "movie.widget": (movies_widgets_xml, xmls.default_widget, "MovieWidgets"),
    "tvshow.widget": (tvshows_widgets_xml, xmls.default_widget, "TVShowWidgets"),
    "custom1.widget": (custom1_widgets_xml, xmls.default_widget, "Custom1Widgets"),
    "custom2.widget": (custom2_widgets_xml, xmls.default_widget, "Custom2Widgets"),
    "custom3.widget": (custom3_widgets_xml, xmls.default_widget, "Custom3Widgets"),
    "movie.main_menu": (movies_main_menu_xml, xmls.default_main_menu, "MoviesMainMenu"),
    "tvshow.main_menu": (
        tvshows_main_menu_xml,
        xmls.default_main_menu,
        "TVShowsMainMenu",
    ),
    "custom1.main_menu": (
        custom1_main_menu_xml,
        xmls.default_main_menu,
        "Custom1MainMenu",
    ),
    "custom2.main_menu": (
        custom2_main_menu_xml,
        xmls.default_main_menu,
        "Custom2MainMenu",
    ),
    "custom3.main_menu": (
        custom3_main_menu_xml,
        xmls.default_main_menu,
        "Custom3MainMenu",
    ),
    "search_providers": (search_providers_xml, xmls.default_search_providers, "SearchProviders"),
}
main_include_dict = {
    "movie": {"main_menu": None, "widget": "MovieWidgets"},
    "tvshow": {"main_menu": None, "widget": "TVShowWidgets"},
    "custom1": {"main_menu": None, "widget": "Custom1Widgets"},
    "custom2": {"main_menu": None, "widget": "Custom2Widgets"},
    "custom3": {"main_menu": None, "widget": "Custom3Widgets"},
}
widget_types = (
    ("BigPoster", "WidgetListBigPoster"),
    ("BigLandscape", "WidgetListBigLandscape"),
    ("BigLandscapeInfo", "WidgetListBigEpisodes"),
    ("Wall Landscape", "WidgetListWallLandscape"),
    ("Wall Poster", "WidgetListWallPoster"),
)

# Maps cpath_type → spotlight.SECTION.type skin string value
_SPOTLIGHT_TYPE_MAP = {
    "WidgetListBigPoster": "poster",
    "WidgetListBigLandscape": "landscape",
    "WidgetListBigEpisodes": "landscapeinfo",
    "WidgetListWallLandscape": "walll",
    "WidgetListWallPoster": "wallp",
}
default_path = "addons://sources/video"

# Spotlight tab include names and list/button ID bases per section
_SPOTLIGHT_INCLUDE_NAMES = {
    "custom1": "Custom1SpotlightTabs",
    "movie":   "MovieSpotlightTabs",
    "tvshow":  "TVShowSpotlightTabs",
    "custom2": "Custom2SpotlightTabs",
    "custom3": "Custom3SpotlightTabs",
}
_SPOTLIGHT_LIST_BASES = {
    "custom1": 39010,
    "movie":   38010,
    "tvshow":  37010,
    "custom2": 36010,
    "custom3": 35010,
}
_SPOTLIGHT_BTN_BASES = {
    "custom1": 39060,
    "movie":   38060,
    "tvshow":  37060,
    "custom2": 36060,
    "custom3": 35060,
}


_SPOTLIGHT_SECTION_LIST_IDS = {
    "custom1": 39100,
    "movie":   39200,
    "tvshow":  39300,
    "custom2": 39400,
    "custom3": 39500,
}

def _calc_tab_widths(labels, gap=20, max_w=1845):
    """Calculate proportional group widths for spotlight tab buttons."""
    raw = [max(80, len(lb) * 16 + 15) for lb in labels]
    total = sum(raw) + gap * (len(raw) - 1)
    if total > max_w:
        available = max_w - gap * (len(raw) - 1)
        scale = available / sum(raw)
        widths = [max(80, int(r * scale)) for r in raw]
        widths[-1] += available - sum(widths)
    else:
        widths = raw
    return widths


def _build_spotlight_xml(tab_widgets, section, spotlight_include, list_base, btn_base):
    """Build the spotlight tabs <include> block for a widget section.

    tab_widgets: list of (slot_int, widget_dict) in order
    Returns the XML string to append to the widget XML file.
    """
    if not tab_widgets:
        return '\n\n    <include name="%s">\n    </include>' % spotlight_include

    xml = xmls.spotlight_tabs_start.format(spotlight_include=spotlight_include)

    labels = [w["cpath_header"] for _, w in tab_widgets]
    widths = _calc_tab_widths(labels)

    # Generate tab buttons + indicator bars
    for idx, (slot, w) in enumerate(tab_widgets):
        tab_btn_id = btn_base + slot
        prev_btn = 9000 if idx == 0 else (btn_base + tab_widgets[idx - 1][0])
        next_btn = (
            tab_btn_id if idx == len(tab_widgets) - 1
            else (btn_base + tab_widgets[idx + 1][0])
        )
        if idx == 0:
            active_cond = (
                "String.IsEmpty(Window(Home).Property(spotlight.%s.tab))"
                " | String.IsEqual(Window(Home).Property(spotlight.%s.tab),%s)"
                % (section, section, slot)
            )
        else:
            active_cond = (
                "String.IsEqual(Window(Home).Property(spotlight.%s.tab),%s)"
                % (section, slot)
            )
        type_value = _SPOTLIGHT_TYPE_MAP.get(
            w.get("cpath_type", "WidgetListBigLandscape"), "landscape"
        )
        base_list_id = _SPOTLIGHT_SECTION_LIST_IDS.get(section, 39100)
        xml += xmls.spotlight_tab_button.format(
            slot=slot,
            cpath_header=w["cpath_header"],
            cpath_path=w["cpath_path"],
            tab_btn_id=tab_btn_id,
            section=section,
            prev_btn=prev_btn,
            next_btn=next_btn,
            section_list_id=base_list_id,
            landscape_id=base_list_id + 10,
            landscapeinfo_id=base_list_id + 21,
            walll_id=base_list_id + 51,
            wallp_id=base_list_id + 61,
            active_condition=active_cond,
            group_width=widths[idx],
            type_value=type_value,
        )

    xml += xmls.spotlight_tab_bar_end
    xml += xmls.spotlight_tabs_end
    return xml


class CPaths:
    def __init__(self, cpath_setting):
        self.connect_database()
        self.cpath_setting = cpath_setting
        self.cpath_lookup = "'%s'" % (self.cpath_setting + "%")
        # Handle search_providers special case
        if cpath_setting.startswith("search_providers"):
            self.media_type = "search_providers"
            self.path_type = "search_providers"
            self.main_include = None
        else:
            self.media_type, self.path_type = self.cpath_setting.split(".")
            self.main_include = main_include_dict.get(self.media_type, {}).get(self.path_type)
        self.refresh_cpaths, self.last_cpath = False, None

    def connect_database(self):
        if not xbmcvfs.exists(settings_path):
            xbmcvfs.mkdir(settings_path)
        self.dbcon = database.connect(database_path, timeout=20)
        self.dbcon.execute(
            "CREATE TABLE IF NOT EXISTS custom_paths (cpath_setting text unique, cpath_path text, cpath_header text, cpath_type text, cpath_label text)"
        )
        self.dbcur = self.dbcon.cursor()

    def add_cpath_to_database(
        self, cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label
    ):
        self.refresh_cpaths = True
        self.dbcur.execute(
            "INSERT OR REPLACE INTO custom_paths VALUES (?, ?, ?, ?, ?)",
            (cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label),
        )
        self.dbcon.commit()

    def update_cpath_in_database(
        self, cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label
    ):
        self.refresh_cpaths = True
        self.dbcur.execute(
            """
            UPDATE custom_paths
            SET cpath_path = ?, cpath_header = ?, cpath_type = ?, cpath_label = ?
            WHERE cpath_setting = ?
        """,
            (cpath_path, cpath_header, cpath_type, cpath_label, cpath_setting),
        )
        self.dbcon.commit()

    def remove_cpath_from_database(self, cpath_setting):
        self.refresh_cpaths = True
        self.dbcur.execute(
            "DELETE FROM custom_paths WHERE cpath_setting = ?", (cpath_setting,)
        )
        self.dbcon.commit()

    def fetch_current_cpaths(self):
        results = self.dbcur.execute(
            "SELECT * FROM custom_paths WHERE cpath_setting LIKE %s" % self.cpath_lookup
        ).fetchall()
        try:
            results.sort(key=lambda k: int(k[0].split(".")[-1]))
        except (ValueError, IndexError):
            pass
        current_dict = {}
        for item in results:
            try:
                key = int(item[0].split(".")[-1])
            except (ValueError, IndexError):
                key = item[0]
            data = {
                "cpath_setting": item[0],
                "cpath_path": item[1],
                "cpath_header": item[2],
                "cpath_type": item[3],
                "cpath_label": item[4],
            }
            current_dict[key] = data
        return current_dict

    def fetch_one_cpath(self, cpath_setting):
        result = self.dbcur.execute(
            "SELECT * FROM custom_paths WHERE cpath_setting = ?", (cpath_setting,)
        ).fetchone()
        if result is None:
            return None
        return {
            "cpath_setting": result[0],
            "cpath_path": result[1],
            "cpath_header": result[2],
            "cpath_type": result[3],
            "cpath_label": result[4],
        }

    def path_browser(self, label="", file=default_path, thumbnail="", is_search_provider=False):
        """
        Browse addon paths with support for empty directories.
        
        Args:
            label: Display label for the current path
            file: Current directory path
            thumbnail: Icon for the current path
            is_search_provider: If True, allows selecting empty directories (for search endpoints)
        """
        show_busy_dialog()
        label = self.clean_header(label)
        results = files_get_directory(file)
        hide_busy_dialog()
        list_items = []
        
        # For search providers OR non-default paths, always show "Use this path" option
        # This handles the empty folder case for search endpoints
        if is_search_provider or file != default_path:
            if is_search_provider and not results:
                # Empty directory - likely a search endpoint
                use_label = "Use [COLOR dodgerblue]%s[/COLOR] as search provider (empty endpoint - will append query)" % label
            else:
                use_label = "Use [COLOR dodgerblue]%s[/COLOR] as path" % label
            
            listitem = Listitem(
                use_label,
                "Set as path",
                offscreen=True,
            )
            listitem.setArt({"icon": thumbnail})
            listitem.setProperty(
                "item",
                json.dumps({"label": label, "file": file, "thumbnail": thumbnail}),
            )
            list_items.append(listitem)
        
        # Add browseable subdirectories
        for i in results:
            stripped_label = i["label"]
            stripped_label = stripped_label.replace("[B]", "").replace("[/B]", "")
            while "[COLOR" in stripped_label:
                start = stripped_label.find("[COLOR")
                end = stripped_label.find("]", start) + 1
                stripped_label = stripped_label[:start] + stripped_label[end:]
            stripped_label = stripped_label.replace("[/COLOR]", "")
            listitem = Listitem(
                "%s »" % stripped_label, "Browse path...", offscreen=True
            )
            listitem.setArt({"icon": i["thumbnail"]})
            listitem.setProperty(
                "item",
                json.dumps(
                    {
                        "label": i["label"],
                        "file": i["file"],
                        "thumbnail": i["thumbnail"],
                    }
                ),
            )
            list_items.append(listitem)
        
        choice = dialog.select("Choose path", list_items, useDetails=True)
        if choice < 0:
            return None
        chosen = json.loads(list_items[choice].getProperty("item"))
        if list_items[choice].getLabel2() == "Set as path":
            return chosen
        return self.path_browser(
            chosen["label"], 
            chosen["file"], 
            chosen["thumbnail"],
            is_search_provider=is_search_provider
        )

    def make_widget_xml(self, active_cpaths, event=None):
        if not self.refresh_cpaths:
            return
        if not active_cpaths:
            self.make_default_xml()
        xml_file = "special://skin/xml/%s.xml" % (
            default_xmls[self.cpath_setting][0]
        )
        final_format = xmls.media_xml_start.format(main_include=self.main_include)
        for count in range(1, 11):
            active_widget = active_cpaths.get(count, {})
            if not active_widget:
                continue
            cpath_setting = active_widget["cpath_setting"]
            if not cpath_setting:
                continue
            try:
                list_id = (
                    int(
                        (self.cpath_setting.split(".")[0])
                        .replace("movie", "19010")
                        .replace("tvshow", "22010")
                        .replace("custom1", "23010")
                        .replace("custom2", "24010")
                        .replace("custom3", "25010")
                    )
                    + int(cpath_setting.split(".")[2])
                )
            except (ValueError, KeyError, IndexError):
                continue
            cpath_path = active_widget["cpath_path"]
            cpath_header = active_widget["cpath_header"]
            cpath_type = active_widget["cpath_type"]
            if "Stacked" in cpath_type:
                body = xmls.stacked_media_xml_body
            else:
                body = xmls.media_xml_body
            body = body.format(
                cpath_path=cpath_path,
                cpath_header=cpath_header,
                cpath_type=cpath_type,
                cpath_list_id=list_id,
            )
            final_format += body
        # Close the main widgets include
        final_format += xmls.media_xml_end

        # Append spotlight tabs include for this section
        spotlight_include = _SPOTLIGHT_INCLUDE_NAMES.get(self.media_type)
        if spotlight_include:
            tab_widgets = [
                (c, active_cpaths[c])
                for c in range(1, 11)
                if active_cpaths.get(c, {}).get("cpath_path")
            ]
            spotlight_xml = _build_spotlight_xml(
                tab_widgets,
                self.media_type,
                spotlight_include,
                _SPOTLIGHT_LIST_BASES[self.media_type],
                _SPOTLIGHT_BTN_BASES[self.media_type],
            )
            # Insert spotlight include before the closing </includes> tag
            final_format = final_format.replace("\n</includes>", spotlight_xml + "\n</includes>", 1)

        self.write_xml(xml_file, final_format)
        self.update_skin_strings()
        if event is not None:
            event.set()
        else:
            Thread(target=self.reload_skin).start()

    def make_main_menu_xml(self, active_cpaths):
        if not self.refresh_cpaths:
            return
        xml_file = "special://skin/xml/%s.xml" % (
            default_xmls[self.cpath_setting][0]
        )
        active_cpath = active_cpaths.get(self.cpath_setting, {})
        if not active_cpath:
            self.make_default_xml()
            return
        main_menu_xml_template_map = {
            "movie.main_menu": xmls.main_menu_movies_xml,
            "tvshow.main_menu": xmls.main_menu_tvshows_xml,
            "custom1.main_menu": xmls.main_menu_custom1_xml,
            "custom2.main_menu": xmls.main_menu_custom2_xml,
            "custom3.main_menu": xmls.main_menu_custom3_xml,
        }
        main_menu_xml_template = main_menu_xml_template_map.get(
            self.cpath_setting, None
        )
        if not main_menu_xml_template:
            return
        final_format = main_menu_xml_template.format(
            cpath_header=active_cpath["cpath_header"],
            main_menu_path=active_cpath["cpath_path"],
        )
        self.write_xml(xml_file, final_format)
        self.update_skin_strings()
        Thread(target=self.reload_skin).start()

    def make_search_providers_xml(self, active_providers, event=None):
        """Generate XML for search providers with dynamic query string appending."""
        if not self.refresh_cpaths:
            return
        if not active_providers:
            self.make_default_xml()
            return
        
        xml_file = "special://skin/xml/%s.xml" % (search_providers_xml)
        final_format = xmls.search_providers_xml_start
        
        for count in range(1, max_search_providers + 1):
            active_provider = active_providers.get(count, {})
            if not active_provider:
                continue
            
            cpath_path = active_provider["cpath_path"]
            cpath_header = active_provider["cpath_header"]
            
            # Generate search provider XML entry
            # The path is the base path, query will be appended by the skin
            body = xmls.search_provider_xml_body.format(
                provider_name=cpath_header,
                provider_path=cpath_path,
                provider_number=count
            )
            final_format += body
        
        final_format += xmls.search_providers_xml_end
        self.write_xml(xml_file, final_format)
        
        if event is not None:
            event.set()
        else:
            Thread(target=self.reload_skin).start()

    def write_xml(self, xml_file, final_format):
        with xbmcvfs.File(xml_file, "w") as f:
            f.write(final_format)

    def handle_path_browser_results(self, cpath_setting, context):
        """
        Handle path browser results for widgets, main menu, or search providers.
        
        Args:
            cpath_setting: The setting identifier
            context: Either 'widget', 'main_menu', or 'search_provider'
        """
        is_search_provider = (context == "search_provider")
        result = self.path_browser(is_search_provider=is_search_provider)
        
        if not result:
            return None
        
        cpath_path = result.get("file", None)
        default_header = result.get("label", None)
        
        if not cpath_path:
            return None
        
        if context == "widget":
            cpath_header = self.widget_header(default_header)
            if not cpath_header:
                return None
            self.create_and_update_widget(cpath_setting, cpath_path, cpath_header)
        elif context == "search_provider":
            cpath_header = self.search_provider_header(default_header)
            if not cpath_header:
                return None
            # For search providers, store with a special type identifier
            self.add_cpath_to_database(
                cpath_setting, 
                cpath_path, 
                cpath_header, 
                "search_provider", 
                cpath_header
            )
        else:  # context == 'main_menu'
            cpath_header = self.main_menu_header(default_header)
            if not cpath_header:
                return None
            self.add_cpath_to_database(cpath_setting, cpath_path, cpath_header, "", "")
            self.update_skin_strings()
        
        return True

    def manage_action_and_check(self, cpath_setting, context):
        action_choice = self.manage_action(cpath_setting, context)
        if action_choice == "clear_path":
            self.make_default_xml()
            dialog.ok("littleduck", "Path cleared")
            return None
        if action_choice is None:
            return None
        return True

    def manage_main_menu_path(self):
        active_cpaths = self.fetch_current_cpaths()
        if active_cpaths and not self.manage_action_and_check(
            self.cpath_setting, "main_menu"
        ):
            return
        if not self.handle_path_browser_results(self.cpath_setting, "main_menu"):
            return self.make_main_menu_xml(active_cpaths)
        self.make_main_menu_xml(self.fetch_current_cpaths())

    def manage_widgets(self):
        active_cpaths = self.fetch_current_cpaths()
        widget_choices = [
            "Widget %s : %s"
            % (count, active_cpaths.get(count, {}).get("cpath_label", ""))
            for count in range(1, 11)
        ]
        choice = dialog.select("Choose widget", widget_choices)
        if choice == -1:
            return self.make_widget_xml(active_cpaths)
        active_cpath_check = choice + 1
        if active_cpath_check in active_cpaths:
            cpath_setting = active_cpaths[active_cpath_check]["cpath_setting"]
            if not self.manage_action_and_check(cpath_setting, "widget"):
                return self.manage_widgets()
        else:
            cpath_setting = "%s.%s" % (self.cpath_setting, active_cpath_check)
        if not self.handle_path_browser_results(cpath_setting, "widget"):
            return self.manage_widgets()
        return self.manage_widgets()

    def manage_search_providers(self):
        """Manage custom search providers - mirrors manage_widgets() pattern."""
        # Use search_providers as the cpath_setting for database lookup
        search_setting = "search_providers"
        self.cpath_setting = search_setting
        self.cpath_lookup = "'%s'" % (search_setting + "%")
        
        active_providers = self.fetch_current_cpaths()
        provider_choices = [
            "Provider %s : %s"
            % (count, active_providers.get(count, {}).get("cpath_label", ""))
            for count in range(1, max_search_providers + 1)
        ]
        
        choice = dialog.select("Choose search provider", provider_choices)
        if choice == -1:
            return self.make_search_providers_xml(active_providers)
        
        active_provider_check = choice + 1
        
        if active_provider_check in active_providers:
            cpath_setting = active_providers[active_provider_check]["cpath_setting"]
            if not self.manage_action_and_check(cpath_setting, "search_provider"):
                return self.manage_search_providers()
        else:
            cpath_setting = "%s.%s" % (search_setting, active_provider_check)
        
        if not self.handle_path_browser_results(cpath_setting, "search_provider"):
            return self.manage_search_providers()
        
        # Refresh the XML after changes
        self.refresh_cpaths = True
        self.make_search_providers_xml(self.fetch_current_cpaths())
        return self.manage_search_providers()

    def manage_action(self, cpath_setting, context):
        """
        Manage actions for a given path setting.
        
        Args:
            cpath_setting: The setting identifier
            context: Either 'widget', 'main_menu', or 'search_provider'
        """
        if context == "search_provider":
            choices = ["Change path", "Change label", "Clear path"]
        elif context == "widget":
            choices = ["Change path", "Change label", "Change display type", "Clear path"]
        else:  # main_menu
            choices = ["Change path", "Change label", "Restore default label", "Clear path"]
        
        choice = dialog.select("Choose action", choices)
        if choice < 0:
            return None
        
        action = choices[choice].lower().replace(" ", "_")
        
        if action == "change_path":
            return self.handle_path_browser_results(cpath_setting, context)
        
        elif action == "change_label":
            result = self.fetch_one_cpath(cpath_setting)
            if not result:
                return None
            
            cpath_path = result.get("cpath_path", None)
            cpath_type = result.get("cpath_type", None)
            cpath_label = result.get("cpath_label", None)
            
            if not cpath_path:
                return None
            
            default_header = result.get("cpath_header", None)
            
            if context == "widget":
                cpath_header = self.widget_header(default_header)
                if not cpath_header:
                    return None
                widget_type = self.get_widget_type(result["cpath_type"])
                if not widget_type:
                    return None
                if "Stacked" in cpath_type:
                    cpath_label = "%s | Stacked (%s) | Category" % (
                        cpath_header,
                        widget_type,
                    )
                else:
                    cpath_label = "%s | %s" % (cpath_header, widget_type)
                self.update_cpath_in_database(
                    cpath_setting,
                    cpath_path,
                    cpath_header,
                    result["cpath_type"],
                    cpath_label,
                )
            elif context == "search_provider":
                cpath_header = self.search_provider_header(default_header)
                if not cpath_header:
                    return None
                self.update_cpath_in_database(
                    cpath_setting,
                    cpath_path,
                    cpath_header,
                    cpath_type,
                    cpath_header
                )
            else:  # main_menu
                cpath_header = self.main_menu_header(default_header)
                if not cpath_header or cpath_header.strip() == "":
                    cpath_map = {
                        "movie.main_menu": xbmc.getLocalizedString(342),
                        "tvshow.main_menu": xbmc.getLocalizedString(20343),
                        "custom1.main_menu": "Custom 1",
                        "custom2.main_menu": "Custom 2",
                        "custom3.main_menu": "Custom 3",
                    }
                    cpath_header = cpath_map.get(
                        cpath_setting, "Default main menu label not found"
                    )
                self.update_cpath_in_database(
                    cpath_setting, cpath_path, cpath_header, "", ""
                )
                self.make_main_menu_xml(self.fetch_current_cpaths())
        
        elif action == "change_display_type":
            result = self.fetch_one_cpath(cpath_setting)
            if not result:
                return None
            cpath_path = result.get("cpath_path", None)
            cpath_header = result.get("cpath_header", None)
            cpath_label = result.get("cpath_label", None)
            if not cpath_path:
                return None
            self.create_and_update_widget(
                cpath_setting, cpath_path, cpath_header, add_to_db=False
            )
        
        elif action == "restore_default_label":
            result = self.fetch_one_cpath(cpath_setting)
            if not result:
                return None
            cpath_path = result.get("cpath_path", None)
            if not cpath_path:
                return None
            cpath_map = {
                "movie.main_menu": xbmc.getLocalizedString(342),
                "tvshow.main_menu": xbmc.getLocalizedString(20343),
                "custom1.main_menu": "Custom 1",
                "custom2.main_menu": "Custom 2",
                "custom3.main_menu": "Custom 3",
            }
            cpath_header = cpath_map.get(
                cpath_setting, "Default main menu label not found"
            )
            self.update_cpath_in_database(
                cpath_setting, cpath_path, cpath_header, "", ""
            )
            self.make_main_menu_xml(self.fetch_current_cpaths())
        
        elif action == "clear_path":
            self.remove_cpath_from_database(cpath_setting)
            if context == "main_menu":
                self.make_default_xml()
                dialog.ok("littleduck", "Path cleared")
            elif context == "search_provider":
                # Refresh search providers XML after clearing
                self.refresh_cpaths = True
                remaining_providers = self.fetch_current_cpaths()
                self.make_search_providers_xml(remaining_providers)
        
        return None

    def swap_widgets(self, parts, current_order, new_order):
        current_widget = f"{parts[0]}.{parts[1]}.{current_order}"
        adjacent_widget = f"{parts[0]}.{parts[1]}.{new_order}"
        self.refresh_cpaths = True
        self.dbcur.execute(
            "UPDATE custom_paths SET cpath_setting = ? WHERE cpath_setting = ?",
            (f"{parts[0]}.{parts[1]}.temp", current_widget),
        )
        self.dbcur.execute(
            "UPDATE custom_paths SET cpath_setting = ? WHERE cpath_setting = ?",
            (current_widget, adjacent_widget),
        )
        self.dbcur.execute(
            "UPDATE custom_paths SET cpath_setting = ? WHERE cpath_setting = ?",
            (adjacent_widget, f"{parts[0]}.{parts[1]}.temp"),
        )
        self.dbcon.commit()

    def handle_widget_remake(self, result, cpath_setting):
        cpath_path, default_header = result.get("file", None), result.get("label", None)
        cpath_header = self.widget_header(default_header)
        self.create_and_update_widget(cpath_setting, cpath_path, cpath_header)

    def _sync_spotlight_type(self, cpath_setting, cpath_type):
        """Update global spotlight.SECTION.type skin string immediately after type change."""
        parts = cpath_setting.split(".")
        if len(parts) < 2 or parts[1] != "widget":
            return
        section = parts[0]
        spotlight_type = _SPOTLIGHT_TYPE_MAP.get(cpath_type, "landscape")
        xbmc.executebuiltin("Skin.SetString(spotlight.%s.type,%s)" % (section, spotlight_type))

    def create_and_update_widget(
        self, cpath_setting, cpath_path, cpath_header, add_to_db=True
    ):
        widget_type = self.widget_type()
        if widget_type is None:
            return
        cpath_type, cpath_label = widget_type[1], "%s | %s" % (
                cpath_header,
                widget_type[0],
            )
        if add_to_db:
            self.add_cpath_to_database(
                cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label
            )
        else:
            self.update_cpath_in_database(
                cpath_setting, cpath_path, cpath_header, cpath_type, cpath_label
            )
        self._sync_spotlight_type(cpath_setting, cpath_type)

    def reload_skin(self):
        if window.getProperty("littleduck.clear_path_refresh") == "true":
            return
        window.setProperty("littleduck.clear_path_refresh", "true")
        while xbmcgui.getCurrentWindowId() == 10035:
            xbmc.sleep(500)
        window.setProperty("littleduck.clear_path_refresh", "")
        xbmc.sleep(200)
        xbmc.executebuiltin("ReloadSkin()")
        starting_widgets()

    def clean_header(self, header):
        return header.replace("[B]", "").replace("[/B]", "").replace(" >>", "")

    def remake_main_menus(self):
        self.refresh_cpaths = True
        active_cpaths = self.fetch_current_cpaths()
        if active_cpaths:
            self.make_main_menu_xml(active_cpaths)
        else:
            self.make_default_xml()

    def remake_widgets(self):
        self.refresh_cpaths = True
        active_cpaths = self.fetch_current_cpaths()
        if active_cpaths:
            self.make_widget_xml(active_cpaths)
        else:
            self.make_default_xml()

    def remake_search_providers(self):
        """Remake search providers XML from database."""
        self.cpath_setting = "search_providers"
        self.cpath_lookup = "'%s'" % (self.cpath_setting + "%")
        self.refresh_cpaths = True
        active_providers = self.fetch_current_cpaths()
        if active_providers:
            self.make_search_providers_xml(active_providers)
        else:
            self.make_default_xml()

    def make_default_xml(self):
        item = default_xmls.get(self.cpath_setting)
        if not item:
            # For search_providers, use the search_providers key
            if "search_providers" in self.cpath_setting:
                item = default_xmls["search_providers"]
            else:
                return

        final_format = item[1].format(includes_type=item[2])

        # For widget types, append an empty spotlight tabs include so the
        # spotlight layout has a valid include to reference even when no
        # widgets are configured.
        spotlight_include = _SPOTLIGHT_INCLUDE_NAMES.get(self.media_type)
        if spotlight_include and self.path_type == "widget":
            empty_spotlight = '\n\n    <include name="%s">\n    </include>' % spotlight_include
            final_format = final_format.replace("\n</includes>", empty_spotlight + "\n</includes>", 1)

        xml_file = "special://skin/xml/%s.xml" % item[0]
        with xbmcvfs.File(xml_file, "w") as f:
            f.write(final_format)
        self.update_skin_strings()
        Thread(target=self.reload_skin).start()

    def widget_header(self, default_header):
        header = dialog.input("Set widget label", defaultt=default_header)
        return header or None

    def main_menu_header(self, default_header):
        header = dialog.input("Set Main Menu label", defaultt=default_header)
        return header or None

    def search_provider_header(self, default_header):
        """Prompt for search provider label."""
        header = dialog.input("Set search provider label", defaultt=default_header)
        return header or None

    def get_widget_type(self, cpath_type):
        for widget_type, widget_list_type in widget_types:
            if widget_list_type == cpath_type:
                return widget_type
            elif "Stacked" in cpath_type and widget_list_type in cpath_type:
                return widget_type
        return None

    def widget_type(self, label="Choose widget display type", type_limit=7):
        choice = dialog.select(label, [i[0] for i in widget_types[0:type_limit]])
        if choice == -1:
            return None
        return widget_types[choice]

    def update_skin_strings(self):
        movie_cpath = self.fetch_one_cpath("movie.main_menu")
        tvshow_cpath = self.fetch_one_cpath("tvshow.main_menu")
        custom1_cpath = self.fetch_one_cpath("custom1.main_menu")
        custom2_cpath = self.fetch_one_cpath("custom2.main_menu")
        custom3_cpath = self.fetch_one_cpath("custom3.main_menu")

        movie_cpath_header = movie_cpath.get("cpath_header") if movie_cpath else None
        tvshow_cpath_header = tvshow_cpath.get("cpath_header") if tvshow_cpath else None
        custom1_cpath_header = (
            custom1_cpath.get("cpath_header") if custom1_cpath else None
        )
        custom2_cpath_header = (
            custom2_cpath.get("cpath_header") if custom2_cpath else None
        )
        custom3_cpath_header = (
            custom3_cpath.get("cpath_header") if custom3_cpath else None
        )

        default_movie_string_id = 342
        default_tvshow_string_id = 20343
        default_custom1_string = "Custom 1"
        default_custom2_string = "Custom 2"
        default_custom3_string = "Custom 3"

        movie_header_final = (
            movie_cpath_header
            if movie_cpath_header
            else xbmc.getLocalizedString(default_movie_string_id)
        )
        tvshow_header_final = (
            tvshow_cpath_header
            if tvshow_cpath_header
            else xbmc.getLocalizedString(default_tvshow_string_id)
        )
        custom1_header_final = (
            custom1_cpath_header if custom1_cpath_header else default_custom1_string
        )
        custom2_header_final = (
            custom2_cpath_header if custom2_cpath_header else default_custom2_string
        )
        custom3_header_final = (
            custom3_cpath_header if custom3_cpath_header else default_custom3_string
        )

        # --- FIXED VARIABLE NAMES BELOW ---
        xbmc.executebuiltin(
            "Skin.SetString(MenuMovieLabel,%s)" % movie_header_final
        )
        xbmc.executebuiltin(
            "Skin.SetString(MenuTVShowLabel,%s)" % tvshow_header_final
        )
        xbmc.executebuiltin(
            "Skin.SetString(MenuCustom1Label,%s)"
            % custom1_header_final
        )
        xbmc.executebuiltin(
            "Skin.SetString(MenuCustom2Label,%s)"
            % custom2_header_final
        )
        xbmc.executebuiltin(
            "Skin.SetString(MenuCustom3Label,%s)"
            % custom3_header_final
        )

def files_get_directory(directory, properties=["title", "file", "thumbnail"]):
    command = {
        "jsonrpc": "2.0",
        "id": "plugin.video.fen",
        "method": "Files.GetDirectory",
        "params": {"directory": directory, "media": "files", "properties": properties},
    }
    try:
        results = [
            i
            for i in get_jsonrpc(command).get("files")
            if i["file"].startswith("plugin://") and i["filetype"] == "directory"
        ]
    except Exception:
        results = []
    return results


def get_jsonrpc(request):
    response = xbmc.executeJSONRPC(json.dumps(request))
    result = json.loads(response)
    return result.get("result", None)


def remake_all_cpaths(silent=False):
    for item in (
        "movie.widget",
        "tvshow.widget",
        "custom1.widget",
        "custom2.widget",
        "custom3.widget",
    ):
        CPaths(item).remake_widgets()
    for item in (
        "movie.main_menu",
        "tvshow.main_menu",
        "custom1.main_menu",
        "custom2.main_menu",
        "custom3.main_menu",
    ):
        CPaths(item).remake_main_menus()
    
    # Remake search providers
    CPaths("search_providers").remake_search_providers()
    
    if not silent:
        xbmcgui.Dialog().ok("littleduck", "Menus, widgets, and search providers remade")


def starting_widgets():
    window = xbmcgui.Window(10000)
    window.setProperty("littleduck.starting_widgets", "finished")
    for item in (
        "movie.widget",
        "tvshow.widget",
        "custom1.widget",
        "custom2.widget",
        "custom3.widget",
    ):
        try:
            active_cpaths = CPaths(item).fetch_current_cpaths()
            if not active_cpaths:
                continue
            widget_type = item.split(".")[0]
            widget_type_id = {
                "movie": 19010,
                "tvshow": 22010,
                "custom1": 23010,
                "custom2": 24010,
                "custom3": 25010,
            }
            base_list_id = widget_type_id.get(widget_type)
            for count in range(1, 11):
                active_widget = active_cpaths.get(count, {})
                if not active_widget:
                    continue
                if not "Stacked" in active_widget["cpath_label"]:
                    continue
                cpath_setting = active_widget["cpath_setting"]
                if not cpath_setting:
                    continue
                try:
                    list_id = base_list_id + int(cpath_setting.split(".")[2])
                except (ValueError, IndexError):
                    continue
                try:
                    first_item = files_get_directory(active_widget["cpath_path"])[0]
                except Exception:
                    continue
                if not first_item:
                    continue
                cpath_label, cpath_path = first_item["label"], first_item["file"]
                window.setProperty("littleduck.%s.label" % list_id, cpath_label)
                window.setProperty("littleduck.%s.path" % list_id, cpath_path)
        except Exception:
            pass
    del window


def show_busy_dialog():
    return xbmc.executebuiltin("ActivateWindow(busydialognocancel)")


def hide_busy_dialog():
    xbmc.executebuiltin("Dialog.Close(busydialognocancel)")
    xbmc.executebuiltin("Dialog.Close(busydialog)")
