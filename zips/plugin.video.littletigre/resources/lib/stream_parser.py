# -*- coding: utf-8 -*-
"""
stream_parser.py — AIOStreams-compatible stream metadata detection for Kodi.

Detects from torrent filenames and Stremio stream objects:
  - Resolution     (2160p, 1080p, 720p, ...)
  - Quality/Source (BluRay REMUX, WEB-DL, WEBRip, ...)
  - Video codec    (HEVC, AVC, AV1, ...)
  - Audio codec    (Atmos, DTS-HD MA, TrueHD, DD+, ...)
  - Audio channels (7.1, 5.1, 2.0)
  - HDR/Visual     (Dolby Vision, HDR10+, HDR10, IMAX, ...)
  - Languages      (English, Multi, French, ...) — from filename patterns & flag emojis
  - Debrid service (Real-Debrid, TorBox, ...) + cache status
  - File size      (bytes, from text or behaviorHints)
  - Seeders        (from emoji patterns in description)
  - Info hash      (from URL or infoHash field)
  - Release group

Usage:
    from resources.lib.stream_parser import StreamParser, ICON_PATHS

    # Parse a filename string
    info = StreamParser.parse_filename("Movie.2024.1080p.BluRay.REMUX.HEVC.DTS-HD.MA.5.1-GROUP")
    # info['resolution'] == '1080p'
    # info['quality']    == 'BluRay REMUX'
    # info['encode']     == 'HEVC'
    # info['audio_tags'] == ['DTS-HD MA']

    # Parse a full Stremio stream dict
    result = StreamParser.parse_stream(stream_dict)
    # result['service'] == {'id': 'realdebrid', 'name': 'Real-Debrid', 'short': 'RD', 'cached': True}
    # result['icons']['resolution'] == '/path/to/res_1080p.png'

Icons:
    All icons live in  resources/media/icons/
    Place the PNG files listed in ICON_PATHS there.
    Already-existing icons: instant.png, cached.png, uncached.png
"""

from __future__ import absolute_import, unicode_literals

import re
import os

try:
    import xbmcaddon as _xbmcaddon
    _ADDON_PATH = _xbmcaddon.Addon().getAddonInfo('path')
except Exception:
    # Allow importing outside Kodi (unit tests, IDE, etc.)
    _ADDON_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_ICONS_DIR = os.path.join(_ADDON_PATH, 'resources', 'media', 'icons')


def _icon(filename):
    """Return full path to an icon in resources/media/icons/."""
    return os.path.join(_ICONS_DIR, filename)


def _icon_or(filename, fallback='lang_multi.png'):
    """
    Return path to icon if the file exists, else path to fallback icon.
    Used for service icons — falls back to diffuse placeholder until real logos are added.
    Drop a real PNG into resources/media/icons/<filename> and restart Kodi to pick it up.
    """
    path = os.path.join(_ICONS_DIR, filename)
    if os.path.isfile(path):
        return path
    return os.path.join(_ICONS_DIR, fallback)


