# -*- coding: utf-8 -*-

media_xml_start = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="{main_include}">'

media_xml_end = "\
\n    </include>\
\n</includes>"

# ----- Spotlight tab switcher templates -----
# Appended as a second <include> block in the same widget XML file.
# Tab slots use numeric values (1-10) to match the widget slot numbers.

spotlight_tabs_start = (
    '\n\n    <include name="{spotlight_include}">'
    '\n        <control type="grouplist">'
    '\n            <left>75</left>'
    '\n            <top>80</top>'
    '\n            <height>50</height>'
    '\n            <width>1845</width>'
    '\n            <orientation>horizontal</orientation>'
    '\n            <itemgap>20</itemgap>'
)

spotlight_tab_button = (
    '\n                <control type="group">'
    '\n                    <width>{group_width}</width>'
    '\n                    <height>50</height>'
    '\n                    <defaultcontrol>{tab_btn_id}</defaultcontrol>'
    '\n                    <control type="button" id="{tab_btn_id}">'
    '\n                        <left>0</left>'
    '\n                        <top>0</top>'
    '\n                        <width>auto</width>'
    '\n                        <height>40</height>'
    '\n                        <label>{cpath_header}</label>'
    '\n                        <font>font25_title</font>'
    '\n                        <textcolor>unfocused_text</textcolor>'
    '\n                        <focusedcolor>accent_color</focusedcolor>'
    '\n                        <shadowcolor>text_shadow</shadowcolor>'
    '\n                        <align>left</align>'
    '\n                        <aligny>center</aligny>'
    '\n                        <texturefocus />'
    '\n                        <texturenofocus />'
    '\n                        <onfocus>SetProperty(spotlight.{section}.tab,{slot},home)</onfocus>'
    '\n                        <onfocus>SetProperty(spotlight.{section}.path,{cpath_path},home)</onfocus>'
    '\n                        <onfocus>Skin.SetString(spotlight.{section}.type,{type_value})</onfocus>'
    '\n                        <onleft>{prev_btn}</onleft>'
    '\n                        <onright>{next_btn}</onright>'
    '\n                        <onup>9000</onup>'
    '\n                        <ondown condition="String.IsEqual(Skin.String(spotlight.{section}.type),landscape)">{landscape_id}</ondown>'
    '\n                        <ondown condition="String.IsEqual(Skin.String(spotlight.{section}.type),landscapeinfo)">{landscapeinfo_id}</ondown>'
    '\n                        <ondown condition="String.IsEqual(Skin.String(spotlight.{section}.type),walll)">{walll_id}</ondown>'
    '\n                        <ondown condition="String.IsEqual(Skin.String(spotlight.{section}.type),wallp)">{wallp_id}</ondown>'
    '\n                        <ondown>{section_list_id}</ondown>'
    '\n                    </control>'
    '\n                    <control type="image">'
    '\n                        <left>0</left>'
    '\n                        <top>43</top>'
    '\n                        <right>0</right>'
    '\n                        <height>3</height>'
    '\n                        <texture colordiffuse="accent_color">colors/white.png</texture>'
    '\n                        <visible>{active_condition}</visible>'
    '\n                    </control>'
    '\n                </control>'
)

spotlight_tab_bar_end = '\n        </control>'

spotlight_tab_list = (
    '\n        <include content="SpotlightTabList">'
    '\n            <param name="content_path" value="{cpath_path}"/>'
    '\n            <param name="widget_target" value="videos"/>'
    '\n            <param name="list_id" value="{list_id}"/>'
    '\n            <param name="tab_up_id" value="{tab_btn_id}"/>'
    '\n            <param name="tab_visible">{visible_condition}</param>'
    '\n        </include>'
)

spotlight_tabs_end = '\n    </include>'

media_xml_body = '\
\n        <include content="{cpath_type}">\
\n            <param name="content_path" value="{cpath_path}"/>\
\n            <param name="widget_header" value="{cpath_header}"/>\
\n            <param name="widget_target" value="videos"/>\
\n            <param name="list_id" value="{cpath_list_id}"/>\
\n        </include>'

history_xml_body = "\
\n        <item>\
\n            <label>{spath}</label>\
\n            <onclick>RunScript(script.littleduck.helper,mode=re_search)</onclick>\
\n        </item>"

