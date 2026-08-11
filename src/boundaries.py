# -*- coding: utf-8 -*-
"""
Build real geographic masks for the study area.

Sources:
  * Port of Latakia polygon & breakwater: OpenStreetMap (OSM way 722818042,
    way 145168166) via Overpass API.
  * Land: Natural Earth 10m land polygons (public domain).
Everything is rasterized on a fixed 10 m UTM-36N grid so all Sentinel-1
scenes share the exact same pixel geometry.
"""
import json, os
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.features import geometry_mask, rasterize
from rasterio.warp import transform_bounds
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union
import pyproj
import urllib.request

from config import (CONFIG_DIR, AOI_BBOX_4326, RTC_EPSG, PIXEL,
                    OSM_GEOJSON, ZONES)

NE_LAND_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
               "master/geojson/ne_10m_land.geojson")
NE_LAND_PATH = os.path.join(CONFIG_DIR, "ne_10m_land.geojson")


def ensure_natural_earth():
    if not os.path.exists(NE_LAND_PATH):
        print("Downloading Natural Earth 10m land...")
        urllib.request.urlretrieve(NE_LAND_URL, NE_LAND_PATH)
    with open(NE_LAND_PATH, encoding="utf-8") as f:
        return [shape(ft["geometry"]) for ft in json.load(f)["features"]]


def build_fixed_grid():
    """Fixed 10 m UTM-36N grid covering the AOI with a ~400 m margin."""
    m = 0.004  # degrees ~ 440 m margin so the land mask covers the whole grid
    bb = [AOI_BBOX_4326[0]-m, AOI_BBOX_4326[1]-m, AOI_BBOX_4326[2]+m, AOI_BBOX_4326[3]+m]
    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{RTC_EPSG}", *bb)
    x0 = np.floor(xmin / PIXEL) * PIXEL
    y1 = np.ceil(ymax / PIXEL) * PIXEL
    w = int(np.ceil((xmax - x0) / PIXEL)) + 1
    h = int(np.ceil((y1 - ymin) / PIXEL)) + 1
    return dict(epsg=RTC_EPSG, pixel=PIXEL, x0=x0, y1=y1, width=w, height=h,
                transform=[x0, PIXEL, 0.0, y1, 0.0, -PIXEL])


def load_geoms():
    feats = {ft["properties"]["role"]: shape(ft["geometry"]) for ft in OSM_GEOJSON["features"]}
    return feats


def sar_median_land(grid, scenes, workers=6):
    """Land mask refined from the median of real Sentinel-1 VV subsets.
    Median across ~30 dates suppresses ships; land stays consistently bright.
    Validated by keeping only components connected to Natural Earth land."""
    import concurrent.futures
    from detect import S1SceneProcessor
    import rasterio, planetary_computer as pc
    from stac import load_item

    def read_vv(rec):
        try:
            item = pc.sign_item(load_item(rec))
            proc = S1SceneProcessor(grid, None, None)
            with rasterio.open(item.assets["vv"].href) as src:
                v = proc.read_fixed_grid(src)
            return v
        except Exception:
            return None

    acc = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for v in ex.map(read_vv, scenes):
            if v is not None and np.isfinite(v[~np.isnan(v)]).sum() > 1e5:
                acc.append(v)
    med = np.nanmedian(np.stack(acc), axis=0)

    # Otsu threshold on the median image
    from skimage.filters import threshold_otsu
    t = threshold_otsu(med[np.isfinite(med)])
    sar_land = (med > t) & np.isfinite(med)
    # keep only components connected to NE land
    T = from_origin(grid["x0"], grid["y1"], PIXEL, PIXEL)
    H, W = grid["height"], grid["width"]
    aoi_4326 = box(AOI_BBOX_4326[0]-0.004, AOI_BBOX_4326[1]-0.004,
                   AOI_BBOX_4326[2]+0.004, AOI_BBOX_4326[3]+0.004)
    ne_land = unary_union([g.intersection(aoi_4326) for g in ensure_natural_earth()
                           if g.is_valid and g.intersects(aoi_4326)])
    from shapely.ops import transform as _st
    t2 = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{RTC_EPSG}", always_xy=True)
    ne_utm = _st(t2.transform, ne_land)
    ne_mask = ~geometry_mask([ne_utm], out_shape=(H, W), transform=T)
    from scipy.ndimage import label as scipy_label
    lab, n = scipy_label(sar_land)
    keep = np.zeros_like(sar_land)
    for i in range(1, n + 1):
        comp = lab == i
        if comp[ne_mask].any():
            keep |= comp
    return keep, med


