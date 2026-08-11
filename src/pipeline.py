# -*- coding: utf-8 -*-
"""
Batch pipeline: process all selected Sentinel-1 RTC scenes (vessel detection)
and Sentinel-2 L2A scenes (true-color crops + coarse optical cross-check).
Resumable: completed scenes are skipped on re-run.
"""
import os, json, sys, time
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import S1_DIR, S2_DIR, DET_DIR, S1_PER_MONTH, S2_PER_MONTH
from boundaries import build_masks
from detect import process_scene

RESULTS_S1 = os.path.join(DET_DIR, "s1_scenes.jsonl")
RESULTS_S2 = os.path.join(DET_DIR, "s2_scenes.jsonl")


def done_ids(path):
    if not os.path.exists(path):
        return set()
    return {json.loads(l)["id"] for l in open(path, encoding="utf-8") if l.strip()}


import numpy as np
def _san(v):
    if isinstance(v, np.generic):
        return v.item()
    return v

def append_result(path, rec):
    rec = {k: _san(v) for k, v in rec.items()}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_s1(scenes, workers=6):
    grid, land, zone = build_masks()
    done = done_ids(RESULTS_S1)
    todo = [r for r in scenes if r["id"] not in done]
    print(f"S1: {len(done)} done, {len(todo)} to process", flush=True)
    t0 = time.time()
    n_ok = n_err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_scene, r, grid, land, zone): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                out = fut.result()
            except Exception as e:
                out = dict(id=r["id"], datetime=r["datetime"], error=f"exc: {e}")
            append_result(RESULTS_S1, out)
            if out.get("error"):
                n_err += 1
                print(f"[{i}/{len(todo)}] ERR {r['id'][:40]}: {out['error']}", flush=True)
            else:
                n_ok += 1
                print(f"[{i}/{len(todo)}] OK  {r['id'][:40]} comp={out['n_total']} "
                      f"ships={out['n_est']} (port={out['n_est_in_port']}, anch={out['n_anchorage']})", flush=True)
    print(f"S1 done in {time.time()-t0:.0f}s | ok={n_ok} err={n_err}", flush=True)


# --------------------------------------------------------------------- S2
def process_s2_scene(rec, grid, land, zone):
    import planetary_computer as pc
    from stac import load_item
    from detect import S1SceneProcessor
    import rasterio
    from rasterio.warp import reproject, Resampling, transform_bounds
    from rasterio.transform import from_origin
    from scipy.ndimage import label as scipy_label
    from PIL import Image

    item = pc.sign_item(load_item(rec))
    proc = S1SceneProcessor(grid, land, zone)  # reuse grid reader
    bands = {}
    for b in ["B02", "B03", "B04"]:
        with rasterio.open(item.assets[b].href) as src:
            v = proc.read_fixed_grid(src)
            if v is None:
                return dict(**rec, error="no overlap")
            bands[b] = v
    # cloud mask from SCL (20 m)
    scl = None
    try:
        with rasterio.open(item.assets["SCL"].href) as src:
            scl = proc.read_fixed_grid(src)
    except Exception:
        pass

    B02, B03, B04 = bands["B02"], bands["B03"], bands["B04"]
    valid = np.isfinite(B04)
    rgb = np.stack([B04, B03, B02], axis=-1) * 2.75
    rgb = np.clip(rgb, 0, 1) ** (1 / 1.1)
    rgb8 = (rgb * 255).astype(np.uint8)
    rgb8[~valid] = [0, 0, 0]
    rgb8[land] = [35, 35, 35]
    outdir = os.path.join(S2_DIR, rec["id"])
    os.makedirs(outdir, exist_ok=True)
    Image.fromarray(rgb8).save(os.path.join(outdir, "rgb.png"))

    # cloud fraction over the AOI (SCL codes 3,8,9,10 = cloud)
    cloud_pct = None
    if scl is not None:
        cf = np.isin(np.round(scl), [3, 8, 9, 10]) & ~land
        cloud_pct = round(float(cf.mean()) * 100, 1)

    # coarse optical bright-object count over sea (verification only)
    sea = ~land & valid
    b4 = np.where(sea, B04, np.nan)
    med = np.nanmedian(b4)
    mad = 1.4826 * np.nanmedian(np.abs(b4 - med))
    t = med + 5 * max(mad, 0.01)
    obj = (B04 > t) & sea
    lab, n = scipy_label(obj)
    sizes = np.bincount(lab.ravel())
    bright = int(((sizes >= 9) & (sizes <= 400)).sum())
    # zone-limited counts (optical cross-check per zone)
    bright_port = bright_anchor = 0
    for i, sz in enumerate(sizes):
        if 9 <= sz <= 400:
            msk = lab == i
            if msk[zone == 2].any():
                bright_port += 1
            elif msk[zone == 1].any():
                bright_anchor += 1

    out = dict(id=rec["id"], datetime=rec["datetime"], year=rec["year"], month=rec["month"],
               satellite="Sentinel-2 L2A", platform=rec["sat"],
               cloud_cover_scene=rec.get("cloud"), cloud_pct_aoi=cloud_pct,
               optical_bright_count=bright, optical_port=bright_port,
               optical_anchor=bright_anchor, error=None)
    return out


def run_s2(scenes, workers=5):
    grid, land, zone = build_masks()
    done = done_ids(RESULTS_S2)
    todo = [r for r in scenes if r["id"] not in done]
    print(f"S2: {len(done)} done, {len(todo)} to process", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_s2_scene, r, grid, land, zone): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                out = fut.result()
            except Exception as e:
                out = dict(id=r["id"], datetime=r["datetime"], error=f"exc: {e}")
            append_result(RESULTS_S2, out)
            status = "ERR " + (out.get("error") or "") if out.get("error") else \
                f"OK cloud={out.get('cloud_pct_aoi')}% bright={out.get('optical_bright_count')}"
            print(f"[{i}/{len(todo)}] {status} {r['id'][:36]}", flush=True)
    print(f"S2 done in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", action="store_true")
    ap.add_argument("--s2", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    from stac import select_s1_scenes, select_s2_scenes
    if args.s1 or not (args.s1 or args.s2):
        run_s1(select_s1_scenes(S1_PER_MONTH * 2), workers=args.workers)
    if args.s2:
        run_s2(select_s2_scenes(S2_PER_MONTH), workers=args.workers)
