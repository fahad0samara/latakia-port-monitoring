# -*- coding: utf-8 -*-
"""
Process the Port of Tartus with the SAME pipeline as Latakia, then produce
monthly/yearly series for the regional comparison.

Tartus configuration: OSM way 160479740 (Port of Tartus polygon),
breakwaters and coastline from OSM. Same Sentinel-1 RTC scenes are reused
(the frames cover both ports; windows are read from the same COGs).
"""
import os, sys, json, math
import numpy as np
import pandas as pd
from scipy.ndimage import binary_closing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ROOT, CONFIG_DIR, DET_DIR, RTC_EPSG, PIXEL, S1_DIR
from detect import S1SceneProcessor, process_scene
from stac import select_s1_scenes

TARTUS_DIR = os.path.join(ROOT, "data", "tartus")
TARTUS_RAW = os.path.join(TARTUS_DIR, "raw")
os.makedirs(TARTUS_DIR, exist_ok=True)
os.makedirs(TARTUS_RAW, exist_ok=True)

ZONES = dict(in_port_m=400, anchorage_m=4000)


def build_tartus_masks(force=False):
    """Fixed 10 m UTM-36N grid + land mask + zones for Tartus AOI."""
    cache = os.path.join(CONFIG_DIR, "tartus_masks.npz")
    meta = os.path.join(CONFIG_DIR, "tartus_grid.json")
    if not force and os.path.exists(cache) and os.path.exists(meta):
        grid = json.load(open(meta, encoding="utf-8"))
        z = np.load(cache)
        return grid, z["land"], z["zone"]

    import json as _json
    from shapely.geometry import shape, box
    from shapely.ops import transform as st
    import pyproj
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    osm = _json.load(open(os.path.join(CONFIG_DIR, "tartus_osm.geojson"), encoding="utf-8"))
    feats = {ft["properties"]["role"]: shape(ft["geometry"]) for ft in osm["features"]}
    port4326 = feats["port_boundary"]

    bbox_4326 = [35.80608, 34.85709, 35.90402, 34.96478]
    t = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{RTC_EPSG}", always_xy=True)
    port = st(t.transform, port4326)

    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{RTC_EPSG}", *bbox_4326)
    x0 = np.floor(xmin / PIXEL) * PIXEL
    y1 = np.ceil(ymax / PIXEL) * PIXEL
    w = int(np.ceil((xmax - x0) / PIXEL)) + 1
    h = int(np.ceil((y1 - ymin) / PIXEL)) + 1
    grid = dict(epsg=RTC_EPSG, pixel=PIXEL, x0=float(x0), y1=float(y1), width=w, height=h,
                transform=[x0, PIXEL, 0.0, y1, 0.0, -PIXEL])
    _json.dump(grid, open(meta, "w", encoding="utf-8"))

    T = from_origin(x0, y1, PIXEL, PIXEL)
    aoi_utm = box(*[x0, y1 - h * PIXEL, x0 + w * PIXEL, y1])
    aoi_4326 = box(*bbox_4326)

    # land: Natural Earth clipped in 4326 then transformed
    ne_path = os.path.join(CONFIG_DIR, "ne_10m_land.geojson")
    land = []
    if os.path.exists(ne_path):
        ne = [shape(ft["geometry"]) for ft in _json.load(open(ne_path, encoding="utf-8"))["features"]]
        for g in ne:
            if g.is_valid and g.intersects(aoi_4326):
                gc = g.intersection(aoi_4326)
                if gc.is_empty or not gc.is_valid:
                    continue
                gu = st(t.transform, gc)
                if gu.is_valid and gu.intersects(aoi_utm):
                    land.append(gu.intersection(aoi_utm))
    land.append(port.intersection(aoi_utm))
    for ft in osm["features"]:
        if ft["properties"]["role"] == "breakwater":
            bw = st(t.transform, shape(ft["geometry"]))
            land.append(bw.buffer(70).intersection(aoi_utm))
    from shapely.ops import unary_union
    land_geom = unary_union([g for g in land if not g.is_empty and g.area > 0])
    land_mask = ~geometry_mask([land_geom], out_shape=(h, w), transform=T)
    land_mask = binary_closing(land_mask, iterations=1)

    # zones
    zone = np.zeros((h, w), dtype=np.uint8)
    zone[land_mask] = 9
    sea = ~land_mask
    in_anchor = geometry_mask([port.buffer(4000).intersection(aoi_utm)], out_shape=(h, w),
                              transform=T, invert=True)
    in_port = geometry_mask([port.buffer(400).intersection(aoi_utm)], out_shape=(h, w),
                            transform=T, invert=True)
    zone[sea & in_anchor & ~in_port] = 1
    zone[sea & in_port] = 2
    np.savez(cache, land=land_mask, zone=zone)
    return grid, land_mask, zone


