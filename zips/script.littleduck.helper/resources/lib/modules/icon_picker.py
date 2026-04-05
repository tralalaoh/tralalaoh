# -*- coding: utf-8 -*-
"""
Icon Picker dialog for skin.littleduck.
Allows the user to choose a menu icon from:
  - Side Menu  (icons/sidemenu/)
  - Logos      (icons/logo/)
  - Emoji      (icons/emoji/)
Or browse the filesystem for a custom image.
"""
import os
import unicodedata
import xbmc
import xbmcgui
import xbmcvfs
import xbmcaddon

# ── Control IDs (must match Custom_1120_IconPicker.xml) ───────────────────────
CTRL_GRID         = 200
CTRL_SCROLLBAR    = 201
CTRL_SEARCH       = 300
CTRL_CLEAR        = 301
CTRL_TAB_SIDEMENU = 400
CTRL_TAB_LOGOS    = 401
CTRL_TAB_EMOJI    = 402
CTRL_BROWSE       = 500
CTRL_CANCEL       = 9991

# ── Constants ─────────────────────────────────────────────────────────────────
SKIN_MEDIA = 'special://skin/media/'
XML_FILE   = 'Custom_1120_IconPicker.xml'

# Built-in side-menu icons with display names
SIDEMENU_ICONS = [
    ("Addons",           "icons/sidemenu/addons.png"),
    ("Android",          "icons/sidemenu/android.png"),
    ("Anime",            "icons/sidemenu/anime.png"),
    ("Disc",             "icons/sidemenu/disc.png"),
    ("Download",         "icons/sidemenu/download.png"),
    ("Favourite Star",   "icons/sidemenu/favorite-custom.png"),
    ("Favourites",       "icons/sidemenu/favourites.png"),
    ("Games",            "icons/sidemenu/games.png"),
    ("Home",             "icons/sidemenu/home.png"),
    ("List",             "icons/sidemenu/list.png"),
    ("Live TV",          "icons/sidemenu/livetv.png"),
    ("Manage",           "icons/sidemenu/manage.png"),
    ("Movies Classic",   "icons/sidemenu/movies.png"),
    ("Movies Custom",    "icons/sidemenu/movie-custom.png"),
    ("Music",            "icons/sidemenu/music.png"),
    ("Music Videos",     "icons/sidemenu/musicvideos.png"),
    ("Pictures",         "icons/sidemenu/pictures.png"),
    ("Programs",         "icons/sidemenu/programs.png"),
    ("Radio",            "icons/sidemenu/radio.png"),
    ("TV",               "icons/sidemenu/tv.png"),
    ("TV Shows Custom",  "icons/sidemenu/tv-show-custom.png"),
    ("Videos",           "icons/sidemenu/videos.png"),
    ("Weather",          "icons/sidemenu/weather.png"),
]


def _nice_name(stem):
    """Turn a filename stem into a display name (title-case, spaces)."""
    return stem.replace('-', ' ').replace('_', ' ').replace('.', ' ').title()


def _emoji_name(stem):
    """
    Derive a short human-readable name from an emoji codepoint filename.
    stem examples: '1F004', '1F1E6-1F1E8', '0023-20E3'

    Rules applied (in order):
    - Two Regional Indicator letters → 'Flag XX'  (e.g. Flag AC, Flag AD)
    - Keycap sequences (digit/char + 20E3) → drop the enclosing suffix
    - Everything else → first 3 words of the unicode name
    """
    parts = stem.split('-')
    try:
        chars = ''.join(chr(int(p, 16)) for p in parts)
    except (ValueError, OverflowError):
        return stem

    raw_names = []
    for ch in chars:
        try:
            raw_names.append(unicodedata.name(ch))
        except ValueError:
            raw_names.append(hex(ord(ch)))

    joined = ' '.join(raw_names).upper()

    # Flags: two "REGIONAL INDICATOR SYMBOL LETTER X" → "Flag XY"
    if joined.count('REGIONAL INDICATOR') == 2:
        letters = [n.split()[-1] for n in raw_names if 'REGIONAL INDICATOR' in n]
        return 'Flag ' + ''.join(letters)

    # Single regional indicator
    if 'REGIONAL INDICATOR' in joined:
        letter = raw_names[0].split()[-1]
        return f'Flag {letter}'

    # Keycap sequences: drop "COMBINING ENCLOSING KEYCAP" suffix
    if 'COMBINING ENCLOSING KEYCAP' in joined:
        base = raw_names[0].title().replace('Digit ', '').replace('Number Sign', '#')
        return f'Keycap {base}'

    # General: first 3 words, title-case
    words = ' '.join(raw_names).title().split()
    return ' '.join(words[:3])


def _scan_folder(rel_folder, name_func):
    """
    Scan a skin media sub-folder and return list of (display_name, rel_path).
    rel_folder: e.g. 'icons/logo'
    name_func:  callable(stem) → display name
    """
    real_dir = xbmcvfs.translatePath(SKIN_MEDIA + rel_folder)
    items = []
    try:
        for fname in sorted(os.listdir(real_dir)):
            if fname.lower().endswith('.png'):
                stem = os.path.splitext(fname)[0]
                items.append((name_func(stem), f'{rel_folder}/{fname}'))
    except Exception as exc:
        xbmc.log(f'###littleduck icon_picker: error scanning {rel_folder}: {exc}', 2)
    return items


