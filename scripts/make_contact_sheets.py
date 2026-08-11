#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge per-vessel SAR crop thumbnails into one contact-sheet image per scene.

Why: the monitoring archive keeps one ~8 KB crop per detected vessel
(10,300+ files, ~53 MB). Contact sheets keep the same visual evidence in
one JPEG per scene (~65 KB average) — cutting the archive from ~11,300 to
~1,300 files and making it fit comfortably in the 10,000-file / 128 MB
storage budget of the platform.

The vessel coordinates, dimensions and attributes stay in vessels.json
(never touched); only the thumbnail files are replaced.

Usage:
  python3 scripts/make_contact_sheets.py          # build sheets + delete crops
  python3 scripts/make_contact_sheets.py --keep   # build sheets, keep crops
"""
import os, sys, json, glob, argparse, io
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S1 = os.path.join(ROOT, "data", "raw_s1")
TILE = 150
COLS = 6
QUALITY = 72
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return None


def build_sheet(scene_dir):
    """One JPEG per scene containing every vessel crop, labelled #idx length."""
    crops = sorted(glob.glob(os.path.join(scene_dir, "vessels", "*.jpg")))
    if not crops:
        return 0
    by_id = {}
    vj = os.path.join(scene_dir, "vessels.json")
    if os.path.exists(vj):
        for v in json.load(open(vj)):
            by_id[v["vessel_id"].split("_")[-1]] = v
    n = len(crops)
    rows = int(np.ceil(n / COLS))
    W, H = COLS * TILE, rows * TILE
    sheet = Image.new("RGB", (W, H), (20, 22, 26))
    d = ImageDraw.Draw(sheet)
    f_lbl = _font(21)
    for i, cp in enumerate(crops):
        im = Image.open(cp).convert("RGB")
        im.thumbnail((TILE - 10, TILE - 10), Image.LANCZOS)
        x = (i % COLS) * TILE + 5
        y = (i // COLS) * TILE + 5
        sheet.paste(im, (x, y))
        key = os.path.basename(cp).rsplit("_", 1)[-1].replace(".jpg", "")
        tag = f"#{key}"
        info = by_id.get(key)
        if info and info.get("length_m"):
            tag += f" {info['length_m']:.0f}m"
        if f_lbl:
            d.text((x + 3, y + 2), tag, fill=(1, 184, 170), font=f_lbl)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    out = os.path.join(scene_dir, "vessels", "sheet.jpg")
    with open(out, "wb") as f:
        f.write(buf.getvalue())
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="build sheets but do not delete the individual crops")
    args = ap.parse_args()

    total_crops, total_sheets, total_bytes = 0, 0, 0
    for d in sorted(glob.glob(os.path.join(S1, "*"))):
        if not os.path.isdir(d) or not os.path.exists(os.path.join(d, "vessels")):
            continue
        n = build_sheet(d)
        if n:
            total_crops += n
            total_sheets += 1
            total_bytes += os.path.getsize(os.path.join(d, "vessels", "sheet.jpg"))
    print(f"sheets built: {total_sheets} | crops merged: {total_crops:,} "
          f"| sheets size: {total_bytes/1048576:.1f} MB")
    if not args.keep:
        removed = 0
        for cp in glob.glob(os.path.join(S1, "*", "vessels", "*.jpg")):
            if os.path.basename(cp) == "sheet.jpg":
                continue
            os.remove(cp)
            removed += 1
        print(f"individual crops removed: {removed:,}")
    print("vessels.json files untouched — all detection data intact.")


if __name__ == "__main__":
    main()
