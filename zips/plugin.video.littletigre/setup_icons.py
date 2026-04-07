#!/usr/bin/env python3
"""
setup_icons.py — Copy icons from skin packs into the addon's icons folder.

Source:  skin.arctic.fuse.3-omega  (primary)
         skin.arctic.horizon.2-main (supplement: tel.png, bra.png, HDR.png, 3D.png, web-dl.png)
Target:  resources/media/icons/

Run from the addon root:
    python3 setup_icons.py
"""

import os
import shutil

# ── Paths ────────────────────────────────────────────────────────────────────
ADDON_DIR  = os.path.dirname(os.path.abspath(__file__))
ICONS_DIR  = os.path.join(ADDON_DIR, 'resources', 'media', 'icons')

FUSE       = '/home/bazzite/Documents/kodi-dev/skin.arctic.fuse.3-omega/media/flags/color'
HORIZON    = '/home/bazzite/Documents/kodi-dev/skin.arctic.horizon.2-main/media/flags/color'

os.makedirs(ICONS_DIR, exist_ok=True)


def cp(src, dest_name):
    """Copy src → ICONS_DIR/dest_name, skipping if src missing."""
    dest = os.path.join(ICONS_DIR, dest_name)
    if os.path.isfile(src):
        shutil.copy2(src, dest)
        print(f'  OK  {dest_name}')
    else:
        print(f'  --  {dest_name}  (source not found: {src})')


