# -*- coding: utf-8 -*-
import xbmc, xbmcgui, xbmcvfs
import xml.etree.ElementTree as ET
from xml.dom import minidom

KEYMAP_LOCATION = "special://userdata/keymaps/"
POSSIBLE_KEYMAP_NAMES = ["gen.xml", "keyboard.xml", "keymap.xml"]


def set_image():
    image_file = xbmcgui.Dialog().browse(
        2, "Choose Custom Background Image", "network", ".jpg|.png|.bmp", False, False
    )
    if image_file:
        xbmc.executebuiltin("Skin.SetString(CustomBackground,%s)" % image_file)


def pick_menu_icon(params):
    setting = params.get("setting")
    if not setting:
        return
    from modules.icon_picker import show_icon_picker
    show_icon_picker(setting)


def fix_black_screen():
    if xbmc.getCondVisibility("Skin.HasSetting(TrailerPlaying)"):
        xbmc.executebuiltin("Skin.ToggleSetting(TrailerPlaying)")


def make_backup(keymap_path):
    backup_path = f"{keymap_path}.backup"
    if not xbmcvfs.exists(backup_path):
        xbmcvfs.copy(keymap_path, backup_path)


def restore_from_backup(keymap_path):
    backup_path = f"{keymap_path}.backup"
    if xbmcvfs.exists(backup_path):
        xbmcvfs.delete(keymap_path)
        xbmcvfs.rename(backup_path, keymap_path)


def get_all_existing_keymap_paths():
    existing_paths = []
    for name in POSSIBLE_KEYMAP_NAMES:
        path = xbmcvfs.translatePath(f"special://profile/keymaps/{name}")
        if xbmcvfs.exists(path):
            existing_paths.append(path)
    return existing_paths


def set_tmdb_key():
    """Prompt user to enter their TMDb API key."""
    keyboard = xbmc.Keyboard("", "Enter TMDb API Key")
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        api_key = keyboard.getText().strip()
        if api_key:
            xbmc.executebuiltin(f"Skin.SetString(tmdb_api_key,{api_key})")
            xbmcgui.Dialog().notification(
                "littleduck", 
                "TMDb API Key Saved",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )
        else:
            xbmcgui.Dialog().notification(
                "littleduck", 
                "No API Key Entered",
                xbmcgui.NOTIFICATION_WARNING,
                2000
            )


def set_tvdb_key():
    """Prompt user to enter their TVDb API key."""
    keyboard = xbmc.Keyboard("", "Enter TVDb API Key")
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        api_key = keyboard.getText().strip()
        if api_key:
            xbmc.executebuiltin(f"Skin.SetString(tvdb_api_key,{api_key})")
            xbmcgui.Dialog().notification(
                "littleduck", 
                "TVDb API Key Saved",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )
        else:
            xbmcgui.Dialog().notification(
                "littleduck", 
                "No API Key Entered",
                xbmcgui.NOTIFICATION_WARNING,
                2000
            )


def set_rpdb_key():
    """Prompt user to enter their RPDB (RatingPosterDB) API key."""
    keyboard = xbmc.Keyboard("", "Enter RPDB API Key")
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        api_key = keyboard.getText().strip()
        if api_key:
            xbmc.executebuiltin(f"Skin.SetString(rpdb_api_key,{api_key})")
            xbmcgui.Dialog().notification(
                "littleduck", 
                "RPDB API Key Saved",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )
        else:
            xbmcgui.Dialog().notification(
                "littleduck", 
                "No API Key Entered",
                xbmcgui.NOTIFICATION_WARNING,
                2000
            )


def set_mdblist_key():
    """Prompt user to enter their MDbList API key."""
    keyboard = xbmc.Keyboard("", "Enter MDbList API Key")
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        api_key = keyboard.getText().strip()
        if api_key:
            xbmc.executebuiltin(f"Skin.SetString(mdblist_api_key,{api_key})")
            xbmcgui.Dialog().notification(
                "littleduck", 
                "MDbList API Key Saved",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )
        else:
            xbmcgui.Dialog().notification(
                "littleduck", 
                "No API Key Entered",
                xbmcgui.NOTIFICATION_WARNING,
                2000
            )


def set_omdb_key():
    """Prompt user to enter their OMDb API key."""
    keyboard = xbmc.Keyboard("", "Enter OMDb API Key")
    keyboard.doModal()
    if keyboard.isConfirmed() and keyboard.getText():
        api_key = keyboard.getText().strip()
        if api_key:
            xbmc.executebuiltin(f"Skin.SetString(omdb_api_key,{api_key})")
            xbmcgui.Dialog().notification(
                "littleduck",
                "OMDb API Key Saved",
                xbmcgui.NOTIFICATION_INFO,
                2000
            )
        else:
            xbmcgui.Dialog().notification(
                "littleduck",
                "No API Key Entered",
                xbmcgui.NOTIFICATION_WARNING,
                2000
            )


def manage_trailer_playback(params):
    enabled = params.get("enabled")
    keymap_paths = get_all_existing_keymap_paths()
    if not keymap_paths:
        keymap_path = xbmcvfs.translatePath(KEYMAP_LOCATION + "gen.xml")
        root = ET.Element("keymap")
        keyboard_tag = ET.SubElement(root, "keyboard")
    else:
        keymap_path = keymap_paths[0]
        make_backup(keymap_path)
        tree = ET.parse(keymap_path)
        root = tree.getroot()
        keyboard_tag = root.find("keyboard")
        if keyboard_tag is None:
            keyboard_tag = ET.SubElement(root, "keyboard")

    def has_play_trailer_tag(tag):
        return "play_trailer" in tag.text if tag.text else False

    t_key_tags = [tag for tag in keyboard_tag.findall("t") if has_play_trailer_tag(tag)]
    play_pause_tags = [
        tag
        for tag in keyboard_tag.findall("play_pause")
        if has_play_trailer_tag(tag)
    ]
    if enabled:
        if t_key_tags:
            t_key_tags[
                0
            ].text = "RunScript(script.littleduck.helper, mode=play_trailer)"
            for tag in t_key_tags[1:]:
                keyboard_tag.remove(tag)
        else:
            t_key_tag = ET.SubElement(keyboard_tag, "t")
            t_key_tag.text = "RunScript(script.littleduck.helper, mode=play_trailer)"
        if play_pause_tags:
            play_pause_tags[
                0
            ].text = "RunScript(script.littleduck.helper, mode=play_trailer)"
            for tag in play_pause_tags[1:]:
                keyboard_tag.remove(tag)
        else:
            play_pause_tag = ET.SubElement(
                keyboard_tag, "play_pause", mod="longpress"
            )
            play_pause_tag.text = (
                "RunScript(script.littleduck.helper, mode=play_trailer)"
            )
    else:
        for tag_list in [play_pause_tags, t_key_tags]:
            for tag in tag_list:
                if has_play_trailer_tag(tag):
                    keyboard_tag.remove(tag)
    xml_string = ET.tostring(root, encoding="utf-8").decode("utf-8")
    pretty_xml = minidom.parseString(xml_string).toprettyxml(indent="  ")
    pretty_xml = "\n".join(
        [line for line in pretty_xml.split("\n") if line.strip()]
    )
    with xbmcvfs.File(keymap_path, "w") as xml_file:
        xml_file.write(pretty_xml)
    xbmc.executebuiltin("Action(reloadkeymaps)")