# ─── Icon Path Map ─────────────────────────────────────────────────────────────
# Keys match what StreamParser returns in the 'icons' dict.
# Place the PNG files listed here in:  resources/media/icons/
#
# ALREADY EXISTS: instant.png, cached.png, uncached.png
# YOU NEED TO ADD: everything else below
ICON_PATHS = {
    # ── Cache / Playback speed (already exist) ────────────────────────────────
    'instant':          _icon('instant.png'),
    'cached':           _icon('cached.png'),
    'uncached':         _icon('uncached.png'),

    # ── Resolution ────────────────────────────────────────────────────────────
    'res_4k':           _icon('res_4k.png'),        # 2160p / 4K / UHD
    'res_1440p':        _icon('res_1440p.png'),     # 1440p / 2K / QHD
    'res_1080p':        _icon('res_1080p.png'),     # 1080p / FHD
    'res_720p':         _icon('res_720p.png'),      # 720p / HD
    'res_480p':         _icon('res_480p.png'),      # 480p / SD
    'res_576p':         _icon('res_576p.png'),      # 576p (PAL SD)
    'res_360p':         _icon('res_360p.png'),      # 360p
    'res_sd':           _icon('res_sd.png'),        # 240p / 144p

    # ── Source / Quality ─────────────────────────────────────────────────────
    'quality_remux':    _icon('quality_remux.png'),     # BluRay REMUX
    'quality_bluray':   _icon('quality_bluray.png'),    # BluRay / BDRip
    'quality_webdl':    _icon('quality_webdl.png'),     # WEB-DL
    'quality_webrip':   _icon('quality_webrip.png'),    # WEBRip
    'quality_hdrip':    _icon('quality_hdrip.png'),     # HDRip
    'quality_hchdrip':  _icon('quality_hchdrip.png'),   # HC HD-Rip
    'quality_dvdrip':   _icon('quality_dvdrip.png'),    # DVDRip
    'quality_hdtv':     _icon('quality_hdtv.png'),      # HDTV / TVRip
    'quality_cam':      _icon('quality_cam.png'),       # CAM / HDCAM
    'quality_ts':       _icon('quality_ts.png'),        # TS / TeleSync
    'quality_tc':       _icon('quality_tc.png'),        # TC / TeleCine
    'quality_scr':      _icon('quality_scr.png'),       # SCR / Screener

    # ── Video Codec ───────────────────────────────────────────────────────────
    'codec_hevc':       _icon('codec_hevc.png'),    # HEVC / H.265 / x265
    'codec_avc':        _icon('codec_avc.png'),     # AVC  / H.264 / x264
    'codec_av1':        _icon('codec_av1.png'),     # AV1
    'codec_xvid':       _icon('codec_xvid.png'),    # XviD
    'codec_divx':       _icon('codec_divx.png'),    # DivX

    # ── Audio Codec ───────────────────────────────────────────────────────────
    'audio_atmos':      _icon('audio_atmos.png'),       # Dolby Atmos
    'audio_ddplus':     _icon('audio_ddplus.png'),      # DD+ / EAC-3 / Dolby Digital Plus
    'audio_dd':         _icon('audio_dd.png'),          # DD / AC-3 / Dolby Digital
    'audio_dtsx':       _icon('audio_dtsx.png'),        # DTS:X
    'audio_dtshd_ma':   _icon('audio_dtshd_ma.png'),    # DTS-HD Master Audio
    'audio_dtshd':      _icon('audio_dtshd.png'),       # DTS-HD
    'audio_dts_es':     _icon('audio_dts_es.png'),      # DTS-ES
    'audio_dts':        _icon('audio_dts.png'),         # DTS
    'audio_truehd':     _icon('audio_truehd.png'),      # Dolby TrueHD
    'audio_opus':       _icon('audio_opus.png'),        # Opus
    'audio_aac':        _icon('audio_aac.png'),         # AAC / HE-AAC / QAAC
    'audio_flac':       _icon('audio_flac.png'),        # FLAC (lossless)

    # ── Audio Channels ────────────────────────────────────────────────────────
    'ch_71':            _icon('ch_71.png'),     # 7.1 surround
    'ch_61':            _icon('ch_61.png'),     # 6.1 surround
    'ch_51':            _icon('ch_51.png'),     # 5.1 surround
    'ch_20':            _icon('ch_20.png'),     # 2.0 stereo

    # ── HDR / Visual tags ─────────────────────────────────────────────────────
    'hdr_dv':           _icon('hdr_dv.png'),        # Dolby Vision
    'hdr_hdr10plus':    _icon('hdr_hdr10plus.png'), # HDR10+
    'hdr_hdr10':        _icon('hdr_hdr10.png'),     # HDR10
    'hdr_hdr':          _icon('hdr_hdr.png'),       # HDR (generic)
    'hdr_hlg':          _icon('hdr_hlg.png'),       # HLG (Hybrid Log-Gamma)
    'visual_imax':      _icon('visual_imax.png'),   # IMAX
    'visual_3d':        _icon('visual_3d.png'),     # 3D
    'visual_10bit':     _icon('visual_10bit.png'),  # 10-bit
    'visual_ai':        _icon('visual_ai.png'),     # AI upscaled
    'visual_sdr':       _icon('visual_sdr.png'),    # SDR
    'visual_hsbs':      _icon('visual_hsbs.png'),   # Half-SBS (3D)
    'visual_hou':       _icon('visual_hou.png'),    # Half Over-Under (3D)

    # ── Debrid / Cloud services ───────────────────────────────────────────────
    # Falls back to lang_multi.png (diffuse) until you drop a real logo into icons/.
    # To add a real logo: copy your PNG as resources/media/icons/service_rd.png etc.
    'service_rd':       _icon_or('service_rd.png'),     # Real-Debrid
    'service_tb':       _icon_or('service_tb.png'),     # TorBox
    'service_pm':       _icon_or('service_pm.png'),     # Premiumize
    'service_ad':       _icon_or('service_ad.png'),     # AllDebrid
    'service_dl':       _icon_or('service_dl.png'),     # Debrid-Link
    'service_en':       _icon_or('service_en.png'),     # Easynews
    'service_pk':       _icon_or('service_pk.png'),     # PikPak
    'service_sr':       _icon_or('service_sr.png'),     # Seedr
    'service_oc':       _icon_or('service_oc.png'),     # Offcloud
    'service_po':       _icon_or('service_po.png'),     # put.io
    'service_dbd':      _icon_or('service_dbd.png'),    # Debrider

    # ── Languages ─────────────────────────────────────────────────────────────
    'lang_multi':       _icon('lang_multi.png'),
    'lang_dual':        _icon('lang_dual.png'),
    'lang_dubbed':      _icon('lang_dubbed.png'),
    'lang_en':          _icon('lang_en.png'),       # English
    'lang_fr':          _icon('lang_fr.png'),       # French
    'lang_de':          _icon('lang_de.png'),       # German
    'lang_es':          _icon('lang_es.png'),       # Spanish
    'lang_pt':          _icon('lang_pt.png'),       # Portuguese
    'lang_it':          _icon('lang_it.png'),       # Italian
    'lang_ru':          _icon('lang_ru.png'),       # Russian
    'lang_ja':          _icon('lang_ja.png'),       # Japanese
    'lang_zh':          _icon('lang_zh.png'),       # Chinese
    'lang_ko':          _icon('lang_ko.png'),       # Korean
    'lang_ar':          _icon('lang_ar.png'),       # Arabic
    'lang_hi':          _icon('lang_hi.png'),       # Hindi
    'lang_tr':          _icon('lang_tr.png'),       # Turkish
    'lang_pl':          _icon('lang_pl.png'),       # Polish
    'lang_nl':          _icon('lang_nl.png'),       # Dutch
    'lang_sv':          _icon('lang_sv.png'),       # Swedish
    'lang_da':          _icon('lang_da.png'),       # Danish
    'lang_fi':          _icon('lang_fi.png'),       # Finnish
    'lang_no':          _icon('lang_no.png'),       # Norwegian
    'lang_cs':          _icon('lang_cs.png'),       # Czech
    'lang_hu':          _icon('lang_hu.png'),       # Hungarian
    'lang_ro':          _icon('lang_ro.png'),       # Romanian
    'lang_bg':          _icon('lang_bg.png'),       # Bulgarian
    'lang_sr':          _icon('lang_sr.png'),       # Serbian
    'lang_hr':          _icon('lang_hr.png'),       # Croatian
    'lang_sk':          _icon('lang_sk.png'),       # Slovak
    'lang_el':          _icon('lang_el.png'),       # Greek
    'lang_uk':          _icon('lang_uk.png'),       # Ukrainian
    'lang_he':          _icon('lang_he.png'),       # Hebrew
    'lang_fa':          _icon('lang_fa.png'),       # Persian
    'lang_th':          _icon('lang_th.png'),       # Thai
    'lang_vi':          _icon('lang_vi.png'),       # Vietnamese
    'lang_id':          _icon('lang_id.png'),       # Indonesian
    'lang_ms':          _icon('lang_ms.png'),       # Malay
    'lang_ta':          _icon('lang_ta.png'),       # Tamil
    'lang_te':          _icon('lang_te.png'),       # Telugu
    'lang_bn':          _icon('lang_bn.png'),       # Bengali
    'lang_ml':          _icon('lang_ml.png'),       # Malayalam
    'lang_mr':          _icon('lang_mr.png'),       # Marathi
    'lang_gu':          _icon('lang_gu.png'),       # Gujarati
    'lang_kn':          _icon('lang_kn.png'),       # Kannada
    'lang_pa':          _icon('lang_pa.png'),       # Punjabi
    'lang_lt':          _icon('lang_lt.png'),       # Lithuanian
    'lang_lv':          _icon('lang_lv.png'),       # Latvian
    'lang_et':          _icon('lang_et.png'),       # Estonian
    'lang_sl':          _icon('lang_sl.png'),       # Slovenian
    'lang_lat':         _icon('lang_lat.png'),      # Latino (Spanish Latin America)
}


# ─── Regex Builders ────────────────────────────────────────────────────────────
# Mirrors AIOStreams createRegex() / createLanguageRegex() exactly.
# Lookbehind: not preceded by a character outside [whitespace  [ ( _ - . ,]
# Lookahead:  followed by [whitespace ) ] _ . - ,] or end-of-string

def _br(pattern):
    """Word-boundary-aware regex for FILENAMES (AIOStreams style)."""
    return re.compile(
        r'(?<![^\s\[(_\-.,])(' + pattern + r')(?=[\s\)\]_.\-,]|$)',
        re.IGNORECASE
    )


