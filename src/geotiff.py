# -*- coding: utf-8 -*-
"""
GeoTIFF export — detection results as GIS-ready raster layers.

Every layer is built on the SAME fixed UTM-36N 10 m grid used by the SAR
detection pipeline (config/fixed_grid.json), so the exported rasters align
pixel-perfectly with the radar scenes, the land mask and each other.

All cell values are REAL counts derived from the vessels.json detection
files (or ratios of those counts) — nothing is interpolated, smoothed or
synthesized. Land cells are set to NoData so GIS software displays the
marine area only.

Layers:
  * vessel_count_total.tif   — total detections per 10 m cell (whole series)
  * vessel_count_by_year.tif — multiband stack: one band per year with data
  * occupancy_share.tif      — share of valid scenes with a ship in the cell
                               (count / number of valid scenes), 0..1 float
  * latest_scene_<id>.tif    — 0/1 presence mask of a single scene
  * *_4326.tif               — WGS84 copies (warped) for lon/lat GIS users

Usage:
  python3 -m src.geotiff                 # generate all layers
  python3 -m src.geotiff --scene <id>    # + single-scene layer for <id>
"""
import os, json, sys, argparse
import numpy as np
import pandas as pd

import rasterio
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CONFIG_DIR, DET_DIR, S1_DIR, DATA_DIR, RTC_EPSG, PIXEL
from analysis import load_scenes

GTIFF_DIR = os.path.join(DATA_DIR, "geotiff")
GRID_JSON = os.path.join(CONFIG_DIR, "fixed_grid.json")
MASKS_NPZ = os.path.join(CONFIG_DIR, "masks.npz")

# pixel size used for the WGS84 copies (approx. 10 m at lat 35.5)
WGS84_PIXEL_DEG = 0.00010


def load_grid():
    """Fixed UTM-36N detection grid (10 m). Falls back to a recompute if the
    cache is missing so the exporter never breaks."""
    if os.path.exists(GRID_JSON):
        return json.load(open(GRID_JSON, encoding="utf-8"))
    from boundaries import build_fixed_grid
    g = build_fixed_grid()
    json.dump(g, open(GRID_JSON, "w", encoding="utf-8"), indent=1)
    return g


def _transform(grid):
    return from_origin(grid["x0"], grid["y1"], PIXEL, PIXEL)


def _land_mask():
    z = np.load(MASKS_NPZ)
    return z["land"].astype(bool)  # True = land


