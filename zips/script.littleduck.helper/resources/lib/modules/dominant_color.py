# -*- coding: utf-8 -*-
"""
dominant_color.py — extract dominant color from the current fanart and set
Window(Home).Property(fanart.bgcolor) for the FanartColorBg skin setting.

Uses the same path-resolution technique as script.embuary.helper's _openimage:
strips image:// wrapper, probes the Kodi thumbnail cache, falls back to direct
access.  Color is obtained by blurring to 200x200 then squeezing to 1x1.
"""
import os
import xbmc
import xbmcgui
import xbmcvfs

try:
    from urllib.parse import unquote as url_unquote
except ImportError:
    from urllib import unquote as url_unquote

try:
    from PIL import Image, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    xbmc.log('###littleduck dominant_color: PIL not available', 2)

_color_cache = {}   # image_path (original) -> 'FFRRGGBB'


def _openimage(image):
    """
    Resolve any Kodi image path to a PIL Image.
    Mirrors script.embuary.helper image._openimage closely so the same
    cached thumbnails are found.
    """
    if not image:
        return None

    # Strip image:// wrapper + URL-decode  (embuary does the same)
    bare = url_unquote(image.replace('image://', ''))
    if bare.endswith('/'):
        bare = bare[:-1]

    # Build candidate thumbnail-cache paths (Kodi stores thumbs as *.jpg / *.png)
    candidates = []
    for src in [xbmc.getCacheThumbName(bare), xbmc.getCacheThumbName(image)]:
        base = 'special://profile/Thumbnails/%s/' % src[0]
        candidates += [
            base + src[:-4] + '.jpg',
            base + src[:-4] + '.png',
            'special://profile/Thumbnails/Video/%s/%s' % (src[0], src),
        ]

    for cache in candidates:
        if xbmcvfs.exists(cache):
            try:
                return Image.open(xbmcvfs.translatePath(cache))
            except Exception:
                continue

    # Last resort: direct path (works for local library fanart)
    if xbmcvfs.exists(image):
        try:
            return Image.open(xbmcvfs.translatePath(image))
        except Exception:
            pass

    return None


def _extract_color(image_path):
    """
    Blur to 200x200, squeeze to 1x1, return average as 'FFRRGGBB'.
    Darkens by 0.65 so the colour is usable as a readable background.
    Returns '' on failure.
    """
    if image_path in _color_cache:
        return _color_cache[image_path]

    img = _openimage(image_path)
    if img is None:
        return ''

    try:
        img = img.resize((200, 200), Image.LANCZOS)
        img = img.convert('RGB')
        img = img.filter(ImageFilter.GaussianBlur(30))
        col = img.resize((1, 1), Image.LANCZOS).getpixel((0, 0))
        # Darken 65% — keeps the hue visible while staying readable as bg
        r = max(15, int(col[0] * 0.65))
        g = max(15, int(col[1] * 0.65))
        b = max(15, int(col[2] * 0.65))
        color = 'FF%02X%02X%02X' % (r, g, b)

        if len(_color_cache) >= 200:
            for k in list(_color_cache.keys())[:50]:
                del _color_cache[k]
        _color_cache[image_path] = color
        return color

    except Exception as e:
        xbmc.log('###littleduck dominant_color extract: %s' % e, 2)
        return ''


def update_fanart_bgcolor(fanart_art_label):
    """
    Called from listitem_monitor whenever the focused item changes.
    Sets (or clears) Window(Home).Property(fanart.bgcolor).
    """
    home = xbmcgui.Window(10000)

    if not PIL_AVAILABLE:
        return
    if not xbmc.getCondVisibility('Skin.HasSetting(FanartColorBg)'):
        home.setProperty('fanart.bgcolor', '')
        return
    if not fanart_art_label:
        home.setProperty('fanart.bgcolor', '')
        return

    color = _extract_color(fanart_art_label)
    home.setProperty('fanart.bgcolor', color)