def _lr(pattern):
    """Language regex — same boundaries but also excludes subtitle suffixes."""
    return re.compile(
        r'(?<![^\s\[(_\-.,])(' + pattern + r')(?![ .\-_]?sub(?:title)?s?)(?=[\s\)\]_.\-,]|$)',
        re.IGNORECASE
    )


# ─── Detection Patterns ────────────────────────────────────────────────────────
# Lists of (label, compiled_regex).
# Single-value fields (resolution, quality, encode): FIRST match wins → order matters.
# Multi-value fields (audio_tags, visual_tags, channels, languages): ALL matches kept.

# Resolution — ordered highest → lowest
RESOLUTION_PATTERNS = [
    ('2160p', _br(r'(bd|hd|m)?(4k|2160[pi]?)|u(?:ltra)?[ .\-_]?hd|3840\s?x\s?\d{4}')),
    ('1440p', _br(r'(bd|hd|m)?1440[pi]?|2k|w?q(?:uad)?[ .\-_]?hd|2560\s?x\d{4}')),
    ('1080p', _br(r'(bd|hd|m)?1080[pi]?|f(?:ull)?[ .\-_]?hd|1920\s?x\s?\d{3,4}')),
    ('720p',  _br(r'(bd|hd|m)?(?:720|800)[pi]?|hd|1280\s?x\s?\d{3,4}')),
    ('576p',  _br(r'(bd|hd|m)?(?:576|534)[pi]?')),
    ('480p',  _br(r'(bd|hd|m)?480[pi]?|sd')),
    ('360p',  _br(r'(bd|hd|m)?360[pi]?')),
    ('240p',  _br(r'(bd|hd|m)?(?:240|266)[pi]?')),
    ('144p',  _br(r'(bd|hd|m)?144[pi]?')),
]

# Source/Quality — ordered best → worst. REMUX must be before BluRay.
QUALITY_PATTERNS = [
    ('BluRay REMUX', _br(r'(?:bd|br|b|uhd)?remux')),
    ('BluRay',       _br(r'(?:bd|blu[ .\-_]?ray|(?:bd|br)[ .\-_]?rip)')),
    ('WEB-DL',       _br(r'web[ .\-_]?(?:dl)?(?![ .\-_]?(?:rip|dlrip|cam))')),
    ('WEBRip',       _br(r'web[ .\-_]?rip')),
    ('HDRip',        _br(r'hd[ .\-_]?rip|web[ .\-_]?dl[ .\-_]?rip')),
    ('HC HD-Rip',    _br(r'hc|hd[ .\-_]?rip')),
    ('DVDRip',       _br(r'dvd[ .\-_]?(?:rip|mux|r|full|5|9)?')),
    ('HDTV',         _br(r'(?:hd|pd)tv|tv[ .\-_]?rip|hdtv[ .\-_]?rip|dsr(?:ip)?|sat[ .\-_]?rip')),
    ('CAM',          _br(r'cam|hdcam|cam[ .\-_]?rip')),
    ('TS',           _br(r'telesync|ts|hd[ .\-_]?ts|pdvd|predvd(?:rip)?')),
    ('TC',           _br(r'telecine|tc|hd[ .\-_]?tc')),
    ('SCR',          _br(r'(?:(?:dvd|bd|web|hd)?[ .\-_]?)?scr(?:eener)?')),
]

# HDR / Visual tags — DV before HDR variants, HDR10+ before HDR10 before HDR
VISUAL_TAG_PATTERNS = [
    ('DV',     _br(r'do?(?:lby)?[ .\-_]?vi?(?:sion)?(?:[ .\-_]?atmos)?|dv')),
    ('HDR10+', _br(r'hdr[ .\-_]?10[ .\-_]?(?:p(?:lus)?|[+])')),
    ('HDR10',  _br(r'hdr[ .\-_]?10(?![ .\-_]?(?:\+|p(?:lus)?))')),
    ('HDR',    _br(r'hdr(?![ .\-_]?10)(?![ .\-_]?(?:\+|p(?:lus)?))')),
    ('HLG',    _br(r'hlg')),
    ('IMAX',   _br(r'imax')),
    ('3D',     _br(r'(?:bd)?(?:3|three)[ .\-_]?d(?:imension(?:al)?)?')),
    # 10bit moved to BIT_DEPTH_PATTERNS
    ('AI',     _br(r'ai[ .\-_]?(?:upscale|enhanced|remaster)?')),
    ('SDR',    _br(r'sdr')),
    ('H-SBS',  _br(r'h?(?:alf)?[ .\-_]?(?:sbs|side[ .\-_]?by[ .\-_]?side)')),
    ('H-OU',   _br(r'h?(?:alf)?[ .\-_]?(?:ou|over[ .\-_]?under)')),
]

# Audio codecs — ordered most-specific → least-specific to avoid false matches.
# Atmos / DTS:X / DTS-HD MA must come BEFORE their shorter variants.
AUDIO_TAG_PATTERNS = [
    ('Atmos',     _br(r'atmos|ddpa\d?')),
    ('DD+',       _br(r'd(?:olby)?[ .\-_]?d(?:igital)?[ .\-_]?(?:p(?:lus)?|\+)a?(?:[ .\-_]?(?:2[ .\-_]?0|5[ .\-_]?1|7[ .\-_]?1))?|e[ .\-_]?ac[ .\-_]?3')),
    # Note: (?<![eE]) is a fixed-width lookbehind (1 char) — catches EAC3 ≠ DD.
    # "E-AC-3" edge case: DD+ pattern fires first (checked before DD), so dedup handles it.
    ('DD',        _br(r'd(?:olby)?[ .\-_]?d(?:igital)?(?:[ .\-_]?(?:5[ .\-_]?1|7[ .\-_]?1|2[ .\-_]?0))?|(?<![eE])ac[ .\-_]?3')),
    ('DTS:X',     _br(r'dts[ .\-:_]?x')),
    ('DTS-HD MA', _br(r'dts[ .\-_]?hd[ .\-_]?ma')),
    ('DTS-HD',    _br(r'dts[ .\-_]?hd(?![ .\-_]?ma)')),
    ('DTS-ES',    _br(r'dts[ .\-_]?es')),
    ('DTS',       _br(r'dts(?![ .\-:_]?(?:x(?=[\s\)\]_.\-,]|$)|hd[ .\-_]?(?:ma)?|es))')),
    ('TrueHD',    _br(r'true[ .\-_]?hd')),
    ('OPUS',      _br(r'opus')),
    ('AAC',       _br(r'q?aac(?:[ .\-_]?2)?')),
    ('FLAC',      _br(r'flac(?:[ .\-_]?(?:lossless|2\.0|x[2-4]))?')),
]