def _vessel_table(scenes=None):
    """Flatten all vessel detections with their UTM cell + year."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    rows = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(S1_DIR, r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            rows.append((v["utm_x"], v["utm_y"], int(r["dt"].year)))
    return rows


def _rasterize(rows, grid, dtype=np.uint16, nodata=None):
    """Place vessel records on the fixed grid -> array (height, width)."""
    H, W = int(grid["height"]), int(grid["width"])
    out = np.zeros((H, W), dtype=dtype)
    x0, y1 = grid["x0"], grid["y1"]
    for x, y, *_ in rows:
        c = int(round((x - x0) / PIXEL))
        r = int(round((y1 - y) / PIXEL))
        if 0 <= r < H and 0 <= c < W:
            out[r, c] += 1
    return out


def _write(path, arr, grid, dtype, nodata, crs=f"EPSG:{RTC_EPSG}",
           band_names=None, tags=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n_bands = arr.shape[0] if arr.ndim > 2 else 1
    base = dict(
        dtype=dtype, nodata=nodata, crs=crs,
        transform=_transform(grid),
        width=grid["width"], height=grid["height"],
        count=n_bands, compress="deflate", predictor=2,
    )
    # try Cloud-Optimized GeoTIFF first, fall back to classic GTiff
    for driver in ("COG", "GTiff"):
        profile = dict(base, driver=driver)
        if driver == "GTiff":
            profile["tiled"] = True
        try:
            with rasterio.open(path, "w", **profile) as dst:
                if n_bands == 1:
                    dst.write(arr.astype(dtype), 1)
                else:
                    dst.write(arr.astype(dtype))
                if band_names:
                    dst.descriptions = list(band_names)
                if tags:
                    dst.update_tags(**tags)
            break
        except Exception as e:
            if driver == "GTiff":
                raise
            print(f"[geotiff] COG driver unavailable ({e}); using GTiff")
    print("geotiff:", os.path.basename(path), os.path.getsize(path) // 1024, "KB")


def _to_wgs84(src_path, out_path, dtype=None, nodata=None, tags=None):
    """Warp a UTM layer to EPSG:4326 (bilinear for floats, nearest for ints)."""
    with rasterio.open(src_path) as src:
        if dtype is None:
            dtype = src.dtypes[0]
        if nodata is None:
            nodata = src.nodata
        transform, width, height = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds,
            resolution=(WGS84_PIXEL_DEG, WGS84_PIXEL_DEG))
        kwargs = src.meta.copy()
        kwargs.update(driver="GTiff", crs="EPSG:4326", transform=transform,
                      width=width, height=height, dtype=dtype, nodata=nodata,
                      compress="deflate", tiled=True)
        resampling = Resampling.bilinear if np.issubdtype(np.dtype(dtype), np.floating) \
            else Resampling.nearest
        with rasterio.open(out_path, "w", **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(source=rasterio.band(src, i), destination=rasterio.band(dst, i),
                          src_transform=src.transform, src_crs=src.crs,
                          dst_transform=transform, dst_crs="EPSG:4326",
                          resampling=resampling)
            if src.count > 1:
                dst.descriptions = src.descriptions
            if tags:
                dst.update_tags(**tags)
    print("geotiff (WGS84):", os.path.basename(out_path), os.path.getsize(out_path) // 1024, "KB")


def _mask_empty_land(arr, land, nodata):
    """Land cells WITHOUT detections become NoData (clean display in GIS).
    Land cells WITH real detections keep their value — ships moored
    alongside quays/breakwaters are legitimately detected on those cells
    and must never disappear from the export (counts stay 100% consistent
    with the vessel files)."""
    m = arr.copy()
    m[(land) & (arr == 0)] = nodata
    return m


def export_total(scenes=None, wgs84=True, out_dir=None):
    """Total detections per 10 m cell over the whole series."""
    grid = load_grid()
    land = _land_mask()
    rows = _vessel_table(scenes)
    arr = _mask_empty_land(_rasterize(rows, grid), land, 65535)
    out_dir = out_dir or GTIFF_DIR
    out = os.path.join(out_dir, "vessel_count_total.tif")
    _write(out, arr, grid, np.uint16, 65535,
           tags=dict(layer="total detections per 10m cell (real counts)",
                     source="Sentinel-1 SAR detections", grid="UTM-36N 10m"))
    if wgs84:
        _to_wgs84(out, os.path.join(out_dir, "vessel_count_total_4326.tif"))
    return out


def export_yearly_stack(scenes=None, wgs84=True, out_dir=None):
    """Multiband stack: one band per year with detections (order 2022..2026)."""
    grid = load_grid()
    land = _land_mask()
    rows = _vessel_table(scenes)
    years = sorted({y for _, _, y in rows})
    stack = np.zeros((len(years), int(grid["height"]), int(grid["width"])), np.uint16)
    for i, y in enumerate(years):
        stack[i] = _rasterize([r for r in rows if r[2] == y], grid)
    for i in range(len(years)):
        stack[i] = _mask_empty_land(stack[i], land, 65535)
    out_dir = out_dir or GTIFF_DIR
    out = os.path.join(out_dir, "vessel_count_by_year.tif")
    _write(out, stack, grid, np.uint16, 65535,
           band_names=[f"detections_{y}" for y in years],
           tags=dict(layer="yearly detection counts per 10m cell",
                     source="Sentinel-1 SAR detections", grid="UTM-36N 10m"))
    if wgs84:
        _to_wgs84(out, os.path.join(out_dir, "vessel_count_by_year_4326.tif"))
    return out


def export_occupancy(scenes=None, wgs84=True, out_dir=None):
    """Share of valid scenes where the cell was occupied (0..1 float).
    Normalized by the REAL number of valid scenes, so it is comparable
    across periods with different revisit frequencies."""
    grid = load_grid()
    land = _land_mask()
    scenes = scenes if scenes is not None else load_scenes()
    n_valid = int((scenes["error"].isna() | (scenes["error"] == "")).sum())
    if n_valid == 0:
        raise RuntimeError("no valid scenes to normalize occupancy")
    rows = _vessel_table(scenes)
    counts = _rasterize(rows, grid).astype(np.float32)
    occ = (counts / n_valid).astype(np.float32)
    occ = _mask_empty_land(occ, land, -1.0)
    out_dir = out_dir or GTIFF_DIR
    out = os.path.join(out_dir, "occupancy_share.tif")
    _write(out, occ, grid, np.float32, -1.0,
           tags=dict(layer=f"occupancy share (detections / {n_valid} valid scenes)",
                     source="Sentinel-1 SAR detections", grid="UTM-36N 10m"))
    if wgs84:
        _to_wgs84(out, os.path.join(out_dir, "occupancy_share_4326.tif"))
    return out


def export_scene(scene_id, out_dir=None, wgs84=False):
    """0/1 presence layer of a single satellite scene (uint8)."""
    grid = load_grid()
    land = _land_mask()
    vj = os.path.normpath(os.path.join(S1_DIR, scene_id, "vessels.json"))
    if not os.path.exists(vj):
        raise FileNotFoundError(f"vessels.json missing for {scene_id}")
    rows = [(v["utm_x"], v["utm_y"], 0) for v in json.load(open(vj, encoding="utf-8"))]
    arr = _rasterize(rows, grid, dtype=np.uint8)
    arr[arr > 0] = 1
    arr = _mask_empty_land(arr, land, 255)
    out_dir = out_dir or GTIFF_DIR
    safe = scene_id.replace("/", "_")[:80]
    out = os.path.join(out_dir, f"scene_{safe}.tif")
    _write(out, arr, grid, np.uint8, 255,
           tags=dict(layer=f"ship presence {scene_id}", scene=scene_id,
                     source="Sentinel-1 SAR detection", grid="UTM-36N 10m"))
    if wgs84:
        _to_wgs84(out, os.path.join(out_dir, f"scene_{safe}_4326.tif"))
    return out


def run(scenes=None, latest_scene=False):
    """Generate all standard layers."""
    scenes = scenes if scenes is not None else load_scenes()
    export_total(scenes)
    export_yearly_stack(scenes)
    export_occupancy(scenes)
    if latest_scene:
        good = scenes[scenes["error"].isna() | (scenes["error"] == "")]
        good = good.copy()
        good["dt"] = pd.to_datetime(good["datetime"])
        sid = good.loc[good["dt"].idxmax(), "id"]
        print("latest scene layer:", sid)
        export_scene(sid)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", type=str, default=None,
                    help="export a single-scene presence layer for this scene id")
    ap.add_argument("--latest", action="store_true",
                    help="also export the presence layer of the latest scene")
    args = ap.parse_args()
    if args.scene:
        export_scene(args.scene, wgs84=True)
    else:
        run(latest_scene=args.latest)