def build_masks(force=False, sar_scenes=None):
    """Build & cache: land mask, port zone, anchorage zone (10 m grid).
    If sar_scenes given, refine land with the SAR median (recommended)."""
    cache = os.path.join(CONFIG_DIR, "masks.npz")
    meta_path = os.path.join(CONFIG_DIR, "fixed_grid.json")
    if not force and os.path.exists(cache) and os.path.exists(meta_path):
        grid = json.load(open(meta_path, encoding="utf-8"))
        z = np.load(cache)
        return grid, z["land"], z["zone"]

    grid = build_fixed_grid()
    json.dump(grid, open(meta_path, "w", encoding="utf-8"), indent=1)

    T = from_origin(grid["x0"], grid["y1"], PIXEL, PIXEL)
    H, W = grid["height"], grid["width"]
    aoi = box(*transform_bounds("EPSG:4326", f"EPSG:{RTC_EPSG}", *AOI_BBOX_4326))
    aoi_buf = aoi.buffer(500)
    aoi_4326 = box(AOI_BBOX_4326[0]-0.004, AOI_BBOX_4326[1]-0.004,
                   AOI_BBOX_4326[2]+0.004, AOI_BBOX_4326[3]+0.004)

    # transformer 4326 -> UTM 36N
    import pyproj as _pj
    from shapely.ops import transform as _st
    _t = _pj.Transformer.from_crs("EPSG:4326", f"EPSG:{RTC_EPSG}", always_xy=True)

    feats = load_geoms()
    port = _st(_t.transform, feats["port_boundary"])
    bw = _st(_t.transform, feats["breakwater"])

    # --- land mask: Natural Earth land + OSM port land + breakwater buffer ---
    land = []
    ne = ensure_natural_earth()
    for g in ne:
        if not g.is_valid:
            continue
        if g.intersects(aoi_4326):
            gc = g.intersection(aoi_4326)  # clip in 4326 first (avoids antimeridian/NaN)
            if gc.is_empty or not gc.is_valid:
                continue
            gu = _st(_t.transform, gc)
            if gu.is_valid and gu.intersects(aoi_buf):
                land.append(gu.intersection(aoi_buf))
    land.append(port.intersection(aoi_buf))
    land.append(bw.buffer(70).intersection(aoi_buf))  # breakwater is ~10-30 m wide
    land_geom = unary_union([g for g in land if not g.is_empty and g.area > 0])
    # NOTE: geometry_mask returns True where shapes do NOT cover -> invert for land
    land_mask = ~geometry_mask([land_geom], out_shape=(H, W), transform=T)
    # close small holes (single-pixel gaps at the coast)
    from scipy.ndimage import binary_closing
    land_mask = binary_closing(land_mask, iterations=1)

    # --- zones: distance from the real OSM port boundary ---
    port_buffers = {}
    for name, dist in ZONES.items():
        pb = port.buffer(dist).intersection(aoi_buf)
        port_buffers[name] = pb

    zone = np.zeros((H, W), dtype=np.uint8)  # 0=transit,1=anchorage,2=in_port,9=land
    zone[land_mask] = 9
    sea = ~land_mask
    in_anchor = geometry_mask([port_buffers["anchorage_m"]], out_shape=(H, W),
                              transform=T, invert=True)
    in_port = geometry_mask([port_buffers["in_port_m"]], out_shape=(H, W),
                            transform=T, invert=True)
    zone[sea & in_anchor & ~in_port] = 1
    zone[sea & in_port] = 2

    # optional SAR-derived refinement (real data, validated against NE land)
    if sar_scenes:
        sar_land, _med = sar_median_land(grid, sar_scenes)
        # never let SAR land claim the berthing strip (60 m seaward of the
        # OSM port boundary) -> berthed ships stay visible
        strip = geometry_mask([port.buffer(60)], out_shape=(H, W), transform=T, invert=True)
        sar_land &= ~strip
        land_mask = land_mask | sar_land
        land_mask = binary_closing(land_mask, iterations=1)
        zone[land_mask] = 9

    _med = locals().get("_med", None)
    if _med is None:
        _med = np.zeros(0)
    np.savez(cache, land=land_mask, zone=zone, med=_med)
    # save zone vectors for mapping
    out = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"role": "zone_anchor", "name": "Anchorage / approach (0.4-4 km)"},
         "geometry": json.loads(json.dumps(mapping(port_buffers["anchorage_m"].difference(port_buffers["in_port_m"]))))},
        {"type": "Feature", "properties": {"role": "zone_port", "name": "Port basin / berths (<400 m)"},
         "geometry": json.loads(json.dumps(mapping(port_buffers["in_port_m"])))},
    ]}
    json.dump(out, open(os.path.join(CONFIG_DIR, "zones.geojson"), "w", encoding="utf-8"), ensure_ascii=False)
    return grid, land_mask, zone


if __name__ == "__main__":
    g, land, zone = build_masks(force=True)
    print("grid:", g["width"], "x", g["height"], "| pixel:", g["pixel"], "m")
    print("land px:", int(land.sum()), "| sea px:", int((~land).sum()))
    print("zone counts: transit=%d anchorage=%d in_port=%d land=%d" % tuple(np.bincount(zone.ravel(), minlength=10)[[0, 1, 2, 9]]))