# Audio channels — ordered 7.1 → 2.0
AUDIO_CHANNEL_PATTERNS = [
    ('7.1', _br(r'd(?:olby)?[ .\-_]?d(?:igital)?[ .\-_]?(?:(?:p(?:lus)?|\+)a?)?7[ .\-_]?1(?:ch)?|7[ .\-_]?1(?:ch)?')),
    ('6.1', _br(r'd(?:olby)?[ .\-_]?d(?:igital)?[ .\-_]?(?:(?:p(?:lus)?|\+)a?)?6[ .\-_]?1(?:ch)?|6[ .\-_]?1(?:ch)?')),
    ('5.1', _br(r'd(?:olby)?[ .\-_]?d(?:igital)?[ .\-_]?(?:(?:p(?:lus)?|\+)a?)?5[ .\-_]?1(?:ch)?|5[ .\-_]?1(?:ch)?')),
    ('2.0', _br(r'd(?:olby)?[ .\-_]?d(?:igital)?2[ .\-_]?0(?:ch)?|2[ .\-_]?0(?:ch)?')),
]

# Video codec (encode)
ENCODE_PATTERNS = [
    ('HEVC', _br(r'hevc[ .\-_]?(?:10)?|[xh][ .\-_]?265')),
    ('AVC',  _br(r'avc|[xh][ .\-_]?264')),
    ('AV1',  _br(r'av1')),
    ('XviD', _br(r'xvid')),
    ('DivX', _br(r'divx|dvix')),
]

# Bit depth — own field so it can be shown alongside codec (e.g. "HEVC 10bit")
BIT_DEPTH_PATTERNS = [
    ('10bit', _br(r'10[ .\-_]?bit')),
    ('12bit', _br(r'12[ .\-_]?bit')),
    ('8bit',  _br(r'8[ .\-_]?bit')),
]

# Release flags — boolean markers (PROPER / REPACK / DUBBED)
RELEASE_FLAG_PATTERNS = {
    'is_proper': _br(r'proper'),
    'is_repack': _br(r'repack'),
    'is_dubbed': _br(r'dub(?:s|bed|bing)?'),
}

# Languages — ordered so multi/dual come before individual langs
LANGUAGE_PATTERNS = [
    ('Multi',       _lr(r'multi')),
    ('Dual Audio',  _lr(r'dual[ .\-_]?(?:audio|lang(?:uage)?|flac|ac3|aac2?)')),
    ('Dubbed',      _lr(r'dub(?:s|bed|bing)?')),
    ('English',     _lr(r'english|eng')),
    ('Japanese',    _lr(r'japanese|jap|jpn')),
    ('Chinese',     _lr(r'chinese|chi')),
    ('Russian',     _lr(r'russian|rus')),
    ('Arabic',      _lr(r'arabic|ara')),
    ('Portuguese',  _lr(r'portuguese|por')),
    ('Spanish',     _lr(r'spanish|spa|esp')),
    ('French',      _lr(r'french|fra|fr|vf|vff|vfi|vf2|vfq|truefrench')),
    ('German',      _lr(r'deu(?:tsch)?(?:land)?|ger(?:man)?')),
    ('Italian',     _lr(r'italian|ita')),
    ('Korean',      _lr(r'korean|kor')),
    ('Hindi',       _lr(r'hindi|hin')),
    ('Bengali',     _lr(r'bengali|ben(?![ .\-_]?the[ .\-_]?men)')),
    ('Punjabi',     _lr(r'punjabi|pan')),
    ('Marathi',     _lr(r'marathi|mar')),
    ('Gujarati',    _lr(r'gujarati|guj')),
    ('Tamil',       _lr(r'tamil|tam')),
    ('Telugu',      _lr(r'telugu|tel')),
    ('Kannada',     _lr(r'kannada|kan')),
    ('Malayalam',   _lr(r'malayalam|mal')),
    ('Thai',        _lr(r'thai|tha')),
    ('Vietnamese',  _lr(r'vietnamese|vie')),
    ('Indonesian',  _lr(r'indonesian|ind')),
    ('Turkish',     _lr(r'turkish|tur')),
    ('Hebrew',      _lr(r'hebrew|heb')),
    ('Persian',     _lr(r'persian|per')),
    ('Ukrainian',   _lr(r'ukrainian|ukr')),
    ('Greek',       _lr(r'greek|ell')),
    ('Lithuanian',  _lr(r'lithuanian|lit')),
    ('Latvian',     _lr(r'latvian|lav')),
    ('Estonian',    _lr(r'estonian|est')),
    ('Polish',      _lr(r'polish|pol')),
    ('Czech',       _lr(r'czech|cze')),
    ('Slovak',      _lr(r'slovak|slo')),
    ('Hungarian',   _lr(r'hungarian|hun')),
    ('Romanian',    _lr(r'romanian|rum')),
    ('Bulgarian',   _lr(r'bulgarian|bul')),
    ('Serbian',     _lr(r'serbian|srp')),
    ('Croatian',    _lr(r'croatian|hrv')),
    ('Slovenian',   _lr(r'slovenian|slv')),
    ('Dutch',       _lr(r'dutch|dut')),
    ('Danish',      _lr(r'danish|dan')),
    ('Finnish',     _lr(r'finnish|fin')),
    ('Swedish',     _lr(r'swedish|swe')),
    ('Norwegian',   _lr(r'norwegian|nor')),
    ('Malay',       _lr(r'malay')),
    ('Latino',      _lr(r'latino|lat')),
]

# Release group — extracted from end of filename ("-GROUP" pattern)
_RELEASE_GROUP_RE = re.compile(
    r'-[. ]?(?!\d+$|S\d+|\d+x|ep?\d+|[^\[]+\]$)'
    r'([^\-. \[]+[^\-. \[)\]\d][^\-. \[)\]]*)'
    r'(?:\[[\w.\-]+\])?(?=\)|[.\-]+\w{2,4}$|$)',
    re.IGNORECASE
)