# Build category data once at import time (keeps onClick snappy)
_LOGO_ICONS  = _scan_folder('icons/logo',  _nice_name)
_EMOJI_ICONS = _scan_folder('icons/emoji', _emoji_name)

CATEGORY_DATA = {
    'sidemenu': SIDEMENU_ICONS,
    'logos':    _LOGO_ICONS,
    'emoji':    _EMOJI_ICONS,
}

TAB_CONTROLS = {
    'sidemenu': CTRL_TAB_SIDEMENU,
    'logos':    CTRL_TAB_LOGOS,
    'emoji':    CTRL_TAB_EMOJI,
}


# ── Dialog class ──────────────────────────────────────────────────────────────

class IconPickerDialog(xbmcgui.WindowXMLDialog):
    """
    Usage:
        dlg = IconPickerDialog(XML_FILE, addon_path, 'Default', '1080i',
                               setting='menu.movies.icon')
        dlg.doModal()
        del dlg
    """

    def __init__(self, *args, **kwargs):
        self._setting  = kwargs.pop('setting', '')
        self._category = 'sidemenu'
        self._search   = ''
        super().__init__(*args, **kwargs)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def onInit(self):
        self._populate()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _populate(self):
        """Rebuild the grid based on current category + search filter."""
        source      = CATEGORY_DATA.get(self._category, SIDEMENU_ICONS)
        query_lower = self._search.lower().strip()

        grid = self.getControl(CTRL_GRID)
        grid.reset()

        for name, rel_path in source:
            if query_lower and query_lower not in name.lower():
                continue
            li = xbmcgui.ListItem(label=name)
            full = SKIN_MEDIA + rel_path
            li.setArt({'thumb': full, 'icon': full})
            li.setProperty('icon_path', rel_path)
            grid.addItem(li)

        self._update_search_label()
        self._update_tab_labels()

    def _update_search_label(self):
        try:
            btn = self.getControl(CTRL_SEARCH)
            if self._search:
                btn.setLabel(f'[COLOR grey]Search: [/COLOR]{self._search}')
            else:
                btn.setLabel('[COLOR grey]Search icons...[/COLOR]')
        except Exception:
            pass

    def _update_tab_labels(self):
        labels = {
            'sidemenu': ('Side Menu', CTRL_TAB_SIDEMENU),
            'logos':    ('Logos',     CTRL_TAB_LOGOS),
            'emoji':    ('Emoji',     CTRL_TAB_EMOJI),
        }
        for cat, (label, cid) in labels.items():
            try:
                ctrl = self.getControl(cid)
                if cat == self._category:
                    ctrl.setLabel(f'[B]{label}[/B]')
                    # Also boost alpha so active tab looks brighter
                    ctrl.setColorDiffuse('FFFFFFFF')
                else:
                    ctrl.setLabel(label)
                    ctrl.setColorDiffuse('AAFFFFFF')
            except Exception:
                pass

    def _switch_category(self, cat):
        if cat == self._category:
            return
        self._category = cat
        self._search   = ''
        self._populate()

    # ── Event handlers ────────────────────────────────────────────────────────

    def onClick(self, controlId):
        # ── Category tabs ──────────────────────────────────────────────────
        if controlId == CTRL_TAB_SIDEMENU:
            self._switch_category('sidemenu')

        elif controlId == CTRL_TAB_LOGOS:
            self._switch_category('logos')

        elif controlId == CTRL_TAB_EMOJI:
            self._switch_category('emoji')

        # ── Search ─────────────────────────────────────────────────────────
        elif controlId == CTRL_SEARCH:
            kb = xbmc.Keyboard(self._search, 'Search Icons')
            kb.doModal()
            if kb.isConfirmed():
                self._search = kb.getText().strip()
                self._populate()

        elif controlId == CTRL_CLEAR:
            self._search = ''
            self._populate()

        # ── Browse filesystem ───────────────────────────────────────────────
        elif controlId == CTRL_BROWSE:
            image_file = xbmcgui.Dialog().browse(
                2, 'Choose Icon Image', 'network', '.jpg|.png|.bmp', False, False
            )
            if image_file:
                xbmc.executebuiltin(f'Skin.SetString({self._setting},{image_file})')
                self.close()

        # ── Icon selected from grid ─────────────────────────────────────────
        elif controlId == CTRL_GRID:
            item = self.getControl(CTRL_GRID).getSelectedItem()
            if item:
                path = item.getProperty('icon_path')
                if path:
                    xbmc.executebuiltin(f'Skin.SetString({self._setting},{path})')
                    self.close()

        # ── Cancel / close ──────────────────────────────────────────────────
        elif controlId == CTRL_CANCEL:
            self.close()

    def onAction(self, action):
        if action.getId() in (xbmcgui.ACTION_PREVIOUS_MENU, xbmcgui.ACTION_NAV_BACK):
            self.close()
        else:
            super().onAction(action)


# ── Public entry point ────────────────────────────────────────────────────────

def show_icon_picker(setting):
    """
    Launch the icon picker dialog for the given Skin.String setting name.
    Blocks until the user selects an icon or cancels.
    """
    addon_path = xbmcvfs.translatePath(
        xbmcaddon.Addon('script.littleduck.helper').getAddonInfo('path')
    )
    dlg = IconPickerDialog(XML_FILE, addon_path, 'Default', '1080i', setting=setting)
    dlg.doModal()
    del dlg