# ── Mapping: icon_key_name → source_file ──────────────────────────────────────
ICONS = {

    # ── Cache / playback speed (keep your existing ones, listed for reference) ──
    # instant.png, cached.png, uncached.png — already in ICONS_DIR

    # ── Resolution ────────────────────────────────────────────────────────────
    'res_4k.png':       f'{FUSE}/resolution/4K.png',
    'res_1440p.png':    f'{FUSE}/resolution/4K.png',        # no 1440p → use 4K
    'res_1080p.png':    f'{FUSE}/resolution/1080.png',
    'res_720p.png':     f'{FUSE}/resolution/720.png',
    'res_576p.png':     f'{FUSE}/resolution/576.png',
    'res_480p.png':     f'{FUSE}/resolution/480.png',
    'res_360p.png':     f'{FUSE}/resolution/288.png',       # closest small res
    'res_sd.png':       f'{FUSE}/resolution/288.png',

    # ── Source / Quality ─────────────────────────────────────────────────────
    'quality_remux.png':    f'{FUSE}/source/bluray.png',    # no REMUX → use BluRay
    'quality_bluray.png':   f'{FUSE}/source/bluray.png',
    'quality_webdl.png':    f'{HORIZON}/other/web-dl.png',  # HORIZON exclusive
    'quality_webrip.png':   f'{HORIZON}/other/web-dl.png',  # no webrip → use web-dl
    'quality_hdrip.png':    f'{FUSE}/source/hdtv.png',      # no hdrip → use hdtv
    'quality_hchdrip.png':  f'{FUSE}/source/hdtv.png',
    'quality_dvdrip.png':   f'{FUSE}/source/dvd.png',
    'quality_hdtv.png':     f'{FUSE}/source/hdtv.png',
    'quality_cam.png':      f'{FUSE}/source/default.png',   # no cam icon
    'quality_ts.png':       f'{FUSE}/source/default.png',
    'quality_tc.png':       f'{FUSE}/source/default.png',
    'quality_scr.png':      f'{FUSE}/source/default.png',

    # ── Video Codec ───────────────────────────────────────────────────────────
    'codec_hevc.png':   f'{FUSE}/source/hevc.png',
    'codec_avc.png':    f'{FUSE}/source/avc.png',
    'codec_av1.png':    f'{FUSE}/source/default.png',       # no AV1 icon
    'codec_xvid.png':   f'{FUSE}/source/xvid.png',
    'codec_divx.png':   f'{FUSE}/source/divx.png',

    # ── Audio Codec ───────────────────────────────────────────────────────────
    'audio_atmos.png':      f'{FUSE}/audio/atmos.png',
    'audio_ddplus.png':     f'{FUSE}/audio/eac3.png',           # DD+ = EAC-3
    'audio_dd.png':         f'{FUSE}/audio/dolbydigital.png',   # DD = Dolby Digital
    'audio_dtsx.png':       f'{FUSE}/audio/dts_x.png',          # DTS:X
    'audio_dtshd_ma.png':   f'{FUSE}/audio/dtshd_ma.png',       # DTS-HD MA
    'audio_dtshd.png':      f'{FUSE}/audio/dtshd_hra.png',      # DTS-HD (HRA)
    'audio_dts_es.png':     f'{FUSE}/audio/dts.png',            # DTS-ES → use DTS
    'audio_dts.png':        f'{FUSE}/audio/dts.png',
    'audio_truehd.png':     f'{FUSE}/audio/truehd.png',
    'audio_opus.png':       f'{FUSE}/audio/opus.png',
    'audio_aac.png':        f'{FUSE}/audio/aac.png',
    'audio_flac.png':       f'{FUSE}/audio/flac.png',

    # ── Audio Channels ────────────────────────────────────────────────────────
    # Kodi counts channels: 7.1 = 8ch, 6.1 = 7ch, 5.1 = 6ch, 2.0 = 2ch
    'ch_71.png':    f'{FUSE}/channels/8.png',
    'ch_61.png':    f'{FUSE}/channels/7.png',
    'ch_51.png':    f'{FUSE}/channels/6.png',
    'ch_20.png':    f'{FUSE}/channels/2.png',

    # ── HDR / Visual Tags ─────────────────────────────────────────────────────
    'hdr_dv.png':           f'{FUSE}/hdr/dolbyvision.png',
    'hdr_hdr10plus.png':    f'{FUSE}/hdr/hdr10.png',        # no HDR10+ specific → use HDR10
    'hdr_hdr10.png':        f'{FUSE}/hdr/hdr10.png',
    'hdr_hdr.png':          f'{HORIZON}/other/HDR.png',     # HORIZON exclusive generic HDR
    'hdr_hlg.png':          f'{FUSE}/hdr/hlg.png',
    'visual_imax.png':      f'{FUSE}/source/default.png',   # no IMAX icon
    'visual_3d.png':        f'{HORIZON}/other/3D.png',      # HORIZON exclusive
    'visual_10bit.png':     f'{FUSE}/source/default.png',   # no 10bit icon
    'visual_ai.png':        f'{FUSE}/source/default.png',
    'visual_sdr.png':       f'{FUSE}/source/default.png',
    'visual_hsbs.png':      f'{FUSE}/source/default.png',
    'visual_hou.png':       f'{FUSE}/source/default.png',

    # ── Debrid Services (no skin icons — create your own PNGs) ───────────────
    # Uncomment and point to real icons when you have them:
    # 'service_rd.png':  '/path/to/realdebrid.png',
    # 'service_tb.png':  '/path/to/torbox.png',
    # 'service_pm.png':  '/path/to/premiumize.png',
    # 'service_ad.png':  '/path/to/alldebrid.png',
    # 'service_dl.png':  '/path/to/debridlink.png',
    # 'service_en.png':  '/path/to/easynews.png',
    # 'service_pk.png':  '/path/to/pikpak.png',
    # 'service_sr.png':  '/path/to/seedr.png',
    # 'service_oc.png':  '/path/to/offcloud.png',
    # 'service_po.png':  '/path/to/putio.png',

    # ── Languages ─────────────────────────────────────────────────────────────
    'lang_multi.png':   f'{FUSE}/language/diffuse.png',     # diffuse = multi-color blur
    'lang_dual.png':    f'{FUSE}/language/diffuse.png',
    'lang_dubbed.png':  f'{FUSE}/language/diffuse.png',
    'lang_en.png':      f'{FUSE}/language/en.png',
    'lang_fr.png':      f'{FUSE}/language/fr.png',
    'lang_de.png':      f'{FUSE}/language/de.png',
    'lang_es.png':      f'{FUSE}/language/es.png',
    'lang_pt.png':      f'{FUSE}/language/pt.png',
    'lang_it.png':      f'{FUSE}/language/it.png',
    'lang_ru.png':      f'{FUSE}/language/ru.png',
    'lang_ja.png':      f'{FUSE}/language/ja.png',
    'lang_zh.png':      f'{FUSE}/language/zh.png',
    'lang_ko.png':      f'{FUSE}/language/ko.png',
    'lang_ar.png':      f'{FUSE}/language/ar.png',
    'lang_hi.png':      f'{FUSE}/language/hi.png',
    'lang_tr.png':      f'{FUSE}/language/tr.png',
    'lang_pl.png':      f'{FUSE}/language/pl.png',
    'lang_nl.png':      f'{FUSE}/language/nl.png',
    'lang_sv.png':      f'{FUSE}/language/sv.png',
    'lang_da.png':      f'{FUSE}/language/da.png',
    'lang_fi.png':      f'{FUSE}/language/fi.png',
    'lang_no.png':      f'{FUSE}/language/no.png',
    'lang_cs.png':      f'{FUSE}/language/cs.png',
    'lang_hu.png':      f'{FUSE}/language/hu.png',
    'lang_ro.png':      f'{FUSE}/language/ro.png',
    'lang_bg.png':      f'{FUSE}/language/bg.png',
    'lang_sr.png':      f'{FUSE}/language/sr.png',
    'lang_hr.png':      f'{FUSE}/language/hr.png',
    'lang_sk.png':      f'{FUSE}/language/sk.png',
    'lang_sl.png':      f'{FUSE}/language/sl.png',
    'lang_el.png':      f'{FUSE}/language/el.png',
    'lang_uk.png':      f'{FUSE}/language/uk.png',
    'lang_he.png':      f'{FUSE}/language/he.png',
    'lang_fa.png':      f'{FUSE}/language/fa.png',
    'lang_th.png':      f'{FUSE}/language/th.png',
    'lang_vi.png':      f'{FUSE}/language/vi.png',
    'lang_id.png':      f'{FUSE}/language/id.png',
    'lang_ms.png':      f'{FUSE}/language/ms.png',
    'lang_ta.png':      f'{FUSE}/language/tam.png',         # FUSE-only Tamil
    'lang_te.png':      f'{HORIZON}/language/tel.png',     # HORIZON-only Telugu
    'lang_bn.png':      f'{FUSE}/language/diffuse.png',     # no Bengali → diffuse
    'lang_ml.png':      f'{FUSE}/language/mal.png',         # FUSE-only Malayalam
    'lang_mr.png':      f'{FUSE}/language/hi.png',          # no Marathi → use Hindi
    'lang_gu.png':      f'{FUSE}/language/hi.png',          # no Gujarati → use Hindi
    'lang_kn.png':      f'{FUSE}/language/hi.png',          # no Kannada → use Hindi
    'lang_pa.png':      f'{FUSE}/language/hi.png',          # no Punjabi → use Hindi
    'lang_lt.png':      f'{FUSE}/language/lt.png',
    'lang_lv.png':      f'{FUSE}/language/lv.png',
    'lang_et.png':      f'{FUSE}/language/et.png',
    'lang_lat.png':     f'{FUSE}/language/es.png',          # Latino → Spanish flag
}


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'Copying icons to: {ICONS_DIR}')
    print()

    missing_src = []
    for dest_name, src_path in sorted(ICONS.items()):
        if not os.path.isfile(src_path):
            missing_src.append((dest_name, src_path))

    ok = 0
    for dest_name, src_path in sorted(ICONS.items()):
        dest = os.path.join(ICONS_DIR, dest_name)
        if os.path.isfile(src_path):
            shutil.copy2(src_path, dest)
            print(f'  OK  {dest_name}')
            ok += 1
        else:
            print(f'  !!  {dest_name}  <- missing: {os.path.basename(src_path)}')

    print()
    print(f'Done: {ok}/{len(ICONS)} icons copied.')
    if missing_src:
        print(f'Missing sources ({len(missing_src)}):')
        for name, src in missing_src:
            print(f'  {name} <- {src}')
        print()
        print('For service icons (RD, TB, PM, etc.) you need to supply your own PNG files.')
        print('Edit the service section in setup_icons.py once you have them.')