# ─── Debrid Service Definitions ────────────────────────────────────────────────
# Maps service_id → display info + known name patterns for detection
_SERVICE_DETAILS = {
    'realdebrid': {
        'name': 'Real-Debrid', 'short': 'RD', 'icon_key': 'service_rd',
        'known_names': ['RD', 'Real Debrid', 'RealDebrid', 'Real-Debrid'],
    },
    'alldebrid': {
        'name': 'AllDebrid', 'short': 'AD', 'icon_key': 'service_ad',
        'known_names': ['AD', 'All Debrid', 'AllDebrid', 'All-Debrid'],
    },
    'premiumize': {
        'name': 'Premiumize', 'short': 'PM', 'icon_key': 'service_pm',
        'known_names': ['PM', 'Premiumize'],
    },
    'debridlink': {
        'name': 'Debrid-Link', 'short': 'DL', 'icon_key': 'service_dl',
        'known_names': ['DL', 'Debrid Link', 'DebridLink', 'Debrid-Link'],
    },
    'torbox': {
        'name': 'TorBox', 'short': 'TB', 'icon_key': 'service_tb',
        'known_names': ['TB', 'TorBox', 'Torbox', 'TRB'],
    },
    'easynews': {
        'name': 'Easynews', 'short': 'EN', 'icon_key': 'service_en',
        'known_names': ['EN', 'Easynews'],
    },
    'pikpak': {
        'name': 'PikPak', 'short': 'PP', 'icon_key': 'service_pk',
        'known_names': ['PP', 'PikPak', 'PKP'],
    },
    'seedr': {
        'name': 'Seedr', 'short': 'SR', 'icon_key': 'service_sr',
        # Note: 'SDR' conflicts with visual tag SDR — checked only in service context
        'known_names': ['SR', 'Seedr'],
    },
    'offcloud': {
        'name': 'Offcloud', 'short': 'OC', 'icon_key': 'service_oc',
        'known_names': ['OC', 'Offcloud'],
    },
    'putio': {
        'name': 'put.io', 'short': 'PO', 'icon_key': 'service_po',
        'known_names': ['PO', 'put.io', 'putio'],
    },
    'debrider': {
        'name': 'Debrider', 'short': 'DBD', 'icon_key': 'service_dbd',
        'known_names': ['DBD', 'DR', 'DER', 'DB', 'Debrider'],
    },
}

# Cache symbols used in stream names/descriptions
_CACHED_SYMBOLS = ['+', '\u26a1', '\U0001F680', 'cached']       # ⚡ 🚀
_UNCACHED_SYMBOLS = ['\u23f3', 'download', 'UNCACHED']           # ⏳

# Pre-compile service regexes once at import time
_SERVICE_REGEXES = {}
for _sid, _sinfo in _SERVICE_DETAILS.items():
    _escaped = [re.escape(n) for n in _sinfo['known_names']]
    _SERVICE_REGEXES[_sid] = re.compile(
        r'(?:^|(?<=[ |\[(_/\-\.]))(' + '|'.join(_escaped) + r')(?=$|[ |\]\)_.\-+/\n])',
        re.IGNORECASE | re.MULTILINE
    )


# ─── Flag Emoji → Language Name ────────────────────────────────────────────────
# Country flag emojis (pairs of regional indicator symbols U+1F1E6–U+1F1FF)
# Used to extract languages from stream descriptions.
_FLAG_RE = re.compile(r'[\U0001F1E6-\U0001F1FF]{2}')

_FLAG_LANGUAGE_MAP = {
    '\U0001F1FA\U0001F1F8': 'English',      # 🇺🇸
    '\U0001F1EC\U0001F1E7': 'English',      # 🇬🇧
    '\U0001F1E6\U0001F1FA': 'English',      # 🇦🇺
    '\U0001F1EB\U0001F1F7': 'French',       # 🇫🇷
    '\U0001F1E7\U0001F1EA': 'French',       # 🇧🇪
    '\U0001F1E8\U0001F1ED': 'French',       # 🇨🇭 (also German/Italian)
    '\U0001F1E9\U0001F1EA': 'German',       # 🇩🇪
    '\U0001F1E6\U0001F1F9': 'German',       # 🇦🇹
    '\U0001F1EE\U0001F1F9': 'Italian',      # 🇮🇹
    '\U0001F1EA\U0001F1F8': 'Spanish',      # 🇪🇸
    '\U0001F1F2\U0001F1FD': 'Spanish',      # 🇲🇽
    '\U0001F1E6\U0001F1F7': 'Spanish',      # 🇦🇷
    '\U0001F1F5\U0001F1F9': 'Portuguese',   # 🇵🇹
    '\U0001F1E7\U0001F1F7': 'Portuguese',   # 🇧🇷
    '\U0001F1F7\U0001F1FA': 'Russian',      # 🇷🇺
    '\U0001F1EF\U0001F1F5': 'Japanese',     # 🇯🇵
    '\U0001F1F0\U0001F1F7': 'Korean',       # 🇰🇷
    '\U0001F1E8\U0001F1F3': 'Chinese',      # 🇨🇳
    '\U0001F1ED\U0001F1F0': 'Chinese',      # 🇭🇰
    '\U0001F1F9\U0001F1FC': 'Chinese',      # 🇹🇼
    '\U0001F1F8\U0001F1E6': 'Arabic',       # 🇸🇦
    '\U0001F1EA\U0001F1EC': 'Arabic',       # 🇪🇬
    '\U0001F1EE\U0001F1F3': 'Hindi',        # 🇮🇳
    '\U0001F1F9\U0001F1F7': 'Turkish',      # 🇹🇷
    '\U0001F1F5\U0001F1F1': 'Polish',       # 🇵🇱
    '\U0001F1F3\U0001F1F1': 'Dutch',        # 🇳🇱
    '\U0001F1E7\U0001F1EA': 'Dutch',        # 🇧🇪 (also French)
    '\U0001F1F8\U0001F1EA': 'Swedish',      # 🇸🇪
    '\U0001F1E9\U0001F1F0': 'Danish',       # 🇩🇰
    '\U0001F1EB\U0001F1EE': 'Finnish',      # 🇫🇮
    '\U0001F1F3\U0001F1F4': 'Norwegian',    # 🇳🇴
    '\U0001F1E8\U0001F1FF': 'Czech',        # 🇨🇿
    '\U0001F1ED\U0001F1FA': 'Hungarian',    # 🇭🇺
    '\U0001F1F7\U0001F1F4': 'Romanian',     # 🇷🇴
    '\U0001F1E7\U0001F1EC': 'Bulgarian',    # 🇧🇬
    '\U0001F1F8\U0001F1F0': 'Slovak',       # 🇸🇰
    '\U0001F1F8\U0001F1EE': 'Slovenian',    # 🇸🇮
    '\U0001F1ED\U0001F1F7': 'Croatian',     # 🇭🇷
    '\U0001F1F7\U0001F1F8': 'Serbian',      # 🇷🇸
    '\U0001F1EC\U0001F1F7': 'Greek',        # 🇬🇷
    '\U0001F1FA\U0001F1E6': 'Ukrainian',    # 🇺🇦
    '\U0001F1EE\U0001F1F1': 'Hebrew',       # 🇮🇱
    '\U0001F1EE\U0001F1F7': 'Persian',      # 🇮🇷
    '\U0001F1F9\U0001F1ED': 'Thai',         # 🇹🇭
    '\U0001F1FB\U0001F1F3': 'Vietnamese',   # 🇻🇳
    '\U0001F1EE\U0001F1E9': 'Indonesian',   # 🇮🇩
    '\U0001F1F2\U0001F1FE': 'Malay',        # 🇲🇾
    '\U0001F1F1\U0001F1F9': 'Lithuanian',   # 🇱🇹
    '\U0001F1F1\U0001F1FB': 'Latvian',      # 🇱🇻
    '\U0001F1EA\U0001F1EA': 'Estonian',     # 🇪🇪
    '\U0001F1F1\U0001F1F0': 'Tamil',        # 🇱🇰 (Sri Lanka, Tamil speaker)
}