stacked_media_xml_body = '\
\n        <include content="WidgetListCategoryStacked">\
\n            <param name="content_path" value="{cpath_path}"/>\
\n            <param name="widget_header" value="{cpath_header}"/>\
\n            <param name="widget_target" value="videos"/>\
\n            <param name="list_id" value="{cpath_list_id}"/>\
\n        </include>\
\n        <include content="{cpath_type}">\
\n            <param name="content_path" value="$INFO[Window(Home).Property(littleduck.{cpath_list_id}.path)]"/>\
\n            <param name="widget_header" value="$INFO[Window(Home).Property(littleduck.{cpath_list_id}.label)]"/>\
\n            <param name="widget_target" value="videos"/>\
\n            <param name="list_id" value="{cpath_list_id}1"/>\
\n        </include>'

main_menu_movies_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="MoviesMainMenu">\
\n        <item>\
\n            <label>{cpath_header}</label>\
\n            <onclick>ActivateWindow(Videos,{main_menu_path},return)</onclick>\
\n            <property name="menu_id">$NUMBER[19000]</property>\
\n            <thumb>icons/sidemenu/movie-custom.png</thumb>\
\n            <property name="id">movies</property>\
\n            <visible>!Skin.HasSetting(HomeMenuNoMovieButton)</visible>\
\n        </item>\
\n    </include>\
\n</includes>'

main_menu_tvshows_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="TVShowsMainMenu">\
\n        <item>\
\n            <label>{cpath_header}</label>\
\n            <onclick>ActivateWindow(Videos,{main_menu_path},return)</onclick>\
\n            <property name="menu_id">$NUMBER[22000]</property>\
\n            <thumb>icons/sidemenu/tv-show-custom.png</thumb>\
\n            <property name="id">tvshows</property>\
\n            <visible>!Skin.HasSetting(HomeMenuNoTVShowsButton)</visible>\
\n        </item>\
\n    </include>\
\n</includes>'

main_menu_custom1_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="Custom1MainMenu">\
\n        <item>\
\n            <label>{cpath_header}</label>\
\n            <onclick>ActivateWindow(Videos,{main_menu_path},return)</onclick>\
\n            <property name="menu_id">$NUMBER[23000]</property>\
\n            <thumb>icons/sidemenu/home.png</thumb>\
\n            <property name="id">custom1</property>\
\n        </item>\
\n    </include>\
\n</includes>'

main_menu_custom2_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="Custom2MainMenu">\
\n        <item>\
\n            <label>{cpath_header}</label>\
\n            <onclick>ActivateWindow(Videos,{main_menu_path},return)</onclick>\
\n            <property name="menu_id">$NUMBER[24000]</property>\
\n            <thumb>icons/sidemenu/anime.png</thumb>\
\n            <property name="id">custom2</property>\
\n            <visible>!Skin.HasSetting(HomeMenuNoCustom2Button)</visible>\
\n        </item>\
\n    </include>\
\n</includes>'

main_menu_custom3_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="Custom3MainMenu">\
\n        <item>\
\n            <label>{cpath_header}</label>\
\n            <onclick>ActivateWindow(Videos,{main_menu_path},return)</onclick>\
\n            <property name="menu_id">$NUMBER[25000]</property>\
\n            <thumb>icons/sidemenu/list.png</thumb>\
\n            <property name="id">custom3</property>\
\n            <visible>!Skin.HasSetting(HomeMenuNoCustom3Button)</visible>\
\n        </item>\
\n    </include>\
\n</includes>'

search_history_xml = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="SearchHistory">\
\n        <item>\
\n            <label>{spath}</label>\
\n            <onclick>RunScript(script.littleduck.helper,mode=re_search)</onclick>\
\n        </item>\
\n    </include>\
\n</includes>'

# Search Providers XML Templates
search_providers_xml_start = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="SearchProviders">'

search_providers_xml_end = "\
\n    </include>\
\n</includes>"

search_provider_xml_body = '\
\n        <item>\
\n            <label>{provider_name}</label>\
\n            <onclick>ActivateWindow(Videos,{provider_path}&query=$INFO[Skin.String(SearchInputEncoded)],return)</onclick>\
\n            <property name="provider_id">{provider_number}</property>\
\n        </item>'

# Default XML templates
default_widget = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="{includes_type}">\
\n    </include>\
\n</includes>'

default_main_menu = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="{includes_type}">\
\n    </include>\
\n</includes>'

default_history = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="{includes_type}">\
\n    </include>\
\n</includes>'

default_search_providers = '\
<?xml version="1.0" encoding="UTF-8"?>\
\n<includes>\
\n    <include name="{includes_type}">\
\n    </include>\
\n</includes>'