def process_all():
    grid, land, zone = build_tartus_masks(force=True)
    print("grid:", grid["width"], "x", grid["height"])
    print("land px:", int(land.sum()), "| sea px:", int((~land).sum()))
    recs = select_s1_scenes(8)  # same scene catalogue as Latakia
    print("candidates:", len(recs))

    out_path = os.path.join(TARTUS_DIR, "tartus_scenes.jsonl")
    done = set()
    if os.path.exists(out_path):
        done = {json.loads(l)["id"] for l in open(out_path, encoding="utf-8") if l.strip()}
    todo = [r for r in recs if r["id"] not in done]
    print("to process:", len(todo))

    import json as _json
    from shapely.geometry import shape as _shape
    osm = _json.load(open(os.path.join(CONFIG_DIR, "tartus_osm.geojson"), encoding="utf-8"))
    tgeoms = {ft["properties"]["role"]: _shape(ft["geometry"]) for ft in osm["features"]}
    tbbox = [35.80608, 34.85709, 35.90402, 34.96478]

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(process_scene, r, grid, land, zone, False, tbbox, tgeoms, TARTUS_RAW): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                out = fut.result()
            except Exception as e:
                out = dict(id=r["id"], datetime=r["datetime"], error=f"exc: {e}")
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
            if out.get("error"):
                print(f"[{i}/{len(todo)}] ERR {r['id'][:36]}: {out['error'][:60]}", flush=True)
            else:
                print(f"[{i}/{len(todo)}] OK {r['id'][:36]} port={out['n_est_in_port']} anch={out['n_anchorage']}", flush=True)
    print("Tartus processing done")


def build_series():
    """Monthly + yearly series for Tartus (same normalization as Latakia)."""
    rows = []
    with open(os.path.join(TARTUS_DIR, "tartus_scenes.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["datetime"])
    good = df[df["error"].isna() | (df["error"] == "")].copy()
    good["ym"] = good["dt"].dt.strftime("%Y-%m")
    good["year"] = good["dt"].dt.year
    good["month"] = good["dt"].dt.month

    monthly = good.groupby("ym").agg(
        n_obs=("id", "count"),
        mean_ships_port=("n_est_in_port", "mean"),
        mean_anchorage=("n_anchorage", "mean"),
        max_ships_port=("n_est_in_port", "max"),
        mean_coverage=("coverage", "mean"),
    ).reset_index()
    monthly["year"] = monthly["ym"].str[:4].astype(int)
    monthly["month"] = monthly["ym"].str[5:7].astype(int)
    monthly["mean_ships_port_adj"] = monthly["mean_ships_port"]  # coverage already high
    monthly.to_csv(os.path.join(TARTUS_DIR, "tartus_monthly.csv"), index=False)

    yearly = monthly.groupby("year").agg(
        n_months=("ym", "count"), n_obs=("n_obs", "sum"),
        annual_mean=("mean_ships_port_adj", "mean"),
        peak_month=("mean_ships_port_adj", "idxmax"),
        peak_value=("mean_ships_port_adj", "max"),
    ).reset_index()
    yearly["yoy_pct"] = yearly["annual_mean"].pct_change() * 100
    yearly.to_csv(os.path.join(TARTUS_DIR, "tartus_yearly.csv"), index=False)
    print("Tartus series saved")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--series", action="store_true")
    args = ap.parse_args()
    if args.process or not (args.process or args.series):
        process_all()
    if args.series:
        build_series()