# ─── Language → Icon key ───────────────────────────────────────────────────────
_LANGUAGE_ICON_KEYS = {
    'Multi': 'lang_multi',         'Dual Audio': 'lang_dual',
    'Dubbed': 'lang_dubbed',       'English': 'lang_en',
    'French': 'lang_fr',           'German': 'lang_de',
    'Spanish': 'lang_es',          'Portuguese': 'lang_pt',
    'Italian': 'lang_it',          'Russian': 'lang_ru',
    'Japanese': 'lang_ja',         'Chinese': 'lang_zh',
    'Korean': 'lang_ko',           'Arabic': 'lang_ar',
    'Hindi': 'lang_hi',            'Turkish': 'lang_tr',
    'Polish': 'lang_pl',           'Dutch': 'lang_nl',
    'Swedish': 'lang_sv',          'Danish': 'lang_da',
    'Finnish': 'lang_fi',          'Norwegian': 'lang_no',
    'Czech': 'lang_cs',            'Hungarian': 'lang_hu',
    'Romanian': 'lang_ro',         'Bulgarian': 'lang_bg',
    'Serbian': 'lang_sr',          'Croatian': 'lang_hr',
    'Slovak': 'lang_sk',           'Slovenian': 'lang_sl',
    'Greek': 'lang_el',            'Ukrainian': 'lang_uk',
    'Hebrew': 'lang_he',           'Persian': 'lang_fa',
    'Thai': 'lang_th',             'Vietnamese': 'lang_vi',
    'Indonesian': 'lang_id',       'Malay': 'lang_ms',
    'Tamil': 'lang_ta',            'Telugu': 'lang_te',
    'Bengali': 'lang_bn',          'Malayalam': 'lang_ml',
    'Marathi': 'lang_mr',          'Gujarati': 'lang_gu',
    'Kannada': 'lang_kn',          'Punjabi': 'lang_pa',
    'Lithuanian': 'lang_lt',       'Latvian': 'lang_lv',
    'Estonian': 'lang_et',         'Latino': 'lang_lat',
}

# ─── Resolution → Icon key ────────────────────────────────────────────────────
_RESOLUTION_ICON_KEYS = {
    '2160p': 'res_4k',
    '1440p': 'res_1440p',
    '1080p': 'res_1080p',
    '720p':  'res_720p',
    '576p':  'res_576p',
    '480p':  'res_480p',
    '360p':  'res_360p',
    '240p':  'res_sd',
    '144p':  'res_sd',
}

# ─── Quality → Icon key ───────────────────────────────────────────────────────
_QUALITY_ICON_KEYS = {
    'BluRay REMUX': 'quality_remux',
    'BluRay':       'quality_bluray',
    'WEB-DL':       'quality_webdl',
    'WEBRip':       'quality_webrip',
    'HDRip':        'quality_hdrip',
    'HC HD-Rip':    'quality_hchdrip',
    'DVDRip':       'quality_dvdrip',
    'HDTV':         'quality_hdtv',
    'CAM':          'quality_cam',
    'TS':           'quality_ts',
    'TC':           'quality_tc',
    'SCR':          'quality_scr',
}

# ─── Audio → Icon key ─────────────────────────────────────────────────────────
_AUDIO_ICON_KEYS = {
    'Atmos':     'audio_atmos',
    'DD+':       'audio_ddplus',
    'DD':        'audio_dd',
    'DTS:X':     'audio_dtsx',
    'DTS-HD MA': 'audio_dtshd_ma',
    'DTS-HD':    'audio_dtshd',
    'DTS-ES':    'audio_dts_es',
    'DTS':       'audio_dts',
    'TrueHD':    'audio_truehd',
    'OPUS':      'audio_opus',
    'AAC':       'audio_aac',
    'FLAC':      'audio_flac',
}

# ─── Audio channel → Icon key ─────────────────────────────────────────────────
_CHANNEL_ICON_KEYS = {
    '7.1': 'ch_71',
    '6.1': 'ch_61',
    '5.1': 'ch_51',
    '2.0': 'ch_20',
}

# ─── Visual → Icon key ───────────────────────────────────────────────────────
_VISUAL_ICON_KEYS = {
    'DV':     'hdr_dv',
    'HDR10+': 'hdr_hdr10plus',
    'HDR10':  'hdr_hdr10',
    'HDR':    'hdr_hdr',
    'HLG':    'hdr_hlg',
    'IMAX':   'visual_imax',
    '3D':     'visual_3d',
    '10bit':  'visual_10bit',
    'AI':     'visual_ai',
    'SDR':    'visual_sdr',
    'H-SBS':  'visual_hsbs',
    'H-OU':   'visual_hou',
}

# ─── Codec → Icon key ────────────────────────────────────────────────────────
_ENCODE_ICON_KEYS = {
    'HEVC': 'codec_hevc',
    'AVC':  'codec_avc',
    'AV1':  'codec_av1',
    'XviD': 'codec_xvid',
    'DivX': 'codec_divx',
}


# ─── Low-level Extraction Helpers ─────────────────────────────────────────────

# Size: matches "12.45 GB", "700 MB", etc.
_SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB)', re.IGNORECASE)

# Seeders: from 👥 or 👤 emoji in description
_SEEDERS_RE = re.compile(r'[\U0001F465\U0001F464]\s*(\d+)', re.UNICODE)

# Info-hash: 40-hex-char SHA1 (BitTorrent v1)
_INFO_HASH_RE = re.compile(r'(?<=[-/\[(;:&])[a-fA-F0-9]{40}(?=[-\]\)/:;&])')

# Magnet hash shortcut
_MAGNET_HASH_RE = re.compile(r'urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})', re.IGNORECASE)


def _extract_size_bytes(text, k=1024):
    """Return file size in bytes from a text string, or None."""
    m = _SIZE_RE.search(text or '')
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).upper()
    multipliers = {'KB': k, 'MB': k ** 2, 'GB': k ** 3, 'TB': k ** 4}
    return int(value * multipliers[unit])


def _extract_seeders(description):
    """Return seeder count from emoji pattern (👥N / 👤N), or None."""
    m = _SEEDERS_RE.search(description or '')
    return int(m.group(1)) if m else None


def _extract_info_hash(url):
    """Return lowercase info-hash from a URL or magnet link, or None."""
    if not url:
        return None
    # Magnet link: urn:btih:HASH
    m = _MAGNET_HASH_RE.search(url)
    if m:
        h = m.group(1)
        # Base32 magnet hashes are 32 chars — skip (too complex to decode here)
        if len(h) == 40:
            return h.lower()
    # Hash embedded in URL path/query
    m = _INFO_HASH_RE.search(url)
    return m.group(0).lower() if m else None


def _extract_flag_languages(text):
    """Return list of language names detected from country flag emojis in text."""
    seen = []
    for flag in _FLAG_RE.findall(text or ''):
        lang = _FLAG_LANGUAGE_MAP.get(flag)
        if lang and lang not in seen:
            seen.append(lang)
    return seen


def _match_first(text, patterns):
    """Return label of first matching pattern, or None."""
    for label, regex in patterns:
        if regex.search(text):
            return label
    return None


def _match_all(text, patterns):
    """Return labels of ALL matching patterns (preserves order, deduped)."""
    seen = []
    for label, regex in patterns:
        if label not in seen and regex.search(text):
            seen.append(label)
    return seen


def _detect_service(stream_name):
    """
    Detect debrid service + cache status from the stream name field.

    Returns dict {'id', 'name', 'short', 'cached', 'icon_key'} or None.
    Cache heuristic (same logic as AIOStreams):
      - Check uncached symbols first (⏳, 'download', 'UNCACHED')
      - Then cached symbols (+, ⚡, 🚀, 'cached')
      - Default to False (unknown)
    """
    # Strip WEB-DL to avoid 'DL' (Debrid-Link) false-positive
    clean = re.sub(r'web-?dl', '', stream_name or '', flags=re.IGNORECASE)

    for service_id, regex in _SERVICE_REGEXES.items():
        if regex.search(clean):
            info = _SERVICE_DETAILS[service_id]
            if any(sym in stream_name for sym in _UNCACHED_SYMBOLS):
                cached = False
            elif any(sym in stream_name for sym in _CACHED_SYMBOLS):
                cached = True
            else:
                cached = False
            return {
                'id':       service_id,
                'name':     info['name'],
                'short':    info['short'],
                'icon_key': info['icon_key'],
                'cached':   cached,
            }
    return None


# ─── Main Parser ───────────────────────────────────────────────────────────────

class StreamParser:
    """
    AIOStreams-compatible stream metadata parser for Kodi addons.

    All methods are static — no instantiation needed.

    parse_filename(filename)  → ParsedFile dict
    parse_stream(stream_dict) → ParsedStream dict  (superset of ParsedFile)
    get_icon(key)             → str path (or None if icon file missing)
    """

    @staticmethod
    def parse_filename(filename):
        """
        Parse a torrent filename and return a dict with all detected metadata.

        Args:
            filename (str): Filename like "Movie.2024.1080p.BluRay.REMUX.HEVC.DTS-HD.MA.5.1-GROUP"

        Returns:
            dict with keys:
                resolution   (str|None)   — '2160p', '1080p', '720p', ...
                quality      (str|None)   — 'BluRay REMUX', 'WEB-DL', ...
                encode       (str|None)   — 'HEVC', 'AVC', 'AV1', ...
                audio_tags   (list[str])  — ['Atmos', 'TrueHD']
                audio_ch     (list[str])  — ['7.1']
                visual_tags  (list[str])  — ['HDR10+', 'DV']
                languages    (list[str])  — ['English', 'French']
                release_group(str|None)
                icons        (dict)       — icon keys → full path strings
        """
        text = filename or ''

        resolution   = _match_first(text, RESOLUTION_PATTERNS)
        quality      = _match_first(text, QUALITY_PATTERNS)
        encode       = _match_first(text, ENCODE_PATTERNS)
        bit_depth    = _match_first(text, BIT_DEPTH_PATTERNS)
        audio_tags   = _match_all(text, AUDIO_TAG_PATTERNS)
        audio_ch     = _match_all(text, AUDIO_CHANNEL_PATTERNS)
        visual_tags  = _match_all(text, VISUAL_TAG_PATTERNS)
        languages    = _match_all(text, LANGUAGE_PATTERNS)

        rg_match = _RELEASE_GROUP_RE.search(text)
        release_group = rg_match.group(1) if rg_match else None

        is_proper = bool(RELEASE_FLAG_PATTERNS['is_proper'].search(text))
        is_repack = bool(RELEASE_FLAG_PATTERNS['is_repack'].search(text))
        is_dubbed = bool(RELEASE_FLAG_PATTERNS['is_dubbed'].search(text))

        icons = StreamParser._build_icons(resolution, quality, encode, audio_tags, audio_ch, visual_tags, languages)

        return {
            'resolution':    resolution,
            'quality':       quality,
            'encode':        encode,
            'bit_depth':     bit_depth,
            'audio_tags':    audio_tags,
            'audio_ch':      audio_ch,
            'visual_tags':   visual_tags,
            'languages':     languages,
            'release_group': release_group,
            'is_proper':     is_proper,
            'is_repack':     is_repack,
            'is_dubbed':     is_dubbed,
            'icons':         icons,
        }

    @staticmethod
    def parse_stream(stream):
        """
        Parse a Stremio stream dict (as returned by addon API) into rich metadata.

        Args:
            stream (dict): Raw stream object with keys like:
                name, title, description, url, infoHash, fileIdx,
                sources, behaviorHints (filename, videoSize, folderName, ...)

        Returns:
            dict with all ParsedFile keys PLUS:
                filename     (str|None)
                folder_name  (str|None)
                size         (int|None)  — bytes
                seeders      (int|None)
                info_hash    (str|None)
                file_idx     (int|None)
                service      (dict|None) — {id, name, short, cached, icon_key}
                stream_type  (str)       — 'debrid'|'p2p'|'http'|'live'|'external'
                icons        (dict)      — extended with service + cache_status keys
        """
        name        = stream.get('name') or ''
        description = stream.get('description') or stream.get('title') or ''
        url         = stream.get('url') or stream.get('externalUrl') or ''
        hints       = stream.get('behaviorHints') or {}

        # ── Filename / folder name ────────────────────────────────────────────
        filename    = hints.get('filename') or _pick_filename_line(name, description)
        folder_name = hints.get('folderName') or None

        # ── File-based metadata (parse the best available name string) ────────
        parse_text = filename or description.split('\n')[0] if description else name
        file_info  = StreamParser.parse_filename(parse_text)

        # If folder name also exists, parse it and MERGE array fields
        if folder_name:
            folder_info = StreamParser.parse_filename(folder_name)
            file_info['audio_tags']  = _dedup(folder_info['audio_tags']  + file_info['audio_tags'])
            file_info['audio_ch']    = _dedup(folder_info['audio_ch']    + file_info['audio_ch'])
            file_info['visual_tags'] = _dedup(folder_info['visual_tags'] + file_info['visual_tags'])
            file_info['languages']   = _dedup(folder_info['languages']   + file_info['languages'])
            # Scalar fields: file takes priority, folder as fallback
            file_info['resolution']   = file_info['resolution']   or folder_info['resolution']
            file_info['quality']      = file_info['quality']      or folder_info['quality']
            file_info['encode']       = file_info['encode']       or folder_info['encode']
            file_info['bit_depth']    = file_info['bit_depth']    or folder_info['bit_depth']
            file_info['release_group']= file_info['release_group']or folder_info['release_group']
            # Flags: OR across file + folder
            file_info['is_proper'] = file_info['is_proper'] or folder_info['is_proper']
            file_info['is_repack'] = file_info['is_repack'] or folder_info['is_repack']
            file_info['is_dubbed'] = file_info['is_dubbed'] or folder_info['is_dubbed']

        # ── Language enrichment from flag emojis in description + name ────────
        flag_langs = _dedup(
            _extract_flag_languages(name) +
            _extract_flag_languages(description)
        )
        for lang in flag_langs:
            if lang not in file_info['languages']:
                file_info['languages'].append(lang)

        # ── Service / cache detection ─────────────────────────────────────────
        service = _detect_service(name) or _detect_service(description)

        # ── Size ─────────────────────────────────────────────────────────────
        video_size = hints.get('videoSize') or stream.get('size') or stream.get('sizeBytes')
        if isinstance(video_size, (int, float)):
            size = int(video_size)
        elif isinstance(video_size, str):
            size = _extract_size_bytes(video_size) or 0
        else:
            # Fall back to parsing the text
            size = (_extract_size_bytes(description) or
                    _extract_size_bytes(name) or
                    0)

        # ── Seeders ──────────────────────────────────────────────────────────
        seeders = (_extract_seeders(description) or
                   _extract_seeders(name) or
                   _extract_seeders(stream.get('title') or ''))

        # ── Info hash ────────────────────────────────────────────────────────
        info_hash = (stream.get('infoHash') or
                     _extract_info_hash(url) or
                     _extract_info_hash(stream.get('externalUrl') or ''))
        if info_hash:
            info_hash = info_hash.lower()

        file_idx = stream.get('fileIdx')

        # ── Stream type ───────────────────────────────────────────────────────
        stream_type = _classify_stream_type(url, stream, service)

        # ── Build extended icons dict ─────────────────────────────────────────
        icons = dict(file_info['icons'])  # copy from filename parse
        if service:
            icons['service'] = ICON_PATHS.get(service['icon_key'])
        icons['cache_status'] = (
            ICON_PATHS['cached'] if (service and service['cached'])
            else ICON_PATHS.get('instant') if stream_type == 'debrid'
            else ICON_PATHS.get('uncached')
        )

        result = dict(file_info)
        result.update({
            'filename':    filename,
            'folder_name': folder_name,
            'size':        size if size else None,
            'size_gb':     round(size / (1024 ** 3), 2) if size else 0.0,
            'seeders':     seeders,
            'info_hash':   info_hash,
            'file_idx':    file_idx,
            'service':     service,
            'stream_type': stream_type,
            'icons':       icons,
        })
        return result

    @staticmethod
    def get_icon(key):
        """
        Return full path to an icon by key, or None if the file doesn't exist.

        Args:
            key (str): One of the keys in ICON_PATHS (e.g. 'res_1080p', 'audio_atmos')
        Returns:
            str path or None
        """
        path = ICON_PATHS.get(key)
        if path and os.path.isfile(path):
            return path
        return None

    @staticmethod
    def _build_icons(resolution, quality, encode, audio_tags, audio_ch, visual_tags, languages):
        """Build an icons dict from parsed field values."""
        icons = {}

        if resolution:
            key = _RESOLUTION_ICON_KEYS.get(resolution)
            if key:
                icons['resolution'] = ICON_PATHS.get(key)

        if quality:
            key = _QUALITY_ICON_KEYS.get(quality)
            if key:
                icons['quality'] = ICON_PATHS.get(key)

        if encode:
            key = _ENCODE_ICON_KEYS.get(encode)
            if key:
                icons['encode'] = ICON_PATHS.get(key)

        # Primary audio: first (highest-priority) audio tag
        if audio_tags:
            key = _AUDIO_ICON_KEYS.get(audio_tags[0])
            if key:
                icons['audio_primary'] = ICON_PATHS.get(key)
        icons['audio_all'] = [
            ICON_PATHS.get(_AUDIO_ICON_KEYS[t])
            for t in audio_tags if t in _AUDIO_ICON_KEYS
        ]

        # Primary channel
        if audio_ch:
            key = _CHANNEL_ICON_KEYS.get(audio_ch[0])
            if key:
                icons['audio_channel'] = ICON_PATHS.get(key)

        # Primary visual / HDR: DV > HDR10+ > HDR10 > HDR > HLG > others
        if visual_tags:
            key = _VISUAL_ICON_KEYS.get(visual_tags[0])
            if key:
                icons['visual_primary'] = ICON_PATHS.get(key)
        icons['visual_all'] = [
            ICON_PATHS.get(_VISUAL_ICON_KEYS[t])
            for t in visual_tags if t in _VISUAL_ICON_KEYS
        ]

        # Language icons list
        icons['languages'] = [
            ICON_PATHS.get(_LANGUAGE_ICON_KEYS[l])
            for l in languages if l in _LANGUAGE_ICON_KEYS
        ]

        return icons


# ─── Private Helpers ───────────────────────────────────────────────────────────

def _dedup(lst):
    """Return list with duplicates removed (preserving order)."""
    seen = []
    for x in lst:
        if x not in seen:
            seen.append(x)
    return seen


def _pick_filename_line(name, description):
    """
    Heuristic to pick the best filename from stream name/description.
    Mirrors AIOStreams' getFilename() logic.
    """
    for text in [name, description]:
        if not text:
            continue
        for line in text.split('\n')[:5]:
            line = line.strip()
            if not line:
                continue
            # A good filename line usually has a year, season, or episode marker
            if re.search(r'\b(19|20)\d{2}\b|S\d{2}E\d{2}|\b\d{3,4}p\b', line, re.IGNORECASE):
                # Strip leading emoji/service tags
                line = re.sub(r'^[\U00010000-\U0010ffff\U0001F000-\U0001FFFF]+', '', line)
                line = re.sub(r'^[^\s:]+:\s*', '', line)
                return line.strip()
    # Fallback: first non-empty line of description
    if description:
        first = description.split('\n')[0].strip()
        return re.sub(r'^[\U00010000-\U0010ffff\U0001F000-\U0001FFFF]+', '', first).strip() or None
    return None


def _classify_stream_type(url, stream, service):
    """Classify stream type (mirrors AIOStreams getStreamType logic)."""
    if url and url.endswith('.m3u8'):
        return 'live'
    if service:
        if service['id'] == 'easynews':
            return 'usenet'
        return 'debrid'
    if url:
        return 'http'
    if stream.get('infoHash'):
        return 'p2p'
    if stream.get('externalUrl'):
        return 'external'
    if stream.get('ytId'):
        return 'youtube'
    return 'http'
